r"""Compare Minnesota's transcriptions with an independent read of the page images.

Usage:
    python tools/compare_mn_image_read.py --table-6-1 table-6-1.csv \\
        --table-6-2 table-6-2.csv --table-6-2-next table-6-2-page-45.csv \\
        --notes NOTES.md --notes-next NOTES-page-45.md [--apply]

The second reader saw only the page images (PDF pages 42 to 45). Its files are:

* ``table-6-1.csv``: ``image,row,name_as_printed,type_as_printed,city_as_printed,
  net_revenue_as_printed,percent_as_printed``, one line per printed row of Table 6.1;
* ``table-6-2.csv`` and ``table-6-2-page-45.csv``: ``image,row,dimension_as_printed,
  net_revenue_as_printed,percent_as_printed``, one line per printed row of Table 6.2,
  for the part of the table on page 44 and the part on page 45;
* two notes files with the running text it saw around the tables.

This tool

* stores a normalised copy of the reads in ``verification/mn/2024/``: two files that keep
  every printed cell (``mn-2024-table-6-1.second-read.csv``, ``mn-2024-table-6-2.second-read.csv``),
  and one file per record in the layout the other states use
  (``page,schedule,line,amount,claims,answer``);
* compares every name, type, city, figure and page exactly as printed, apart from the ``$``
  sign and runs of spaces, so a mark that differs (a ``%``, a comma, an apostrophe) is a
  difference;
* with ``--apply``, marks a row ``text_and_image`` only when the read agrees with it. A record
  whose name, type or city differs, or a figure the reader marked ``?``, is left ``unverified``
  and listed. Nothing in a transcription is ever changed except that mark.

A text row (a paragraph, a title, a "Source:" line) is marked only when its exact text is
found in the notes file of the page it is printed on.
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

from filings340b.forms import (
    KIND_STATE_ROW,
    KIND_STATE_TOTALS,
    MN_ENTITY_SCHEDULE,
    MN_FORM,
    MN_NOTE_SCHEDULE,
    MN_TOTAL_DIMENSIONS,
    MN_TOTALS_SCHEDULE,
)
from filings340b.imageread import READ_COLUMNS, image_read_file
from filings340b.load import ROW_COLUMNS, load_filings
from filings340b.model import Filing, Verification

T61_COLUMNS = (
    "image",
    "row",
    "name_as_printed",
    "type_as_printed",
    "city_as_printed",
    "net_revenue_as_printed",
    "percent_as_printed",
)
T62_COLUMNS = (
    "image",
    "row",
    "dimension_as_printed",
    "net_revenue_as_printed",
    "percent_as_printed",
)
Key = tuple[str, str]


def _figure(printed: str) -> str:
    """Drop the dollar sign and spaces from a printed value; keep every other mark."""
    return re.sub(r"[$\s]", "", printed)


def _words(text: str) -> str:
    return " ".join(text.split())


def _page_of(image: str) -> int:
    found = re.search(r"-(\d+)\.png$", image)
    if not found:
        raise SystemExit(f"cannot read a page number from {image!r}")
    return int(found.group(1))


def _read(path: Path, columns: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != columns:
            raise SystemExit(f"{path.name}: columns must be exactly {', '.join(columns)}")
        return list(reader)


def _write(path: Path, header: list[str], rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def _value(filing: Filing, schedule: str, line: str) -> tuple[str, int] | None:
    for row in filing.rows:
        if (row.schedule, row.line) == (schedule, line):
            return row.amount_as_filed, row.page
    return None


def _entity_agreement(
    filing: Filing, read: dict[str, str] | None, page: int
) -> tuple[set[Key], int]:
    """Compare one Table 6.1 record with its read; return the rows that agree and the gaps."""
    fid = filing.meta.filing_id
    if read is None:
        print(f"DIFF {fid}: the image read has no row with this name")
        return set(), 1
    gaps = 0
    text_ok = True
    for what, mine, seen in (
        ("name", filing.meta.name_as_filed, read["name_as_printed"]),
        ("type", filing.meta.entity_type_as_filed, read["type_as_printed"]),
        ("city", filing.meta.city_as_filed, read["city_as_printed"]),
    ):
        if _words(mine) != _words(seen):
            text_ok = False
            gaps += 1
            print(f"DIFF {fid} {what}: transcription {mine!r}, image read {seen!r}")
    agreed: set[Key] = set()
    for line, seen in (
        ("net_revenue", read["net_revenue_as_printed"]),
        ("pct_of_statewide", read["percent_as_printed"]),
    ):
        mine_row = _value(filing, MN_ENTITY_SCHEDULE, line)
        if mine_row is None:
            continue
        printed, row_page = mine_row
        if "?" in seen or _figure(printed) != _figure(seen) or row_page != page:
            gaps += 1
            print(
                f"DIFF {fid} {line}: transcription {printed!r} (page {row_page}), "
                f"image read {seen!r} (page {page})"
            )
        elif text_ok:
            agreed.add((MN_ENTITY_SCHEDULE, line))
    return agreed, gaps


def _totals_agreement(
    filing: Filing, reads: dict[str, tuple[dict[str, str], int]], notes: dict[int, str]
) -> tuple[set[Key], int, list[str]]:
    """Compare the statewide record; return rows that agree, the gaps, and rows with one read."""
    fid = filing.meta.filing_id
    agreed: set[Key] = set()
    gaps = 0
    missing: list[str] = []
    for dimension, label in MN_TOTAL_DIMENSIONS:
        read = reads.get(_words(label))
        for column, seen_key in (
            ("net_revenue", "net_revenue_as_printed"),
            ("pct_of_total", "percent_as_printed"),
        ):
            line = f"{dimension}_{column}"
            mine = _value(filing, MN_TOTALS_SCHEDULE, line)
            if mine is None:
                continue
            if read is None:
                missing.append(line)
                gaps += 1
                print(f"DIFF {fid} {line}: the image read has no row {label!r}")
                continue
            seen, page = read[0][seen_key], read[1]
            if "?" in seen or _figure(mine[0]) != _figure(seen) or mine[1] != page:
                gaps += 1
                print(
                    f"DIFF {fid} {line}: transcription {mine[0]!r} (page {mine[1]}), "
                    f"image read {seen!r} (page {page})"
                )
            else:
                agreed.add((MN_TOTALS_SCHEDULE, line))
    for row in filing.rows:
        if row.schedule != MN_NOTE_SCHEDULE:
            continue
        if _words(row.label_as_filed) in notes.get(row.page, ""):
            agreed.add((row.schedule, row.line))
        else:
            gaps += 1
            print(f"DIFF {fid} {row.line}: text not found in the notes for page {row.page}")
    return agreed, gaps, missing


def _mark(root: Path, filing: Filing, agreed: set[Key]) -> int:
    """Mark the unverified rows that agree; change nothing else."""
    fid = filing.meta.filing_id
    path = root / "transcriptions" / "mn" / str(filing.meta.reporting_year) / f"{fid}.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        stored = list(csv.DictReader(handle))
    marked = 0
    for record in stored:
        key = (record["schedule"], record["line"])
        if record["verification"] == Verification.UNVERIFIED.value and key in agreed:
            record["verification"] = Verification.TEXT_AND_IMAGE.value
            marked += 1
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ROW_COLUMNS), lineterminator="\n")
        writer.writeheader()
        writer.writerows(stored)
    return marked


def _table_6_1(
    root: Path, entities: list[Filing], t61: list[dict[str, str]], apply: bool
) -> tuple[int, int]:
    """Compare every Table 6.1 record; return the gaps and the rows marked."""
    by_name = {_words(r["name_as_printed"]): r for r in t61}
    if len(by_name) != len(t61):
        raise SystemExit("two rows of Table 6.1 share a name in the image read")
    folder = root / "verification" / "mn" / "2024"
    _write(
        folder / "mn-2024-table-6-1.second-read.csv",
        ["page", "row", "name", "type", "city", "net_revenue", "percent"],
        [
            [
                _page_of(r["image"]),
                r["row"],
                _words(r["name_as_printed"]),
                _words(r["type_as_printed"]),
                _words(r["city_as_printed"]),
                _figure(r["net_revenue_as_printed"]),
                _figure(r["percent_as_printed"]),
            ]
            for r in t61
        ],
    )
    gaps = marked = 0
    for filing in entities:
        read = by_name.get(_words(filing.meta.name_as_filed))
        page = _page_of(read["image"]) if read else 0
        agreed, found = _entity_agreement(filing, read, page)
        gaps += found
        if read is not None:
            net, pct = _figure(read["net_revenue_as_printed"]), _figure(read["percent_as_printed"])
            _write(
                image_read_file(root, filing),
                list(READ_COLUMNS),
                [
                    [page, MN_ENTITY_SCHEDULE, "net_revenue", net, "", ""],
                    [page, MN_ENTITY_SCHEDULE, "pct_of_statewide", pct, "", ""],
                ],
            )
        if apply:
            marked += _mark(root, filing, agreed)
    carried = {_words(f.meta.name_as_filed) for f in entities}
    for name in sorted(set(by_name) - carried):
        gaps += 1
        print(f"DIFF the image read has a row {name!r} that no record carries")
    print(f"Table 6.1: {len(entities)} records, {len(t61)} rows read")
    return gaps, marked


def _table_6_2(root: Path, statewide: Filing, args: argparse.Namespace) -> tuple[int, int]:
    """Compare the statewide record; return the gaps and the rows marked."""
    reads: dict[str, tuple[dict[str, str], int]] = {}
    stored: list[list[object]] = []
    for path in (args.table_6_2, args.table_6_2_next):
        if path is None or not path.exists():
            print(f"NOTE no image read of Table 6.2 from {path}; those rows stay unverified")
            continue
        for r in _read(path, T62_COLUMNS):
            page = _page_of(r["image"])
            reads[_words(r["dimension_as_printed"])] = (r, page)
            stored.append(
                [
                    page,
                    r["row"],
                    _words(r["dimension_as_printed"]),
                    _figure(r["net_revenue_as_printed"]),
                    _figure(r["percent_as_printed"]),
                ]
            )
    folder = root / "verification" / "mn" / "2024"
    _write(
        folder / "mn-2024-table-6-2.second-read.csv",
        ["page", "row", "dimension", "net_revenue", "percent"],
        stored,
    )
    notes: dict[int, str] = {}
    for path, pages in ((args.notes, (42, 43, 44)), (args.notes_next, (45,))):
        if path is not None and path.exists():
            notes.update(dict.fromkeys(pages, _words(path.read_text(encoding="utf-8"))))
    agreed, gaps, _ = _totals_agreement(statewide, reads, notes)
    lines: list[list[object]] = []
    for dimension, label in MN_TOTAL_DIMENSIONS:
        found = reads.get(_words(label))
        if found is not None:
            read, page = found
            net, pct = _figure(read["net_revenue_as_printed"]), _figure(read["percent_as_printed"])
            lines.append([page, MN_TOTALS_SCHEDULE, f"{dimension}_net_revenue", net, "", ""])
            lines.append([page, MN_TOTALS_SCHEDULE, f"{dimension}_pct_of_total", pct, "", ""])
    _write(image_read_file(root, statewide), list(READ_COLUMNS), lines)
    marked = _mark(root, statewide, agreed) if args.apply else 0
    print(f"Table 6.2 and notes: {len(agreed)} of {len(statewide.rows)} rows agree")
    return gaps, marked


def main() -> int:
    """Run from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table-6-1", type=Path, required=True)
    parser.add_argument("--table-6-2", type=Path, required=True)
    parser.add_argument("--table-6-2-next", type=Path, default=None)
    parser.add_argument("--notes", type=Path, required=True)
    parser.add_argument("--notes-next", type=Path, default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root: Path = args.root
    filings = [f for f in load_filings(root) if f.meta.form == MN_FORM]
    entities = [f for f in filings if f.meta.record_kind == KIND_STATE_ROW]
    (statewide,) = [f for f in filings if f.meta.record_kind == KIND_STATE_TOTALS]
    gaps_1, marked_1 = _table_6_1(root, entities, _read(args.table_6_1, T61_COLUMNS), args.apply)
    gaps_2, marked_2 = _table_6_2(root, statewide, args)
    problems = gaps_1 + gaps_2
    print(
        f"{problems} differences" + (f"; {marked_1 + marked_2} rows marked" if args.apply else "")
    )
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
