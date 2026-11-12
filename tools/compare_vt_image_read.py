"""Compare Vermont's transcriptions with an independent read of the page images.

Usage:
    python tools/compare_vt_image_read.py <image-read.csv> [--notes NOTES.md] [--apply]

The second reader's file has one line per printed figure row, in printed order:
``image,hospital_as_printed,row,label_as_printed,value_as_printed``. This tool

* stores a normalised copy per filing in ``verification/vt/2025/`` in the layout the
  Rhode Island image reads use (``page,schedule,line,amount,claims,answer``);
* compares every figure with the transcription exactly as printed, apart from the
  ``$`` sign and spaces, so a parenthesis, a minus sign or a ``%`` that differs is a
  difference (the shared comparison in ``imageread.py`` ignores those marks);
* compares the hospital name and each row's label, and reports any that differ;
* with ``--apply``, marks the rows that agree as ``text_and_image``. A row that differs
  is left ``unverified`` and listed. Nothing in a transcription is ever changed.

A text row with no figure (a note printed below the figures) is marked only when its
exact text is found in the reader's notes file.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path

from filings340b.forms import VT_FORM, VT_LINES
from filings340b.imageread import READ_COLUMNS, image_read_file
from filings340b.load import ROW_COLUMNS, load_filings
from filings340b.model import Filing, Verification

READER_COLUMNS = ("image", "hospital_as_printed", "row", "label_as_printed", "value_as_printed")


def _figure(printed: str) -> str:
    """Drop the dollar sign and spaces from a printed value; keep every other mark."""
    return re.sub(r"[$\s]", "", printed)


def _words(text: str) -> str:
    return " ".join(text.split())


Key = tuple[str, str]


def _slug_to_filing(filings: tuple[Filing, ...]) -> dict[str, Filing]:
    """Map the state's document slug (the image name without ``-1.png``) to a filing."""
    out: dict[str, Filing] = {}
    for filing in filings:
        if filing.meta.form == VT_FORM:
            slug = filing.source.cover_page_url.rsplit("/", 1)[-1]
            out[slug] = filing
    return out


def _read_reader_file(path: Path) -> dict[str, list[dict[str, str]]]:
    """Read the second reader's file, grouped by the state's document slug."""
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != READER_COLUMNS:
            raise SystemExit(f"columns must be exactly {', '.join(READER_COLUMNS)}")
        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        for record in reader:
            grouped[record["image"].removesuffix("-1.png")].append(record)
    return grouped


def _store_read(root: Path, filing: Filing, lines: list[dict[str, str]]) -> None:
    """Write the normalised copy of one filing's image read."""
    path = image_read_file(root, filing)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(READ_COLUMNS)
        for (schedule, line, _, _), record in zip(VT_LINES, lines, strict=True):
            writer.writerow([1, schedule, line, _figure(record["value_as_printed"]), "", ""])


def _compare(filing: Filing, lines: list[dict[str, str]], notes_text: str) -> tuple[set[Key], int]:
    """Compare one filing with its image read; return the rows that agree and the count of gaps."""
    fid = filing.meta.filing_id
    agreed: set[Key] = set()
    problems = 0
    if any(_words(r["hospital_as_printed"]) != _words(filing.meta.name_as_filed) for r in lines):
        seen = {r["hospital_as_printed"] for r in lines}
        print(f"NAME {fid}: transcribed {filing.meta.name_as_filed!r}, image read {seen}")
    for (schedule, line, label, _), record in zip(VT_LINES, lines, strict=True):
        row = next(r for r in filing.rows if (r.schedule, r.line) == (schedule, line))
        if _words(record["label_as_printed"]) != _words(row.label_as_filed):
            print(
                f"LABEL {fid} {schedule}.{line}: transcribed {row.label_as_filed!r}, "
                f"image read {record['label_as_printed']!r}"
            )
        if _words(row.label_as_filed) != _words(label):
            print(f"LABEL {fid} {schedule}.{line}: the form lists {label!r}")
        read = record["value_as_printed"]
        if _figure(row.amount_as_filed) == _figure(read):
            agreed.add((schedule, line))
        else:
            problems += 1
            print(
                f"DIFF {fid} {schedule}.{line} ({label}): "
                f"transcription {row.amount_as_filed!r}, image read {read!r}"
            )
    for row in filing.rows:
        if row.schedule != "page_note":
            continue
        if _words(row.label_as_filed) in notes_text:
            agreed.add((row.schedule, row.line))
        else:
            problems += 1
            print(f"DIFF {fid} {row.schedule}.{row.line}: text not found in the notes file")
    return agreed, problems


def _mark(root: Path, filing: Filing, agreed: set[Key]) -> None:
    """Mark the unverified rows that agree; change nothing else."""
    fid = filing.meta.filing_id
    path = root / "transcriptions" / "vt" / str(filing.meta.reporting_year) / f"{fid}.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        stored = list(csv.DictReader(handle))
    for record in stored:
        key = (record["schedule"], record["line"])
        if record["verification"] == Verification.UNVERIFIED.value and key in agreed:
            record["verification"] = Verification.TEXT_AND_IMAGE.value
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ROW_COLUMNS), lineterminator="\n")
        writer.writeheader()
        writer.writerows(stored)


def main() -> int:
    """Run from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image_read", type=Path)
    parser.add_argument("--notes", type=Path, default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root: Path = args.root
    by_slug = _slug_to_filing(load_filings(root))
    grouped = _read_reader_file(args.image_read)
    notes_text = _words(args.notes.read_text(encoding="utf-8")) if args.notes else ""
    problems = 0
    for slug, filing in sorted(by_slug.items(), key=lambda item: item[1].meta.filing_id):
        lines = grouped.get(slug, [])
        if len(lines) != len(VT_LINES):
            print(f"DIFF {filing.meta.filing_id}: {len(lines)} rows read, {len(VT_LINES)} expected")
            problems += 1
            continue
        _store_read(root, filing, lines)
        agreed, gaps = _compare(filing, lines, notes_text)
        problems += gaps
        print(f"{filing.meta.filing_id}: {len(agreed)} of {len(filing.rows)} rows agree")
        if args.apply:
            _mark(root, filing, agreed)
    print(f"{problems} differences")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
