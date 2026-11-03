"""Shared deterministic primitives; Python standard library only."""
from __future__ import annotations

import csv
import hashlib
import json
import os
from collections import defaultdict, deque
from pathlib import Path

VERSION = "1.0.0"
MASK64 = (1 << 64) - 1
PAYLOAD_BLOCK_BYTES = 1024 * 1024


class RNG:
    """SplitMix64 plus rejection sampling and Fisher-Yates, explicitly specified.

    This avoids depending on implementation changes in random.sample/shuffle.
    It is a simulation RNG, not a cryptographic randomness source.
    """
    def __init__(self, seed: int):
        self.state = seed & MASK64

    def u64(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & MASK64
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK64
        return (z ^ (z >> 31)) & MASK64

    def below(self, n: int) -> int:
        if not 0 < n <= 1 << 64:
            raise ValueError("RNG bound must be in 1..2**64")
        limit = (1 << 64) - ((1 << 64) % n)
        while True:
            x = self.u64()
            if x < limit:
                return x % n

    def shuffle(self, values: list) -> None:
        for i in range(len(values) - 1, 0, -1):
            j = self.below(i + 1)
            values[i], values[j] = values[j], values[i]

    def choice(self, values):
        return values[self.below(len(values))]


def apportion(total: int, weights: list[int]) -> list[int]:
    """Largest remainder allocation, integer-only and deterministic."""
    if total < 0 or not weights or any(w <= 0 for w in weights):
        raise ValueError("Invalid apportionment")
    denominator = sum(weights)
    result = [total * w // denominator for w in weights]
    remaining = total - sum(result)
    order = sorted(range(len(weights)),
                   key=lambda i: (-(total * weights[i] % denominator), i))
    for i in order[:remaining]:
        result[i] += 1
    return result


def bounded_sizes(total: int, count: int, lower: int, upper: int,
                  weights: list[int]) -> list[int]:
    """Exact integer volume allocation under per-page limits."""
    if len(weights) != count or not count * lower <= total <= count * upper:
        raise ValueError("Payload volume is infeasible under page-size limits")
    sizes = [lower] * count
    remaining = total - count * lower
    active = list(range(count))
    capacity = upper - lower
    while remaining:
        denominator = sum(weights[i] for i in active)
        saturated = [i for i in active
                     if remaining * weights[i] >= capacity * denominator]
        if saturated:
            marked = set(saturated)
            for i in saturated:
                sizes[i] += capacity
                remaining -= capacity
            active = [i for i in active if i not in marked]
            if remaining and not active:
                raise ValueError("No remaining size capacity")
        else:
            allocations = apportion(remaining, [weights[i] for i in active])
            for i, value in zip(active, allocations):
                sizes[i] += value
            remaining = 0
    return sizes


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(obj, ensure_ascii=False, indent=2,
                                sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_jsonl(path: Path, records: list[dict]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in records:
            handle.write(json.dumps(row, ensure_ascii=False,
                                    sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def payload_seed(seed: int, page_id: str) -> str:
    return hashlib.sha256(
        f"WtE1000-Synthetic-v1:{seed}:{page_id}".encode("ascii")
    ).hexdigest()


def payload_chunks(seed_hex: str, length: int):
    """Deterministic bytes; public test data, not encrypted engineering data."""
    seed = bytes.fromhex(seed_hex)
    block_index = 0
    remaining = length
    while remaining:
        amount = min(PAYLOAD_BLOCK_BYTES, remaining)
        prefix = b"WtE1000-payload-v1\0" + seed + block_index.to_bytes(8, "big")
        yield hashlib.shake_256(prefix).digest(amount)
        remaining -= amount
        block_index += 1


def adjacency(nodes: list[dict], edges: list[dict]):
    children = {row["node_id"]: [] for row in nodes}
    parents = {row["node_id"]: [] for row in nodes}
    for edge in edges:
        children[edge["parent_id"]].append(edge["child_id"])
        parents[edge["child_id"]].append(edge["parent_id"])
    return children, parents


def traverse(roots: list[str], children: dict[str, list[str]]) -> set[str]:
    visited = set()
    stack = list(roots)
    while stack:
        node = stack.pop()
        if node not in visited:
            visited.add(node)
            stack.extend(children[node])
    return visited
