"""Compare each transcription with the independent read of the page images.

The second reader sees only the page images and writes the figures it reads to
``verification/<state>/<year>/<filing_id>.image-read.csv``. A transcribed row
may be marked as checked only when that read agrees with it, figure for figure
as printed. Rows where the two reads differ are settled by a third look at the
page image and marked ``adjudicated`` with a note.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from filings340b.errors import DataError
from filings340b.model import Filing, Row, Verification
from filings340b.sealing import MARKER, is_unknown
from filings340b.textcheck import core

READ_COLUMNS = ("page", "schedule", "line", "amount", "claims", "answer")
# A file that withholds a claim count has this column after the others.
SEALED_READ_COLUMNS = (*READ_COLUMNS, MARKER)

# Marks that say a row agrees with the image read.
AGREED = frozenset({Verification.TEXT_AND_IMAGE, Verification.TWO_IMAGE_READS})


@dataclass(frozen=True, slots=True)
class Difference:
    """One place where the transcription and the image read do not agree."""

    filing_id: str
    schedule: str
    line: str
    detail: str


def image_read_file(root: Path, filing: Filing) -> Path:
    """Return where a filing's image read is kept."""
    folder = root / "verification" / filing.meta.state.lower() / str(filing.meta.reporting_year)
    return folder / f"{filing.meta.filing_id}.image-read.csv"


def read_image_read(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    """Read an image-read file, keyed by (schedule, line)."""
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) not in (READ_COLUMNS, SEALED_READ_COLUMNS):
            raise DataError(
                f"{path.name}: columns must be exactly {', '.join(READ_COLUMNS)}, "
                f"with or without a last column {MARKER}"
            )
        out: dict[tuple[str, str], dict[str, str]] = {}
        for record in reader:
            record.setdefault(MARKER, "")
            key = (record["schedule"], record["line"])
            if key in out:
                raise DataError(f"{path.name}: schedule {key[0]} line {key[1]} appears twice")
            out[key] = record
    return out


def _carries_a_figure(row: Row) -> bool:
    return bool(row.amount_as_filed.strip() or row.claims_as_filed.strip() or row.schedule == "I")


def row_differences(
    row: Row, read: dict[str, str] | None, held_read: str | None = None
) -> list[str]:
    """List how one transcribed row differs from the image read of it.

    ``held_read`` is the withheld claim count of the image read, when the private counts
    are there. Without them a withheld claim cell is not compared.
    """
    if read is None:
        return ["the image read has no such row"] if _carries_a_figure(row) else []
    found = []
    withheld_read = bool(read.get(MARKER))
    if bool(row.claims_withheld) != withheld_read:
        found.append("claims: withheld in one and not in the other")
    seen_claims = held_read if withheld_read and held_read is not None else read["claims"]
    skip_claims = is_unknown(row)
    pairs = (
        ("amount", core(row.amount_as_filed), core(read["amount"])),
        *(() if skip_claims else (("claims", core(row.claims_as_filed), core(seen_claims)),)),
        ("answer", row.answer_as_filed.strip().upper(), read["answer"].strip().upper()),
        ("page", str(row.page), read["page"].strip()),
    )
    for what, transcribed, seen in pairs:
        if transcribed != seen:
            found.append(f"{what}: transcription {transcribed!r}, image read {seen!r}")
    return found


def compare(filing: Filing, read: dict[tuple[str, str], dict[str, str]]) -> list[Difference]:
    """Compare every row of a filing with the image read, both ways."""
    fid = filing.meta.filing_id
    out: list[Difference] = []
    seen: set[tuple[str, str]] = set()
    for row in filing.rows:
        key = (row.schedule, row.line)
        seen.add(key)
        out.extend(
            Difference(fid, row.schedule, row.line, detail)
            for detail in row_differences(row, read.get(key), filing.held_reads.get(key))
        )
    for key, record in read.items():
        if key not in seen and (record["amount"] or record["claims"] or record["answer"]):
            out.append(
                Difference(fid, key[0], key[1], f"only in the image read (page {record['page']})")
            )
    return out


def unsupported_marks(root: Path, filing: Filing) -> list[Difference]:
    """List rows marked as agreeing with the image read when the read says otherwise."""
    path = image_read_file(root, filing)
    marked = [r for r in filing.rows if r.verification in AGREED]
    if not marked:
        return []
    fid = filing.meta.filing_id
    if not path.exists():
        return [Difference(fid, "", "", f"rows are marked as checked but {path.name} is missing")]
    read = read_image_read(path)
    out: list[Difference] = []
    for row in marked:
        out.extend(
            Difference(fid, row.schedule, row.line, detail)
            for detail in row_differences(
                row,
                read.get((row.schedule, row.line)),
                filing.held_reads.get((row.schedule, row.line)),
            )
        )
    return out
