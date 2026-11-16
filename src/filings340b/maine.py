"""Tie-out rules for Maine's first annual 340B report (Maine Health Data Organization).

Maine's hospitals report to the Maine Health Data Organization (MHDO), which publishes one
report that adds them together. It prints no figure for any single hospital, so the whole
report is one record: its totals (printed in sentences), its two tables of drugs and the
sentences that give each table's share of the total acquisition cost are rows.

The report does not state any rule that its figures must satisfy, so every rule here is a
``comparison``: a figure the report prints beside the same thing worked out from other
figures it prints. A difference is recorded and shown; the published figures are never
changed.

Two of the report's totals are printed rounded, with a letter for millions ("$409.9M"). A
share worked out from such a figure is only known to the rounding, so the share rule accepts
any printed share that the rounded figure allows (see ``_share_from_tile``).

The record is a statewide total, so it has no measures: those compare covered entities.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal

from filings340b.forms import (
    ME_COSTLY_SCHEDULE,
    ME_FREQUENT_SCHEDULE,
    ME_SHARE_LINE,
    ME_SUMMARY_SCHEDULE,
    PERCENT,
)
from filings340b.model import Basis, Check, Filing

# A total in the sentences prints a rounded figure with a letter for millions: "$409.9M".
_MILLIONS = re.compile(r"^\$?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)M$")
_MILLION = Decimal(1_000_000)

# (schedule, what the report calls the table), in the order the report prints them.
_TABLES: tuple[tuple[str, str], ...] = (
    (ME_COSTLY_SCHEDULE, "Top 3 Most Costly 340B Prescription Drugs"),
    (ME_FREQUENT_SCHEDULE, "Top 3 Most Frequently Dispensed 340B Prescription Drugs"),
)


def _amount(filing: Filing, schedule: str, line: str) -> Decimal | None:
    for row in filing.rows:
        if (row.schedule, row.line) == (schedule, line):
            return row.amount
    return None


def _answer(filing: Filing, schedule: str, line: str) -> str:
    for row in filing.rows:
        if (row.schedule, row.line) == (schedule, line):
            return row.answer_as_filed.strip()
    return ""


def _column(filing: Filing, schedule: str, figure: str) -> Decimal | None:
    """Add one figure of a drug table over its rows, or return nothing when it has none."""
    found = [
        row.amount
        for row in filing.rows
        if row.schedule == schedule
        and re.fullmatch(rf"\d{{11}}_{figure}", row.line)
        and row.amount is not None
    ]
    return sum(found, Decimal(0)) if found else None


def _tile(printed: str) -> tuple[Decimal, Decimal] | None:
    """Read a figure such as "$409.9M": return its value in dollars and the step it rounds to."""
    found = _MILLIONS.match(printed)
    if not found:
        return None
    millions = Decimal(found.group(1).replace(",", ""))
    step = Decimal(1).scaleb(int(millions.as_tuple().exponent))
    return millions * _MILLION, step * _MILLION


def _percent(part: Decimal, whole: Decimal, printed: Decimal) -> Decimal:
    exponent = int(printed.as_tuple().exponent)
    return (part / whole * 100).quantize(Decimal(1).scaleb(exponent), rounding=ROUND_HALF_UP)


def _share_from_tile(
    part: Decimal | None, tile: tuple[Decimal, Decimal] | None, printed: Decimal | None
) -> Decimal | None:
    """Return the share the printed total allows, at the number of decimals the report prints.

    The total is printed to the nearest ``step`` (a tenth of a million), so the share has a
    range. When the printed share is inside that range it is the figure expected; when it is
    outside, the share at the printed total itself is.
    """
    if part is None or tile is None or printed is None or tile[0] == 0:
        return None
    value, step = tile
    low = _percent(part, value + step / 2, printed)
    high = _percent(part, value - step / 2, printed)
    if low <= printed <= high:
        return printed
    return _percent(part, value, printed)


def checks(filing: Filing) -> tuple[Check, ...]:
    """Run every Maine rule on the statewide record."""
    fid = filing.meta.filing_id
    tile = _tile(_answer(filing, ME_SUMMARY_SCHEDULE, "acquisition_cost"))
    hospitals = _amount(filing, ME_SUMMARY_SCHEDULE, "hospitals_reporting")
    out: list[Check] = []
    for schedule, table in _TABLES:
        printed = _amount(filing, schedule, ME_SHARE_LINE)
        out.append(
            Check(
                fid,
                f"{schedule}.{ME_SHARE_LINE}=acquisition_cost.sum/summary.acquisition_cost",
                Basis.COMPARISON,
                f"The share the report prints above {table} beside the table's Total Acquisition "
                "Cost rows added together, divided by the total acquisition cost the report "
                "prints in millions of dollars (to the nearest 0.1 million, so a share inside "
                "the range that rounding allows counts as agreeing), times 100, at the "
                "precision the report prints (percentage points)",
                _share_from_tile(_column(filing, schedule, "acquisition_cost"), tile, printed),
                printed,
                unit=PERCENT,
            )
        )
    for schedule, table in _TABLES:
        out.append(
            Check(
                fid,
                f"{schedule}.hospitals=3*summary.hospitals_reporting",
                Basis.COMPARISON,
                f"The # of Hospitals column of {table} added together beside three times the "
                "number of hospitals the report says submitted data, because the report gives "
                "each hospital's top 3",
                hospitals * 3 if hospitals is not None else None,
                _column(filing, schedule, "hospitals"),
                unit="count",
            )
        )
    return tuple(out)
