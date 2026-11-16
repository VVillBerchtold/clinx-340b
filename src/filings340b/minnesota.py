"""Tie-out rules for Minnesota's report to the legislature (Appendix Tables 6.1 and 6.2).

The Minnesota Department of Health publishes figures about the covered entities it
names; the entities' own filings are not public. Table 6.1 prints one row per entity
with one net revenue figure and one percentage of the statewide total. Table 6.2 prints
six rows: the named group, the remaining entities and a total, each unadjusted and
adjusted. Each Table 6.1 row is a record of its own; Table 6.2 and the report's framing
text are one statewide record.

So these rules compare figures across records. They are attached to the record they
describe: the entity rows carry the percentage comparison, the statewide record carries
the rest. Rules marked ``form`` are ones the report's own text states (the number of
entities, the Table 6.1 group's total, a total row beside its rows). Rules marked
``comparison`` are ones the report does not state. A difference is recorded and shown;
the published figures are never changed.

The report with 2023 data prints other tables: Appendix Table 5 (one row per named entity) and
Appendix Table 6 (five groupings by five payer columns). Its entity rows carry the percentage
comparison against Table 6's grand total, and its statewide record carries the number of
entities the paragraph above Table 5 states, the sums of Table 6's rows and columns beside
their Total, and a comparison of the Table 5 rows with the share the paragraph states.

Minnesota has no acquisition cost and no payments to pharmacies or vendors, so it has
no measures.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal

from filings340b.forms import (
    KIND_STATE_ROW,
    KIND_STATE_TOTALS,
    MN_ENTITY_SCHEDULE,
    MN_FORM,
    MN_NOTE_SCHEDULE,
    MN_TABLE5_SCHEDULE,
    MN_TABLE6_GROUPS,
    MN_TABLE6_PAYERS,
    MN_TABLE6_SCHEDULE,
    MN_TOTAL_DIMENSIONS,
    MN_TOTALS_SCHEDULE,
)
from filings340b.model import Basis, Check, Filing

# The sentence above Table 6.1 (2024 data) states how many entities the table lists; so does
# the sentence above Table 5 (2023 data).
_STATED_ENTITIES = re.compile(r"\b(?:MDH identified|There were) (\d+) Covered Entities\b")
# The same sentence of the 2023 report says what share of statewide net revenue they made.
_STATED_SHARE = re.compile(r"\btogether generated the top (\d+)% of statewide net 340B revenue\b")


def _amount(filing: Filing, schedule: str, line: str) -> Decimal | None:
    for row in filing.rows:
        if (row.schedule, row.line) == (schedule, line):
            return row.amount
    return None


def _total(filing: Filing, key: str) -> Decimal | None:
    return _amount(filing, MN_TOTALS_SCHEDULE, f"{key}_net_revenue")


def _entities(everyone: tuple[Filing, ...], year: int) -> tuple[Filing, ...]:
    return tuple(
        f
        for f in everyone
        if f.meta.form == MN_FORM
        and f.meta.record_kind == KIND_STATE_ROW
        and f.meta.reporting_year == year
    )


def _statewide(everyone: tuple[Filing, ...], year: int) -> Filing | None:
    found = [
        f
        for f in everyone
        if f.meta.form == MN_FORM
        and f.meta.record_kind == KIND_STATE_TOTALS
        and f.meta.reporting_year == year
    ]
    return found[0] if found else None


def _stated_count(statewide: Filing) -> Decimal | None:
    """Return the number of entities the report's own paragraph says Table 6.1 lists."""
    for row in statewide.rows:
        if row.schedule == MN_NOTE_SCHEDULE:
            found = _STATED_ENTITIES.search(row.label_as_filed)
            if found:
                return Decimal(found.group(1))
    return None


def _share(part: Decimal | None, whole: Decimal | None, printed: Decimal | None) -> Decimal | None:
    """Return part over whole as a percentage, at the number of decimals the report prints."""
    if part is None or whole is None or whole == 0 or printed is None:
        return None
    exponent = int(printed.as_tuple().exponent)
    return (part / whole * 100).quantize(Decimal(1).scaleb(exponent), rounding=ROUND_HALF_UP)


