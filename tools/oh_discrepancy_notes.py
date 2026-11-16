"""Write the discrepancy notes of Ohio's filings into ``reference/discrepancy_notes.csv``.

When one of the template's own sums or ratios does not hold in a workbook, the dataset shows
the difference and keeps a note that says only what the cells hold ("The total cell holds X.
The five payer cells add to Y."). The note never gives a cause: the dataset does not know
one. For Ohio this tool writes those notes from the rules in ``src/filings340b/ohio.py``, so
that a person does not type thousands of numbers. It keeps every note of the other states
as it is and replaces only the Ohio ones, so running it again changes nothing.

Usage:
    python tools/oh_discrepancy_notes.py [--root <repository>]

It needs the private small counts only if some rule is evaluated over a withheld cell, and
no rule is: a rule over a withheld cell does not apply, so it has no note.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from filings340b.forms import OH_FORM
from filings340b.load import load_filings
from filings340b.ohio import note_text
from filings340b.tieout import checks


def main() -> int:
    """Run from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    path = args.root / "reference" / "discrepancy_notes.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        kept = [r for r in csv.DictReader(handle) if not r["filing_id"].startswith("oh-")]
    filings = load_filings(args.root, check_sums=False)
    written: list[dict[str, str]] = []
    for filing in filings:
        if filing.meta.form != OH_FORM:
            continue
        written.extend(
            {"filing_id": c.filing_id, "rule": c.rule, "note": note_text(c)}
            for c in checks(filing, filings)
            if c.applicable and not c.passed
        )
    rows = [*kept, *sorted(written, key=lambda r: (r["filing_id"], r["rule"]))]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["filing_id", "rule", "note"], lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(written)} Ohio notes written, {len(kept)} others kept")
    return 0


if __name__ == "__main__":
    sys.exit(main())
