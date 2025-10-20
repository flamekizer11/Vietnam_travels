"""Async Neo4j helpers.

Async versions of graph fetch helpers. Drivers are bound to event loops to
avoid cross-loop problems on Windows.
"""
from typing import List, Dict, Any
from neo4j import AsyncGraphDatabase
import config
import asyncio
from async_runner import create_driver, submit_and_wait, submit_sync


# Map drivers by event-loop id so drivers are bound to the loop they were
# created on. This prevents using a driver created for a closed loop in a new
# one (which leads to 'NoneType' send errors on Windows/Proactor).
_ASYNC_DRIVERS: Dict[int, AsyncGraphDatabase] = {}


def get_async_driver() -> AsyncGraphDatabase:
    """Return a driver tied to the current event loop (create if missing)."""
    loop = asyncio.get_running_loop()
    key = id(loop)
    driver = _ASYNC_DRIVERS.get(key)
    if driver is None:
        pool_size = getattr(config, "NEO4J_MAX_CONN_POOL_SIZE", None)
        if pool_size is not None:
            driver = AsyncGraphDatabase.driver(
                config.NEO4J_URI,
                auth=(config.NEO4J_USER, config.NEO4J_PASSWORD),
                max_connection_pool_size=pool_size,
            )
        else:
            driver = AsyncGraphDatabase.driver(
                config.NEO4J_URI, auth=(config.NEO4J_USER, config.NEO4J_PASSWORD)
            )
        _ASYNC_DRIVERS[key] = driver
    return driver


def submit_fetch_graph(node_ids: list):
    """Sync-friendly submitter that runs the async fetch in the background runner
    and returns the result. This avoids asyncio.run overhead in sync callers.
    """
    if not node_ids:
        return []

    # Ensure the background runner has created a driver; create_driver will
    # run in the runner and return a driver bound to that loop.
    try:
        create_driver()
    except Exception:
        # If runner is disabled or creation fails, fall back to sync wrapper
        return submit_and_wait(fetch_graph_context_async(node_ids))

    # Submit the actual coroutine to the runner and wait for result
    return submit_and_wait(fetch_graph_context_async(node_ids))


async def close_async_driver() -> None:
    """Close the driver for the current event loop if present."""
    loop = asyncio.get_running_loop()
    key = id(loop)
    driver = _ASYNC_DRIVERS.pop(key, None)
    if driver is not None:
        try:
            await driver.close()
        except Exception:
            pass


async def close_all_async_drivers() -> None:
    """Close all known async drivers (best-effort)."""
    # Copy keys to avoid mutation during iteration
    keys = list(_ASYNC_DRIVERS.keys())
    for k in keys:
        d = _ASYNC_DRIVERS.pop(k, None)
        if d is not None:
            try:
                await d.close()
            except Exception:
                pass


async def fetch_graph_context_async(node_ids: List[str]) -> List[Dict[str, Any]]:
    """Fetch neighbors (1- and 2-hop) for the provided node ids."""
    if not node_ids:
        return []

    facts: List[Dict[str, Any]] = []
    # Reuse a persistent driver created in the current event loop. This
    # avoids the cost of creating/closing the driver on every call, which was
    # the primary source of latency in the benchmark.
    driver = get_async_driver()
    async with driver.session() as session:
            query = (
                "UNWIND $node_ids AS nid "
                "MATCH (n:Entity {id: nid})-[r]-(m:Entity) "
                "OPTIONAL MATCH (m)-[r2]-(o:Entity) WHERE o <> n "
                "RETURN type(r) AS rel, labels(m) AS labels, m.id AS id, "
                "m.name AS name, m.type AS type, m.description AS description, "
                "type(r2) AS rel2, labels(o) AS labels2, o.id AS id2, "
                "o.name AS name2, o.type AS type2, o.description AS description2 "
                "LIMIT 100"
            )
            result = await session.run(query, node_ids=node_ids)
            async for r in result:
                # 1-hop fact
                facts.append({
                    "source": None,
                    "rel": r["rel"],
                    "target_id": r["id"],
                    "target_name": r["name"],
                    "target_desc": (r["description"] or "")[:400],
                    "labels": r["labels"],
                })
                # 2-hop fact if exists
                if r.get("rel2"):
                    facts.append({
                        "source": r["id"],
                        "rel": r["rel2"],
                        "target_id": r["id2"],
                        "target_name": r["name2"],
                        "target_desc": (r["description2"] or "")[:400],
                        "labels": r["labels2"],
                    })

    return facts[:50]
