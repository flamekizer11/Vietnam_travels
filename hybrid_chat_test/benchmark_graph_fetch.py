"""Benchmark sync vs async graph fetchers.



The script will:
 - use a small sample of node IDs (override SAMPLE_NODE_IDS or set env var BENCH_NODE_IDS)
 - run a configurable number of iterations per method
 - print mean, median, and stddev for each method

Notes:
 - The async fetcher is called via the sync wrapper `fetch_graph_context_async_wrapper` so
   you don't need to change existing code to benchmark it.
 - If you have a running Neo4j instance and want realistic results, set `BENCH_NODE_IDS`
   environment variable to a comma-separated list of node ids.
"""

import os
import time
import math
import statistics
from typing import List

from graph import fetch_graph_context, fetch_graph_context_async_wrapper
from async_graph import (
    fetch_graph_context_async,
    get_async_driver,
    close_async_driver,
    close_all_async_drivers,
)
import asyncio
import json
import csv
from statistics import quantiles
from pathlib import Path


def parse_node_ids() -> List[str]:
    env = os.environ.get("BENCH_NODE_IDS")
    if env:
        return [s.strip() for s in env.split(",") if s.strip()]
    # default sample ids - replace with real ids for realistic benchmarks
    return ["sample1", "sample2", "sample3"]


def time_func(func, args=(), iterations=5):
    times = []
    for i in range(iterations):
        t0 = time.perf_counter()
        try:
            func(*args)
        except Exception as e:
            print(f"Iteration {i+1} raised: {e}")
            times.append(float('nan'))
            continue
        t1 = time.perf_counter()
        times.append(t1 - t0)
    # filter out failed runs (NaN values)
    times = [t for t in times if not (isinstance(t, float) and math.isnan(t))]
    return times


def summarize(name: str, times: List[float]):
    if not times:
        print(f"{name}: no successful runs")
        return
    print(f"--- {name} ---")
    print(f"runs: {len(times)}")
    print(f"mean: {statistics.mean(times):.4f}s")
    print(f"median: {statistics.median(times):.4f}s")
    if len(times) > 1:
        print(f"stdev: {statistics.stdev(times):.4f}s")
    print(f"min: {min(times):.4f}s")
    print(f"max: {max(times):.4f}s")
    print()


def percentile(values: List[float], p: float) -> float:
    if not values:
        return float('nan')
    s = sorted(values)
    idx = int(round((p / 100.0) * (len(s) - 1)))
    return s[max(0, min(idx, len(s) - 1))]


def main():
    node_ids = parse_node_ids()
    iterations = int(os.environ.get("BENCH_ITERS", "5"))
    concurrency = int(os.environ.get("BENCH_CONCURRENCY", "10"))
    concurrent_iters = int(os.environ.get("BENCH_CONCURRENT_ITERS", "20"))

    print("Node IDs:", node_ids)
    print(f"Iterations per method: {iterations}")
    print("Running warmups...")

    # Warmup sync
    try:
        fetch_graph_context(node_ids)
    except Exception as e:
        print("Sync warmup raised:", e)

    # Warmup async wrapper
    try:
        fetch_graph_context_async_wrapper(node_ids)
    except Exception as e:
        print("Async warmup raised:", e)

    print("Timing sync fetcher...")
    sync_times = time_func(fetch_graph_context, args=(node_ids,), iterations=iterations)

    print("Timing async fetcher (via sync wrapper)...")
    async_times = time_func(fetch_graph_context_async_wrapper, args=(node_ids,), iterations=iterations)

    summarize("Sync fetch_graph_context", sync_times)
    summarize("Async fetch_graph_context_async (wrapper)", async_times)

    # Concurrent async benchmark
    print("Running concurrent async benchmark...")
    async def run_concurrent():
        # Ensure driver is created in this loop
        get_async_driver()

        async def worker(latencies: list):
            t0 = time.perf_counter()
            await fetch_graph_context_async(node_ids)
            t1 = time.perf_counter()
            latencies.append(t1 - t0)

        times = []
        all_latencies = []
        for _ in range(concurrent_iters):
            latencies = []
            await asyncio.gather(*[worker(latencies) for _ in range(concurrency)])
            # per-round time
            times.append(sum(latencies) / max(1, len(latencies)))
            all_latencies.append(latencies)
        return times, all_latencies

    try:
        res = asyncio.run(run_concurrent())
        if isinstance(res, tuple):
            loop_times, per_task_latencies = res
        else:
            loop_times = res
            per_task_latencies = None

        summarize(f"Concurrent async: {concurrency} parallel tasks", loop_times)

        if per_task_latencies:
            # flatten list of lists
            flat = [t for sub in per_task_latencies for t in sub]
            print("Per-task stats:")
            print(f"count: {len(flat)}")
            print(f"p50: {percentile(flat,50):.4f}s")
            print(f"p95: {percentile(flat,95):.4f}s")
            print(f"p99: {percentile(flat,99):.4f}s")

            out_dir = os.environ.get("BENCH_OUT_DIR")
            if out_dir:
                p = Path(out_dir)
                p.mkdir(parents=True, exist_ok=True)
                # CSV
                csv_path = p / "per_task_latencies.csv"
                with open(csv_path, "w", newline="") as f:
                    w = csv.writer(f)
                    w.writerow(["latency_s"])
                    for v in flat:
                        w.writerow([f"{v:.6f}"])
                # JSON summary
                json_path = p / "summary.json"
                summary = {
                    "count": len(flat),
                    "p50": percentile(flat,50),
                    "p95": percentile(flat,95),
                    "p99": percentile(flat,99),
                }
                with open(json_path, "w") as f:
                    json.dump(summary, f, indent=2)
    finally:
        # cleanup drivers created in any event loop
        try:
            asyncio.run(close_all_async_drivers())
        except Exception:
            pass


if __name__ == "__main__":
    main()
