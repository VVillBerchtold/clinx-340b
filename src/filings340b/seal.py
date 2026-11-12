"""``filings340b seal``: move claim counts of 1 to 5 out of the working files.

Run it after transcribing a filing with its counts as read. It writes the counts to
``private/small-counts.csv``, empties them in the transcription and the image-read file
with the reason beside them, and writes the claim sums the public run needs. Running it
again changes nothing.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from filings340b.errors import DataError
from filings340b.imageread import image_read_file, read_image_read
from filings340b.load import load_filings
from filings340b.model import Filing
from filings340b.sealing import (
    MARKER,
    Held,
    claim_sums,
    is_unknown,
    sums_path,
    withheld_for,
    write_private,
    write_sums,
)
from filings340b.smallcounts import RowKey

LineKey = tuple[str, str]


def _mask(path: Path, marked: dict[LineKey, str], claims_column: str) -> int:
    """Empty the claim cell of the marked rows of one file; return how many held a value."""
    with path.open(newline="", encoding="utf-8") as handle:
        old = handle.read()
    rows = list(csv.reader(io.StringIO(old, newline="")))
    header = rows[0]
    if MARKER not in header:
        header.append(MARKER)
        for record in rows[1:]:
            record.append("")
    at = {name: header.index(name) for name in ("schedule", "line", claims_column, MARKER)}
    cleared = 0
    for record in rows[1:]:
        reason = marked.get((record[at["schedule"]], record[at["line"]]))
        if reason:
            cleared += 1 if record[at[claims_column]] else 0
            record[at[claims_column]] = ""
            record[at[MARKER]] = reason
    buffer = io.StringIO(newline="")
    csv.writer(buffer, lineterminator="\n").writerows(rows)
    if buffer.getvalue() != old:
        with path.open("w", newline="", encoding="utf-8") as handle:
            handle.write(buffer.getvalue())
    return cleared


def _transcription_file(root: Path, filing: Filing) -> Path:
    folder = root / "transcriptions" / filing.meta.state.lower() / str(filing.meta.reporting_year)
    return folder / f"{filing.meta.filing_id}.csv"


def seal(root: Path) -> str:
    """Seal every filing under ``root`` and return a one-line summary."""
    filings = load_filings(root, check_sums=False)
    if any(is_unknown(r) for f in filings for r in f.rows):
        raise DataError("some counts are withheld and private/small-counts.csv is not there")
    withheld = withheld_for(filings)
    held: dict[RowKey, Held] = {}
    sums: dict[Path, dict[LineKey, int]] = {}
    marks: dict[str, dict[LineKey, str]] = {}
    for filing in filings:
        fid = filing.meta.filing_id
        marked = {(s, line): why for (f, s, line), why in withheld.items() if f == fid}
        if not marked:
            continue
        marks[fid] = marked
        read_path = image_read_file(root, filing)
        read = read_image_read(read_path) if read_path.exists() else {}
        for row in filing.rows:
            key = (row.schedule, row.line)
            if key in marked:
                seen = filing.held_reads.get(key)
                if seen is None:
                    seen = read.get(key, {}).get("claims", "")
                held[(fid, *key)] = Held(row.claims_as_filed, seen)
        sums.setdefault(sums_path(root, filing), {}).update(
            claim_sums(filing, {s for s, _ in marked})
        )
    write_private(root, held)
    cleared = [0, 0]
    for filing in filings:
        marked = marks.get(filing.meta.filing_id, {})
        if not marked:
            continue
        cleared[0] += _mask(_transcription_file(root, filing), marked, "claims_as_filed")
        read_path = image_read_file(root, filing)
        if read_path.exists():
            cleared[1] += _mask(read_path, marked, "claims")
    for path, entries in sums.items():
        write_sums(path, entries)
    return (
        f"sealed {len(held)} withheld counts: {cleared[0]} emptied in transcriptions, "
        f"{cleared[1]} in image-read files"
    )
