"""Background async runner.

Run an asyncio loop in a daemon thread so sync code can submit coroutines
without using `asyncio.run` each time. Provides helpers to create/close a
loop-bound Neo4j driver.
"""
import threading
import asyncio
from typing import Any
import atexit

import config
from neo4j import AsyncGraphDatabase


_loop = None
_thread = None
_started = False


def _start_loop():
    """Start the event loop in a thread (internal)."""
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    _loop.run_forever()


def start_background_loop():
    global _thread, _started
    if _started:
        return
    _thread = threading.Thread(target=_start_loop, daemon=True)
    _thread.start()
    _started = True


def stop_background_loop():
    global _loop, _thread, _started
    if not _started:
        return
    if _loop is not None:
        _loop.call_soon_threadsafe(_loop.stop)
    if _thread is not None:
        _thread.join(timeout=1.0)
    _loop = None
    _thread = None
    _started = False


atexit.register(stop_background_loop)


def submit_sync(coro) -> None:
    """Submit a coroutine without waiting for the result."""
    if not _started:
        if not config.ENABLE_ASYNC_RUNNER:
            raise RuntimeError("Async runner is disabled in config")
        start_background_loop()
    asyncio.run_coroutine_threadsafe(coro, _loop)


def submit_and_wait(coro) -> Any:
    """Submit a coroutine and block until it returns."""
    if not _started:
        if not config.ENABLE_ASYNC_RUNNER:
            raise RuntimeError("Async runner is disabled in config")
        start_background_loop()
    fut = asyncio.run_coroutine_threadsafe(coro, _loop)
    return fut.result()


async def _create_driver_in_loop():
    # Called inside the background loop
    return AsyncGraphDatabase.driver(
        config.NEO4J_URI,
        auth=(config.NEO4J_USER, config.NEO4J_PASSWORD),
        max_connection_pool_size=getattr(config, "NEO4J_MAX_CONN_POOL_SIZE", 50),
    )


def create_driver():
    """Create a Neo4j async driver inside the background loop and return it."""
    if not _started:
        start_background_loop()

    # Schedule the synchronous _create_driver_in_loop to run in the background
    # loop's default executor and wait for result.
    fut = asyncio.run_coroutine_threadsafe(
        _run_in_executor(_create_driver_in_loop), _loop
    )
    return fut.result()


async def _run_in_executor(func):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, func)


def close_driver(driver):
    """Close a driver object inside the background loop."""
    if driver is None:
        return
    async def _close():
        try:
            await driver.close()
        except Exception:
            pass

    submit_and_wait(_close())
