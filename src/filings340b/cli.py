"""Command line: rebuild the dataset, check that it is current, or seal small counts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from filings340b.build import stale_outputs, write_outputs
from filings340b.errors import DataError
from filings340b.load import load_filings
from filings340b.seal import seal
from filings340b.sealing import describe_run
from filings340b.textcheck import check_filing, text_file_for
from filings340b.tieout import checks


def _build(root: Path) -> int:
    changed = write_outputs(root)
    print("rebuilt data/: " + (", ".join(changed) if changed else "no file changed"))
    return 0


def _check(root: Path) -> int:
    stale = stale_outputs(root)
    if stale:
        print("data/ is not what the sources rebuild to: " + ", ".join(stale))
        return 1
    print("data/ is byte-identical to a fresh rebuild")
    print(describe_run(root, load_filings(root)))
    return 0


def _tieout(root: Path, only: str | None = None) -> int:
    everyone = load_filings(root)
    print(describe_run(root, everyone))
    for filing in (f for f in everyone if only is None or f.meta.filing_id == only):
        for check in checks(filing, everyone):
            if not check.applicable:
                state = "n/a "
            elif check.passed:
                state = "ok  "
            else:
                state = "DIFF"
            detail = ""
            if check.applicable and not check.passed:
                detail = (
                    f"  filed {check.filed} expected {check.expected} difference {check.difference}"
                )
            print(f"{state} {check.filing_id}  {check.rule}  [{check.basis.value}]{detail}")
    return 0


def _textcheck(root: Path, only: str | None = None) -> int:
    fatal = 0
    everyone = load_filings(root)
    print(describe_run(root, everyone))
    for filing in (f for f in everyone if only is None or f.meta.filing_id == only):
        if filing.source.scanned:
            print(f"scan {filing.meta.filing_id}  no text layer; checked by two image reads")
            continue
        problems = check_filing(filing, text_file_for(root, filing), everyone)
        fatal += sum(1 for p in problems if p.fatal)
        for problem in problems:
            state = "FAIL" if problem.fatal else "note"
            print(f"{state} {problem.filing_id} page {problem.page}: {problem.detail}")
        if not problems:
            print(f"ok   {filing.meta.filing_id}")
    return 1 if fatal else 0


def main(argv: list[str] | None = None) -> int:
    """Run the command line."""
    parser = argparse.ArgumentParser(prog="filings340b", description=__doc__)
    parser.add_argument("command", choices=["build", "check", "tieout", "textcheck", "seal"])
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository folder")
    parser.add_argument("--filing", default=None, help="tieout and textcheck: one filing id")
    args = parser.parse_args(argv)
    try:
        if args.command == "tieout":
            return _tieout(args.root, args.filing)
        if args.command == "textcheck":
            return _textcheck(args.root, args.filing)
        if args.command == "seal":
            print(seal(args.root))
            return 0
        return _build(args.root) if args.command == "build" else _check(args.root)
    except DataError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
