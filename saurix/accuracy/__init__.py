"""
Accuracy measurement: runtime truth against inferred Edges.

The package exists to answer one question honestly: of the calls a repository
really makes, how many did the Indexing pipeline infer? It says nothing about
recall, because a trace cannot see the paths no test executes.
"""

from __future__ import annotations

from .matching import Comparison, InferredEdge, ObservedCall, compare, symbol_key
from .report import render_markdown

__all__ = [
    "Comparison",
    "InferredEdge",
    "ObservedCall",
    "compare",
    "render_markdown",
    "symbol_key",
]
