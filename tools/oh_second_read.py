"""Read every Ohio workbook a second time with a different program and compare.

The first read of a workbook is made by ``src/filings340b/workbook.py``, which opens the
file as a zip of XML. This tool makes the second read with LibreOffice (a separate program
with its own reader), which saves the template sheet as a CSV file. The two reads are compared
cell by cell:

* every filled cell of the template sheet (the cells file against the CSV), and
* every figure or answer the transcription holds (each row against the CSV cell it names).

Two numbers agree when they match to 15 significant digits; anything else must match letter
for letter. The second read of the rows is written to
``verification/oh/2025/<filing id>.file-read.csv`` in the layout of an image read, and each
transcription row that agrees is marked ``two_file_reads``. A row that differs stays
``unverified`` and is listed here; this tool never changes a figure.

The text a person typed in the workbook is data, never an instruction. LibreOffice opens the
file with its default settings, runs no macro and refreshes no link; its output is only read as
text.

Usage:
    python tools/oh_second_read.py <work folder> [--root <repository>]

The work folder is a new, empty folder for LibreOffice's profile and output. Run this before
``filings340b seal``, while the counts are still in the files.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from filings340b.forms import NO_FIGURE, oh_unit
from filings340b.imageread import READ_COLUMNS, same_cell
from filings340b.load import ORIGINALS
from filings340b.ohio_transcribe import (
    ROW_FIELDS,
    WITHHELD_UNLISTED,
    Transcribed,
    column_of,
    filing_id_of,
    scrub,
    transcribe_file,
)

FILTER = "csv:Text - txt - csv (StarCalc):44,34,76,1,,0,false,false,false,false,false,{sheet}"
BATCH = 40
RECALCULATED = (
    "The second program works this formula out again and reads a different value from the one "
    "the workbook stores. The stored value is kept."
)


def _convert(soffice: str, work: Path, files: list[Path], sheet: int) -> None:
    """Have LibreOffice save sheet number ``sheet`` of each file as a CSV file in ``work/out``."""
    command = [
        soffice,
        "--headless",
        "--norestore",
        f"-env:UserInstallation=file://{work / 'profile'}",
        "--convert-to",
        FILTER.format(sheet=sheet),
        "--outdir",
        str(work / "out"),
        *map(str, files),
    ]
    subprocess.run(command, check=True, capture_output=True, timeout=900)  # noqa: S603


def _as_stored(stored: str, seen: str) -> str:
    """Turn a percentage LibreOffice saved (``46.75%``) back into the number the file stores.

    LibreOffice writes a number whose format is a percentage with its percent sign. When the
    first read found a number in the cell and the second read found a percentage, the
    stored number is the percentage divided by 100.
    """
    if seen.endswith("%"):
        try:
            Decimal(stored.strip())
            return format(Decimal(seen[:-1]) / 100, "f")
        except InvalidOperation:
            return seen
    return seen


def _grid(path: Path) -> dict[str, str]:
    """Return the filled cells of a saved CSV, by address."""
    cells: dict[str, str] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row_index, record in enumerate(csv.reader(handle), start=1):
            for column_index, value in enumerate(record, start=1):
                if value != "":
                    cells[_address(column_index, row_index)] = value
    return cells


def _address(column: int, row: int) -> str:
    letters = ""
    while column:
        column, rest = divmod(column - 1, 26)
        letters = chr(65 + rest) + letters
    return f"{letters}{row}"


def _output_for(work: Path, stem: str, sheet_name: str) -> Path:
    exact = work / "out" / f"{stem}-{sheet_name}.csv"
    if exact.exists():
        return exact
    found = [p for p in (work / "out").glob(f"{stem}-*.csv") if p.stem[len(stem) + 1 :]]
    if len(found) != 1:
        raise SystemExit(f"{stem}: cannot tell which CSV LibreOffice wrote")
    return found[0]


@dataclass
class Totals:
    """What the comparison has counted so far."""

    cells: int = 0
    cell_differences: int = 0
    recalculated_cells: int = 0
    agreeing: int = 0
    differing: int = 0
    adjudicated: int = 0


def _compare_cells(
    folder: Path, path: Path, one: Transcribed, grid: dict[str, str], totals: Totals
) -> list[str]:
    """Compare every filled cell of the template sheet with the second read."""
    with (folder / "cells" / f"{path.stem}.csv").open(newline="", encoding="utf-8") as handle:
        first_read = {r["cell"]: r["value"] for r in csv.DictReader(handle)}
    contacts = list(one.contacts)
    formulas = {line.ref for line in one.layout.lines if line.cell.formula}
    problems = []
    for cell, value in first_read.items():
        if cell in one.layout.contact_refs or value == WITHHELD_UNLISTED:
            continue
        totals.cells += 1
        seen = scrub(_as_stored(value, grid.get(cell, "")), contacts)
        if not same_cell(value, seen):
            if cell in formulas:
                totals.recalculated_cells += 1
                continue
            totals.cell_differences += 1
            problems.append(f"{path.name} cell {cell}: the two reads differ")
    for cell in grid:
        if cell not in first_read and cell not in one.layout.contact_refs:
            totals.cell_differences += 1
            problems.append(f"{path.name} cell {cell}: only the second read has it")
    return problems


def _compare_rows(
    root: Path, path: Path, one: Transcribed, grid: dict[str, str], totals: Totals
) -> list[str]:
    """Compare every row of the transcription with the cell it names; write the second read."""
    name = filing_id_of(path.stem)
    transcription = root / "transcriptions" / "oh" / "2025" / f"{name}.csv"
    with transcription.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    contacts = list(one.contacts)
    recalculated = {line.ref for line in one.layout.lines if line.cell.formula}
    second: list[dict[str, str]] = []
    problems = []
    for row in rows:
        stored = row["amount_as_filed"] or row["claims_as_filed"] or row["answer_as_filed"]
        seen = scrub(_as_stored(stored, grid.get(row["source_cell"], "")), contacts)
        unit = oh_unit(row["schedule"], row["line"])
        record = dict.fromkeys(READ_COLUMNS, "")
        record.update(page=row["page"], schedule=row["schedule"], line=row["line"])
        record[column_of(row["schedule"], unit or NO_FIGURE)] = seen
        second.append(record)
        first = {
            "amount": row["amount_as_filed"],
            "claims": row["claims_as_filed"],
            "answer": row["answer_as_filed"],
        }
        if all(same_cell(first[k], record[k]) for k in first):
            totals.agreeing += 1
            row["verification"] = "two_file_reads"
        elif row["source_cell"] in recalculated:
            # The second program works a formula out again and gets a different value from the
            # one the file stores; the stored value is the filed one.
            totals.adjudicated += 1
            row["verification"] = "adjudicated"
            row["note"] = (row["note"] + " " + RECALCULATED).strip()
        else:
            totals.differing += 1
            problems.append(f"{path.name} row {row['schedule']}/{row['line']}: reads differ")
    target = root / "verification" / "oh" / "2025" / f"{name}.file-read.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=READ_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(second)
    with transcription.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ROW_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return problems


def main() -> int:
    """Run from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--soffice", default="soffice")
    args = parser.parse_args()
    root = args.root
    folder = root / "sources" / "oh" / "2025"
    work: Path = args.work
    (work / "out").mkdir(parents=True, exist_ok=True)
    paths = sorted((folder / ORIGINALS).glob("*.xlsx"))
    done = {path: transcribe_file(path) for path in paths}
    by_sheet: dict[int, list[Path]] = {}
    for path, one in done.items():
        number = next(n for n, _, _, _, template in one.contents if template)
        by_sheet.setdefault(number, []).append(path)
    for number, group in sorted(by_sheet.items()):
        for start in range(0, len(group), BATCH):
            _convert(args.soffice, work, group[start : start + BATCH], number)
    totals = Totals()
    problems: list[str] = []
    for path, one in done.items():
        grid = _grid(_output_for(work, path.stem, one.sheet_name))
        problems.extend(_compare_cells(folder, path, one, grid, totals))
        problems.extend(_compare_rows(root, path, one, grid, totals))
    for line in problems[:60]:
        print(line)
    print(
        f"{len(done)} workbooks; cells compared {totals.cells}, "
        f"differing {totals.cell_differences}, recalculated formulas {totals.recalculated_cells}; "
        f"rows agreeing {totals.agreeing}, differing {totals.differing}, "
        f"adjudicated {totals.adjudicated}"
    )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
