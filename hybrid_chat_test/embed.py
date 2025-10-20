"""embed.py

Embedding helpers and a small file cache. Provides sync and async helpers
for creating embeddings. Async functions use aiohttp and optional Redis
cache when configured.
"""

import hashlib
import json
import os
import asyncio
from typing import List, Optional
import logging

import aiohttp
try:
    import redis.asyncio as aioredis
    _AIOR= True
except Exception:
    aioredis = None
    _AIOR = False
try:
    from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
    _TENACITY_AVAILABLE = True
except Exception:
    # Tenacity not available — provide no-op fallbacks so module still imports
    _TENACITY_AVAILABLE = False

    def retry(**kwargs):
        def _decorator(func):
            return func
        return _decorator

    def stop_after_attempt(*args, **kwargs):
        return None

    def wait_exponential(*args, **kwargs):
        return None

    def retry_if_exception_type(*args, **kwargs):
        return None

import config
from openai import OpenAI

logger = logging.getLogger(__name__)

# sync OpenAI client left for backward compatibility
client = OpenAI(api_key=config.OPENAI_API_KEY)

# Simple file-based cache
CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# Concurrency control for async embedding requests
_EMBED_CONCURRENCY = getattr(config, 'EMBED_CONCURRENCY', 8)
_SEMAPHORE = asyncio.Semaphore(_EMBED_CONCURRENCY)

OPENAI_EMBED_URL = "https://api.openai.com/v1/embeddings"

# Keep references to background tasks so they are not GC'd prematurely
_BACKGROUND_TASKS: List[asyncio.Task] = []


async def _gather_and_store(tasks: List[asyncio.Task]):
    """Gather tasks and keep a reference to prevent GC."""
    await asyncio.gather(*tasks)


def get_text_hash(text: str, model: Optional[str] = None) -> str:
    """Return a stable SHA256 key for a text (+ optional model)."""
    key = text if model is None else f"{model}:{text}"
    return hashlib.sha256(key.encode()).hexdigest()


def _cache_path(hash_key: str) -> str:
    return os.path.join(CACHE_DIR, f"{hash_key}.json")


def load_cache(hash_key: str) -> Optional[List[float]]:
    """Return cached embedding or None if missing/corrupt."""
    cache_file = _cache_path(hash_key)
    if os.path.exists(cache_file):
        with open(cache_file, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except Exception:
                logger.exception("Failed parsing cache file %s", cache_file)
    return None


def save_cache(hash_key: str, embedding: List[float]):
    """Atomically write an embedding to the file cache."""
    cache_file = _cache_path(hash_key)
    tmp = cache_file + ".tmp"
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(embedding, f)
    os.replace(tmp, cache_file)


def embed_text(text: str, model: str = "text-embedding-3-small", use_cache: bool = True) -> List[float]:
    """Sync wrapper: return an embedding, using cache if enabled."""
    if use_cache:
        hash_key = get_text_hash(text, model=model)
        cached = load_cache(hash_key)
        if cached is not None:
            return cached

    resp = client.embeddings.create(model=model, input=[text])
    embedding = resp.data[0].embedding

    if use_cache:
        save_cache(hash_key, embedding)

    return embedding


def embed_texts(texts: List[str], model: str = "text-embedding-3-small", batch_size: int = 32, use_cache: bool = True) -> List[List[float]]:
    """Batch sync embedding with optional file-cache support."""
    def _process_batch(batch_texts: List[str]):
        batch_embeddings_local = [None] * len(batch_texts)
        uncached_texts_local = []
        uncached_indices_local = []
        for j, text in enumerate(batch_texts):
            if use_cache:
                hash_key = get_text_hash(text, model=model)
                cached = load_cache(hash_key)
                if cached is not None:
                    batch_embeddings_local[j] = cached
                    continue
            uncached_texts_local.append(text)
            uncached_indices_local.append(j)

        if uncached_texts_local:
            resp = client.embeddings.create(model=model, input=uncached_texts_local)
            for k, emb in enumerate(resp.data):
                original_idx = uncached_indices_local[k]
                batch_embeddings_local[original_idx] = emb.embedding
                if use_cache:
                    hash_key = get_text_hash(uncached_texts_local[k], model=model)
                    save_cache(hash_key, emb.embedding)

        return batch_embeddings_local

    embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        embeddings.extend(_process_batch(batch))

    return list(embeddings)


# Async native embedding (aiohttp) with retries and concurrency control


async def _load_cache_async(hash_key: str) -> Optional[List[float]]:
    """Load cache using a thread executor to avoid blocking the loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, load_cache, hash_key)


async def _save_cache_async(hash_key: str, embedding: List[float]):
    """Save cache entry without blocking the event loop."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, save_cache, hash_key, embedding)


@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), retry=retry_if_exception_type(Exception))
async def _fetch_embeddings_aiohttp(texts: List[str], model: str):
    """Call OpenAI embeddings endpoint and return the embeddings list."""
    headers = {"Authorization": f"Bearer {config.OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": model, "input": texts}
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(OPENAI_EMBED_URL, headers=headers, json=payload) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return [it.get('embedding') for it in data.get('data', [])]


