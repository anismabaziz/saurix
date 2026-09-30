"""
Tests for the hand-labeled sample.

A runtime trace can only judge the paths a test suite executes. The sample
covers the rest: a region of the target repository nobody runs, labeled by
hand, so the report can say what the pipeline infers there. Every assertion
here is about the rendered report or the loader a maintainer edits by hand. The
matching is exact on purpose, so no fuzzy credit can lift the figure.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

from saurix.accuracy.harness import Measurement, run_accuracy
from saurix.accuracy.labels import (
    InferredInRegion,
    SampleCheck,
    compare_sample,
    load_sample,
)
from saurix.accuracy.matching import Comparison
from saurix.accuracy.report import render_markdown
from saurix.core.indexing import build_graph
from tests.test_accuracy import TEST_COMMAND, _origin, _target

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "accuracy_target"

# The published sample, quoted by docs/accuracy.md.
PUBLISHED_SAMPLE = REPO_ROOT / "docs" / "accuracy" / "click-examples.labels"

# Every call `calculator/report.py` makes, written the way the graph names it.
# `indirect` really does reach `add`, through a variable the pipeline cannot
# follow, and nothing calls `unused`. Together they are the two mistakes a hand
# label finds and a trace never sees, because the suite runs neither path.
FIXTURE_LABELS = """\
    # Every call `calculator/report.py` makes.
    calculator/report.py:total -> calculator.ops.add
    calculator/report.py:label -> calculator.report:total
    calculator/report.py:indirect -> calculator.ops.add
    calculator/report.py:unused -> calculator.ops.add
