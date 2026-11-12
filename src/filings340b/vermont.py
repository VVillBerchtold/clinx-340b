"""Tie-out rules and measures for Vermont's FY2025 340B Program Financial Reporting Detail.

The page prints four payment rows by distribution channel and their total, the
acquisition cost, three expense rows and their total, a net revenue figure with
the note "(payments received minus acquisition costs minus expenses)", and an
operating margin as a percentage. It prints no schedule letters or line numbers;
rows are found by the keys this dataset assigns (see ``forms.VT_LINES``).

Rules marked ``form`` are ones the page itself states: a total row beside its
rows, and the net revenue note. The operating margin rule is a ``comparison``:
the page does not say how the margin is calculated. A difference is recorded and
shown; the filed figures are never changed.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from filings340b.model import Basis, Check, Filing

PAYMENT_CHANNELS = (
    "in_house_pharmacy",
    "contract_pharmacy",
    "administered_paid_separately",
    "administered_bundled",
)
EXPENSE_ROWS = ("contract_pharmacies", "internal", "outside_vendors")


def _amount(filing: Filing, schedule: str, line: str) -> Decimal | None:
    for row in filing.rows:
        if (row.schedule, row.line) == (schedule, line):
            return row.amount
    return None


def _sum(filing: Filing, schedule: str, lines: tuple[str, ...]) -> Decimal | None:
    """Add the printed figures of some rows; a cell with no figure (N/R) adds nothing."""
    found = [v for v in (_amount(filing, schedule, line) for line in lines) if v is not None]
    return sum(found, Decimal(0)) if found else None


def _net_revenue_expected(filing: Filing) -> Decimal | None:
    received = _amount(filing, "payments", "total")
    cost = _amount(filing, "acquisition", "cost")
    expenses = _amount(filing, "expenses", "total")
    if received is None or cost is None or expenses is None:
        return None
    return received - cost - expenses


def _margin_expected(filing: Filing) -> Decimal | None:
    """Net revenue divided by payments received, as a percentage at the printed precision."""
    net = _amount(filing, "result", "net_revenue")
    received = _amount(filing, "payments", "total")
    printed = _amount(filing, "result", "operating_margin")
    if net is None or received is None or received == 0 or printed is None:
        return None
    exponent = int(printed.as_tuple().exponent)
    return (net / received * 100).quantize(Decimal(1).scaleb(exponent), rounding=ROUND_HALF_UP)


def checks(filing: Filing) -> tuple[Check, ...]:
    """Run every tie-out rule on one Vermont filing."""
    fid = filing.meta.filing_id
    return (
        Check(
            fid,
            "payments.rows=total",
            Basis.FORM,
            "The four payment rows add up to Total 340B Payments Received",
            _sum(filing, "payments", PAYMENT_CHANNELS),
            _amount(filing, "payments", "total"),
        ),
        Check(
            fid,
            "expenses.rows=total",
            Basis.FORM,
            "The three expense rows add up to Total 340B Expenses",
            _sum(filing, "expenses", EXPENSE_ROWS),
            _amount(filing, "expenses", "total"),
        ),
        Check(
            fid,
            "net_revenue=payments-acquisition-expenses",
            Basis.FORM,
            "340B Net Revenue equals Total 340B Payments Received minus 340B Prescription "
            "Drug Acquisition Costs minus Total 340B Expenses",
            _net_revenue_expected(filing),
            _amount(filing, "result", "net_revenue"),
        ),
        Check(
            fid,
            "operating_margin=net_revenue/payments",
            Basis.COMPARISON,
            "340B Operating Margin beside 340B Net Revenue divided by Total 340B Payments "
            "Received, at the precision the page prints (percentage points)",
            _margin_expected(filing),
            _amount(filing, "result", "operating_margin"),
            unit="percent",
        ),
    )


def measures(filing: Filing) -> tuple[tuple[str, str, Decimal | None], ...]:
    """Return (measure, formula, value) for the derived measures of one Vermont filing.

    The same three measures as Rhode Island's, on Vermont's rows. The share is
    rounded to six decimal places and left blank when the margin is not above zero.
    """
    received = _amount(filing, "payments", "total")
    cost = _amount(filing, "acquisition", "cost")
    pharmacies = _amount(filing, "expenses", "contract_pharmacies")
    vendors = _amount(filing, "expenses", "outside_vendors")
    margin = received - cost if received is not None and cost is not None else None
    external = pharmacies + vendors if pharmacies is not None and vendors is not None else None
    share: Decimal | None = None
    if margin is not None and external is not None and margin > 0:
        share = (external / margin).quantize(Decimal("0.000001"))
    return (
        (
            "gross_margin",
            "Total 340B Payments Received minus 340B Prescription Drug Acquisition Costs",
            margin,
        ),
        (
            "external_cost",
            "Payments Made to Contract Pharmacies plus Payments Made to Outside Vendors",
            external,
        ),
        (
            "external_share_of_margin",
            "external_cost divided by gross_margin; blank when gross_margin is not above zero",
            share,
        ),
    )
