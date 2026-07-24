"""Find and parse n8n workflow exports."""

from __future__ import annotations

import json
from pathlib import Path

from .model import LoadError, Node, Workflow
from .text_utils import line_of_node

SKIP_DIRS = frozenset({".git", "node_modules", "__pycache__", ".venv", "venv"})


def collect_files(paths: list[str]) -> list[Path]:
    """Expand paths into a sorted, de-duplicated list of JSON files."""
    found: list[Path] = []
    seen: set[Path] = set()

    for raw in paths:
        path = Path(raw)
        candidates = (
            sorted(path.rglob("*.json")) if path.is_dir()
            else [path] if path.suffix == ".json"
            else []
        )
        for candidate in candidates:
            if any(part in SKIP_DIRS for part in candidate.parts):
                continue
            resolved = candidate.resolve()
            if resolved not in seen:
                seen.add(resolved)
                found.append(candidate)

    return found


def load(path: Path) -> Workflow | LoadError:
    """Parse one file into a Workflow, or a LoadError explaining why not."""
    where = str(path)
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return LoadError(where, f"could not read file — {exc}")

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return LoadError(where, f"invalid JSON — {exc}")

    if not isinstance(data, dict) or "nodes" not in data:
        return LoadError(where, "not an n8n workflow export (no top-level 'nodes')")

    raw_nodes = data.get("nodes")
    if not isinstance(raw_nodes, list):
        return LoadError(where, "'nodes' is not a list")

    nodes = tuple(
        Node(
            name=str(raw.get("name", "?")),
            type=str(raw.get("type", "")),
            raw=raw,
            line=line_of_node(raw_text, str(raw.get("name", ""))),
        )
        for raw in raw_nodes
        if isinstance(raw, dict)
    )

    return Workflow(
        path=where,
        name=str(data.get("name") or path.stem),
        nodes=nodes,
        connections=data.get("connections") or {},
        pin_data=data.get("pinData") or {},
        raw=data,
        raw_text=raw_text,
    )
