"""
Saurix Accuracy Harness

Traces a target repository's own test suite at runtime, records the calls that
actually happen, and reports how many of the CALLS Edges Saurix inferred match
one. The result is published as a snapshot, not a gate: the target is a foreign
repository whose suite needs its own dependencies, which is a slow and fragile
thing to hang on every push.

Usage:
    uv run scripts/accuracy.py
    uv run scripts/accuracy.py --commit HEAD
    uv run scripts/accuracy.py --repository pallets/itsdangerous \\
        --url https://github.com/pallets/itsdangerous.git \\
        --commit=<sha> --test-command="-m pytest -q" --out /tmp/accuracy.md
"""

from __future__ import annotations

import argparse
import shlex
from dataclasses import replace
from pathlib import Path

from saurix.accuracy.harness import Target, run_accuracy
from saurix.accuracy.report import render_markdown

# The published target, pinned to a commit so the number it produces can be
# rerun exactly. Click is small, pure Python, and has a suite that exercises
# most of what it ships, which is what makes it a fair thing to measure against.
DEFAULT_TARGET = Target(
    repository="pallets/click",
    url="https://github.com/pallets/click.git",
    commit="874ca2bc1c30d93a4ac6e36a15ed685eafe89097",
    test_command=("-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider"),
    requirements=("-e", ".", "-r", "requirements/tests.txt"),
)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """
    Read the command line. Every field of the published target is overridable,
    so a maintainer can measure a different repository without editing code.
    """
    parser = argparse.ArgumentParser(
        prog="accuracy", description="Saurix accuracy harness"
    )
    parser.add_argument(
        "--repository",
        default=DEFAULT_TARGET.repository,
        help="Slug the report names the target by",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_TARGET.url,
        help="Clone URL of the target (default: the published target)",
    )
    parser.add_argument(
        "--commit",
        default=DEFAULT_TARGET.commit,
        help="Commit of the target to measure (default: the published pin)",
    )
    parser.add_argument(
        "--test-command",
        default=" ".join(DEFAULT_TARGET.test_command),
        help="How to run the target's test suite, as one quoted string",
    )
    parser.add_argument(
        "--requirements",
        default=" ".join(DEFAULT_TARGET.requirements),
        help="What to hand pip in the checkout, as one quoted string",
    )
    parser.add_argument(
        "--python",
        default=None,
        help="Interpreter to run the suite with, instead of building a venv",
    )
    parser.add_argument(
        "--no-install",
        action="store_true",
        help="Do not install anything, which is what --python is for",
    )
    parser.add_argument(
        "--out",
        default="docs/accuracy.md",
        help="Destination path for the markdown report",
    )
    parser.add_argument(
        "--workdir",
        default="tmp/accuracy",
        help="Where the checkout and the virtual environment are kept",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """
    Run the harness and write the report. Returns non-zero on a failed run.
    """
    args = parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    target = replace(
        DEFAULT_TARGET,
        repository=args.repository,
        url=args.url,
        commit=args.commit,
        test_command=tuple(shlex.split(args.test_command)),
        requirements=tuple(shlex.split(args.requirements)),
    )

    comparison = run_accuracy(
        target,
        root / args.workdir,
        interpreter=Path(args.python) if args.python else None,
        install=not args.no_install,
    )
    out = Path(args.out) if Path(args.out).is_absolute() else root / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(comparison), encoding="utf-8")

    precision = comparison.precision
    if precision is None:
        print(
            "Trace failed. Nothing was measured.\n"
            f"{comparison.failure or 'the trace observed no calls'}"
        )
        print(f"\nReport written to {out}")
        return 1

    print(
        f"{target.repository} at {comparison.commit[:12]}: "
        f"{comparison.matched_count} of {comparison.observed_total} observed "
        f"calls matched ({precision * 100:.2f}%)."
    )
    print(f"Report written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
