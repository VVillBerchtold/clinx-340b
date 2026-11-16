"""Tie-out rules for Ohio's covered entity report (Department of Health template).

The template does its own arithmetic, and each rule here is one of those sums or ratios:

* a table's TOTAL cell equals the payer cells of its row added (the Indeterminate column of
  the contract pharmacy table is not part of its total);
* in the administered drugs table, the total payments row equals the actual payments row
  plus the estimated payments row;
* a percentage row equals the 340B prescriptions over all prescriptions, times 100.

A filer may type over a formula, so any of these can differ in a filing. A difference is
recorded and shown; the filed figures are never changed.

A rule that would use a cell the small-number rule withholds is not applied, so that
no published difference can give a withheld count away. Each rule is applied to a cell that
exists in the workbook; a cell that holds words has no value and the rule does not apply.
Workbooks store figures as binary floating-point numbers, so two figures within a tolerance
(a thousandth of a dollar, a billionth of a percentage point) count as equal. A percentage a
filer typed with fewer decimal places is compared at the places its cell holds: 63 agrees with
62.69, and 0.93 with 0.930002. A rounded percentage is not a difference.
"""

from __future__ import annotations

from decimal import Decimal

from filings340b.forms import (
    COUNT,
    OH_ADMINISTERED_ROWS,
    OH_CONTRACT_ROWS,
    OH_FRACTION_NOTE,
    OH_IN_HOUSE_ROWS,
    OH_INDETERMINATE,
    OH_PAYERS,
    OH_PERCENT_OF,
    OH_TOTAL,
    PERCENT,
    USD,
)
from filings340b.model import Basis, Check, Filing, Row

USD_TOLERANCE = Decimal("0.001")
PERCENT_TOLERANCE = Decimal("0.000000001")
PAYERS = tuple(key for key, _ in OH_PAYERS)

# What each row of a table is called in a rule's description.
_MEASURES = {
    "acquisition_cost": "aggregate acquisition cost",
    "payments_received": "aggregate payments received",
    "payments_actual": "actual payments",
    "payments_estimated": "estimated payments",
    "payments_total": "total payments",
    "rx_all": "total prescriptions",
    "rx_340b": "340B prescriptions",
}
_PLACES = {
    "in_house": "dispensed in house",
    "contract": "dispensed through contract pharmacies",
}


def _place(schedule: str) -> tuple[str, str]:
    for prefix in ("in_house", "contract", "administered"):
        if schedule.startswith(prefix + "_"):
            return prefix, schedule.removeprefix(prefix + "_")
    raise ValueError(schedule)


def _value(row: Row | None) -> Decimal | None:
    """Return the number a row holds, or None when absent, in words or withheld."""
    if row is None or row.claims_withheld:
        return None
    if row.claims is not None:
        return Decimal(row.claims)
    return row.amount


def _percent_tolerance(filed: Decimal | None) -> Decimal:
    """Return half a unit of the last decimal place the cell holds, at least a billionth."""
    if filed is None:
        return PERCENT_TOLERANCE
    exponent = filed.as_tuple().exponent
    if not isinstance(exponent, int):
        return PERCENT_TOLERANCE
    return max(PERCENT_TOLERANCE, Decimal(5).scaleb(min(exponent, 0) - 1))


def _sum(rows: list[Row | None]) -> Decimal | None:
    """Add cells; None when there are none, or when any holds words or is withheld."""
    present = [r for r in rows if r is not None]
    if not present:
        return None
    values = [_value(r) for r in present]
    if any(v is None for v in values):
        return None
    return sum((v for v in values if v is not None), Decimal(0))


def _tables() -> tuple[tuple[str, str, str], ...]:
    """(schedule, unit label, rule kind) for every row the template totals."""
    out: list[tuple[str, str, str]] = []
    for rows in (OH_IN_HOUSE_ROWS, OH_CONTRACT_ROWS, OH_ADMINISTERED_ROWS):
        out.extend((schedule, unit, "sum") for schedule, _, unit in rows if unit != PERCENT)
    return tuple(out)


