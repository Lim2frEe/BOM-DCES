#!/usr/bin/env python3
"""Plan or materialize deterministic synthetic page payloads."""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

from common import payload_chunks, read_csv, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, default=Path("generated_payloads"))
    parser.add_argument("--mode", choices=["full", "prefix", "sparse"], default="prefix")
    parser.add_argument("--page-id", action="append", dest="page_ids")
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--all-pages", action="store_true")
    parser.add_argument("--prefix-bytes", type=int, default=65536)
    parser.add_argument("--execute", action="store_true",
                        help="Actually write files; otherwise print the plan only")
    args = parser.parse_args()
    if args.max_pages < 1 or args.prefix_bytes < 1:
        parser.error("max-pages and prefix-bytes must be positive")
    if args.all_pages and args.page_ids:
        parser.error("Choose either all-pages or explicit page-id values")
    pages = read_csv(args.data / "pages.csv")
    if args.page_ids:
        requested = set(args.page_ids)
        selected = [p for p in pages if p["page_id"] in requested]
        if len(selected) != len(requested):
            parser.error("Unknown page-id")
    else:
        selected = pages if args.all_pages else pages[:args.max_pages]
    lengths = [int(p["size_bytes"]) for p in selected]
    logical = sum(lengths)
    output_length = (sum(min(n, args.prefix_bytes) for n in lengths)
                     if args.mode == "prefix" else logical)
    print(f"Mode: {args.mode}; pages: {len(selected)}; logical bytes: {logical}")
    print(f"Output file lengths: {output_length} bytes")
    if args.mode == "sparse":
        print("Sparse files contain zero-filled holes; unsuitable for payload throughput benchmarks.")
    if not args.execute:
        print("Plan only. Add --execute to write the selected files.")
        return
    folder = args.output / args.mode
    folder.mkdir(parents=True, exist_ok=True)
    for page in selected:
        page_id = page["page_id"]
        if not page_id.startswith("P") or not page_id[1:].isdigit():
            raise ValueError("Invalid page ID")
        if (folder / f"{page_id}.bin").exists():
            raise FileExistsError("Refusing to overwrite an existing payload")
    records = []
    for page in selected:
        logical_size = int(page["size_bytes"])
        amount = (min(logical_size, args.prefix_bytes)
                  if args.mode == "prefix" else logical_size)
        path = folder / f"{page['page_id']}.bin"
        digest = hashlib.sha256()
        with path.open("xb") as handle:
            if args.mode == "sparse":
                handle.truncate(amount)
            else:
                for chunk in payload_chunks(page["payload_seed"], amount):
                    handle.write(chunk)
                    digest.update(chunk)
        allocated = getattr(path.stat(), "st_blocks", None)
        records.append({
            "page_id": page["page_id"], "mode": args.mode,
            "logical_page_bytes": logical_size, "output_file_bytes": amount,
            "complete_deterministic_payload":
                args.mode == "full" or (args.mode == "prefix" and amount == logical_size),
            "sha256_of_written_bytes": digest.hexdigest() if args.mode != "sparse" else None,
            "allocated_disk_bytes": allocated * 512 if allocated is not None else None,
        })
    write_json(folder / "materialization_report.json", {
        "mode": args.mode, "logical_catalog_bytes_selected": logical,
        "output_file_lengths_total": output_length,
        "files": records,
        "note": "Prefix and sparse modes are not equivalent to full payload materialization.",
    })
    print(f"Wrote {len(records)} files and materialization_report.json")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        print(f"MATERIALIZATION FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
