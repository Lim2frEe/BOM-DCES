#!/usr/bin/env python3
"""Independently check schema relations, graph invariants, sizes, and workloads."""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path, PurePosixPath

from common import (VERSION, payload_seed, read_csv, read_json, read_jsonl,
                    sha256_file, write_json)

PUBLISHED_TARGETS = {
    "nodes": 18563,
    "leaf_entities": 4116,
    "max_hierarchical_levels": 19,
    "disciplines": 9,
    "spcs": 52,
    "drawing_page_records": 12820,
    "logical_payload_bytes": 272000000000,
    "maximum_page_bytes": 280000000,
}


def require(condition: bool, message: str):
    if not condition:
        raise ValueError(message)


def unique(rows, key):
    indexed = {row[key]: row for row in rows}
    require(len(indexed) == len(rows), f"Duplicate {key}")
    return indexed


def validate(directory: Path, check_manifest: bool = True) -> dict:
    config = read_json(directory / "generation_config.json")
    manifest = read_json(directory / "manifest.json")
    if check_manifest:
        for name, entry in manifest["files"].items():
            require(Path(name).name == name, "Unsafe manifest filename")
            path = directory / name
            require(path.is_file(), f"Missing manifest file {name}")
            require(path.stat().st_size == entry["size_bytes"],
                    f"Byte-size mismatch for {name}")
            require(sha256_file(path) == entry["sha256"],
                    f"SHA-256 mismatch for {name}")
    nodes = read_csv(directory / "nodes.csv")
    edges = read_csv(directory / "edges.csv")
    entities = read_csv(directory / "entities.csv")
    pages = read_csv(directory / "pages.csv")
    spcs = read_csv(directory / "spcs.csv")
    disciplines = read_csv(directory / "disciplines.csv")
    requests = read_jsonl(directory / "modifications.jsonl")
    batches = read_jsonl(directory / "confirmation_batches.jsonl")
    node_by_id = unique(nodes, "node_id")
    entity_by_id = unique(entities, "entity_id")
    page_by_id = unique(pages, "page_id")
    spc_by_id = unique(spcs, "spc_id")
    discipline_by_id = unique(disciplines, "discipline_id")
    unique(requests, "request_id")
    unique(batches, "batch_id")
    children = {node: [] for node in node_by_id}
    parents = {node: [] for node in node_by_id}
    primary_parents = defaultdict(list)
    edge_pairs = set()
    shared_leaves = set()
    for edge in edges:
        parent, child = edge["parent_id"], edge["child_id"]
        require(parent in node_by_id and child in node_by_id,
                "Edge has unknown endpoint")
        require(parent != child and (parent, child) not in edge_pairs,
                "Self-edge or duplicate edge")
        edge_pairs.add((parent, child))
        children[parent].append(child)
        parents[child].append(parent)
        kind = edge["edge_type"]
        require(kind in {"primary", "shared_reference"}, "Unknown edge type")
        if kind == "primary":
            primary_parents[child].append(parent)
        else:
            shared_leaves.add(child)
            require(node_by_id[child]["node_kind"] == "CP",
                    "Shared references must point to leaves")
    roots = sorted(node for node in node_by_id if not parents[node])
    require(len(roots) == 1, "Graph must have exactly one root")
    root = roots[0]
    indegrees = {node: len(parents[node]) for node in node_by_id}
    queue = deque(roots)
    computed_levels = {root: 1}
    processed = 0
    while queue:
        parent = queue.popleft()
        processed += 1
        for child in children[parent]:
            computed_levels[child] = max(
                computed_levels.get(child, 0), computed_levels[parent] + 1)
            indegrees[child] -= 1
            if indegrees[child] == 0:
                queue.append(child)
    require(processed == len(nodes), "Cycle or disconnected component detected")
    structural_leaves = {node for node in node_by_id if not children[node]}
    require(sum(e["edge_type"] == "primary" for e in edges) == len(nodes) - 1,
            "Primary graph must have N-1 edges")
    for row in nodes:
        node = row["node_id"]
        level = int(row["level"])
        require(level == computed_levels[node], "Stored level is incorrect")
        if node == root:
            require(row["node_kind"] == "FP" and not row["primary_parent_id"],
                    "Invalid root metadata")
        else:
            require(len(primary_parents[node]) == 1,
                    "Each non-root node needs exactly one primary parent")
            require(row["primary_parent_id"] == primary_parents[node][0],
                    "Primary-parent metadata mismatch")
            require(row["discipline_id"] in discipline_by_id,
                    "Unknown node discipline")
        require((row["node_kind"] == "CP") == (node in structural_leaves),
                "Declared leaf status differs from graph")
        if node in structural_leaves:
            require(row["responsible_party"] in spc_by_id,
                    "Unknown leaf owner")
            require(row["entity_id"] in entity_by_id, "Missing leaf entity")
        else:
            require(row["responsible_party"] == "LC" and not row["entity_id"],
                    "Internal nodes must have the logical LC role")
    for parent, child in edge_pairs:
        require(computed_levels[child] == computed_levels[parent] + 1,
                "Edges must join adjacent levels in this synthetic profile")
    entity_nodes = {row["node_id"] for row in entities}
    require(entity_nodes == structural_leaves
            and len(entities) == len(structural_leaves),
            "Leaf/entity mapping must be one-to-one")
    for entity in entities:
        row = node_by_id[entity["node_id"]]
        require(entity["entity_id"] == row["entity_id"]
                and entity["owner_spc_id"] == row["responsible_party"]
                and entity["discipline_id"] == row["discipline_id"],
                "Entity owner or discipline mismatch")
    require({entity["owner_spc_id"] for entity in entities} == set(spc_by_id),
            "Every synthetic SPC must own at least one entity")
    require({row["discipline_id"] for row in entities} == set(discipline_by_id),
            "Every discipline must be represented by an entity")
    require(len(shared_leaves) == int(config["shared_leaf_count"])
            and sum(e["edge_type"] == "shared_reference" for e in edges)
            == len(shared_leaves), "Shared-reference profile mismatch")
    page_counts, entity_bytes, sizes, paths = Counter(), Counter(), [], set()
    for page in pages:
        page_id, entity_id = page["page_id"], page["entity_id"]
        require(entity_id in entity_by_id, "Page references unknown entity")
        require(re.fullmatch(r"P[0-9]{6}", page_id) is not None,
                "Invalid page identifier")
        size = int(page["size_bytes"])
        require(int(config["page_min_bytes"]) <= size
                <= int(config["page_max_bytes"]), "Page size outside bounds")
        require(page["payload_seed"] == payload_seed(int(config["seed"]), page_id),
                "Incorrect deterministic payload seed")
        relative = PurePosixPath(page["relative_path"])
        require(not relative.is_absolute() and ".." not in relative.parts
                and str(relative) == f"payload/{page_id}.bin",
                "Unsafe or unexpected payload path")
        require(str(relative) not in paths, "Duplicate payload path")
        paths.add(str(relative))
        sizes.append(size)
        page_counts[entity_id] += 1
        entity_bytes[entity_id] += size
    for entity_id, entity in entity_by_id.items():
        require(page_counts[entity_id] >= 1, "Entity has no page")
        require(page_counts[entity_id] == int(entity["page_count"]),
                "Entity page count mismatch")
        require(entity_bytes[entity_id] == int(entity["logical_payload_bytes"]),
                "Entity byte total mismatch")
    require(len(requests) == int(config["modification_count"]),
            "Modification count differs from config")
    request_nodes, request_levels, request_owners = [], [], []
    for request in requests:
        visited, stack = set(), list(request["affected_roots"])
        require(stack and all(node in node_by_id for node in stack),
                "Unknown or empty affected roots")
        while stack:
            node = stack.pop()
            if node not in visited:
                visited.add(node)
                stack.extend(children[node])
        leaf_ids = visited & structural_leaves
        require(request["target_leaf"] in leaf_ids,
                "Target must be a leaf in the affected scope")
        owners = sorted({node_by_id[node]["responsible_party"] for node in leaf_ids})
        span = (max(computed_levels[node] for node in visited)
                - min(computed_levels[node] for node in visited) + 1)
        require(len(visited) == request["expected_visited_nodes"],
                "Incorrect expected traversal count")
        require(len(leaf_ids) == request["expected_affected_leaves"]
                and owners == request["expected_affected_spcs"]
                and span == request["expected_level_span"],
                "Incorrect expected affected scope")
        require(len(visited) <= int(config["local_max_nodes"])
                and span <= int(config["local_max_levels"]),
                "Local workload exceeds author-specified scenario caps")
        request_nodes.append(len(visited))
        request_levels.append(span)
        request_owners.append(len(owners))
    for batch in batches:
        count = int(batch["participant_count"])
        require(len(batch["spc_ids"]) == count
                and len(set(batch["spc_ids"])) == count
                and set(batch["spc_ids"]) <= set(spc_by_id), "Invalid batch SPCs")
        require(batch["confirmation_transaction_count"] == count
                and batch["total_ledger_write_count"] == count + 2
                and batch["separate_confirmation_query_count"] == count,
                "Incorrect confirmation operation counts")
    observed = {
        "nodes": len(nodes), "leaf_entities": len(structural_leaves),
        "max_hierarchical_levels": max(computed_levels.values()),
        "disciplines": len(disciplines), "spcs": len(spcs),
        "drawing_page_records": len(pages),
        "logical_payload_bytes": sum(sizes), "maximum_page_bytes": max(sizes),
    }
    for metric, target in PUBLISHED_TARGETS.items():
        require(observed[metric] == target,
                f"Published-profile mismatch: {metric}={observed[metric]}, expected {target}")
    require(min(sizes) == int(config["page_min_bytes"]),
            "Synthetic minimum-size anchor is missing")
    stored_summary = read_json(directory / "summary.json")
    for metric, actual in observed.items():
        require(stored_summary[metric] == actual, "Summary disagrees with source CSVs")
    boundary_root = stored_summary.get("synthetic_boundary_root")
    if config.get("boundary_subtree_level_counts"):
        require(boundary_root in node_by_id, "Missing synthetic boundary root")
        scope, stack = set(), [boundary_root]
        while stack:
            node = stack.pop()
            if node not in scope:
                scope.add(node)
                stack.extend(children[node])
        marked = {row["node_id"] for row in nodes
                  if row["synthetic_boundary_member"] == "True"}
        require(scope == marked and len(scope) == int(config["local_max_nodes"]),
                "Boundary subtree membership or size mismatch")
        offset = computed_levels[boundary_root]
        profile = Counter(computed_levels[n] - offset for n in scope)
        require([profile[i] for i in range(len(profile))]
                == config["boundary_subtree_level_counts"],
                "Boundary subtree level profile mismatch")
        require(max(request_nodes) == int(config["local_max_nodes"])
                and max(request_levels) == int(config["local_max_levels"]),
                "Workload does not exercise both local boundary caps")
    return {
        "validator_version": VERSION, "all_checks_passed": True,
        "manifest_sha256_checked": check_manifest,
        "profile_conventions": {
            "GB_bytes": 1_000_000_000, "MB_bytes": 1_000_000,
            "root_level": 1,
            "reported_approximate_counts_used_as_exact_synthetic_targets": True,
        },
        "published_profile": [
            {"metric": metric, "target": target, "observed": observed[metric],
             "matched": True} for metric, target in PUBLISHED_TARGETS.items()],
        "additional_synthetic_properties": {
            "edges": len(edges), "shared_leaves": len(shared_leaves),
            "minimum_page_bytes": min(sizes),
            "modification_requests": len(requests),
            "local_max_visited_nodes": max(request_nodes, default=0),
            "local_max_level_span": max(request_levels, default=0),
            "local_max_affected_spcs": max(request_owners, default=0),
            "confirmation_microbenchmark_sizes":
                [b["participant_count"] for b in batches],
        },
        "check_groups": [
            "Shipped-file SHA-256 and byte counts",
            "Unique identifiers and foreign keys",
            "Root, reachability, acyclicity and primary tree",
            "Independently recomputed levels and structural leaves",
            "Discipline, owner, entity and page mappings",
            "Exact page count, payload volume and page-size limits",
            "Reference workload results recomputed by traversal",
            "Ledger write and query operation counts",
        ],
        "limitations": [
            "Distributional choices are synthetic assumptions, not estimated industrial distributions.",
            "272 GB describes logical unencrypted payload bytes; payload files are generated on demand.",
            "This validation does not reproduce or certify manuscript runtime measurements.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = validate(args.data)
        if args.output:
            write_json(args.output, report)
        for entry in report["published_profile"]:
            print(f"PASS {entry['metric']}: {entry['observed']}")
        print("PASS all structural, volume, ownership, workload and manifest checks")
    except (ValueError, KeyError, OSError) as error:
        print(f"VALIDATION FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
