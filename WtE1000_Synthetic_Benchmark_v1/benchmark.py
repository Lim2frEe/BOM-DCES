#!/usr/bin/env python3
"""Reference affected-scope traversal benchmark; no cryptography or blockchain."""
from __future__ import annotations

import argparse
import platform
import statistics
import sys
import time
from pathlib import Path

from common import adjacency, read_csv, read_jsonl, traverse, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", type=Path, default=Path("traversal_results.json"))
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("repeats must be positive")
    nodes = read_csv(args.data / "nodes.csv")
    children, _ = adjacency(nodes, read_csv(args.data / "edges.csv"))
    owners = {row["node_id"]: row["responsible_party"]
              for row in nodes if not children[row["node_id"]]}
    requests = read_jsonl(args.data / "modifications.jsonl")
    durations, scope_counts, spc_counts = [], [], []
    for _ in range(args.repeats):
        for request in requests:
            started = time.perf_counter_ns()
            visited = traverse(request["affected_roots"], children)
            affected = {owners[n] for n in visited if n in owners}
            elapsed = time.perf_counter_ns() - started
            if (len(visited) != request["expected_visited_nodes"]
                    or sorted(affected) != request["expected_affected_spcs"]):
                raise ValueError("Traversal result does not match workload")
            durations.append(elapsed)
            scope_counts.append(len(visited))
            spc_counts.append(len(affected))
    ordered = sorted(durations)
    percentile95 = ordered[min(len(ordered) - 1, (95 * len(ordered) + 99) // 100 - 1)]
    report = {
        "benchmark_scope": "Descendant traversal from explicitly supplied affected roots and SPC deduplication only",
        "dataset_seed": __import__("json").loads(
            (args.data / "generation_config.json").read_text())["seed"],
        "python_version": platform.python_version(),
        "platform": platform.system(), "machine": platform.machine(),
        "requests_per_repeat": len(requests), "repeats": args.repeats,
        "total_checked_requests": len(durations),
        "mean_microseconds": statistics.mean(durations) / 1000,
        "median_microseconds": statistics.median(durations) / 1000,
        "p95_microseconds": percentile95 / 1000,
        "maximum_visited_nodes": max(scope_counts),
        "maximum_affected_spcs": max(spc_counts),
        "mismatches": 0,
        "excluded": [
            "Engineering-semantic selection of affected ancestor roots",
            "Encryption, signatures, chameleon hashes and threshold reconstruction",
            "Blockchain, network transmission and human approval",
        ],
        "interpretation": "These are new reference-traversal measurements on synthetic metadata, not the manuscript's engineering-case runtimes.",
    }
    write_json(args.output, report)
    print(f"Checked {len(durations)} requests; zero mismatches")
    print(f"Mean traversal time: {report['mean_microseconds']:.3f} microseconds")


if __name__ == "__main__":
    main()
