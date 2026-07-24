"""Parsed representation of an n8n workflow export.

The linter works against these dataclasses rather than raw dicts so that rules
stay readable and a malformed export is rejected once, at load time, instead of
crashing an individual rule deep in a run.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Node:
    """A single node on the workflow canvas."""

    name: str
    type: str
    raw: dict
    line: int | None = None

    @property
    def disabled(self) -> bool:
        return bool(self.raw.get("disabled"))

    @property
    def type_version(self) -> float | int | None:
        return self.raw.get("typeVersion")

    @property
    def parameters(self) -> dict:
        return self.raw.get("parameters") or {}

    @property
    def credentials(self) -> dict:
        return self.raw.get("credentials") or {}

    @property
    def retry_on_fail(self) -> bool:
        return bool(self.raw.get("retryOnFail"))

    def type_is(self, *suffixes: str) -> bool:
        """True if the node type ends with any of the given suffixes.

        n8n node types are namespaced (`n8n-nodes-base.httpRequest`,
        `@n8n/n8n-nodes-langchain.agent`), so rules match on the suffix to stay
        agnostic to the namespace.
        """
        return any(self.type.endswith(suffix) for suffix in suffixes)


@dataclass(frozen=True)
class Workflow:
    """A loaded, well-formed workflow export."""

    path: str
    name: str
    nodes: tuple[Node, ...]
    connections: dict
    pin_data: dict
    raw: dict
    raw_text: str

    def nodes_by_name(self) -> dict[str, Node]:
        return {node.name: node for node in self.nodes}


@dataclass(frozen=True)
class LoadError:
    """A file that could not be parsed as a workflow."""

    path: str
    message: str