def checks(filing: Filing) -> tuple[Check, ...]:
    """Run every tie-out rule of the Ohio form on one filing."""
    fid = filing.meta.filing_id
    index = {(r.schedule, r.line): r for r in filing.rows}
    out: list[Check] = []

    for schedule, unit, _ in _tables():
        total = index.get((schedule, OH_TOTAL))
        if total is None:
            continue
        place, measure = _place(schedule)
        parts = [index.get((schedule, key)) for key in PAYERS]
        where = {
            "in_house": "dispensed in house",
            "contract": "dispensed through contract pharmacies",
            "administered": "administered",
        }[place]
        note = " (the Indeterminate column is not part of the total)" if place == "contract" else ""
        out.append(
            Check(
                fid,
                f"{schedule}.rows=total",
                Basis.FORM,
                f"The five payer cells of {_MEASURES[measure]} {where} add up to "
                f"the Total cell{note}",
                _sum(parts),
                _value(total),
                unit=COUNT if unit == COUNT else USD,
                tolerance=Decimal(0) if unit == COUNT else USD_TOLERANCE,
            )
        )

    actual = "administered_payments_actual"
    estimated = "administered_payments_estimated"
    total_schedule = "administered_payments_total"
    for key in (*PAYERS, OH_TOTAL):
        row = index.get((total_schedule, key))
        if row is None:
            continue
        out.append(
            Check(
                fid,
                f"{total_schedule}.{key}=actual+estimated",
                Basis.FORM,
                f"Administered drugs, {key.replace('_', ' ')} column: total payments equal "
                "actual payments plus estimated payments",
                _sum([index.get((actual, key)), index.get((estimated, key))]),
                _value(row),
                tolerance=USD_TOLERANCE,
            )
        )

    for schedule, (numerator, denominator) in OH_PERCENT_OF.items():
        for key in (*PAYERS, OH_INDETERMINATE, OH_TOTAL):
            row = index.get((schedule, key))
            if row is None:
                continue
            top, bottom = _value(index.get((numerator, key))), _value(index.get((denominator, key)))
            expected = None
            if top is not None and bottom is not None and bottom != 0:
                # A cell formatted as a percentage stores a fraction of one.
                scale = 1 if OH_FRACTION_NOTE in row.note else 100
                expected = top / bottom * scale
            out.append(
                Check(
                    fid,
                    f"{schedule}.{key}=340b/all",
                    Basis.FORM,
                    f"{_place(schedule)[0].replace('_', '-')} {key.replace('_', ' ')} column: "
                    "the percentage equals the 340B prescriptions over all "
                    "prescriptions, times 100",
                    expected,
                    _value(row),
                    unit=PERCENT,
                    tolerance=_percent_tolerance(_value(row)),
                )
            )
    return tuple(out)


def _figure(value: Decimal, unit: str) -> str:
    """Write a figure for a note: dollars to the cent, counts whole, percentages trimmed."""
    if unit == USD:
        return f"{value:.2f}"
    if unit == COUNT:
        return f"{value:.0f}"
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text or "0"


def note_text(check: Check) -> str:
    """Say in plain words what the cells of a failed rule hold, and nothing about why.

    The sentence names the table and the column and gives the two numbers the rule compares.
    It does not say which of the two is right.
    """
    if check.expected is None or check.filed is None:
        raise ValueError("a rule that does not apply has no note")
    schedule, _, rest = check.rule.partition(".")
    key = rest.split("=")[0]
    column = key.replace("_", " ")
    expected = _figure(check.expected, check.unit)
    filed = _figure(check.filed, check.unit)
    if rest.endswith("=total"):
        place, measure = _place(schedule)
        where = f"{_MEASURES[measure].capitalize()}, {_PLACES.get(place, 'administered drugs')}"
        leaving = " The Indeterminate cell is not part of the total." if place == "contract" else ""
        return (
            f"{where}. The total cell holds {filed}. The five payer cells add to "
            f"{expected}.{leaving}"
        )
    if rest.endswith("=actual+estimated"):
        return (
            f"Administered drugs, {column} column. The total payments cell holds {filed}. "
            f"The actual payments cell and the estimated payments cell add to {expected}."
        )
    place = _place(schedule)[0].replace("_", "-")
    return (
        f"The {place} percentage cell, {column} column, holds {filed}. "
        f"The 340B prescriptions divided by all prescriptions in the same column give {expected}"
        " when the percentage is written the way the cell is."
    )
