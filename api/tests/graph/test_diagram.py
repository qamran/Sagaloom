"""The diagram in the docs is the compiled graph (R18.1, R18.9). It must not drift."""

import re
from pathlib import Path

import pytest

from checkpointers import memory_checkpointer
from sagaloom.config import Settings
from sagaloom.graph.build import build_graph

ROOT = Path(__file__).resolve().parents[3]
DOCS = ["README.md", "docs/requirements.md"]


def _body(mermaid: str) -> list[str]:
    """Lines normalised for CRLF and trailing whitespace. The docs keep the `---` front-matter
    config that `draw_mermaid()` emits, so both sides contain it and the whole block is compared."""
    return [line.rstrip() for line in mermaid.replace("\r\n", "\n").strip().split("\n")]


def _documented(path: str) -> list[str]:
    text = (ROOT / path).read_text(encoding="utf-8")
    blocks = re.findall(r"```mermaid\r?\n(.*?)```", text, flags=re.DOTALL)
    assert len(blocks) == 1, f"{path} should hold exactly one mermaid block"
    return _body(blocks[0])


@pytest.mark.parametrize("path", DOCS)
def test_documented_diagram_matches_compiled_graph(path):
    graph = build_graph(
        store=object(),  # never called: the graph is only compiled and drawn
        model_for=lambda role: None,
        checkpointer=memory_checkpointer(),
    )
    assert _documented(path) == _body(graph.get_graph().draw_mermaid())
