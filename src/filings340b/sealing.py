"""Keep the withheld claim counts out of the repository, and put them back for the maintainer.

A claim count of 1 to 5 (see ``smallcounts.py``) is not held in any table file. In a
transcription or an image-read file the cell is empty and a ``claims_withheld`` column
says why. The counts live in ``private/small-counts.csv``, which is never committed.

Two ways to run:

* With the private file, ``restore`` puts the counts back in memory. Every check works
  on the counts as read, and the committed ``claim-sums.csv`` is proven against them.
* Without it, the build takes what depends on a withheld count from ``claim-sums.csv``
  (the sum of a schedule's claim counts) and the checks skip the withheld cells.
"""

from __future__ import annotations

import csv
import dataclasses
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from filings340b.errors import DataError
from filings340b.model import Filing, Row, RowKind
from filings340b.money import parse_count
from filings340b.smallcounts import (
    BESIDE_SMALL,
    FEWER_THAN,
    SMALL_HIGHEST,
    RowKey,
    is_small,
    withheld_rows,
)

# The column that holds the reason, last in a file that withholds anything.
MARKER = "claims_withheld"
REASONS = frozenset({FEWER_THAN, BESIDE_SMALL})

PRIVATE_FILE = Path("private") / "small-counts.csv"
PRIVATE_COLUMNS = ("filing_id", "schedule", "line", "claims_as_filed", "image_read_claims")
SUMS_NAME = "claim-sums.csv"
SUMS_COLUMNS = ("filing_id", "schedule", "claim_sum")

SumKey = tuple[str, str]


@dataclass(frozen=True, slots=True)
class Held:
    """The two reads of one withheld count, as written."""

    claims_as_filed: str
    image_read_claims: str


def read_private(root: Path) -> dict[RowKey, Held] | None:
    """Read the private counts, or return None when the file is not there."""
    path = root / PRIVATE_FILE
    if not path.exists():
        return None
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != PRIVATE_COLUMNS:
            raise DataError(f"{path.name}: columns must be exactly {', '.join(PRIVATE_COLUMNS)}")
        out: dict[RowKey, Held] = {}
        for record in reader:
            key = (record["filing_id"], record["schedule"], record["line"])
            if key in out:
                raise DataError(f"{path.name}: {key[0]} schedule {key[1]} line {key[2]} twice")
            out[key] = Held(record["claims_as_filed"], record["image_read_claims"])
    return out


