"""
Saurix package.
"""

from importlib.metadata import PackageNotFoundError, version

__all__ = ["__version__"]


def _version() -> str:
    """
    Return the version the packaging metadata declares.

    An installed Saurix answers from its own metadata, so there is no second copy
    to fall out of step with PyPI. A source checkout with no install falls back to
    the `pyproject.toml` beside it, which is the same file the install reads.
    """
    try:
        return version("saurix")
    except PackageNotFoundError:
        import tomllib
        from pathlib import Path

        pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
        metadata = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        return str(metadata["project"]["version"])


__version__ = _version()
