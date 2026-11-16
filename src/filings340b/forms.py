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

Idaho is a third kind. The State Controller publishes one report of statewide totals
and names no covered entity; the entities' filings are confidential. The whole report
is one record. Every printed cell of its tables, its highlight tiles and its chart is a
row, under schedule and line keys assigned by this dataset.

Maine is a fourth kind, and like Idaho's its one record is a statewide report of totals. The
Maine Health Data Organization publishes one report that adds its hospitals together and names
no figure for any single hospital. Its totals, its two tables of drugs (each row a drug, with
figures added across the hospitals) and its sentences that state a figure are rows. Each
hospital's own description of how it uses the program is text, listed as an attachment.

Minnesota's earlier report (2023 data) prints different tables from the later one: Appendix
Table 5 (one row per named entity, with three figures and a text cell) and Appendix Table 6
(five groupings by five payer columns). They are added to the Minnesota form beside Tables 6.1
and 6.2; a record uses the tables of the report it comes from.

Ohio is a fifth kind. Each covered entity files its own report with the Department of
Health as an Excel workbook on the Department's template, so the source of a filing is the
cells of one sheet, not a printed page. Every cell of the template that holds a figure or an
answer is a row, under schedule and line keys assigned by this dataset: a schedule is one
row of the template's tables (for example ``in_house_acquisition_cost``) and a line is the
payer column (``commercial``, ``medicare``, ``total``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

RI_FORM = "ri-oag-340b"
VT_FORM = "vt-gmcb-340b-financial"
MN_FORM = "mn-mdh-340b-report"
ID_FORM = "id-sco-340b-report"
ME_FORM = "me-mhdo-340b-report"
OH_FORM = "oh-odh-340b-report"

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

# The report with 2023 data, Appendix Table 5: the figures and the text cell printed on each
# entity's row, (line key, column heading the table prints, unit), in printed order. The
# entity's name, type and city are the record's own (``meta.toml``), as in Table 6.1.
MN_TABLE5_SCHEDULE = "table_5"
MN_TABLE5_LINES: tuple[tuple[str, str, str], ...] = (
    ("scope", "Scope of Reported Data", NO_FIGURE),
    ("net_revenue", "Net 340B Revenue ($)", USD),
    ("pct_of_statewide", "% of Statewide Net 340B Revenue", PERCENT),
    (
        "pct_mhcp",
        "% of Entity\u2019s 340B Net Revenue attributed to Minnesota Health Care Programs",
        PERCENT,
    ),
)
# Appendix Table 6: (row key, label the table prints, printed Covered Entity Major Type), in
# printed order. The Total row prints no major type.
MN_TABLE6_SCHEDULE = "table_6"
MN_TABLE6_GROUPS: tuple[tuple[str, str, str], ...] = (
    ("general_acute_care", "General Acute Care Hospitals (DSH)", "Hospital"),
    ("critical_access", "Critical Access Hospitals", "Hospital"),
    ("other_hospitals", "Other Hospitals", "Hospital"),
    ("disease_specific_grantees", "Disease Specific Federal Grantees", "Grantee"),
    ("safety_net_grantees", "Safety-Net Federal Grantees", "Grantee"),
    ("total", "Total", ""),
)
# The five payer columns, (column key, heading the table prints), in printed order.
MN_TABLE6_PAYERS: tuple[tuple[str, str], ...] = (
    ("commercial", "Commercial"),
    ("medicare", "Medicare"),
    ("mhcp", "Minnesota Health Care Programs (MHCP)"),
    ("other", "Other"),
    ("total", "Total"),
)
MN_TABLE6_MAJOR_HEADING = "Covered Entity Major Type"
MN_TABLE6_GROUPING_HEADING = "Covered Entity Grouping"
MN_LINES: dict[tuple[str, str], str] = {
    **{(MN_ENTITY_SCHEDULE, line): unit for line, _, unit in MN_ENTITY_LINES},
    **{
        (MN_TOTALS_SCHEDULE, f"{dimension}_{column}"): unit
        for dimension, _ in MN_TOTAL_DIMENSIONS
        for column, _, unit in MN_TOTAL_COLUMNS
    },
    **{(MN_TABLE5_SCHEDULE, line): unit for line, _, unit in MN_TABLE5_LINES},
    **{
        (MN_TABLE6_SCHEDULE, f"{group}_{payer}"): USD
        for group, _, _ in MN_TABLE6_GROUPS
        for payer, _ in MN_TABLE6_PAYERS
    },
    **{
        (MN_TABLE6_SCHEDULE, f"{group}_major_type"): NO_FIGURE
        for group, _, major in MN_TABLE6_GROUPS
        if major
    },
}
MN_SCHEDULES = frozenset(
    {
        MN_ENTITY_SCHEDULE,
        MN_TOTALS_SCHEDULE,
        MN_TABLE5_SCHEDULE,
        MN_TABLE6_SCHEDULE,
        MN_NOTE_SCHEDULE,
    }
)


# Idaho: the payer rows every payer table prints, in printed order (line key, printed label).
ID_PAYERS: tuple[tuple[str, str], ...] = (
    ("commercial", "Commercial"),
    ("medicare", "Medicare"),
    ("medicaid", "Medicaid"),
    ("self_pay", "Self-Pay"),
    ("other", "Other"),
    ("uninsured", "Uninsured"),
    ("total", "TOTAL"),
)
ID_TOTAL = "total"
# Idaho's four payer tables: (schedule key, figure key, figure column, unit, percentage column).
ID_PAYER_TABLES: tuple[tuple[str, str, str, str, str], ...] = (
    ("acquisition_cost", "amount", "Aggregate Acquisition Cost", USD, "% of Total Cost"),
    ("payments_received", "amount", "Aggregate Payments Received", USD, "% of Total Payments"),
    (
        "contract_pharmacy_payments",
        "amount",
        "Payments to Contract Pharmacies",
        USD,
        "% of Total CP Payments",
    ),
    ("claims", "claims", "Total Claims", COUNT, "% of Total"),
)
# Idaho's table of how savings were used: (line key, printed label), in printed order.
ID_SAVINGS_SCHEDULE = "savings_use"
ID_SAVINGS_COLUMNS = ("Amount Applied", "% of Total Savings")
ID_SAVINGS_USES: tuple[tuple[str, str], ...] = (
    (
        "under_reimbursement",
        "Offset financial loss due to under-reimbursement from government programs",
    ),
    ("uncompensated_care", "Offset financial loss due to providing uncompensated care"),
    (
        "patient_financial_assistance",
        "Financial assistance for patients who cannot pay for care or medications",
    ),
    ("prescription_assistance", "Prescription medication assistance programs"),
    ("community_health", "Community health programs and outreach/education"),
    ("subsidized_services", "Subsidized health services provided below actual cost"),
    (
        "health_professional_education",
        "Education of health professionals serving underserved populations",
    ),
    ("access_barriers", "Programs addressing barriers to healthcare access"),
    ("other_uses", "Additional / Other reported uses (10 entities*)"),
    ("total", "TOTAL"),
)
ID_HIGHLIGHTS_SCHEDULE = "key_highlights"
ID_CHART_SCHEDULE = "key_financial_metrics"
ID_SUBMISSIONS_SCHEDULE = "submissions"
ID_NOTE_SCHEDULE = "page_note"
# Every printed cell that is a row: (schedule, line, row label, column heading, unit),
# in printed order. A tile or a chart label has no column heading.
ID_CELLS: tuple[tuple[str, str, str, str, str], ...] = (
    (ID_HIGHLIGHTS_SCHEDULE, "total_claims", "Total Claims Dispensed", "", COUNT),
    # The two money tiles print rounded figures with a letter ("$812.9M"); kept as text.
    (ID_HIGHLIGHTS_SCHEDULE, "payments_received", "Aggregate Payments Received", "", NO_FIGURE),
    (ID_HIGHLIGHTS_SCHEDULE, "savings_to_community", "340B Savings to Community", "", NO_FIGURE),
    (ID_HIGHLIGHTS_SCHEDULE, "covered_entities", "Unique Covered Entities", "", COUNT),
    (ID_CHART_SCHEDULE, "contract_pharmacy_payments", "Payments to Contract Pharmacies", "", USD),
    (ID_CHART_SCHEDULE, "acquisition_cost", "Aggregate Acquisition Cost", "", USD),
    (ID_CHART_SCHEDULE, "savings_utilized", "340B Savings Utilized", "", USD),
    (ID_CHART_SCHEDULE, "payments_received", "Aggregate Payments Received", "", USD),
    (ID_SUBMISSIONS_SCHEDULE, "received_count", "Total submissions received", "Count", COUNT),
    (ID_SUBMISSIONS_SCHEDULE, "received_notes", "Total submissions received", "Notes", NO_FIGURE),
    (ID_SUBMISSIONS_SCHEDULE, "child_sites_count", "Total child sites", "Count", COUNT),
    # One printed cell, "62 (100%)", is two rows: the count and the percentage.
    (ID_SUBMISSIONS_SCHEDULE, "complete_count", "Submissions with complete status", "Count", COUNT),
    (ID_SUBMISSIONS_SCHEDULE, "complete_pct", "Submissions with complete status", "Count", PERCENT),
    (
        ID_SUBMISSIONS_SCHEDULE,
        "complete_notes",
        "Submissions with complete status",
        "Notes",
        NO_FIGURE,
    ),
    *(
        cell
        for schedule, figure, column, unit, pct_column in ID_PAYER_TABLES
        for payer, label in ID_PAYERS
        for cell in (
            (schedule, f"{payer}_{figure}", label, column, unit),
            (schedule, f"{payer}_pct", label, pct_column, PERCENT),
        )
    ),
    *(
        cell
        for use, label in ID_SAVINGS_USES
        for cell in (
            (ID_SAVINGS_SCHEDULE, f"{use}_amount", label, ID_SAVINGS_COLUMNS[0], USD),
            (ID_SAVINGS_SCHEDULE, f"{use}_pct", label, ID_SAVINGS_COLUMNS[1], PERCENT),
        )
    ),
)
ID_LINES: dict[tuple[str, str], str] = {
    (schedule, line): unit for schedule, line, _, _, unit in ID_CELLS
}
ID_SCHEDULES = frozenset({schedule for schedule, _ in ID_LINES} | {ID_NOTE_SCHEDULE})


# Maine: the report's totals, printed in sentences, (line key, unit), in printed order. The
# two money figures print rounded with a letter ("$409.9M") and are kept as text.
ME_SUMMARY_SCHEDULE = "summary"
ME_SUMMARY_LINES: tuple[tuple[str, str], ...] = (
    ("hospitals_reporting", COUNT),
    ("acquisition_cost", NO_FIGURE),
    ("pct_of_drug_spend", PERCENT),
    ("estimated_savings", NO_FIGURE),
)
# The two tables of drugs. Each prints, for a drug (an NDC), its total acquisition cost, its
# total estimated savings and the number of hospitals that listed it; a sentence above each
# prints that table's share of the total acquisition cost.
ME_COSTLY_SCHEDULE = "top3_costly"
ME_FREQUENT_SCHEDULE = "top3_frequent"
ME_DRUG_SCHEDULES = (ME_COSTLY_SCHEDULE, ME_FREQUENT_SCHEDULE)
ME_SHARE_LINE = "pct_of_acquisition_cost"
# (figure key, unit). The heading each table prints is the row's ``description_as_filed``.
ME_DRUG_FIGURES: tuple[tuple[str, str], ...] = (
    ("acquisition_cost", USD),
    ("estimated_savings", USD),
    ("hospitals", COUNT),
)
ME_NOTE_SCHEDULE = "page_note"
ME_SCHEDULES = frozenset({ME_SUMMARY_SCHEDULE, *ME_DRUG_SCHEDULES, ME_NOTE_SCHEDULE})
# A drug row's line key is its 11-digit NDC and a figure key, joined by an underscore.
_ME_DRUG_LINE = re.compile(r"^(\d{11})_(acquisition_cost|estimated_savings|hospitals)$")
ME_SUMMARY_UNITS = dict(ME_SUMMARY_LINES)


def me_unit(schedule: str, line: str) -> str | None:
    """Return the unit of a Maine row, or ``None`` when the form has no such row."""
    if schedule == ME_SUMMARY_SCHEDULE:
        return ME_SUMMARY_UNITS.get(line)
    if schedule in ME_DRUG_SCHEDULES:
        if line == ME_SHARE_LINE:
            return PERCENT
        found = _ME_DRUG_LINE.match(line)
        if found:
            return dict(ME_DRUG_FIGURES)[found.group(2)]
    return None


# Ohio: the payer columns of the template's tables, in template order (line key, heading).
OH_PAYERS: tuple[tuple[str, str], ...] = (
    ("commercial", "Commercial Insurance/Private Insurance"),
    ("medicare", "Medicare"),
    ("medicaid", "Medicaid (all states)"),
    ("other_third_party", "Other Third-Party Payor"),
    ("uninsured", "Uninsured/Self-Pay"),
)
# The note of a percentage row whose cell is formatted as a percentage: the number the workbook
# stores is then a fraction of one (0.25 shows as 25%), not the percentage points (25).
OH_FRACTION_NOTE = (
    "The cell is formatted as a percentage, so the stored number is a fraction of one "
    "(0.25 shows as 25%)."
)
OH_TOTAL = "total"
OH_INDETERMINATE = "indeterminate"
# The template's tables: (schedule, line keys of the columns, template row, unit). The figures of a
# count row are kept in the claim fields, a percentage is kept as the number the workbook stores.
OH_IN_HOUSE_ROWS: tuple[tuple[str, int, str], ...] = (
    ("in_house_acquisition_cost", 17, USD),
    ("in_house_payments_received", 18, USD),
    ("in_house_rx_all", 19, COUNT),
    ("in_house_rx_340b", 20, COUNT),
    ("in_house_rx_pct", 21, PERCENT),
)
OH_CONTRACT_ROWS: tuple[tuple[str, int, str], ...] = (
    ("contract_acquisition_cost", 26, USD),
    ("contract_payments_received", 27, USD),
    ("contract_rx_all", 28, COUNT),
    ("contract_rx_340b", 29, COUNT),
    ("contract_rx_pct", 30, PERCENT),
)
OH_ADMINISTERED_ROWS: tuple[tuple[str, int, str], ...] = (
    ("administered_acquisition_cost", 35, USD),
    ("administered_payments_actual", 36, USD),
    ("administered_payments_estimated", 37, USD),
    ("administered_payments_total", 38, USD),
    ("administered_rx_all", 39, COUNT),
    ("administered_rx_340b", 40, COUNT),
    ("administered_rx_pct", 41, PERCENT),
)
# Section 4 and 5: schedule ``costs`` (template row, line key, unit).
OH_COSTS_SCHEDULE = "costs"
OH_COSTS: tuple[tuple[int, str], ...] = (
    (46, "contract_pharmacies"),
    (47, "third_party_administrators"),
    (48, "consultants"),
    (49, "software_it"),
    (50, "other_external"),
    (53, "staffing"),
    (54, "internal_it"),
    (55, "other_internal"),
)
OH_PHARMACY_SCHEDULE = "contract_pharmacies"
OH_PHARMACY_COUNT = "count"
OH_IDENTITY_SCHEDULE = "identity"
OH_EXPLANATION_SCHEDULE = "contract_pharmacy_notes"
OH_EXPLANATION_LINE = "indeterminate_explanation"
OH_USES_SCHEDULE = "uses"
# Rows whose figure is a prescription count: the figure is kept in the claim fields.
OH_COUNT_SCHEDULES = frozenset(
    schedule
    for rows in (OH_IN_HOUSE_ROWS, OH_CONTRACT_ROWS, OH_ADMINISTERED_ROWS)
    for schedule, _, unit in rows
    if unit == COUNT
)
OH_PERCENT_SCHEDULES = frozenset(
    schedule
    for rows in (OH_IN_HOUSE_ROWS, OH_CONTRACT_ROWS, OH_ADMINISTERED_ROWS)
    for schedule, _, unit in rows
    if unit == PERCENT
)
# For a percentage row: the two count schedules it divides (numerator, denominator).
OH_PERCENT_OF: dict[str, tuple[str, str]] = {
    "in_house_rx_pct": ("in_house_rx_340b", "in_house_rx_all"),
    "contract_rx_pct": ("contract_rx_340b", "contract_rx_all"),
    "administered_rx_pct": ("administered_rx_340b", "administered_rx_all"),
}
# The unit of each table schedule: a cell a filer typed in a table row, beside the template's
# columns, is a line ``cell_<column letter>`` of the row's own schedule.
OH_TABLE_UNITS: dict[str, str] = {
    schedule: unit
    for rows in (OH_IN_HOUSE_ROWS, OH_CONTRACT_ROWS, OH_ADMINISTERED_ROWS)
    for schedule, _, unit in rows
}
OH_EXTRA_PREFIX = "cell_"
_OH_FIXED: dict[tuple[str, str], str] = {}
for _rows, _lines in (
    (OH_IN_HOUSE_ROWS, (*(k for k, _ in OH_PAYERS), OH_TOTAL)),
    (OH_CONTRACT_ROWS, (*(k for k, _ in OH_PAYERS), OH_INDETERMINATE, OH_TOTAL)),
    (OH_ADMINISTERED_ROWS, (*(k for k, _ in OH_PAYERS), OH_TOTAL)),
):
    for _schedule, _, _unit in _rows:
        for _line in _lines:
            _OH_FIXED[(_schedule, _line)] = _unit
for _, _line in OH_COSTS:
    _OH_FIXED[(OH_COSTS_SCHEDULE, _line)] = USD
_OH_FIXED[(OH_PHARMACY_SCHEDULE, OH_PHARMACY_COUNT)] = COUNT
_OH_FIXED[(OH_EXPLANATION_SCHEDULE, OH_EXPLANATION_LINE)] = NO_FIGURE
for _line in ("reporting_period", "hrsa_id", "id_prefix", "id_number"):
    _OH_FIXED[(OH_IDENTITY_SCHEDULE, _line)] = NO_FIGURE
for _line in ("other_uses_description", "narrative", "alternative_narrative"):
    _OH_FIXED[(OH_USES_SCHEDULE, _line)] = NO_FIGURE
_OH_FIXED[(OH_USES_SCHEDULE, "other_uses_amount")] = USD
OH_LINES: dict[tuple[str, str], str] = dict(_OH_FIXED)
OH_OTHER_SCHEDULE = "other_cells"
_OH_EXTRA = re.compile(r"^cell_[A-Z]{1,3}$")
_OH_OTHER_CELL = re.compile(r"^cell_[A-Z]{1,3}[1-9][0-9]*$")
_OH_NPI = re.compile(r"^npi_[1-9][0-9]{0,2}$")
_OH_LISTED_USE = re.compile(r"^(program|equipment)_[1-9][0-9]{0,2}_(description|amount)$")
OH_SCHEDULES = frozenset({schedule for schedule, _ in OH_LINES} | {OH_OTHER_SCHEDULE})


def oh_unit(schedule: str, line: str) -> str | None:
    """Return the unit of an Ohio line key, or None when the form has no such line."""
    if (schedule, line) in OH_LINES:
        return OH_LINES[(schedule, line)]
    if schedule in OH_TABLE_UNITS and _OH_EXTRA.match(line):
        return OH_TABLE_UNITS[schedule]
    if schedule == OH_OTHER_SCHEDULE and _OH_OTHER_CELL.match(line):
        return NO_FIGURE
    if schedule == OH_IDENTITY_SCHEDULE and _OH_NPI.match(line):
        return NO_FIGURE
    if schedule == OH_USES_SCHEDULE and _OH_LISTED_USE.match(line):
        return USD if line.endswith("_amount") else NO_FIGURE
    return None


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


def _assigned_unit(key: str, schedule: str, line: str) -> str | None:
    """Return a row's unit on a form whose keys this dataset assigns, or ``None`` if unknown."""
    if key == MN_FORM:
        return MN_LINES.get((schedule, line))
    if key == ID_FORM:
        return ID_LINES.get((schedule, line))
    if key == ME_FORM:
        return me_unit(schedule, line)
    if key == OH_FORM:
        return oh_unit(schedule, line)
    for s, k, _, unit in VT_LINES:
        if (s, k) == (schedule, line):
            return unit
    return None


@dataclass(frozen=True, slots=True)
class Form:
    """What a form fixes for the filings made on it."""

    key: str
    schedules: frozenset[str]
    # True when the form has a Schedule E whose rows are given a spending category.
    has_spending_categories: bool
    # The kinds of record a filing on this form may be.
    record_kinds: tuple[str, ...] = (KIND_FILING,)
    # True when the source is a workbook of cells, not a PDF: a filing's "pages" are its sheets,
    # a row names the cell it was read from, and a cell that holds words where a figure belongs is
    # kept as the words, with no amount.
    workbook: bool = False

    def unit_of(self, schedule: str, line: str) -> str:
        """Return the unit of the amount a row carries."""
        if self.key == RI_FORM:
            return NO_FIGURE if schedule == "I" else USD
        return _assigned_unit(self.key, schedule, line) or NO_FIGURE

    def knows(self, schedule: str, line: str) -> bool:
        """Say whether a schedule and line key can appear in a transcription on this form."""
        if self.key == RI_FORM:
            return schedule in self.schedules
        if schedule in (VT_NOTE_SCHEDULE, MN_NOTE_SCHEDULE, ID_NOTE_SCHEDULE, ME_NOTE_SCHEDULE):
            return line.startswith("note_")
        return _assigned_unit(self.key, schedule, line) is not None


FORMS: dict[str, Form] = {
    RI_FORM: Form(RI_FORM, RI_SCHEDULES, has_spending_categories=True),
    VT_FORM: Form(VT_FORM, VT_SCHEDULES, has_spending_categories=False),
    MN_FORM: Form(
        MN_FORM,
        MN_SCHEDULES,
        has_spending_categories=False,
        record_kinds=(KIND_STATE_ROW, KIND_STATE_TOTALS),
    ),
    ID_FORM: Form(
        ID_FORM,
        ID_SCHEDULES,
        has_spending_categories=False,
        record_kinds=(KIND_STATE_TOTALS,),
    ),
    ME_FORM: Form(
        ME_FORM,
        ME_SCHEDULES,
        has_spending_categories=False,
        record_kinds=(KIND_STATE_TOTALS,),
    ),
    OH_FORM: Form(OH_FORM, OH_SCHEDULES, has_spending_categories=False, workbook=True),
}


def form_of(key: str) -> Form:
    """Return the form a filing names, or refuse an unknown one."""
    try:
        return FORMS[key]
    except KeyError:
        raise UnknownFormError(f"unknown form {key!r}; known forms: {', '.join(FORMS)}") from None
