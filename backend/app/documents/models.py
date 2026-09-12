from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class ProcessedDocument:
    source_path: str
    file_name: str
    kind: str
    text: str
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    diagram: Dict[str, Any] = field(default_factory=dict)
    pages: List[Dict[str, Any]] = field(default_factory=list)
    artifacts: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def routing_text(self) -> str:
        """
        Text passed to SemanticAgentRouter.

        The friend's rag_document()['text'] is already retrieval-oriented, so
        for drawings this generally returns that text unchanged. Structured
        diagram information is appended only if it is not already represented.
        """
        parts = [self.text.strip()]

        nodes = self.diagram.get("nodes", [])
        edges = self.diagram.get("edges", [])

        if nodes:
            node_lines = []
            for node in nodes:
                text = str(node.get("text", "")).strip()
                shape = str(node.get("shape", "")).strip()
                if text:
                    node_lines.append(
                        f"- {text}" + (f" ({shape})" if shape else "")
                    )
            if node_lines:
                parts.append(
                    "Diagram nodes:\n" + "\n".join(node_lines)
                )

        if edges:
            edge_lines = []
            for edge in edges:
                src = (
                    edge.get("source")
                    or edge.get("from")
                    or edge.get("src")
                    or ""
                )
                dst = (
                    edge.get("target")
                    or edge.get("to")
                    or edge.get("dst")
                    or ""
                )
                label = str(edge.get("label", "")).strip()

                if src or dst:
                    line = f"- {src} -> {dst}"
                    if label:
                        line += f" [{label}]"
                    edge_lines.append(line)

            if edge_lines:
                parts.append(
                    "Diagram edges:\n" + "\n".join(edge_lines)
                )

        return "\n\n".join(
            part for part in parts if part
        ).strip()
