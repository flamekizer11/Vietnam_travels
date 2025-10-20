
hybrid_chat_test 

Date: 2025-10-20
Author: Pratik

Quick overview
--------------

This is a dev-diary style log describing what I changed, why I changed it, where I got stuck, and how I fixed the problems. Use this as the guide for the recent async/caching work.

TL;DR
-----

- Switched embeddings to async (aiohttp).
- Added Redis caching with TTL plus a file-based fallback.
- Implemented per-event-loop Neo4j drivers and a background asyncio runner for sync compatibility.
- Wrote a benchmark to compare sync vs async graph fetch modes and export latency percentiles (p50/p95/p99) as CSV/JSON.
- Cleaned up docstrings and comments across core modules.

Why I did this
--------------

Performance and reliability. Blocking network calls and repeated embedding requests were slowing everything down. Neo4j’s async driver behaves poorly when reused across loops on Windows — that had to be fixed. Redis makes repeated calls cheap; file cache keeps local dev working.

What I changed (high level)
---------------------------

1) Async embeddings (`embed.py`)

- Replaced sync embedding calls with async functions using `aiohttp`.
- Added `async_embed_text` and `async_embed_texts` with a concurrency semaphore.
- Kept sync wrappers so older code can keep working.

Where I got stuck
-----------------

Issue 1: Dependency and import errors during initial runs.

Symptoms: At first I got ModuleNotFoundError for `aiohttp` and later for `redis` when running smoke tests on a fresh environment.

Fix: Installed the missing packages in the virtualenv (user ran `py -m pip install -r requirements.txt` and a manual install for redis). Verified with `py -c "import aiohttp, redis; print(aiohttp.__version__, redis.__version__)"`.

Issue 2: Reconnect overhead and slightly worse performance in small-batch tests.

Symptoms: Each embedding call created a new TCP connection; short tests didn't look dramatically better than sync.

Fix: Decided to keep per-call sessions initially (safer), added a note to move to a persistent `ClientSession` stored in the background runner for high-throughput runs. This is in the roadmap.

2) Embedding caching (Redis + file fallback)

- Implemented Redis-based cache with TTL and hashed keys.
- Implemented atomic file cache under `cache/` as a fallback.

Where I got stuck
-----------------

Issue: Redis not running locally (ConnectionRefused) during tests.

Symptoms: Redis client raised connection errors; embedding still returned values because file cache was present — but logs were noisy.

Fix: Make Redis optional — wrap Redis operations in try/except and fall back to file cache. Added clear log messages so it’s easy to see whether the cache hit was from Redis or file.

3) Neo4j async drivers & background runner

- Implemented per-event-loop Async drivers. Drivers are keyed by loop ID and created lazily.
- Implemented a background asyncio runner running in a daemon thread that owns drivers and accepts coroutine submissions from sync code via `submit_sync`/`submit_and_wait`.

Where I got stuck
-----------------

Issue: Cross-event-loop socket/SSL errors on Windows when reusing drivers.

Symptoms: On Windows (Proactor loop), reusing a driver across separate event loops led to "socket already in use" and SSL transport errors.

Fix: After debugging stack traces and reading the Neo4j driver docs, I switched to per-loop driver instances: create the driver on the loop that will use it and store it in a mapping keyed by the loop id. That resolved the cross-loop errors. Also ensured drivers are closed from the same loop they were created on.

Issue: Driver lifecycle management on shutdown.

Symptoms: Drivers and connections sometimes lingered after test runs.

Fix: Added close helpers on the runner and documented the need to call them during app shutdown. Next step: wire them into application lifecycle hooks or atexit handlers.

4) Benchmarking

- Wrote `benchmark_graph_fetch.py` to compare sync vs async sequential vs async concurrent fetches.
- Outputs p50/p95/p99 and CSV/JSON for offline analysis.

Where I got stuck
-----------------

Issue: Benchmark noise due to connection setup cost.

Symptoms: First-run latencies higher because drivers and sessions were created lazily.

Fix: Warm up connections before measurement in the benchmark script. Re-run and validate latency percentiles after warmup.

5) Humanized comments and docstrings

- Rewrote module headers and important docstrings in core files to be concise and human-readable.

Where I got stuck
-----------------

Issue: A failed patch on `visualize_graph.py` due to invalid context in the automated edit attempt.

Fix: Read the actual file contents, prepared a precise patch using the file content as context, and applied the update. Confirmed imports and behavior remained unchanged.

6) Prompt Engineering

- I also refined the prompt templates for clearer instructions and consistent tone. 

The assistant now includes brief reasoning cues (“think step by step”) and improved context injection from both Pinecone and Neo4j results before calling the chat model.



Verification and quick sanity checks
----------------------------------


What I ran locally (PowerShell):

```powershell
py -c "import embed, graph, async_graph, async_runner, visualize_graph; print('imports ok')"
py .\hybrid_chat.py
py benchmark_graph_fetch.py --mode concurrent --concurrency 20
```

Status

- Build / imports: Done
- Lint / type-check:Not run yet
- Tests: No unit tests added; manual smoke tests used instead

Notes and limitations
---------------------

- Redis is optional: file cache works when Redis is down.
- Persistent `aiohttp.ClientSession` is not implemented yet but is on the short-term roadmap.
- Drivers are bound to event-loops — be careful when spawning threads and event loops.

Next steps we can take are 
----------------------

Short term

- Implement persistent `aiohttp.ClientSession` in the background runner and re-run benchmarks.
- Add a small integration test using a local Neo4j Docker instance or a mocked server.
- Continue humanizing comments across the rest of the repository in small batches.

Medium term

- Add unit tests for caching and mock the external embedding API.
- Add CI job to run benchmarks and store artifacts for regression checks.

Long term

- Make the cache pluggable (Redis, FS, Memcached adapters).
- Add production lifecycle management for drivers and sessions (shutdown hooks, health checks).

Files edited 
------------

- embed.py
- async_graph.py
- async_runner.py
- graph.py
- visualize_graph.py
- improvements.md (this file)

Final thoughts
--------------

This felt like a clean, practical iteration: faster, more robust, and less painful to run locally. I intentionally kept changes incremental, added fallbacks, and left a clear migration path to full async if/when we want it.

I have learnt a lot in the process of making this project, figuring out issues and errors here n there. It was very Insightful. 
I still have some doubts and would like to discuss with you if given the opportunity.

I have submitted by contact details with the google form . If you want, you can contact me for more details.

— Pratik
