"""Tie-out rules for Rhode Island Form RIOAG-340B, and the measures derived from it.

Each filing names its form, and ``checks`` and ``measures`` use that form's rules:
Rhode Island's are here, Vermont's are in ``vermont.py``.

Most rules compare two figures the form itself says agree: a schedule's rows
and its printed total, or a total and the Schedule A line it says it supports.
Two rules are comparisons the form does not make: Schedule H's total beside
Schedule A line 6, and the claim counts of Schedules C and G. Every rule carries
its basis, so a comparison is never presented as a rule of the form.

A difference is recorded and shown; the filed figures are never changed.
"""

from __future__ import annotations

from decimal import Decimal

from filings340b import minnesota, vermont
from filings340b.forms import MN_FORM, RI_FORM, VT_FORM, UnknownFormError
from filings340b.model import Basis, Check, Filing, Row, RowKind

# Schedule A line each supporting schedule says it supports.
SUPPORTS = {"B": "1", "C": "2", "D": "3", "E": "4", "F": "5"}


def _line_a(filing: Filing, line: str) -> Decimal | None:
    for row in filing.schedule("A"):
        if row.line == line:
            return row.amount
    return None


def _parts(rows: tuple[Row, ...]) -> tuple[Row, ...]:
    return tuple(r for r in rows if r.row_kind is not RowKind.TOTAL)


def _printed_total(rows: tuple[Row, ...]) -> Row | None:
    totals = [r for r in rows if r.row_kind is RowKind.TOTAL]
    return totals[0] if totals else None


def _sum_amounts(rows: tuple[Row, ...]) -> Decimal | None:
    amounts = [r.amount for r in _parts(rows) if r.amount is not None]
    return sum(amounts, Decimal(0)) if amounts else None


def _sum_claims(filing: Filing, letter: str) -> Decimal | None:
    """Sum a schedule's claim counts.

    Without the private counts the sum comes from the results file (see ``sealing.py``).
    """
    if letter in filing.claim_sums:
        return Decimal(filing.claim_sums[letter])
    claims = [r.claims for r in _parts(filing.schedule(letter)) if r.claims is not None]
    return Decimal(sum(claims)) if claims else None


def schedule_total(filing: Filing, letter: str) -> Decimal | None:
    """Return a schedule's printed total, or the sum of its rows when none is printed."""
    rows = filing.schedule(letter)
    total = _printed_total(rows)
    if total is not None and total.amount is not None:
        return total.amount
    return _sum_amounts(rows)


def claim_total(filing: Filing, letter: str) -> Decimal | None:
    """Return a schedule's printed claim total, or the sum of its rows' claims."""
    rows = filing.schedule(letter)
    total = _printed_total(rows)
    if total is not None and total.claims is not None:
        return Decimal(total.claims)
    return _sum_claims(filing, letter)


def _net_revenue_expected(filing: Filing) -> Decimal | None:
    lines = [_line_a(filing, n) for n in "12345"]
    if any(v is None for v in lines):
        return None
    cost, received, pharmacies, vendors, admin = (v for v in lines if v is not None)
    return received - cost - pharmacies - vendors - admin


def checks(filing: Filing, everyone: tuple[Filing, ...] = ()) -> tuple[Check, ...]:
    """Run every tie-out rule of the filing's form on one filing.

    ``everyone`` is every loaded filing. Rhode Island's and Vermont's rules look at one
    filing only. Minnesota's compare figures across its records, so pass all filings.
    """
    if filing.meta.form == RI_FORM:
        return _ri_checks(filing)
    if filing.meta.form == VT_FORM:
        return vermont.checks(filing)
    if filing.meta.form == MN_FORM:
        return minnesota.checks(filing, everyone)
    raise UnknownFormError(f"no tie-out rules for form {filing.meta.form!r}")


def _ri_checks(filing: Filing) -> tuple[Check, ...]:
    fid = filing.meta.filing_id
    out = [
        Check(
            fid,
            "A6=A2-A1-A3-A4-A5",
            Basis.FORM,
            "Schedule A line 6 equals line 2 minus lines 1, 3, 4 and 5",
            _net_revenue_expected(filing),
            _line_a(filing, "6"),
        )
    ]
    for letter, line in SUPPORTS.items():
        rows = filing.schedule(letter)
        total = _printed_total(rows)
        out.append(
            Check(
                fid,
                f"{letter}.rows=total",
                Basis.FORM,
                f"Schedule {letter} rows add up to its printed total",
                _sum_amounts(rows),
                total.amount if total else None,
            )
        )
        out.append(
            Check(
                fid,
                f"{letter}.total=A{line}",
                Basis.FORM,
                f"Schedule {letter} total equals Schedule A line {line}",
                _line_a(filing, line),
                schedule_total(filing, letter),
            )
        )
    for letter in "GH":
        rows = filing.schedule(letter)
        total = _printed_total(rows)
        out.append(
            Check(
                fid,
                f"{letter}.rows=total",
                Basis.FORM,
                f"Schedule {letter} rows add up to its printed total",
                _sum_amounts(rows),
                total.amount if total else None,
            )
        )
    out.append(
        Check(
            fid,
            "H.total=A6",
            Basis.COMPARISON,
            "Schedule H total beside Schedule A line 6",
            _line_a(filing, "6"),
            schedule_total(filing, "H"),
        )
    )
    for letter in "CG":
        rows = filing.schedule(letter)
        total = _printed_total(rows)
        out.append(
            Check(
                fid,
                f"{letter}.claims=total",
                Basis.FORM,
                f"Schedule {letter} claim counts add up to its printed claim total",
                _sum_claims(filing, letter),
                Decimal(total.claims) if total and total.claims is not None else None,
                unit="count",
            )
        )
    out.append(
        Check(
            fid,
            "C.claims=G.claims",
            Basis.COMPARISON,
            "Schedule G claim total beside Schedule C claim total",
            claim_total(filing, "C"),
            claim_total(filing, "G"),
            unit="count",
        )
    )
    return tuple(out)


def measures(filing: Filing) -> tuple[tuple[str, str, Decimal | None], ...]:
    """Return (measure, formula, value) for the derived measures of one filing.

    Ratios are rounded to six decimal places; nothing filed is rounded.
    """
    if filing.meta.form == VT_FORM:
        return vermont.measures(filing)
    if filing.meta.form == MN_FORM:
        # Minnesota prints no acquisition cost and no payments to pharmacies or vendors.
        return ()
    if filing.meta.form != RI_FORM:
        raise UnknownFormError(f"no measures for form {filing.meta.form!r}")
    cost, received = _line_a(filing, "1"), _line_a(filing, "2")
    pharmacies, vendors = _line_a(filing, "3"), _line_a(filing, "4")
    margin = received - cost if received is not None and cost is not None else None
    external = pharmacies + vendors if pharmacies is not None and vendors is not None else None
    share: Decimal | None = None
    if margin is not None and external is not None and margin > 0:
        share = (external / margin).quantize(Decimal("0.000001"))
    return (
        ("gross_margin", "Schedule A line 2 minus line 1", margin),
        ("external_cost", "Schedule A line 3 plus line 4", external),
        ("external_share_of_margin", "external_cost divided by gross_margin", share),
    )
