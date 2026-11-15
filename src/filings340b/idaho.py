"""Tie-out rules for Idaho's statewide report (State Controller's Office).

Idaho's covered entities report to the State and their filings are confidential. The
State Controller publishes one report that adds them together and names no entity. The
whole report is one record: every printed cell of its tables, its highlight tiles and
its chart is a row.

Rules marked ``form`` are ones the report's own layout states: a table's TOTAL row
beside the rows above it. Rules marked ``comparison`` are ones the report does not
state: a printed percentage beside the division it appears to show, a tile or a chart
label beside the table total of the same name, and the savings total beside payments
received less acquisition cost. A difference is recorded and shown; the published
figures are never changed.

The record is a statewide total, so it has no measures: those compare covered entities.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal

from filings340b.forms import (
    COUNT,
    ID_CHART_SCHEDULE,
    ID_HIGHLIGHTS_SCHEDULE,
    ID_PAYER_TABLES,
    ID_PAYERS,
    ID_SAVINGS_COLUMNS,
    ID_SAVINGS_SCHEDULE,
    ID_SAVINGS_USES,
    ID_SUBMISSIONS_SCHEDULE,
    ID_TOTAL,
    PERCENT,
    USD,
)
from filings340b.model import Basis, Check, Filing

# A highlight tile prints a rounded figure with a letter for millions: "$812.9M".
_MILLIONS = re.compile(r"^\$?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)M$")
_MILLION = Decimal(1_000_000)

# Chart label -> the payer table (or the savings table) whose TOTAL it draws.
_CHART: tuple[tuple[str, str, str, str], ...] = (
    (
        "contract_pharmacy_payments",
        "Payments to Contract Pharmacies",
        "contract_pharmacy_payments",
        "Payments to Contract Pharmacies",
    ),
    (
        "acquisition_cost",
        "Aggregate Acquisition Cost",
        "acquisition_cost",
        "Aggregate Acquisition Cost",
    ),
    ("savings_utilized", "340B Savings Utilized", ID_SAVINGS_SCHEDULE, "340B Savings Utilization"),
    (
        "payments_received",
        "Aggregate Payments Received",
        "payments_received",
        "Aggregate Payments Received",
    ),
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


def _added(figures: list[Decimal | None]) -> Decimal | None:
    """Add a table's rows, or return nothing when a row prints no figure."""
    if not figures or any(figure is None for figure in figures):
        return None
    return sum((figure for figure in figures if figure is not None), Decimal(0))


def _share(part: Decimal | None, whole: Decimal | None, printed: Decimal | None) -> Decimal | None:
    """Return part over whole as a percentage, at the number of decimals the report prints."""
    if part is None or whole is None or whole == 0 or printed is None:
        return None
    exponent = int(printed.as_tuple().exponent)
    return (part / whole * 100).quantize(Decimal(1).scaleb(exponent), rounding=ROUND_HALF_UP)


def _whole_dollars(figure: Decimal | None) -> Decimal | None:
    return None if figure is None else figure.quantize(Decimal(1), rounding=ROUND_HALF_UP)


def _tile(printed: str) -> tuple[Decimal, Decimal] | None:
    """Read a tile such as "$812.9M": return its value in dollars and the step it is rounded to."""
    found = _MILLIONS.match(printed)
    if not found:
        return None
    millions = Decimal(found.group(1).replace(",", ""))
    step = Decimal(1).scaleb(int(millions.as_tuple().exponent))
    return millions * _MILLION, step


def _at_tile_precision(
    figure: Decimal | None, tile: tuple[Decimal, Decimal] | None
) -> Decimal | None:
    if figure is None or tile is None:
        return None
    return (figure / _MILLION).quantize(tile[1], rounding=ROUND_HALF_UP) * _MILLION