async def async_embed_text(text: str, model: str = "text-embedding-3-small", use_cache: bool = True) -> List[float]:
    """Return embedding for a single text. Uses cache if enabled."""
    hash_key = get_text_hash(text, model=model)
    if use_cache:
        cached = await _load_cache_async(hash_key)
        if cached is not None:
            return cached

    # Try Redis cache first (async) if configured
    if use_cache and _AIOR and config.EMBEDDING_REDIS_URL:
        try:
            redis = aioredis.from_url(config.EMBEDDING_REDIS_URL)
            cached_raw = await redis.get(hash_key)
            if cached_raw:
                return json.loads(cached_raw)
        except Exception:
            logger.exception("Redis cache read failed")

    # Acquire semaphore to limit concurrent remote calls
    await _SEMAPHORE.acquire()
    try:
        embeddings = await _fetch_embeddings_aiohttp([text], model)
    finally:
        _SEMAPHORE.release()

    if not embeddings:
        raise RuntimeError("No embedding returned from OpenAI")

    embedding = embeddings[0]
    if use_cache:
        # Save to file cache in background
        await _save_cache_async(hash_key, embedding)
        # Also save to Redis if enabled
        if _AIOR and config.EMBEDDING_REDIS_URL:
            try:
                redis = aioredis.from_url(config.EMBEDDING_REDIS_URL)
                await redis.set(hash_key, json.dumps(embedding), ex=config.EMBEDDING_CACHE_TTL_SECONDS)
            except Exception:
                logger.exception("Redis cache write failed")
    return embedding


async def async_embed_texts(texts: List[str], model: str = "text-embedding-3-small", batch_size: int = 32, use_cache: bool = True) -> List[List[float]]:
    """Batch async embedding with caching and concurrency control."""
    results: List[Optional[List[float]]] = [None] * len(texts)

    # 1. Check cache for each text
    tasks = []
    for i, t in enumerate(texts):
        if use_cache:
            hk = get_text_hash(t, model=model)
            tasks.append((_load_cache_async(hk), i, t, hk))
        else:
            tasks.append((None, i, t, get_text_hash(t, model=model)))

    async def _map_loaded_caches(tasks_list):
        """Load caches concurrently and populate results; return uncached lists."""
        coros_with_index = [(entry[0], entry[1], entry[2]) for entry in tasks_list if entry[0] is not None]
        if not coros_with_index:
            # no cache coros, all texts are uncached
            return [entry[2] for entry in tasks_list], [entry[1] for entry in tasks_list]

        coros = [c[0] for c in coros_with_index]
        loaded_vals = await asyncio.gather(*coros)
        unc_texts_local = []
        unc_indices_local = []
        for v, (_, idx, text) in zip(loaded_vals, coros_with_index):
            if v is not None:
                results[idx] = v
            else:
                unc_texts_local.append(text)
                unc_indices_local.append(idx)
        return unc_texts_local, unc_indices_local

    async def _embed_batches_and_cache(unc_texts, unc_indices):
        """Embed uncached texts in batches, populate results, schedule cache writes."""
        for start in range(0, len(unc_texts), batch_size):
            batch = unc_texts[start:start + batch_size]
            await _SEMAPHORE.acquire()
            try:
                    embeddings = await _fetch_embeddings_aiohttp(batch, model)
            finally:
                _SEMAPHORE.release()

            bg_tasks = []
            for k, emb in enumerate(embeddings):
                orig_idx = unc_indices[start + k]
                results[orig_idx] = emb
                if use_cache:
                    hk = get_text_hash(batch[k], model=model)
                    bg = asyncio.create_task(_save_cache_async(hk, emb))
                    bg_tasks.append(bg)

            if bg_tasks:
                # keep a reference to the background gather task so it is not GC'd
                gather_task = asyncio.create_task(asyncio.gather(*bg_tasks))
                _BACKGROUND_TASKS.append(gather_task)

    uncached_texts, uncached_indices = await _map_loaded_caches(tasks)
    # if there are uncached items, embed them
    if uncached_texts:
        await _embed_batches_and_cache(uncached_texts, uncached_indices)

    # 2. For uncached texts, call OpenAI in batches
    for start in range(0, len(uncached_texts), batch_size):
        batch = uncached_texts[start:start + batch_size]
        # acquire semaphore (limit concurrent HTTP calls)
        await _SEMAPHORE.acquire()
        try:
                embeddings = await _fetch_embeddings_aiohttp(batch, model)
        finally:
            _SEMAPHORE.release()

        # assign and optionally cache
        background_tasks = []
        for k, emb in enumerate(embeddings):
            orig_idx = uncached_indices[start + k]
            results[orig_idx] = emb
            if use_cache:
                hk = get_text_hash(batch[k], model=model)
                # save in background to avoid blocking; track tasks to prevent GC
                bg = asyncio.create_task(_save_cache_async(hk, emb))
                background_tasks.append(bg)

        # if we scheduled background cache writes, await them in background
        if background_tasks:
            # schedule completion but don't block primary flow
            asyncio.create_task(asyncio.gather(*background_tasks))

    # All results should be filled
    return list(results)
