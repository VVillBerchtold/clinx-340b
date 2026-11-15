"""Compare Idaho's transcription with an independent read of the page images.

Usage:
    python tools/compare_id_image_read.py <cells.csv> [--notes NOTES.md] [--apply]

The second reader sees only the page pictures and writes one line per printed cell:
``page,block,row,column,value`` (``block`` is the heading above a table, a tile panel or
a chart; a tile or a chart label has no ``column``; the labels of a chart's value axis
are lines whose ``row`` is ``axis``). The reader also types out the running text of
every page into a notes file. This tool

* finds, for every row of the transcription, the reader's cell on the same page with
  the same row label and column heading, and compares the two exactly as printed,
  apart from the ``$`` sign and spaces;
* stores a normalised copy in ``verification/id/<year>/`` in the layout the other
  image reads use (``page,schedule,line,amount,claims,answer``);
* reports every cell the reader typed that no row carries;
* with ``--apply``, marks the rows that agree as ``text_and_image``. A row that differs
  is left ``unverified`` and listed. Nothing in a transcription is ever changed.

One printed cell, ``62 (100%)``, is two rows of the transcription (a count and a
percentage); it agrees when the two rows put back together read as the cell does.

A text row with no figure (a sentence the report prints, a chart's title, the labels of
its value axis) is marked only when its exact text is found in the reader's notes file,
is a heading the reader gave for a block on that page, or is the reader's axis labels
on that page, top to bottom, joined with spaces.
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

from filings340b.forms import ID_CELLS, ID_FORM, ID_NOTE_SCHEDULE, NO_FIGURE
from filings340b.imageread import READ_COLUMNS, image_read_file
from filings340b.load import ROW_COLUMNS, load_filings
from filings340b.model import Filing, Row, Verification

READER_COLUMNS = ("page", "block", "row", "column", "value")
AXIS = "axis"
# The one cell that holds a count and a percentage: "62 (100%)".
_COUNT_AND_SHARE = re.compile(r"^(\d[\d,]*) \((\d+(?:\.\d+)?%)\)$")

Key = tuple[str, str]
Cell = dict[str, str]


def _figure(printed: str) -> str:
    """Drop the dollar sign and spaces from a printed value; keep every other mark."""
    return re.sub(r"[$\s]", "", printed)


def _words(text: str) -> str:
    return " ".join(text.split())


def _read_reader_file(path: Path) -> list[Cell]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != READER_COLUMNS:
            raise SystemExit(f"columns must be exactly {', '.join(READER_COLUMNS)}")
        return list(reader)


def _take(cells: list[Cell], used: set[int], page: int, label: str, column: str) -> Cell | None:
    """Return the first unused cell on a page with this row label and column heading."""
    for number, cell in enumerate(cells):
        if number in used or cell["page"].strip() != str(page):
            continue
        if (_words(cell["row"]), _words(cell["column"])) == (label, column):
            used.add(number)
            return cell
    return None


def _match(filing: Filing, cells: list[Cell]) -> tuple[dict[Key, str], set[int]]:
    """Pair each figure or text row with what the reader typed for its cell."""
    rows = {(r.schedule, r.line): r for r in filing.rows}
    used: set[int] = set()
    seen: dict[Key, str] = {}
    shared: dict[tuple[str, str, str], Cell | None] = {}
    for schedule, line, label, column, _ in ID_CELLS:
        row = rows.get((schedule, line))
        if row is None:
            continue
        cell_key = (schedule, label, column)
        twice = sum(1 for s, _, lb, c, _ in ID_CELLS if (s, lb, c) == cell_key) > 1
        if twice:
            if cell_key not in shared:
                shared[cell_key] = _take(cells, used, row.page, label, column)
            cell = shared[cell_key]
            if cell is not None:
                parts = _COUNT_AND_SHARE.match(_words(cell["value"]))
                position = 0 if line.endswith("_count") else 1
                seen[(schedule, line)] = parts.groups()[position] if parts else cell["value"]
            continue
        cell = _take(cells, used, row.page, label, column)
        if cell is not None:
            seen[(schedule, line)] = cell["value"]
    return seen, used


def _note_agrees(row: Row, cells: list[Cell], notes_text: str) -> bool:
    text = _words(row.label_as_filed)
    on_page = [c for c in cells if c["page"].strip() == str(row.page)]
    axis = " ".join(_words(c["value"]) for c in on_page if _words(c["row"]) == AXIS)
    blocks = {_words(c["block"]) for c in on_page}
    return bool(text) and (text in notes_text or text in blocks or text == axis)


def _compare(
    root: Path, filing: Filing, cells: list[Cell], notes_text: str
) -> tuple[set[Key], int]:
    """Store the image read; return the rows that agree and the number of differences."""
    fid = filing.meta.filing_id
    units = {(s, k): unit for s, k, _, _, unit in ID_CELLS}
    labels = {(s, k): (label, column) for s, k, label, column, _ in ID_CELLS}
    seen, used = _match(filing, cells)
    agreed: set[Key] = set()
    problems = 0
    for row in filing.rows:
        key = (row.schedule, row.line)
        if row.schedule == ID_NOTE_SCHEDULE:
            if _note_agrees(row, cells, notes_text):
                agreed.add(key)
            else:
                problems += 1
                print(f"DIFF {fid} {row.schedule}.{row.line}: text not found in the image read")
            continue
        if (_words(row.label_as_filed), _words(row.description_as_filed)) != labels[key]:
            problems += 1
            print(f"LABEL {fid} {row.schedule}.{row.line}: the form lists {labels[key]!r}")
        if key not in seen:
            problems += 1
            print(f"DIFF {fid} {row.schedule}.{row.line}: the image read has no such cell")
            continue
        if units[key] == NO_FIGURE:
            same = _words(row.answer_as_filed) == _words(seen[key])
            mine = row.answer_as_filed
        else:
            same = _figure(row.amount_as_filed) == _figure(seen[key])
            mine = row.amount_as_filed
        if same:
            agreed.add(key)
        else:
            problems += 1
            print(
                f"DIFF {fid} {row.schedule}.{row.line}: transcription {mine!r}, "
                f"image read {seen[key]!r}"
            )
    for number, cell in enumerate(cells):
        if number not in used and _words(cell["row"]) != AXIS:
            problems += 1
            print(
                f"DIFF {fid}: only in the image read, page {cell['page']}: "
                f"{cell['row']!r} / {cell['column']!r} = {cell['value']!r}"
            )
    _store_read(root, filing, seen, units)
    return agreed, problems


def _store_read(root: Path, filing: Filing, seen: dict[Key, str], units: dict[Key, str]) -> None:
    """Write the normalised copy of the image read."""
    path = image_read_file(root, filing)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(READ_COLUMNS)
        for row in filing.rows:
            key = (row.schedule, row.line)
            if key not in seen:
                continue
            text = units[key] == NO_FIGURE
            amount = "" if text else _figure(seen[key])
            writer.writerow([row.page, *key, amount, "", _words(seen[key]) if text else ""])


def _mark(root: Path, filing: Filing, agreed: set[Key]) -> None:
    """Mark the unverified rows that agree; change nothing else."""
    fid = filing.meta.filing_id
    path = root / "transcriptions" / "id" / str(filing.meta.reporting_year) / f"{fid}.csv"
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
    parser.add_argument("--filing", default=None, help="one filing id; default every Idaho record")
    args = parser.parse_args()
    cells = _read_reader_file(args.image_read)
    notes_text = _words(args.notes.read_text(encoding="utf-8")) if args.notes else ""
    problems = 0
    for filing in load_filings(args.root, only=args.filing):
        if filing.meta.form != ID_FORM:
            continue
        agreed, gaps = _compare(args.root, filing, cells, notes_text)
        problems += gaps
        print(f"{filing.meta.filing_id}: {len(agreed)} of {len(filing.rows)} rows agree")
        if args.apply:
            _mark(args.root, filing, agreed)
    print(f"{problems} differences")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
