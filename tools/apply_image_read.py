"""Compare transcriptions with the image reads and mark the rows that agree.

Usage:
    python tools/apply_image_read.py <filing_id> [--apply]

Without ``--apply`` it only prints the differences. With it, every row that is
still ``unverified`` and agrees with the image read is marked ``text_and_image``
(``two_image_reads`` for a scanned filing). Rows that differ are left
``unverified`` until a further look at the page image settles them; this tool
never changes a figure.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from filings340b.imageread import compare, image_read_file, read_image_read, row_differences
from filings340b.load import load_filings
from filings340b.model import Verification


def main() -> int:
    """Run from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("filing_id")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    (filing,) = load_filings(args.root, args.filing_id)
    read = read_image_read(image_read_file(args.root, filing))
    differences = compare(filing, read)
    for d in differences:
        print(f"DIFF {d.filing_id} schedule {d.schedule} line {d.line}: {d.detail}")
    print(f"{len(filing.rows)} rows, {len(differences)} differences")
    if not args.apply:
        return 1 if differences else 0
    scan = filing.source.scanned
    folder = args.root / "transcriptions" / filing.meta.state.lower()
    path = folder / str(filing.meta.reporting_year) / f"{filing.meta.filing_id}.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        records = list(csv.DictReader(handle))
    marked = 0
    for record, row in zip(records, filing.rows, strict=True):
        key = (row.schedule, row.line)
        agrees = not row_differences(row, read.get(key), filing.held_reads.get(key))
        if record["verification"] == Verification.UNVERIFIED.value and agrees:
            gap = f"{row.schedule}:{row.line}" in filing.meta.text_layer_gaps
            images_only = scan or gap
            mark = Verification.TWO_IMAGE_READS if images_only else Verification.TEXT_AND_IMAGE
            record["verification"] = mark.value
            marked += 1
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
    print(f"marked {marked} rows as agreeing with the image read")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
