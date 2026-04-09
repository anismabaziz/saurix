"""Tests for Python extractor."""
from __future__ import annotations

from pathlib import Path

import pytest

from code_atlas.extractors.python_extractor import PythonExtractor
from code_atlas.graph import GraphStore


class TestPythonExtractorBasics:
    """Test basic Python extraction."""

    def test_extract_module(self, tmp_path: Path) -> None:
        """Test extracting a simple module."""
        (tmp_path / "test_module.py").write_text("""
import os
from sys import path

def my_function():
    return 42

class MyClass:
    def method(self):
        return my_function()
""")

        graph = GraphStore()
        extractor = PythonExtractor()
        extractor.extract(repo_root=tmp_path, file_path=tmp_path / "test_module.py", graph=graph)

        # Check module node exists
        assert "python://test_module" in graph.nodes
        assert graph.nodes["python://test_module"].type == "module"

    def test_extract_function(self, tmp_path: Path) -> None:
        """Test extracting functions."""
        (tmp_path / "funcs.py").write_text("""
def standalone_func():
    pass

async def async_func():
    pass
""")

        graph = GraphStore()
        extractor = PythonExtractor()
        extractor.extract(repo_root=tmp_path, file_path=tmp_path / "funcs.py", graph=graph)

        # Check function nodes
        assert "python://funcs:standalone_func" in graph.nodes
        assert "python://funcs:async_func" in graph.nodes
        assert graph.nodes["python://funcs:standalone_func"].type == "function"

    def test_extract_class(self, tmp_path: Path) -> None:
        """Test extracting classes."""
        (tmp_path / "classes.py").write_text("""
class BaseClass:
    pass

class DerivedClass(BaseClass):
    def __init__(self):
        self.value = 10

    def get_value(self):
        return self.value
""")

        graph = GraphStore()
        extractor = PythonExtractor()
        extractor.extract(repo_root=tmp_path, file_path=tmp_path / "classes.py", graph=graph)

        # Check class node
        assert "python://classes:BaseClass" in graph.nodes
        assert "python://classes:DerivedClass" in graph.nodes

        # Check inheritance edge
        inherits_edges = [e for e in graph.edges if e.type == "INHERITS"]
        assert len(inherits_edges) == 1
        assert inherits_edges[0].source == "python://classes:DerivedClass"

    def test_extract_imports(self, tmp_path: Path) -> None:
        """Test extracting import statements."""
        (tmp_path / "imports.py").write_text("""
import os
import sys as system
from collections import defaultdict
from typing import List, Dict
""")

        graph = GraphStore()
        extractor = PythonExtractor()
        extractor.extract(repo_root=tmp_path, file_path=tmp_path / "imports.py", graph=graph)

        # Check import edges
        import_edges = [e for e in graph.edges if e.type == "IMPORTS"]
        assert len(import_edges) >= 4  # os, sys, collections, typing

        targets = {e.target for e in import_edges}
        assert "python://os" in targets
        assert "python://collections.defaultdict" in targets


class TestPythonExtractorCalls:
    """Test call extraction."""

    def test_extract_function_calls(self, tmp_path: Path) -> None:
        """Test extracting function calls."""
        (tmp_path / "calls.py").write_text("""
def helper():
    return 1

def caller():
    result = helper()
    return result + helper()
""")

        graph = GraphStore()
        extractor = PythonExtractor()
        extractor.extract(repo_root=tmp_path, file_path=tmp_path / "calls.py", graph=graph)

        # Check call edges
        call_edges = [e for e in graph.edges if e.type == "CALLS"]
        assert len(call_edges) >= 2

        # Check that caller calls helper
        caller_calls = [e for e in call_edges if e.source == "python://calls:caller"]
        assert len(caller_calls) >= 1
        assert any("helper" in e.target for e in caller_calls)

    def test_extract_method_calls(self, tmp_path: Path) -> None:
        """Test extracting method calls within classes."""
        (tmp_path / "methods.py").write_text("""
class Calculator:
    def add(self, a, b):
        return a + b

    def sum_list(self, numbers):
        return sum(numbers)

    def calculate(self):
        result = self.add(1, 2)
        return self.sum_list([result, result])
""")

        graph = GraphStore()
        extractor = PythonExtractor()
        extractor.extract(repo_root=tmp_path, file_path=tmp_path / "methods.py", graph=graph)

        # Should have method nodes
        assert "python://methods:Calculator.add" in graph.nodes
        assert "python://methods:Calculator.sum_list" in graph.nodes
        assert "python://methods:Calculator.calculate" in graph.nodes


