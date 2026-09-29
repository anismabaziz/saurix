"""
The target repository of the accuracy harness, kept small enough to reason
about exhaustively. Every call it can make at runtime is written down here,
which is what lets the same files serve as the harness fixture and as the
hand-labeled sample.

Four things are worth noticing, because each one lands in a different part of
the report:

- `total` and `label` are called by the tests and resolve to real symbols.
- `indirect` calls `add` through a local variable. The trace sees the call to
  `add`; no static inference can, so it shows up as an observed miss.
- `unused` calls `add` and nothing calls it, so it is an inferred edge the
  trace never sees.
- `multiply` is never called from anywhere.
"""

from calculator.ops import add


def total(values):
    """Return the sum of the first two values."""
    return add(values[0], values[1])


def label(values):
    """Return a human-readable total."""
    return f"total={total(values)}"


def indirect(values):
    """Return the sum of the first two values, reached through a variable."""
    handler = add
    return handler(values[0], values[1])


def unused(values):
    """Return the first value unchanged. No test calls this."""
    return add(values[0], 0)