"""


def _flat(text: str) -> str:
    """
    Collapse the report's line wrapping, so a prose assertion is about what the
    report says rather than where it happens to break.
    """
    return " ".join(text.split())


def _write_labels(directory: Path, body: str) -> Path:
    """
    Write a label file and return its path.
    """
    path = directory / "sample.labels"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def fixture_graph():
    """
    The graph of the committed fixture, indexed for real.
    """
    return build_graph(FIXTURE).graph


@pytest.fixture(scope="module")
def sample_check(tmp_path_factory: pytest.TempPathFactory, fixture_graph):
    """
    The fixture's hand-labeled sample, checked against the fixture's graph.
    """
    path = _write_labels(tmp_path_factory.mktemp("labels"), FIXTURE_LABELS)
    return compare_sample(load_sample(path), fixture_graph)


class TestTheLoader:
    """
    A label file is written by hand, so the loader is strict about what it
    accepts and forgiving about how it is spaced.
    """

    def test_it_reads_every_label(self, tmp_path: Path) -> None:
        """
        One line is one edge, and all of them are read.
        """
        sample = load_sample(_write_labels(tmp_path, FIXTURE_LABELS))
        assert len(sample.labels) == 4
        assert sample.path.name == "sample.labels"

    def test_it_ignores_comments_and_blank_lines(self, tmp_path: Path) -> None:
        """
        A hand-written file is annotated, and the notes are not edges.
        """
        sample = load_sample(
            _write_labels(
                tmp_path,
                """
                # A comment.

                calculator/report.py:total -> calculator.ops.add

                # Another comment.
                calculator/report.py:label -> calculator.report.total
                """,
            )
        )
        assert len(sample.labels) == 2

    def test_it_rejects_a_line_it_cannot_read(self, tmp_path: Path) -> None:
        """
        A malformed line is refused by name and line, rather than dropped.
        """
        path = _write_labels(
            tmp_path, "calculator/report.py:total calculator.ops.add\n"
        )
        with pytest.raises(ValueError, match="sample.labels:1"):
            load_sample(path)

    def test_it_rejects_a_label_without_a_caller(self, tmp_path: Path) -> None:
        """
        An edge needs both ends named.
        """
        path = _write_labels(tmp_path, "calculator.ops.add\n")
        with pytest.raises(ValueError, match="sample.labels:1"):
            load_sample(path)

    def test_a_label_is_read_the_way_the_graph_names_it(self, tmp_path: Path) -> None:
        """
        The caller is a file and a qualified name, the callee the target the
        graph writes, so a label can be checked against both the graph and the
        source it was read from.
        """
        sample = load_sample(_write_labels(tmp_path, FIXTURE_LABELS))
        first = sample.labels[0]
        assert first.caller_file == "calculator/report.py"
        assert first.caller_qualname == "total"
        assert first.callee == "calculator.ops.add"
        assert first.render() == (
            "`calculator/report.py:total` -> `calculator.ops.add`"
        )

    def test_a_label_names_the_file_it_came_from(self, tmp_path: Path) -> None:
        """
        Every edge in one file shares it, which is how a region is described.
        """
        sample = load_sample(_write_labels(tmp_path, FIXTURE_LABELS))
        assert sample.files == ("calculator/report.py",)


class TestTheSampleCheck:
    """
    Precision over a labeled region: the share of the edges the pipeline
    inferred there that a person confirmed by reading the code.
    """

    def test_it_reports_the_share_of_confirmed_edges(self, sample_check) -> None:
        """
        Three of the four edges the pipeline inferred in the region are real.
        """
        assert sample_check.inferred_in_region == 4
        assert len(sample_check.confirmed) == 3
        assert sample_check.precision == pytest.approx(0.75)

    def test_it_names_the_edge_the_pipeline_got_wrong(self, sample_check) -> None:
        """
        The call through a variable is recorded against a target nothing
        defines, so it earns no credit and is shown rather than dropped.
        """
        rendered = [edge.render() for edge in sample_check.unconfirmed]
        assert "`calculator/report.py:indirect` -> `handler`" in " ".join(rendered)

    def test_it_names_the_call_the_pipeline_missed(self, sample_check) -> None:
        """
        `indirect` really does reach `add`. A label the graph does not hold is
        listed too, because a reader is owed the other direction as well.
        """
        rendered = [label.render() for label in sample_check.missing]
        assert "`calculator/report.py:indirect` -> `calculator.ops.add`" in rendered

    def test_it_judges_only_calls_made_from_the_labeled_files(
        self, sample_check
    ) -> None:
        """
        The region is a set of files, and only calls made from those files are
        judged. A call from the test suite into the region is outside the claim.
        """
        judged = list(sample_check.confirmed) + list(sample_check.unconfirmed)
        assert judged
        assert all(edge.caller_file == "calculator/report.py" for edge in judged)


class TestThePublishedSample:
    """
    The sample behind the published figure is committed, and it covers a region
    the target's own test suite never reaches.
    """

    def test_it_is_committed(self) -> None:
        """
        The report quotes a figure, and the labels behind it are in the tree.
        """
        assert PUBLISHED_SAMPLE.exists(), (
            "the published report quotes a hand-labeled sample, so the sample "
            "has to be committed next to it"
        )

    def test_it_labels_a_region_the_suite_never_runs(self) -> None:
        """
        Every labeled file sits under `examples/`, which click's test suite
        never imports. If that stopped being true the sample would measure
        something the trace already measures, and the two figures would overlap.

        The published trace run confirms it directly: none of its 2518 observed
        calls names a module under `examples`.
        """
        sample = load_sample(PUBLISHED_SAMPLE)
        assert sample.files
        assert all(f.startswith("examples/") for f in sample.files)

    def test_it_states_its_method_in_the_file(self) -> None:
        """
        A reader auditing the figure needs the method without leaving the file.
        """
        header = PUBLISHED_SAMPLE.read_text(encoding="utf-8").split("\n\n")[0]
        assert "Method" in header

    def test_the_published_report_still_matches_the_sample(self) -> None:
        """
        The committed report is not regenerated by the test suite: doing so needs
        a network clone of the target. What can be checked offline is that it
        has not drifted from the sample, which is the part a maintainer edits by
        hand. A label added, removed, or renamed without regenerating the report
        fails here.
        """
        report = (REPO_ROOT / "docs" / "accuracy.md").read_text(encoding="utf-8")
        sample = load_sample(PUBLISHED_SAMPLE)
        flat = _flat(report)

        assert f"holding {len(sample.labels)} hand-labeled edges" in flat
        assert str(len(sample.files)) + " files of the target" in flat
        for name in sample.files:
            assert name in report, f"{name} is labeled but absent from the report"

    def test_the_published_report_keeps_the_two_figures_apart(self) -> None:
        """
        The committed report states both figures and says they are not combined.
        A hand edit that drops the second, or blends the two, fails here.
        """
        report = (REPO_ROOT / "docs" / "accuracy.md").read_text(encoding="utf-8")
        assert "### Precision on observed calls" in report
        assert "### Precision on the hand-labeled sample" in report
        assert "The two figures are not combined" in _flat(report)


class TestThePublishedReport:
    """
    What a reader of the report is entitled to find in it.
    """

    @pytest.fixture(scope="class")
    def report(self, tmp_path_factory: pytest.TempPathFactory) -> str:
        """
        A report rendered from a real measured run and a real sample, so the
        assertions below are about prose a reader actually reads.
        """
        workdir = tmp_path_factory.mktemp("published-report")
        origin = _origin(workdir)
        measurement = run_accuracy(
            _target(origin, TEST_COMMAND),
            workdir / "run",
            interpreter=Path(sys.executable),
            install=False,
            labels=_write_labels(workdir, FIXTURE_LABELS),
        )
        return render_markdown(measurement)

    def test_it_leads_with_the_figure_and_the_commit(self, report: str) -> None:
        """
        The number and the commit it was measured at come before the method, so
        a reader knows what is claimed before being told how it was measured.
        """
        head = report.split("## Method")[0]
        assert "Precision on observed calls" in head
        assert "5 of 6 observed calls" in _flat(head)

    def test_it_reports_the_two_figures_apart(self, report: str) -> None:
        """
        Precision on the trace and precision on the sample are claims about two
        different populations. The report says so and never adds them up.
        """
        flat = _flat(report)
        assert "Precision on observed calls" in flat
        assert "Precision on the hand-labeled sample" in flat
        assert "not combined" in flat
        assert "83.33%" in flat
        assert "75.00%" in flat

    def test_it_states_the_size_and_method_of_the_sample(self, report: str) -> None:
        """
        A reader can judge the weight of the second figure from what it covers.
        """
        flat = _flat(report)
        assert "1 file" in flat
        assert "4 hand-labeled edges" in flat
        assert "no test in the suite executes" in flat

    def test_it_says_recall_is_not_measured(self, report: str) -> None:
        """
        What the figures do not cover is said outright.
        """
        assert "Recall is not measured here and none is claimed" in _flat(report)

    def test_it_names_the_weakest_languages_and_call_shapes(self, report: str) -> None:
        """
        A reader learns where the tool is wrong, not only how often.
        """
        flat = _flat(report)
        assert "Only Python is traced" in flat
        assert "Go, Java and TypeScript" in flat
        assert "A call through a variable" in flat

    def _measured_with_sample(self, sample_check) -> Measurement:
        """
        A measurement carrying a real sample check, for the prose assertions
        below. The trace side is a stand-in: what these assertions are about is
        the sample section's wording.
        """
        return Measurement(
            comparison=Comparison(
                repository="fixture/target",
                commit="a" * 40,
                test_command="-m unittest",
                observed_total=6,
                matched=(),
                inferred_total=4,
            ),
            sample=sample_check,
        )

    def test_it_says_it_is_a_snapshot_and_not_a_gate(self, report: str) -> None:
        """
        The report says what it is, and what would have to change for it to
        become something that fails a build.
        """
        flat = _flat(report)
        assert "published snapshot" in flat
        assert "scheduled" in flat

    def test_it_says_so_when_there_is_no_sample(self) -> None:
        """
        A run with no hand-labeled sample reports one figure and says the
        second is missing, rather than quietly omitting it.
        """
        report = render_markdown(
            Measurement(
                comparison=Comparison(
                    repository="fixture/target",
                    commit="a" * 40,
                    test_command="-m unittest",
                    observed_total=6,
                    matched=(),
                    inferred_total=4,
                )
            )
        )
        assert "No hand-labeled sample was supplied" in _flat(report)
        assert "Precision on the hand-labeled sample" not in report

    def test_it_says_when_the_sample_edges_were_never_resolved(
        self, sample_check
    ) -> None:
        """
        A region of example code is mostly calls to a library the repository
        does not define, so most sample edges are recorded against a name
        nothing defines. A figure over those says the calls were found, not that
        their targets were resolved, and the report has to say which it is.
        """
        flat = _flat(render_markdown(self._measured_with_sample(sample_check)))
        # The fixture resolves some of its callees, so this takes the partial
        # branch. The disclosure paragraph is what matters either way.
        assert (
            f"{sample_check.unresolved_in_region} of the "
            f"{sample_check.inferred_in_region} point at a name the graph "
            "does not define"
        ) in flat
        assert "It says nothing about whether the target would have been" in flat

    def test_it_says_so_even_when_every_edge_is_unresolved(self) -> None:
        """
        The whole region unresolved is the common case, and the report has to
        say it just as plainly rather than hiding it inside a ratio.
        """
        unresolved = tuple(
            InferredInRegion(
                caller_file="pkg/mod.py",
                caller_qualname="handler",
                callee="outside.helper",
            )
            for _ in range(3)
        )
        check = SampleCheck(confirmed=unresolved, unconfirmed=(), missing=())
        flat = _flat(render_markdown(self._measured_with_sample(check)))
        assert "None of the 3 is resolved" in flat
