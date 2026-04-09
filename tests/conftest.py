"""Pytest fixtures for Code Atlas tests."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from code_atlas.graph import GraphStore
from code_atlas.models import Edge, Node


@pytest.fixture
def empty_graph() -> GraphStore:
    """Return an empty graph store."""
    return GraphStore()


@pytest.fixture
def sample_graph() -> GraphStore:
    """Return a populated graph with sample nodes and edges."""
    graph = GraphStore()

    # Add nodes
    nodes = [
        Node(id="python://module1", type="module", language="python", name="module1", file="module1.py", line=1),
        Node(id="python://module1:func1", type="function", language="python", name="func1", file="module1.py", line=5),
        Node(id="python://module1:func2", type="function", language="python", name="func2", file="module1.py", line=15),
        Node(id="python://module2", type="module", language="python", name="module2", file="module2.py", line=1),
        Node(id="python://module2:Class1", type="class", language="python", name="Class1", file="module2.py", line=3),
        Node(id="python://module2:Class1.method1", type="method", language="python", name="method1", file="module2.py", line=8),
    ]

    for node in nodes:
        graph.add_node(node)

    # Add edges
    edges = [
        Edge(type="CONTAINS", source="python://module1", target="python://module1:func1", language="python", confidence="high", file="module1.py", line=5),
        Edge(type="CONTAINS", source="python://module1", target="python://module1:func2", language="python", confidence="high", file="module1.py", line=15),
        Edge(type="CONTAINS", source="python://module2", target="python://module2:Class1", language="python", confidence="high", file="module2.py", line=3),
        Edge(type="CONTAINS", source="python://module2:Class1", target="python://module2:Class1.method1", language="python", confidence="high", file="module2.py", line=8),
        Edge(type="CALLS", source="python://module1:func1", target="python://module1:func2", language="python", confidence="high", file="module1.py", line=10),
        Edge(type="CALLS", source="python://module2:Class1.method1", target="python://module1:func1", language="python", confidence="medium", file="module2.py", line=12),
        Edge(type="IMPORTS", source="python://module2", target="python://module1", language="python", confidence="high", file="module2.py", line=1),
    ]

    for edge in edges:
        graph.add_edge(edge)

    return graph


@pytest.fixture
def temp_graph_file(sample_graph: GraphStore) -> Path:
    """Create a temporary graph file and return its path."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        path = Path(f.name)
        sample_graph.write_json(path)
        return path


@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    """Create a temporary repository with sample files."""
    # Create Python files
    (tmp_path / "module1.py").write_text("""
def func1():
    return func2()

def func2():
    return 42
""")

    (tmp_path / "module2.py").write_text("""
from module1 import func1

class Class1:
    def method1(self):
        return func1()
""")

    (tmp_path / "README.md").write_text("# Test Repo\n")

    return tmp_path
