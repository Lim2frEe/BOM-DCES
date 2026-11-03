#!/usr/bin/env python3
"""Rebuild all metadata and run reproducibility and corruption-detection checks."""
from __future__ import annotations

import argparse
import hashlib
import platform
import shutil
import tempfile
from pathlib import Path

from common import (payload_chunks, read_csv, read_json, sha256_file,
                    write_csv, write_json)
from generate import generate
from validate import validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path,
                        default=Path("reports/reproducibility_report.json"))
    args = parser.parse_args()
    checks = {}
    validate(args.data)
    checks["shipped_dataset_independent_validation"] = True
    with tempfile.TemporaryDirectory(prefix="wte1000_reproduce_") as temporary:
        root = Path(temporary)
        rebuilt = root / "rebuilt"
        config = read_json(args.data / "generation_config.json")
        generate(config, rebuilt)
        validate(rebuilt)
        source_files = sorted(p.name for p in args.data.iterdir() if p.is_file())
        rebuilt_files = sorted(p.name for p in rebuilt.iterdir() if p.is_file())
        if source_files != rebuilt_files:
            raise AssertionError("Regenerated file set differs")
        hashes = {name: sha256_file(args.data / name) for name in source_files}
        if any(sha256_file(rebuilt / name) != digest for name, digest in hashes.items()):
            raise AssertionError("Regenerated metadata is not byte-identical")
        checks["same_seed_all_metadata_byte_identical"] = True

        altered_config = dict(config)
        altered_config["seed"] = int(config["seed"]) + 1
        altered_config["shared_leaf_count"] = 0
        variant = root / "variant"
        generate(altered_config, variant)
        validate(variant)
        checks["different_seed_zero_shared_references_remain_valid"] = True
        checks["different_seed_changes_metadata"] = (
            sha256_file(variant / "nodes.csv") != sha256_file(args.data / "nodes.csv"))
        if not checks["different_seed_changes_metadata"]:
            raise AssertionError("Seed variation had no effect")

        for mutation in ["page_size", "graph_cycle", "unknown_owner"]:
            corrupt = root / ("corrupt_" + mutation)
            shutil.copytree(args.data, corrupt)
            if mutation == "page_size":
                rows = read_csv(corrupt / "pages.csv")
                rows[0]["size_bytes"] = int(rows[0]["size_bytes"]) + 1
                write_csv(corrupt / "pages.csv", list(rows[0]), rows)
            elif mutation == "graph_cycle":
                rows = read_csv(corrupt / "edges.csv")
                nodes = read_csv(corrupt / "nodes.csv")
                leaf = next(n["node_id"] for n in nodes if n["node_kind"] == "CP")
                rows.append({"parent_id": leaf, "child_id": nodes[0]["node_id"],
                             "edge_type": "shared_reference"})
                write_csv(corrupt / "edges.csv", list(rows[0]), rows)
            else:
                rows = read_csv(corrupt / "nodes.csv")
                row = next(n for n in rows if n["node_kind"] == "CP")
                row["responsible_party"] = "UNKNOWN"
                write_csv(corrupt / "nodes.csv", list(rows[0]), rows)
            try:
                validate(corrupt, check_manifest=False)
            except ValueError:
                checks["independent_detection_" + mutation] = True
            else:
                raise AssertionError("Validator accepted deliberate corruption")
            try:
                validate(corrupt)
            except ValueError:
                checks["manifest_detection_" + mutation] = True
            else:
                raise AssertionError("Manifest accepted altered files")

        pages = read_csv(args.data / "pages.csv")
        first = pages[0]
        content = b"".join(payload_chunks(first["payload_seed"], int(first["size_bytes"])))
        repeated = b"".join(payload_chunks(first["payload_seed"], int(first["size_bytes"])))
        if content != repeated or len(content) != int(first["size_bytes"]):
            raise AssertionError("Payload determinism failed")
        checks["small_complete_payload_reproducible"] = True
        checks["distinct_page_payload_seeds"] = first["payload_seed"] != pages[1]["payload_seed"]
        if not checks["distinct_page_payload_seeds"]:
            raise AssertionError("Page seeds are not distinct")
        sample_hash = hashlib.sha256(content).hexdigest()
    report = {
        "all_checks_passed": all(checks.values()),
        "python_version": platform.python_version(), "platform": platform.system(),
        "checks": checks, "canonical_metadata_sha256": hashes,
        "small_complete_payload_sha256": sample_hash,
        "full_272GB_payload_materialized": False,
        "scope": "Metadata reproducibility, independent validation, corruption detection, and a small full-payload smoke check",
    }
    write_json(args.output, report)
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'} {name}")
    if not report["all_checks_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
