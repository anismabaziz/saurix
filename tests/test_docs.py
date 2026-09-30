"""
Tests that keep the documentation honest.

Two properties are enforced here. First, no committed document may name a
module or file path that does not exist: that is the rot that silently creeps
in when a refactor renames a module and nobody re-reads the prose. Second, the
generated MCP demo and the agent-lifecycle walkthrough are reproduced from a
live run of the server, so the identifiers a reader copies are real.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Committed prose. AGENTS.md and CONTEXT.md are local planning artifacts, and
# .plan/ is never committed, so neither takes part in the check.
DOC_FILES = [
    "README.md",
    "demo-mcp.md",
    "docs/agent-lifecycle.md",
    "docs/architecture.md",
    "docs/benchmarks.md",
]

# The two documents a live MCP run writes, as repository-relative paths.
GENERATED_DOCS = ["demo-mcp.md", "docs/agent-lifecycle.md"]

GENERATOR_PATH = REPO_ROOT / "scripts" / "generate_mcp_demo.py"

# Backticked spans are how these documents mark up code, so they are the only
# place a prose module path can hide.
BACKTICKED = re.compile(r"`([^`\n]+)`")
# `saurix/core/indexing` and `saurix.core.indexing` both name a module.
MODULE_REF = re.compile(r"^saurix(?:[./][A-Za-z0-9_]+)+$")
# Paths under a directory this project owns. Deliberately narrow: documents
# also name foreign repositories (`pallets/flask`) and URLs.
PROJECT_PATH = re.compile(r"^(?:saurix|scripts|tests|docs|main\.py)/[A-Za-z0-9_./-]+$")
# The generated documents quote real tool responses; every `file` in one of
# them is a path the graph reported, so it has to exist.
RESPONSE_FILE = re.compile(r'"file":\s*"([^"\n]+)"')


@dataclass(frozen=True)
class GeneratedDocs:
    """
    Two independent generations of the documentation, plus the generator.

    The second generation exists so the determinism check costs one extra run
    instead of a full extra fixture.
    """

    first: dict[str, str]
    second: dict[str, str]


def _load_generator() -> ModuleType:
    """
    Import the doc generator, which lives in scripts/ and is not a package.
    """
    spec = importlib.util.spec_from_file_location("generate_mcp_demo", GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _candidates(ref: str) -> list[Path]:
    """
    Paths a `saurix...` reference could be pointing at, in lookup order.

    A dotted reference is a module path (`saurix.core.graph`), a slashed one is
    a file or package path (`saurix/core/graph.py`), and a plain name like
    `saurix.html` is a generated artifact sitting at the repository root.
    """
    candidates = [REPO_ROOT / ref]
    if "/" not in ref:
        module = ref.replace(".", "/")
        candidates += [REPO_ROOT / module, REPO_ROOT / f"{module}.py"]
    return candidates


def _is_ignored(path: Path) -> bool:
    """
    Report whether git ignores a path, which makes it a generated artifact.
    """
    return (
        subprocess.run(
            ["git", "check-ignore", "-q", str(path.relative_to(REPO_ROOT))],
            cwd=REPO_ROOT,
            capture_output=True,
        ).returncode
        == 0
    )


def _reference_is_broken(ref: str) -> bool:
    """
    Report whether a reference names nothing that exists in the repository.

    Generated artifacts such as the graph and visualizer output are exempt: they
    are gitignored and only exist once a command has run.
    """
    candidates = _candidates(ref)
    if any(candidate.exists() for candidate in candidates):
        return False
    return not _is_ignored(candidates[0])


def _doc_references(markdown: str) -> set[str]:
    """
    Collect the module and project path references a document makes.

    Three shapes, three sources: a module named in backticks, a path under a
    project directory named in backticks, and a file path quoted inside a
    captured tool response.
    """
    backticked = set(BACKTICKED.findall(markdown))
    return {
        span
        for span in backticked
        if MODULE_REF.match(span) or PROJECT_PATH.match(span)
    } | set(RESPONSE_FILE.findall(markdown))


def _body(markdown: str, generator: ModuleType) -> str:
    """
    Compare documents without the provenance block, which tracks the commit.
    """
    return generator.strip_provenance(markdown)


@pytest.fixture(scope="session")
def generator() -> ModuleType:
    """
    Provide the doc generator module.
    """
    return _load_generator()


@pytest.fixture(scope="session")
def generated(generator: ModuleType) -> GeneratedDocs:
    """
    Generate the documentation twice from live MCP runs.
    """
    return GeneratedDocs(generator.generate_docs(), generator.generate_docs())


class TestDocReferencesResolve:
    """
    Every module path a document names must still exist.
    """

    @pytest.mark.parametrize("doc", DOC_FILES)
    def test_module_references_exist(self, doc: str) -> None:
        """
        The document names only modules and files present in the repository.
        """
        markdown = (REPO_ROOT / doc).read_text()
        broken = sorted(
            ref for ref in _doc_references(markdown) if _reference_is_broken(ref)
        )
        assert not broken, f"{doc} references paths that do not exist: {broken}"


class TestGeneratedDocs:
    """
    The generated documents match a fresh generation from the current code.

    The provenance block is compared separately: it carries the commit, which
    moves on every commit, so folding it into the freshness check would report
    rot on a clean tree.
    """

    def test_demo_is_up_to_date(self, generated: GeneratedDocs, generator) -> None:
        """
        demo-mcp.md matches what the script produces right now.
        """
        assert _body(generated.first["demo-mcp.md"], generator) == _body(
            (REPO_ROOT / "demo-mcp.md").read_text(), generator
        )

    def test_lifecycle_is_up_to_date(self, generated: GeneratedDocs, generator) -> None:
        """
        docs/agent-lifecycle.md matches what the script produces right now.
        """
        assert _body(generated.first["docs/agent-lifecycle.md"], generator) == _body(
            (REPO_ROOT / "docs" / "agent-lifecycle.md").read_text(), generator
        )

    def test_generation_is_deterministic(self, generated: GeneratedDocs) -> None:
        """
        Two runs against unchanged code produce byte-identical documents.
        """
        assert generated.first == generated.second

    @pytest.mark.parametrize("doc", GENERATED_DOCS)
    def test_committed_doc_records_provenance(
        self, doc: str, generator: ModuleType
    ) -> None:
        """
        The committed document names this repository, and a commit that exists.

        Checked on the committed file, not on a fresh generation, so a stale or
        hand-edited header cannot slip through.
        """
        markdown = (REPO_ROOT / doc).read_text()
        slug, commit = re.search(
            r"Indexed repository: `([^`]+)`.*\n.*Indexed commit: `([0-9a-f]{7,40})`",
            markdown,
        ).groups()
        assert slug == generator.repo_identity(".")[0]
        assert (
            subprocess.run(
                ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
                cwd=REPO_ROOT,
                capture_output=True,
            ).returncode
            == 0
        ), f"{doc} names a commit that is not in this repository"

    @pytest.mark.parametrize("doc", GENERATED_DOCS)
    def test_no_call_came_back_as_an_error(
        self, generated: GeneratedDocs, doc: str
    ) -> None:
        """
        Every recorded tool call returned ok, in both documents.
        """
        assert '"ok": false' not in generated.first[doc]
