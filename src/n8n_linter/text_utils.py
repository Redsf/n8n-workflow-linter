"""Small text helpers shared across rules and the loader."""

from __future__ import annotations

import json


def line_of_offset(text: str, offset: int) -> int:
    """1-indexed line number containing the character at `offset`."""
    return text.count("\n", 0, offset) + 1


def line_of_node(text: str, node_name: str) -> int | None:
    """Best-effort line number of a node, found by its unique name.

    Node names are unique within an n8n workflow, so the first `"name": "<x>"`
    occurrence is the node's declaration. Returns None if it can't be located
    (e.g. the name contains characters that were escaped differently).
    """
    needle = f'"name": {json.dumps(node_name)}'
    offset = text.find(needle)
    if offset == -1:
        # Fall back to a whitespace-tolerant search for common serializers.
        needle = f'"name":{json.dumps(node_name)}'
        offset = text.find(needle)
    if offset == -1:
        return None
    return line_of_offset(text, offset)


def redact(secret: str) -> str:
    """Show enough of a matched secret to locate it, never the whole thing."""
    if len(secret) <= 12:
        return "…"
    return f"{secret[:6]}…{secret[-4:]}"