def write_private(root: Path, held: Mapping[RowKey, Held]) -> None:
    """Write the private counts, one row per withheld count, in a fixed order."""
    path = root / PRIVATE_FILE
    path.parent.mkdir(exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(PRIVATE_COLUMNS)
        for key in sorted(held):
            writer.writerow([*key, held[key].claims_as_filed, held[key].image_read_claims])


def sums_path(root: Path, filing: Filing) -> Path:
    """Return where the claim sums of a filing's folder are kept."""
    folder = root / "verification" / filing.meta.state.lower() / str(filing.meta.reporting_year)
    return folder / SUMS_NAME


def read_sums(path: Path) -> dict[SumKey, int]:
    """Read a claim-sums file; a missing file has no sums."""
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != SUMS_COLUMNS:
            raise DataError(f"{path.name}: columns must be exactly {', '.join(SUMS_COLUMNS)}")
        return {(r["filing_id"], r["schedule"]): int(r["claim_sum"]) for r in reader}


def write_sums(path: Path, sums: Mapping[SumKey, int]) -> None:
    """Write a claim-sums file in a fixed order."""
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(SUMS_COLUMNS)
        for key in sorted(sums):
            writer.writerow([*key, sums[key]])


def claim_sums(filing: Filing, schedules: Iterable[str]) -> dict[SumKey, int]:
    """Sum the claim counts of the given schedules (the counts must be known)."""
    return {
        (filing.meta.filing_id, letter): sum(
            r.claims or 0 for r in filing.schedule(letter) if r.row_kind is not RowKind.TOTAL
        )
        for letter in schedules
    }


def is_unknown(row: Row) -> bool:
    """Say whether a row's count is withheld and not put back."""
    return bool(row.claims_withheld) and row.claims is None


def _count_of(filing_id: str, row: Row, held: Held) -> int:
    where = f"{filing_id} schedule {row.schedule} line {row.line}"
    try:
        count = parse_count(held.claims_as_filed)
    except ValueError as error:
        raise DataError(f"{where}: the private count is not a count") from error
    if row.claims_withheld == FEWER_THAN and not is_small(count):
        raise DataError(f"{where}: the private count is not 1 to 5 on a {FEWER_THAN} row")
    if row.claims_withheld == BESIDE_SMALL and (count is None or count <= SMALL_HIGHEST):
        raise DataError(f"{where}: the private count is small on a {BESIDE_SMALL} row")
    if count is None:
        raise DataError(f"{where}: the private count is empty")
    return count


def _restored(filing: Filing, held: Mapping[RowKey, Held]) -> Filing:
    rows: list[Row] = []
    reads: dict[SumKey, str] = {}
    for row in filing.rows:
        if row.claims_withheld:
            key = (filing.meta.filing_id, row.schedule, row.line)
            if key not in held:
                raise DataError(
                    f"{key[0]} schedule {key[1]} line {key[2]}: marked as withheld "
                    "but the private file has no count for it"
                )
            reads[(row.schedule, row.line)] = held[key].image_read_claims
            row = dataclasses.replace(  # noqa: PLW2901
                row,
                claims_as_filed=held[key].claims_as_filed,
                claims=_count_of(key[0], row, held[key]),
            )
        rows.append(row)
    return dataclasses.replace(filing, rows=tuple(rows), held_reads=reads)


def _with_sums(root: Path, filing: Filing) -> Filing:
    """Without the private file: take the claim sums from the committed results file."""
    marked = [r for r in filing.rows if r.claims_withheld]
    if not marked:
        return filing
    path = sums_path(root, filing)
    sums = read_sums(path)
    out: dict[str, int] = {}
    for letter in sorted({r.schedule for r in marked}):
        key = (filing.meta.filing_id, letter)
        if key not in sums:
            raise DataError(f"{key[0]} schedule {letter}: no claim sum in {path.name}")
        out[letter] = sums[key]
        _check_sum_range(key, [r for r in filing.rows if r.schedule == letter], sums[key])
    return dataclasses.replace(filing, claim_sums=out)


def _check_sum_range(key: SumKey, rows: Iterable[Row], total: int) -> None:
    """Refuse a sum the visible counts and the withheld rows cannot add up to."""
    parts = [r for r in rows if r.row_kind is not RowKind.TOTAL]
    shown = sum(r.claims or 0 for r in parts if not r.claims_withheld)
    small = sum(1 for r in parts if r.claims_withheld == FEWER_THAN)
    beside = sum(1 for r in parts if r.claims_withheld == BESIDE_SMALL)
    low = shown + small + beside * (SMALL_HIGHEST + 1)
    high = shown + small * SMALL_HIGHEST
    if total < low or (not beside and total > high):
        raise DataError(f"{key[0]} schedule {key[1]}: the claim sum cannot match its rows")


def _check_sums(root: Path, filings: tuple[Filing, ...]) -> None:
    """With the private file: the committed claim sums must be the ones the counts give."""
    paths = {sums_path(root, f) for f in filings}
    for path in sorted(paths):
        here = [f for f in filings if sums_path(root, f) == path]
        ids = {f.meta.filing_id for f in here}
        expected = {
            k: v
            for f in here
            for k, v in claim_sums(f, {r.schedule for r in f.rows if r.claims_withheld}).items()
        }
        committed = {k: v for k, v in read_sums(path).items() if k[0] in ids}
        if committed != expected:
            raise DataError(
                f"{path.relative_to(root)} does not match the counts; "
                "run `filings340b seal` and commit the result"
            )


def restore(
    root: Path, filings: tuple[Filing, ...], *, check_sums: bool = True
) -> tuple[Filing, ...]:
    """Put the withheld counts back when the private file is there; else take the sums."""
    held = read_private(root)
    if held is None:
        return tuple(_with_sums(root, f) for f in filings)
    ids = {f.meta.filing_id for f in filings}
    marked = {
        (f.meta.filing_id, r.schedule, r.line) for f in filings for r in f.rows if r.claims_withheld
    }
    for key in sorted(held):
        if key[0] in ids and key not in marked:
            raise DataError(
                f"{key[0]} schedule {key[1]} line {key[2]}: the private file holds a count "
                f"for a row that is not marked {MARKER}"
            )
    out = tuple(_restored(f, held) for f in filings)
    if check_sums:
        _check_sums(root, out)
    return out


def describe_run(root: Path, filings: Iterable[Filing]) -> str:
    """Say in one line which way a check ran."""
    if (root / PRIVATE_FILE).exists():
        return "Run with the private small counts: every sum was recomputed."
    everyone = list(filings)
    files = sorted({str(sums_path(root, f).relative_to(root)) for f in everyone if f.claim_sums})
    sums = sum(len(f.claim_sums) for f in everyone)
    cells = sum(1 for f in everyone for r in f.rows if is_unknown(r))
    source = (
        f"{sums} claim sums were taken from {', '.join(files)}"
        if files
        else "no claim sums were needed"
    )
    return (
        f"Run without the private small counts: {source}; {cells} withheld cells were not re-read."
    )


def withheld_for(filings: Iterable[Filing]) -> dict[RowKey, str]:
    """Return (filing, schedule, line) -> reason for every row whose count is not published.

    A filing whose counts are all known gets the rule applied to them, and its markers must
    agree with the result. A filing with withheld counts that were not put back keeps its markers.
    """
    out: dict[RowKey, str] = {}
    for filing in filings:
        marks = {
            (filing.meta.filing_id, r.schedule, r.line): r.claims_withheld
            for r in filing.rows
            if r.claims_withheld
        }
        if any(is_unknown(r) for r in filing.rows):
            out.update(marks)
            continue
        computed = withheld_rows(filing.rows)
        for key, reason in marks.items():
            if computed.get(key) != reason:
                raise DataError(
                    f"{key[0]} schedule {key[1]} line {key[2]}: the {MARKER} mark "
                    "is not what the small-number rule gives for the counts"
                )
        out.update(computed)
    return out
