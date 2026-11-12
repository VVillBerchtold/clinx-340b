"""The forms the dataset knows. A filing names its form; nothing is assumed from the state.

A form fixes which schedule and line keys a transcription may use, what unit
each row's amount is in, and which tie-out rules and measures apply to it.

Rhode Island's Form RIOAG-340B prints schedule letters and line numbers, and
those are what ``schedule`` and ``line`` hold. Vermont's financial reporting
page prints neither, so for Vermont ``schedule`` and ``line`` hold short keys
assigned by this dataset, and ``label_as_filed`` holds the label the page prints.

Minnesota is a different kind of source. The Minnesota Department of Health prints,
in a report to the legislature, one table row per covered entity it names (Appendix
Table 6.1) and a six-row table of totals (Appendix Table 6.2). These are the State's
published figures about the entities, not the entities' own filings. Each printed
row of Table 6.1 is one record, so a record's ``schedule`` and ``line`` hold keys
assigned by this dataset, as Vermont's do.
"""

from __future__ import annotations

from dataclasses import dataclass

RI_FORM = "ri-oag-340b"
VT_FORM = "vt-gmcb-340b-financial"
MN_FORM = "mn-mdh-340b-report"

# What a record is. A filing is an entity's own report; the others are rows the
# State published about entities.
KIND_FILING = "filing"
KIND_STATE_ROW = "state_report_row"
KIND_STATE_TOTALS = "state_report_totals"
RECORD_KINDS = (KIND_FILING, KIND_STATE_ROW, KIND_STATE_TOTALS)

USD = "usd"
PERCENT = "percent"
COUNT = "count"
# A row that carries no figure: a yes/no answer, or text the page prints.
NO_FIGURE = "none"
UNITS = (USD, PERCENT, COUNT, NO_FIGURE)

RI_SCHEDULES = frozenset("ABCDEFGHI")

# Vermont: (schedule key, line key, label the page prints, unit), in printed order.
# The keys are assigned by this dataset; the page prints no schedule or line numbers.
VT_LINES: tuple[tuple[str, str, str, str], ...] = (
    ("payments", "in_house_pharmacy", "In-House Pharmacy Dispensed", USD),
    ("payments", "contract_pharmacy", "Contract Pharmacy Dispensed", USD),
    ("payments", "administered_paid_separately", "Administered Drugs Paid Separately", USD),
    ("payments", "administered_bundled", "Administered Drugs Bundled Payments", USD),
    ("payments", "total", "Total 340B Payments Received", USD),
    ("acquisition", "cost", "340B Prescription Drug Acquisition Costs", USD),
    ("expenses", "contract_pharmacies", "Payments Made to Contract Pharmacies", USD),
    ("expenses", "internal", "Internal 340B Program Expenses", USD),
    ("expenses", "outside_vendors", "Payments Made to Outside Vendors", USD),
    ("expenses", "total", "Total 340B Expenses", USD),
    ("result", "net_revenue", "340B Net Revenue", USD),
    ("result", "operating_margin", "340B Operating Margin", PERCENT),
)
# Text the page prints below the figures, kept as a row with no figure.
VT_NOTE_SCHEDULE = "page_note"
VT_SCHEDULES = frozenset({s for s, _, _, _ in VT_LINES} | {VT_NOTE_SCHEDULE})


# Minnesota Table 6.1: the two figures printed on each entity's row.
MN_ENTITY_SCHEDULE = "table_6_1"
MN_ENTITY_LINES: tuple[tuple[str, str, str], ...] = (
    ("net_revenue", "Net 340B Revenue ($)", USD),
    ("pct_of_statewide", "% of Statewide Net 340B Revenue", PERCENT),
)
# Minnesota Table 6.2: (dimension key, label the table prints), in printed order.
# Each carries a net revenue figure and a percentage of the total.
MN_TOTALS_SCHEDULE = "table_6_2"
MN_TOTAL_DIMENSIONS: tuple[tuple[str, str], ...] = (
    ("top_unadjusted", "Top 25, unadjusted"),
    ("remaining_unadjusted", "Remaining 156, unadjusted"),
    ("total_unadjusted", "Total, unadjusted"),
    ("top_adjusted", "Top 25, adjusted"),
    ("remaining_adjusted", "Remaining 156, adjusted"),
    ("total_adjusted", "Total, adjusted"),
)
MN_TOTAL_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("net_revenue", "Net 340B Revenue ($)", USD),
    ("pct_of_total", "% of Total", PERCENT),
)
MN_NOTE_SCHEDULE = "page_note"
MN_LINES: dict[tuple[str, str], str] = {
    **{(MN_ENTITY_SCHEDULE, line): unit for line, _, unit in MN_ENTITY_LINES},
    **{
        (MN_TOTALS_SCHEDULE, f"{dimension}_{column}"): unit
        for dimension, _ in MN_TOTAL_DIMENSIONS
        for column, _, unit in MN_TOTAL_COLUMNS
    },
}
MN_SCHEDULES = frozenset({MN_ENTITY_SCHEDULE, MN_TOTALS_SCHEDULE, MN_NOTE_SCHEDULE})


def mn_entity_type(printed_type: str, record_kind: str) -> str:
    """Return the ``entity_type`` of a Minnesota record from the type its row prints.

    ``hospital`` when the printed type says Hospital, ``other`` for any other printed
    type (nothing is interpreted from abbreviations), ``state_total`` for the statewide record.
    """
    if record_kind == KIND_STATE_TOTALS:
        return "state_total"
    return "hospital" if "hospital" in printed_type.casefold() else "other"


class UnknownFormError(ValueError):
    """A filing names a form the dataset does not know."""


@dataclass(frozen=True, slots=True)
class Form:
    """What a form fixes for the filings made on it."""

    key: str
    schedules: frozenset[str]
    # True when the form has a Schedule E whose rows are given a spending category.
    has_spending_categories: bool
    # The kinds of record a filing on this form may be.
    record_kinds: tuple[str, ...] = (KIND_FILING,)

    def unit_of(self, schedule: str, line: str) -> str:
        """Return the unit of the amount a row carries."""
        if self.key == RI_FORM:
            return NO_FIGURE if schedule == "I" else USD
        if self.key == MN_FORM:
            return MN_LINES.get((schedule, line), NO_FIGURE)
        for s, k, _, unit in VT_LINES:
            if (s, k) == (schedule, line):
                return unit
        return NO_FIGURE

    def knows(self, schedule: str, line: str) -> bool:
        """Say whether a schedule and line key can appear in a transcription on this form."""
        if self.key == RI_FORM:
            return schedule in self.schedules
        if self.key == MN_FORM:
            if schedule == MN_NOTE_SCHEDULE:
                return line.startswith("note_")
            return (schedule, line) in MN_LINES
        if schedule == VT_NOTE_SCHEDULE:
            return line.startswith("note_")
        return any((s, k) == (schedule, line) for s, k, _, _ in VT_LINES)


FORMS: dict[str, Form] = {
    RI_FORM: Form(RI_FORM, RI_SCHEDULES, has_spending_categories=True),
    VT_FORM: Form(VT_FORM, VT_SCHEDULES, has_spending_categories=False),
    MN_FORM: Form(
        MN_FORM,
        MN_SCHEDULES,
        has_spending_categories=False,
        record_kinds=(KIND_STATE_ROW, KIND_STATE_TOTALS),
    ),
}


def form_of(key: str) -> Form:
    """Return the form a filing names, or refuse an unknown one."""
    try:
        return FORMS[key]
    except KeyError:
        raise UnknownFormError(f"unknown form {key!r}; known forms: {', '.join(FORMS)}") from None
