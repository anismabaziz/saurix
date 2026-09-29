"""
Tests for the accuracy harness.

The harness is exercised at the seams a user touches: the report it prints and
the command that produces it. A fixture repository small enough to check by
hand is committed under `tests/fixtures/accuracy_target`, its expected trace is
written out in that directory's README, and every assertion is about what a
reader of the report would see. What the tracer does internally is deliberately
not asserted; it runs for real against the fixture, and a fake would only prove
the fake agrees with itself.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from saurix.accuracy.harness import Target, run_accuracy
from saurix.accuracy.matching import Comparison
from saurix.accuracy.report import render_markdown

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "accuracy_target"

# The fixture's suite is unittest so that the harness needs nothing installed to
# run it. The interpreter is prepended by the harness.
TEST_COMMAND = ("-m", "unittest", "discover", "-s", "tests")

# A command that succeeds without running anything, which is what a trace that
# never reached the repository looks like from the outside.
SILENT_COMMAND = ("-c", "pass")

# A suite that fails, which is the other way a run produces no ground truth.
FAILING_SOURCE = """
import unittest


class BrokenTest(unittest.TestCase):
    def test_that_fails(self):
        self.assertEqual(1, 2)
"""


def _commit(directory: Path, message: str = "fixture") -> str:
    """
    Commit a directory and return the commit it landed on.

    The harness is given a commit to pin to, so the fixture has to be a real
    repository with a real commit rather than a directory on disk.
    """
    for command in (
        ["git", "init", "--quiet"],
        ["git", "add", "--all"],
        [
            "git",
            "-c",
            "user.name=fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--quiet",
            "--message",
            message,
        ],
    ):
        subprocess.run(command, cwd=directory, check=True, capture_output=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=directory,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _origin(workdir: Path, name: str = "origin") -> tuple[Path, str]:
    """
    Copy the fixture into a repository the harness can clone.
    """
    source = workdir / name
    shutil.copytree(FIXTURE, source)
    return source, _commit(source)


def _flat(text: str) -> str:
    """
    Collapse the report's line wrapping, so a prose assertion is about what the
    report says rather than where it happens to break.
    """
    return " ".join(text.split())


def _accuracy_command() -> ModuleType:
    """
    Import the accuracy command, which lives in scripts/ and is not a package.
    """
    path = REPO_ROOT / "scripts" / "accuracy.py"
    spec = importlib.util.spec_from_file_location("accuracy_command", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def accuracy() -> ModuleType:
    """
    The command a user runs to regenerate the report.
    """
    return _accuracy_command()


@pytest.fixture(scope="session")
def origin(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str]:
    """
    One repository built from the committed fixture, shared by every measured
    run so that two runs of the harness are measured at the same commit.
    """
    return _origin(tmp_path_factory.mktemp("origin"))


def _target(origin: tuple[Path, str], test_command: tuple[str, ...]) -> Target:
    """
    Point the harness at the shared fixture repository.
    """
    path, commit = origin
    return Target(
        repository="fixture/target",
        url=str(path),
        commit=commit,
        test_command=test_command,
    )


@pytest.fixture(scope="module")
def measured(
    origin: tuple[Path, str], tmp_path_factory: pytest.TempPathFactory
) -> tuple[str, str]:
    """
    One measured run of the harness against the committed fixture: the report
    it rendered, and the commit it measured.
    """
    workdir = tmp_path_factory.mktemp("accuracy")
    comparison = run_accuracy(
        _target(origin, TEST_COMMAND),
        workdir,
        interpreter=Path(sys.executable),
        install=False,
    )
    return render_markdown(comparison), comparison.commit


@pytest.fixture(scope="module")
def report(measured: tuple[str, str]) -> str:
    """
    The rendered report of the measured run.
    """
    return measured[0]


class TestReportOnAMeasuredRun:
    """
    What a reader of the published report is entitled to find in it.
    """

    def test_it_reports_precision_on_observed_edges(self, report: str) -> None:
        """
        The figure is the share of observed calls that were also inferred.
        """
        assert "5 of 6 observed calls were also inferred as Edges" in _flat(report)
        assert "83.33%" in report

    def test_it_names_the_pinned_commit(
        self, report: str, measured: tuple[str, str]
    ) -> None:
        """
        The result is tied to the commit it was measured at, so it can be rerun.
        """
        commit = measured[1]
        assert len(commit) == 40
        assert f"`{commit[:12]}`" in report

    def test_it_states_that_recall_is_not_claimed(self, report: str) -> None:
        """
        The report says what it does not measure, and why.
        """
        flat = _flat(report)
        assert "Recall is not measured here and none is claimed" in flat
        assert "did not execute" in flat

    def test_it_surfaces_the_observed_call_it_missed(self, report: str) -> None:
        """
        A call that happened and the graph does not hold is named, not dropped.
        """
        assert "| `calculator.report:indirect` | `calculator.ops:add` |" in report, (
            "the call through a function pointer should be listed as a miss"
        )

    def test_it_surfaces_the_inferred_edge_the_trace_never_saw(
        self, report: str
    ) -> None:
        """
        An inferred edge with no observed call behind it is named, not dropped.
        """
        assert "| `calculator.report:unused` | `calculator.ops:add` |" in report
        assert "Inferred edges the trace never saw" in report

    def test_it_says_which_defect_produced_the_misses(self, report: str) -> None:
        """
        A miss is a call the pipeline could not name, one that dynamic dispatch
        moved to a subclass, or one the pipeline never saw, and the report says
        which is which.
        """
        flat = _flat(report)
        assert "recorded the call but could not name its target (1)" in flat
        assert "landed on a method a subclass overrides (0)" in flat
        assert "recorded no call for the caller at all (0)" in flat


class TestReportOnAFailedRun:
    """
    A run that could not be measured must never read as a good result.
    """

    @pytest.fixture(scope="class")
    def failing_report(self, tmp_path_factory: pytest.TempPathFactory) -> str:
        """
        A fixture whose test suite fails.
        """
        workdir = tmp_path_factory.mktemp("failing")
        origin, _ = _origin(workdir)
        (origin / "tests" / "test_broken.py").write_text(FAILING_SOURCE)
        commit = _commit(origin, message="break the suite")
        target = Target(
            repository="fixture/target",
            url=str(origin),
            commit=commit,
            test_command=TEST_COMMAND,
        )
        return render_markdown(
            run_accuracy(
                target, workdir, interpreter=Path(sys.executable), install=False
            )
        )

    def test_a_failing_suite_reports_a_failure(self, failing_report: str) -> None:
        """
        The report says the run failed and shows why.
        """
        assert "## This run failed" in failing_report
        assert "exited 1" in failing_report

    def test_a_failing_suite_reports_no_figure(self, failing_report: str) -> None:
        """
        A failed run publishes no precision, rather than a flattering one.
        """
        assert "not measured" in failing_report
        assert "observed calls were also inferred" not in failing_report

    def test_a_silent_run_is_a_failure_not_a_perfect_score(
        self, origin: tuple[Path, str], tmp_path: Path
    ) -> None:
        """
        A suite that runs but traces nothing is a failed measurement.
        """
        report = render_markdown(
            run_accuracy(
                _target(origin, SILENT_COMMAND),
                tmp_path / "silent",
                interpreter=Path(sys.executable),
                install=False,
            )
        )
        assert "## This run failed" in report
        assert "100.00%" not in report


class TestTheHandLabeledTrace:
    """
    The fixture's README tabulates the six calls it should produce. The report
    states how many matched, but it does not print the five that did, so this
    is the one claim the report cannot make on its own: a tracer that stopped
    recording calls made from test files would leave the figure untouched.
    """

    @pytest.fixture(scope="class")
    def comparison(
        self, origin: tuple[Path, str], tmp_path_factory: pytest.TempPathFactory
    ) -> Comparison:
        """
        The comparison behind the report, for the one claim the report omits.
        """
        return run_accuracy(
            _target(origin, TEST_COMMAND),
            tmp_path_factory.mktemp("accuracy-object"),
            interpreter=Path(sys.executable),
            install=False,
        )

    def test_every_matched_call_really_happened(self, comparison: Comparison) -> None:
        """
        The matched pairs are exactly the five calls the README lists.
        """
        assert [call.render() for call, _ in comparison.matched] == [
            "calculator.report:label -> calculator.report:total",
            "calculator.report:total -> calculator.ops:add",
            "tests.test_report:ReportTest.test_indirect -> calculator.report:indirect",
            "tests.test_report:ReportTest.test_label -> calculator.report:label",
            "tests.test_report:ReportTest.test_total -> calculator.report:total",
        ]


class TestTheCommandSurface:
    """
    One command regenerates the report, so that is what the test runs.
    """

    @pytest.fixture(scope="class")
    def written(
        self,
        accuracy: ModuleType,
        origin: tuple[Path, str],
        tmp_path_factory: pytest.TempPathFactory,
    ) -> Path:
        """
        Run `scripts/accuracy.py` against the fixture and return where it wrote.
        """
        workdir = tmp_path_factory.mktemp("command")
        url, commit = origin
        out = workdir / "accuracy.md"
        status = accuracy.main(
            [
                "--repository",
                "fixture/target",
                "--url",
                str(url),
                "--commit",
                commit,
                f"--test-command={' '.join(TEST_COMMAND)}",
                "--python",
                sys.executable,
                "--no-install",
                "--workdir",
                str(workdir / "run"),
                "--out",
                str(out),
            ]
        )
        assert status == 0, "the command should have measured the fixture"
        return out

    def test_the_command_writes_the_report(self, written: Path, report: str) -> None:
        """
        What the command writes is the report, unchanged.
        """
        assert written.read_text(encoding="utf-8") == report

    def test_the_command_fails_when_the_suite_does(
        self,
        accuracy: ModuleType,
        tmp_path_factory: pytest.TempPathFactory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """
        A run that could not be measured exits non-zero rather than reporting a
        figure nobody should believe.
        """
        workdir = tmp_path_factory.mktemp("command-failing")
        url, commit = _origin(workdir)
        status = accuracy.main(
            [
                "--repository",
                "fixture/target",
                "--url",
                str(url),
                "--commit",
                commit,
                f"--test-command={' '.join(SILENT_COMMAND)}",
                "--python",
                sys.executable,
                "--no-install",
                "--workdir",
                str(workdir / "run"),
                "--out",
                str(workdir / "accuracy.md"),
            ]
        )
        assert status == 1
        assert "Nothing was measured" in capsys.readouterr().out
