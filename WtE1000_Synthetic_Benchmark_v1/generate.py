#!/usr/bin/env python3
"""Generate synthetic metadata matching published aggregate WtE1000 statistics."""
from __future__ import annotations

import argparse
import bisect
from collections import Counter, defaultdict
from pathlib import Path

from common import (RNG, VERSION, adjacency, apportion, bounded_sizes,
                    payload_seed, read_json, sha256_file, write_csv,
                    write_json, write_jsonl)


def generate(config: dict, output: Path) -> dict:
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output must be absent or empty; choose a new directory")
    output.mkdir(parents=True, exist_ok=True)
    rng = RNG(int(config["seed"]))
    total = int(config["node_count"])
    leaf_total = int(config["leaf_count"])
    levels = int(config["max_levels"])
    disciplines = config["disciplines"]
    groups = len(disciplines)
    internal_total = total - leaf_total
    weights = config["internal_level_weights"]
    if levels < 4 or len(weights) != levels - 1:
        raise ValueError("internal_level_weights must have max_levels-1 entries")
    if config["page_count"] < leaf_total:
        raise ValueError("Each leaf entity requires at least one page")
    internals = {1: 1, 2: groups}
    allocations = apportion(internal_total - 1 - groups, weights[2:])
    internals.update({level: value for level, value
                      in zip(range(3, levels), allocations)})
    if min(internals.values()) < 1:
        raise ValueError("Insufficient internal nodes for the requested depth")
    leaves = {level: max(0, internals.get(level - 1, 0)
                         - internals.get(level, 0))
              for level in range(2, levels + 1)}
    surplus = leaf_total - sum(leaves.values())
    if surplus < 0:
        raise ValueError("Internal profile needs more leaves than available")
    extra = apportion(surplus, [(level - 2) ** 2
                               for level in range(4, levels + 1)])
    for level, amount in zip(range(4, levels + 1), extra):
        leaves[level] += amount

    nodes, edges = [], []
    by_level = defaultdict(list)
    by_id = {}
    boundary_profile = config.get("boundary_subtree_level_counts", [])
    boundary_start = levels - len(boundary_profile) + 1 if boundary_profile else None
    boundary_by_level = {}
    boundary_members = set()
    boundary_root = None
    if boundary_profile:
        if (boundary_profile[0] != 1
                or len(boundary_profile) != int(config["local_max_levels"])
                or sum(boundary_profile) != int(config["local_max_nodes"])):
            raise ValueError("Boundary profile must match the specified local caps")

    def add_node(level, kind, discipline=""):
        node_id = f"N{len(nodes) + 1:06d}"
        row = {"node_id": node_id, "level": level, "node_kind": kind,
               "discipline_id": discipline, "entity_id": "",
               "responsible_party": "LC", "primary_parent_id": "",
               "synthetic_boundary_member": False}
        nodes.append(row)
        by_id[node_id] = row
        by_level[level].append(node_id)
        return node_id

    root = add_node(1, "FP", "PROJECT")
    for discipline in disciplines:
        child = add_node(2, "MW", discipline["discipline_id"])
        by_id[child]["primary_parent_id"] = root
        edges.append({"parent_id": root, "child_id": child, "edge_type": "primary"})
    max_children = int(config["max_primary_children_nonroot"])

    def assign_group(parents, child_ids):
        parents, child_ids = list(parents), list(child_ids)
        rng.shuffle(parents)
        rng.shuffle(child_ids)
        if not len(parents) <= len(child_ids) <= max_children * len(parents):
            raise ValueError("Requested level/branch profile exceeds child capacity")
        parent_choices = list(parents)
        degrees = {parent: 0 for parent in parents}
        assigned = []
        for parent, child in zip(parents, child_ids):
            assigned.append((parent, child))
            degrees[parent] = 1
        for child in child_ids[len(parents):]:
            index = rng.below(len(parent_choices))
            parent = parent_choices[index]
            assigned.append((parent, child))
            degrees[parent] += 1
            if degrees[parent] == max_children:
                parent_choices[index] = parent_choices[-1]
                parent_choices.pop()
        return assigned

    for level in range(3, levels + 1):
        new_ids = [add_node(level, "MW")
                   for _ in range(internals.get(level, 0))]
        new_ids += [add_node(level, "CP") for _ in range(leaves.get(level, 0))]
        parents = [n for n in by_level[level - 1]
                   if by_id[n]["node_kind"] != "CP"]
        reserved = []
        if boundary_profile and level >= boundary_start:
            boundary_index = level - boundary_start
            kind = "CP" if level == levels else "MW"
            reserved = [n for n in new_ids if by_id[n]["node_kind"] == kind][
                :boundary_profile[boundary_index]]
            if len(reserved) != boundary_profile[boundary_index]:
                raise ValueError("Not enough nodes for the local boundary profile")
            boundary_by_level[level] = reserved
            boundary_members.update(reserved)
            for node in reserved:
                by_id[node]["synthetic_boundary_member"] = True
            if level == boundary_start:
                boundary_root = reserved[0]
        if boundary_profile and level > boundary_start:
            reserved_set = set(reserved)
            reserved_parents = set(boundary_by_level[level - 1])
            assigned = assign_group(sorted(reserved_parents), reserved)
            assigned += assign_group(
                [p for p in parents if p not in reserved_parents],
                [n for n in new_ids if n not in reserved_set])
        else:
            assigned = assign_group(parents, new_ids)
        for parent, child in assigned:
            by_id[child]["primary_parent_id"] = parent
            by_id[child]["discipline_id"] = by_id[parent]["discipline_id"]
            edges.append({"parent_id": parent, "child_id": child,
                          "edge_type": "primary"})
    if len(nodes) != total:
        raise AssertionError("Node allocation error")

    spcs = []
    spc_by_discipline = defaultdict(list)
    for index in range(int(config["spc_count"])):
        discipline = disciplines[index % groups]["discipline_id"]
        spc_id = f"SPC{index + 1:03d}"
        spcs.append({"spc_id": spc_id, "primary_discipline_id": discipline,
                     "label": f"Synthetic collaborator {index + 1:03d}"})
        spc_by_discipline[discipline].append(spc_id)
    leaf_by_discipline = defaultdict(list)
    for row in nodes:
        if row["node_kind"] == "CP":
            leaf_by_discipline[row["discipline_id"]].append(row["node_id"])
    for discipline, leaf_ids in sorted(leaf_by_discipline.items()):
        rng.shuffle(leaf_ids)
        owners = spc_by_discipline[discipline]
        if len(leaf_ids) < len(owners):
            raise ValueError("Not enough leaves to represent all SPCs")
        offset = rng.below(len(owners))
        for index, node_id in enumerate(leaf_ids):
            by_id[node_id]["responsible_party"] = owners[(index + offset) % len(owners)]

    leaf_ids = [row["node_id"] for row in nodes if row["node_kind"] == "CP"]
    entities = []
    for index, node_id in enumerate(leaf_ids):
        row = by_id[node_id]
        entity_id = f"E{index + 1:06d}"
        row["entity_id"] = entity_id
        entities.append({"entity_id": entity_id, "node_id": node_id,
                         "owner_spc_id": row["responsible_party"],
                         "discipline_id": row["discipline_id"],
                         "page_count": 0, "logical_payload_bytes": 0})

    shared_candidates = []
    for node_id in leaf_ids:
        row = by_id[node_id]
        eligible = [p for p in by_level[row["level"] - 1]
                    if by_id[p]["node_kind"] == "MW"
                    and p != row["primary_parent_id"]
                    and (p not in boundary_members or node_id in boundary_members)]
        if eligible:
            shared_candidates.append((node_id, eligible))
    rng.shuffle(shared_candidates)
    shared_count = int(config["shared_leaf_count"])
    if not 0 <= shared_count <= len(shared_candidates):
        raise ValueError("shared_leaf_count exceeds eligible leaf entities")
    for node_id, eligible in shared_candidates[:shared_count]:
        cross = [p for p in eligible
                 if by_id[p]["discipline_id"] != by_id[node_id]["discipline_id"]]
        parent = rng.choice(cross or eligible)
        edges.append({"parent_id": parent, "child_id": node_id,
                      "edge_type": "shared_reference"})

    page_count = int(config["page_count"])
    minimum, maximum = int(config["page_min_bytes"]), int(config["page_max_bytes"])
    if page_count < 2:
        raise ValueError("At least two pages are needed for range anchors")
    size_weights = [(rng.below(1_000_000) + 1)
                    ** int(config["page_size_weight_power"])
                    for _ in range(page_count - 2)]
    sizes = [minimum, maximum] + bounded_sizes(
        int(config["payload_total_bytes"]) - minimum - maximum,
        page_count - 2, minimum, maximum, size_weights)
    first_entities = list(range(len(entities)))
    rng.shuffle(first_entities)
    assignments = first_entities + [rng.below(len(entities))
                                    for _ in range(page_count - len(entities))]
    pages = []
    for index, (size, entity_index) in enumerate(zip(sizes, assignments)):
        page_id = f"P{index + 1:06d}"
        entity = entities[entity_index]
        pages.append({"page_id": page_id, "entity_id": entity["entity_id"],
                      "size_bytes": size,
                      "payload_seed": payload_seed(int(config["seed"]), page_id),
                      "relative_path": f"payload/{page_id}.bin"})
        entity["page_count"] += 1
        entity["logical_payload_bytes"] += size

    children, _ = adjacency(nodes, edges)
    closures = {}
    for row in reversed(nodes):
        node_id = row["node_id"]
        scope = {node_id}
        for child in children[node_id]:
            scope.update(closures[child])
        closures[node_id] = frozenset(scope)
    candidates = []
    max_nodes = int(config["local_max_nodes"])
    max_levels = int(config["local_max_levels"])
    for row in nodes:
        if row["node_kind"] == "CP":
            continue
        scope = closures[row["node_id"]]
        span = max(by_id[n]["level"] for n in scope) - row["level"] + 1
        if len(scope) <= max_nodes and span <= max_levels:
            scoped_leaves = sorted(n for n in scope if not children[n])
            owners = sorted({by_id[n]["responsible_party"] for n in scoped_leaves})
            candidates.append({"root": row["node_id"], "scope": scope,
                               "span": span, "leaves": scoped_leaves,
                               "owners": owners})
    if not candidates:
        raise ValueError("No local scopes satisfy the requested limits")
    cumulative, cumulative_total = [], 0
    for candidate in candidates:
        cumulative_total += len(candidate["scope"]) ** 2
        cumulative.append(cumulative_total)
    boundary_candidates = [
        max(candidates, key=lambda c: len(c["scope"])),
        max(candidates, key=lambda c: c["span"]),
        max(candidates, key=lambda c: len(c["owners"])),
        min(candidates, key=lambda c: len(c["scope"])),
    ]
    modifications = []
    for index in range(int(config["modification_count"])):
        candidate = (boundary_candidates[index]
                     if index < len(boundary_candidates)
                     else candidates[bisect.bisect_right(
                         cumulative, rng.below(cumulative_total))])
        modifications.append({
            "request_id": f"REQ{index + 1:06d}",
            "target_leaf": rng.choice(candidate["leaves"]),
            "affected_roots": [candidate["root"]],
            "scope_selection": "synthetic_explicit_input",
            "expected_visited_nodes": len(candidate["scope"]),
            "expected_affected_leaves": len(candidate["leaves"]),
            "expected_level_span": candidate["span"],
            "expected_affected_spcs": candidate["owners"],
        })

    batches = []
    spc_ids = [row["spc_id"] for row in spcs]
    for count in sorted({1, 2, 5, 10, 20, len(spc_ids)}):
        if count > len(spc_ids):
            continue
        selected = list(spc_ids)
        rng.shuffle(selected)
        batches.append({"batch_id": f"CF{count:03d}",
                        "participant_count": count,
                        "spc_ids": sorted(selected[:count]),
                        "confirmation_transaction_count": count,
                        "total_ledger_write_count": count + 2,
                        "separate_confirmation_query_count": count,
                        "scope": "synthetic_confirmation_microbenchmark_only"})

    write_json(output / "generation_config.json", config)
    write_csv(output / "nodes.csv", list(nodes[0]), nodes)
    write_csv(output / "edges.csv", ["parent_id", "child_id", "edge_type"], edges)
    write_csv(output / "entities.csv", list(entities[0]), entities)
    write_csv(output / "pages.csv", list(pages[0]), pages)
    write_csv(output / "spcs.csv", list(spcs[0]), spcs)
    write_csv(output / "disciplines.csv", list(disciplines[0]), disciplines)
    write_jsonl(output / "modifications.jsonl", modifications)
    write_jsonl(output / "confirmation_batches.jsonl", batches)
    primary_degrees = Counter(e["parent_id"] for e in edges
                              if e["edge_type"] == "primary")
    summary = {
        "benchmark": config["benchmark_name"], "version": VERSION,
        "seed": config["seed"], "nodes": len(nodes),
        "leaf_entities": len(entities), "primary_edges": len(nodes) - 1,
        "shared_reference_edges": shared_count, "all_edges": len(edges),
        "max_hierarchical_levels": levels, "max_root_to_leaf_edges": levels - 1,
        "depth_convention": "root level is 1; reported depth means level count",
        "disciplines": len(disciplines), "spcs": len(spcs),
        "drawing_page_records": len(pages),
        "logical_payload_bytes": sum(sizes),
        "logical_payload_GB_decimal": sum(sizes) / 1_000_000_000,
        "minimum_page_bytes": min(sizes), "maximum_page_bytes": max(sizes),
        "payload_files_included": False,
        "level_node_counts": dict(sorted(Counter(r["level"] for r in nodes).items())),
        "primary_internal_nodes_with_one_child": sum(
            1 for row in nodes
            if row["node_kind"] != "CP"
            and primary_degrees[row["node_id"]] == 1),
        "modification_requests": len(modifications),
        "generated_local_max_visited_nodes": max(
            r["expected_visited_nodes"] for r in modifications),
        "generated_local_max_level_span": max(
            r["expected_level_span"] for r in modifications),
        "generated_local_max_affected_spcs": max(
            len(r["expected_affected_spcs"]) for r in modifications),
        "synthetic_boundary_root": boundary_root,
        "synthetic_boundary_level_counts": boundary_profile,
        "important_limitation":
            "Only published aggregate statistics are matched. Topology, sharing, "
            "ownership, sizes, and workload choices are synthetic assumptions; "
            "no original industrial records or runtime results are included.",
    }
    write_json(output / "summary.json", summary)
    files = sorted(p for p in output.iterdir() if p.is_file())
    write_json(output / "manifest.json", {
        "format": "sha256-v1", "generator_version": VERSION,
        "files": {p.name: {"size_bytes": p.stat().st_size,
                            "sha256": sha256_file(p)} for p in files}})
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path,
                        default=Path(__file__).with_name("config.json"))
    parser.add_argument("--output", type=Path, default=Path("regenerated_data"))
    parser.add_argument("--seed", type=int)
    parser.add_argument("--shared-leaves", type=int)
    args = parser.parse_args()
    config = read_json(args.config)
    if args.seed is not None:
        config["seed"] = args.seed
    if args.shared_leaves is not None:
        config["shared_leaf_count"] = args.shared_leaves
    summary = generate(config, args.output)
    print(f"Generated {summary['nodes']} nodes, {summary['leaf_entities']} leaf "
          f"entities, {summary['drawing_page_records']} page records; "
          f"{summary['logical_payload_bytes']} logical payload bytes.")
    print("Payload bytes are not materialized. Run validate.py next.")


if __name__ == "__main__":
    main()