def checks(filing: Filing, everyone: tuple[Filing, ...] = ()) -> tuple[Check, ...]:
    """Run every Minnesota rule that belongs to one record.

    ``everyone`` is every loaded record; the rules compare across them. Without it the
    rules that need another record have nothing to compare and do not apply.
    """
    if filing.meta.record_kind == KIND_STATE_ROW:
        return _entity_checks(filing, everyone)
    if filing.meta.record_kind == KIND_STATE_TOTALS:
        return _statewide_checks(filing, everyone)
    return ()


def _entity_checks(filing: Filing, everyone: tuple[Filing, ...]) -> tuple[Check, ...]:
    statewide = _statewide(everyone, filing.meta.reporting_year)
    if any(row.schedule == MN_TABLE5_SCHEDULE for row in filing.rows):
        return _table_5_entity_checks(filing, statewide)
    whole = _total(statewide, "total_unadjusted") if statewide else None
    printed = _amount(filing, MN_ENTITY_SCHEDULE, "pct_of_statewide")
    return (
        Check(
            filing.meta.filing_id,
            "pct_of_statewide=net_revenue/total_unadjusted",
            Basis.COMPARISON,
            "The printed % of Statewide Net 340B Revenue beside this row's Net 340B Revenue "
            "divided by Table 6.2's Total, unadjusted, times 100, at the precision the report "
            "prints (percentage points)",
            _share(_amount(filing, MN_ENTITY_SCHEDULE, "net_revenue"), whole, printed),
            printed,
            unit="percent",
        ),
    )


def _table_5_entity_checks(filing: Filing, statewide: Filing | None) -> tuple[Check, ...]:
    whole = _amount(statewide, MN_TABLE6_SCHEDULE, "total_total") if statewide else None
    printed = _amount(filing, MN_TABLE5_SCHEDULE, "pct_of_statewide")
    return (
        Check(
            filing.meta.filing_id,
            "pct_of_statewide=net_revenue/table_6.total_total",
            Basis.COMPARISON,
            "The printed % of Statewide Net 340B Revenue beside this row's Net 340B Revenue "
            "divided by the Total of Table 6 (Total row, Total column), times 100, at the "
            "precision the report prints (percentage points)",
            _share(_amount(filing, MN_TABLE5_SCHEDULE, "net_revenue"), whole, printed),
            printed,
            unit="percent",
        ),
    )


def _table_6_checks(filing: Filing, everyone: tuple[Filing, ...]) -> tuple[Check, ...]:
    """Rules on the 2023 report's statewide record: Table 5 and Table 6."""
    fid = filing.meta.filing_id
    entities = _entities(everyone, filing.meta.reporting_year)
    out = [
        Check(
            fid,
            "table_5.rows=stated_entities",
            Basis.FORM,
            "The number of rows Table 5 prints beside the number of Covered Entities the "
            "paragraph above it states",
            Decimal(len(entities)) if entities else None,
            _stated_count(filing),
            unit="count",
        )
    ]
    groups = [key for key, _, _ in MN_TABLE6_GROUPS if key != "total"]
    for payer, heading in MN_TABLE6_PAYERS:
        out.append(
            Check(
                fid,
                f"table_6.column_{payer}.rows=total",
                Basis.FORM,
                f"The five groupings' {heading} figures of Table 6 added together beside the "
                "Total row",
                _added([_amount(filing, MN_TABLE6_SCHEDULE, f"{g}_{payer}") for g in groups]),
                _amount(filing, MN_TABLE6_SCHEDULE, f"total_{payer}"),
            )
        )
    for key, label, _ in MN_TABLE6_GROUPS:
        parts = [
            _amount(filing, MN_TABLE6_SCHEDULE, f"{key}_{payer}")
            for payer, _ in MN_TABLE6_PAYERS
            if payer != "total"
        ]
        out.append(
            Check(
                fid,
                f"table_6.row_{key}.payers=total",
                Basis.FORM,
                f"The four payer columns of Table 6's {label} row added together beside its "
                "Total column",
                _added(parts),
                _amount(filing, MN_TABLE6_SCHEDULE, f"{key}_total"),
            )
        )
    whole = _amount(filing, MN_TABLE6_SCHEDULE, "total_total")
    stated = _stated_share(filing)
    shown = _sum_entities(entities, MN_TABLE5_SCHEDULE)
    out.append(
        Check(
            fid,
            "table_5.sum/table_6.total_total=stated_share",
            Basis.COMPARISON,
            "The share the paragraph above Table 5 states its entities generated beside the "
            "Net 340B Revenue rows of Table 5 added together, divided by the Total of Table 6, "
            "times 100, to a whole percent (percentage points)",
            (shown / whole * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)
            if shown is not None and whole
            else None,
            stated,
            unit="percent",
        )
    )
    return tuple(out)