def checks(filing: Filing) -> tuple[Check, ...]:
    """Run every Idaho rule on the statewide record."""
    fid = filing.meta.filing_id
    out: list[Check] = []
    tables = [
        (schedule, figure, column, unit, pct_column, ID_PAYERS)
        for schedule, figure, column, unit, pct_column in ID_PAYER_TABLES
    ]
    tables.append(
        (
            ID_SAVINGS_SCHEDULE,
            "amount",
            ID_SAVINGS_COLUMNS[0],
            USD,
            ID_SAVINGS_COLUMNS[1],
            ID_SAVINGS_USES,
        )
    )
    for schedule, figure, column, unit, _, lines in tables:
        parts = [
            _amount(filing, schedule, f"{key}_{figure}") for key, _ in lines if key != ID_TOTAL
        ]
        out.append(
            Check(
                fid,
                f"{schedule}.rows=total",
                Basis.FORM,
                f"The {column} rows added together beside the table's TOTAL row",
                _added(parts),
                _amount(filing, schedule, f"{ID_TOTAL}_{figure}"),
                unit=unit,
            )
        )
    for schedule, figure, column, _, pct_column, lines in tables:
        whole = _amount(filing, schedule, f"{ID_TOTAL}_{figure}")
        for key, label in lines:
            printed = _amount(filing, schedule, f"{key}_pct")
            out.append(
                Check(
                    fid,
                    f"{schedule}.{key}_pct={key}/total",
                    Basis.COMPARISON,
                    f"The printed {pct_column} for {label} beside its {column} divided by the "
                    "table's TOTAL, times 100, at the precision the report prints "
                    "(percentage points)",
                    _share(_amount(filing, schedule, f"{key}_{figure}"), whole, printed),
                    printed,
                    unit=PERCENT,
                )
            )
    received = _amount(filing, ID_SUBMISSIONS_SCHEDULE, "received_count")
    complete_pct = _amount(filing, ID_SUBMISSIONS_SCHEDULE, "complete_pct")
    out.append(
        Check(
            fid,
            "submissions.complete_pct=complete/received",
            Basis.COMPARISON,
            "The percentage printed beside Submissions with complete status beside that count "
            "divided by Total submissions received, times 100, at the precision the report "
            "prints (percentage points)",
            _share(
                _amount(filing, ID_SUBMISSIONS_SCHEDULE, "complete_count"), received, complete_pct
            ),
            complete_pct,
            unit=PERCENT,
        )
    )
    out.append(
        Check(
            fid,
            "key_highlights.total_claims=claims.total",
            Basis.COMPARISON,
            "The Total Claims Dispensed tile beside the TOTAL row of Number of Claims by Payer "
            "Type",
            _amount(filing, "claims", f"{ID_TOTAL}_claims"),
            _amount(filing, ID_HIGHLIGHTS_SCHEDULE, "total_claims"),
            unit=COUNT,
        )
    )
    out.append(
        Check(
            fid,
            "key_highlights.covered_entities=submissions.received",
            Basis.COMPARISON,
            "The Unique Covered Entities tile beside Total submissions received",
            received,
            _amount(filing, ID_HIGHLIGHTS_SCHEDULE, "covered_entities"),
            unit=COUNT,
        )
    )
    for line, label, schedule, table in (
        (
            "payments_received",
            "Aggregate Payments Received",
            "payments_received",
            "Aggregate Payments Received",
        ),
        (
            "savings_to_community",
            "340B Savings to Community",
            ID_SAVINGS_SCHEDULE,
            "340B Savings Utilization",
        ),
    ):
        tile = _tile(_answer(filing, ID_HIGHLIGHTS_SCHEDULE, line))
        out.append(
            Check(
                fid,
                f"key_highlights.{line}={schedule}.total",
                Basis.COMPARISON,
                f"The {label} tile, a rounded figure in millions of dollars, beside the TOTAL row "
                f"of {table} rounded the same way",
                _at_tile_precision(_amount(filing, schedule, f"{ID_TOTAL}_amount"), tile),
                tile[0] if tile else None,
            )
        )
    for line, label, schedule, table in _CHART:
        out.append(
            Check(
                fid,
                f"key_financial_metrics.{line}={schedule}.total",
                Basis.COMPARISON,
                f"The chart's label for {label} beside the TOTAL row of {table}, to the whole "
                "dollar",
                _whole_dollars(_amount(filing, schedule, f"{ID_TOTAL}_amount")),
                _amount(filing, ID_CHART_SCHEDULE, line),
            )
        )
    paid = _amount(filing, "payments_received", f"{ID_TOTAL}_amount")
    cost = _amount(filing, "acquisition_cost", f"{ID_TOTAL}_amount")
    out.append(
        Check(
            fid,
            "savings_use.total=payments_received.total-acquisition_cost.total",
            Basis.COMPARISON,
            "The TOTAL row of 340B Savings Utilization beside the TOTAL row of Aggregate Payments "
            "Received minus the TOTAL row of Aggregate Acquisition Cost (the difference the "
            "report's summary calls the gross program margin)",
            paid - cost if paid is not None and cost is not None else None,
            _amount(filing, ID_SAVINGS_SCHEDULE, f"{ID_TOTAL}_amount"),
        )
    )
    return tuple(out)