class TestPythonExtractorEdgeCases:
    """Test edge cases."""

    def test_empty_file(self, tmp_path: Path) -> None:
        """Test extracting empty file."""
        (tmp_path / "empty.py").write_text("")

        graph = GraphStore()
        extractor = PythonExtractor()
        extractor.extract(repo_root=tmp_path, file_path=tmp_path / "empty.py", graph=graph)

        # Should still create module node
        assert "python://empty" in graph.nodes

    def test_syntax_error(self, tmp_path: Path) -> None:
        """Test handling syntax errors."""
        (tmp_path / "broken.py").write_text("""
def bad_syntax(
    print("missing paren"
""")

        graph = GraphStore()
        extractor = PythonExtractor()
        extractor.extract(repo_root=tmp_path, file_path=tmp_path / "broken.py", graph=graph)

        # Should create error node
        assert "python://broken.py" in graph.nodes
        assert graph.nodes["python://broken.py"].type == "file"
        assert "parse_error" in graph.nodes["python://broken.py"].metadata

    def test_nested_functions(self, tmp_path: Path) -> None:
        """Test nested function definitions."""
        (tmp_path / "nested.py").write_text("""
def outer():
    def inner():
        return 1
    return inner()
""")

        graph = GraphStore()
        extractor = PythonExtractor()
        extractor.extract(repo_root=tmp_path, file_path=tmp_path / "nested.py", graph=graph)

        # Should extract outer function
        assert "python://nested:outer" in graph.nodes

        # Inner function handling depends on implementation
        # At minimum, outer should be present

    def test_import_from_parent(self, tmp_path: Path) -> None:
        """Test extracting relative imports."""
        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "__init__.py").write_text("")
        (tmp_path / "pkg" / "submodule.py").write_text("""
from . import __init__
from .. import sibling
""")

        graph = GraphStore()
        extractor = PythonExtractor()
        extractor.extract(repo_root=tmp_path, file_path=tmp_path / "pkg" / "submodule.py", graph=graph)

        # Module should be created
        assert "python://pkg.submodule" in graph.nodes


class TestPythonExtractorResolution:
    """Test symbol resolution."""

    def test_resolves_imported_calls(self, tmp_path: Path) -> None:
        """Test that calls to imported symbols are resolved."""
        (tmp_path / "main.py").write_text("""
from math import sqrt
from os.path import join as path_join

def calculate(x):
    return sqrt(x)

def build_path(*parts):
    return path_join(*parts)
""")

        graph = GraphStore()
        extractor = PythonExtractor()
        extractor.extract(repo_root=tmp_path, file_path=tmp_path / "main.py", graph=graph)

        # Should have imports recorded
        import_edges = [e for e in graph.edges if e.type == "IMPORTS"]
        targets = {e.target for e in import_edges}
        assert "python://math.sqrt" in targets
        assert "python://os.path.join" in targets

    def test_resolves_local_calls(self, tmp_path: Path) -> None:
        """Test that local function calls are resolved."""
        (tmp_path / "locals.py").write_text("""
def utility():
    return 42

def main():
    # This should resolve to local utility
    return utility()
""")

        graph = GraphStore()
        extractor = PythonExtractor()
        extractor.extract(repo_root=tmp_path, file_path=tmp_path / "locals.py", graph=graph)

        # Check that main calls utility
        call_edges = [e for e in graph.edges if e.type == "CALLS"]
        main_calls = [e for e in call_edges if e.source == "python://locals:main"]

        # Should have at least one call to utility
        assert any("utility" in e.target for e in main_calls)