def _added(figures: list[Decimal | None]) -> Decimal | None:
    """Add a table's rows, or return nothing when a row prints no figure."""
    if not figures or any(figure is None for figure in figures):
        return None
    return sum((figure for figure in figures if figure is not None), Decimal(0))


def _stated_share(statewide: Filing) -> Decimal | None:
    """Return the share of statewide net revenue the paragraph above Table 5 states."""
    for row in statewide.rows:
        if row.schedule == MN_NOTE_SCHEDULE:
            found = _STATED_SHARE.search(row.label_as_filed)
            if found:
                return Decimal(found.group(1))
    return None


def _statewide_checks(filing: Filing, everyone: tuple[Filing, ...]) -> tuple[Check, ...]:
    if any(row.schedule == MN_TABLE6_SCHEDULE for row in filing.rows):
        return _table_6_checks(filing, everyone)
    fid = filing.meta.filing_id
    entities = _entities(everyone, filing.meta.reporting_year)
    out = [
        Check(
            fid,
            "table_6_1.rows=stated_entities",
            Basis.FORM,
            "The number of rows Table 6.1 prints beside the number of Covered Entities the "
            "paragraph above it states",
            Decimal(len(entities)) if entities else None,
            _stated_count(filing),
            unit="count",
        ),
        Check(
            fid,
            "table_6_1.sum=table_6_2.top_unadjusted",
            Basis.FORM,
            "The Net 340B Revenue rows of Table 6.1 added together beside Table 6.2's Top 25, "
            "unadjusted",
            _sum_entities(entities),
            _total(filing, "top_unadjusted"),
        ),
    ]
    for kind in ("unadjusted", "adjusted"):
        top, remaining = _total(filing, f"top_{kind}"), _total(filing, f"remaining_{kind}")
        out.append(
            Check(
                fid,
                f"table_6_2.{kind}_rows=total",
                Basis.FORM,
                f"Table 6.2's Top 25, {kind} plus Remaining 156, {kind} beside Total, {kind}",
                top + remaining if top is not None and remaining is not None else None,
                _total(filing, f"total_{kind}"),
            )
        )
    for dimension, label in MN_TOTAL_DIMENSIONS:
        kind = dimension.rsplit("_", 1)[1]
        printed = _amount(filing, MN_TOTALS_SCHEDULE, f"{dimension}_pct_of_total")
        out.append(
            Check(
                fid,
                f"table_6_2.{dimension}.pct_of_total=net_revenue/total_{kind}",
                Basis.COMPARISON,
                f"The printed % of Total for {label} beside its Net 340B Revenue divided by "
                f"Total, {kind}, times 100, at the precision the report prints "
                "(percentage points)",
                _share(_total(filing, dimension), _total(filing, f"total_{kind}"), printed),
                printed,
                unit="percent",
            )
        )
    return tuple(out)


def _sum_entities(
    entities: tuple[Filing, ...], schedule: str = MN_ENTITY_SCHEDULE
) -> Decimal | None:
    found = [_amount(f, schedule, "net_revenue") for f in entities]
    figures = [v for v in found if v is not None]
    return sum(figures, Decimal(0)) if figures else None
