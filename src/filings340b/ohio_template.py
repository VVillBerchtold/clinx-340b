"""Find the cells of Ohio's template in a workbook and give each a line key of the Ohio form.

The Department of Health's template puts every figure at a fixed cell. Most workbooks keep
that layout exactly. A few filers inserted rows, so a table sits one or more rows lower, and
two workbooks use an earlier layout that lists contract pharmacies one by one. Nothing here
assumes a fixed address: each row of the template is found by the label the workbook prints
beside it, and a cell is read only where its row was found. A row that cannot be found is
left out and the workbook's cells file still holds the cell.

The function ``map_sheet`` returns one ``OhioLine`` for every cell of the sheet that holds a
figure or an answer. ``source_cell`` of a row is the address the line was read from.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from filings340b.forms import (
    COUNT,
    NO_FIGURE,
    OH_ADMINISTERED_ROWS,
    OH_CONTRACT_ROWS,
    OH_COSTS,
    OH_COSTS_SCHEDULE,
    OH_EXPLANATION_LINE,
    OH_EXPLANATION_SCHEDULE,
    OH_EXTRA_PREFIX,
    OH_IDENTITY_SCHEDULE,
    OH_IN_HOUSE_ROWS,
    OH_INDETERMINATE,
    OH_OTHER_SCHEDULE,
    OH_PAYERS,
    OH_PERCENT_SCHEDULES,
    OH_PHARMACY_COUNT,
    OH_PHARMACY_SCHEDULE,
    OH_TOTAL,
    OH_USES_SCHEDULE,
    USD,
)
from filings340b.model import RowKind
from filings340b.workbook import Cell, Sheet, column_number, row_number

# The schedule that holds a cell the template has no line for outside its tables.
OTHER_SCHEDULE = OH_OTHER_SCHEDULE
# The sentence that marks the sheet that carries the template.
TEMPLATE_TITLE = "ORC 3701.88"
CONTACT_MARKER = "[contact detail withheld]"

# (template row, label the template prints in column B). Rows found by these labels.
ANCHORS: tuple[tuple[int, str], ...] = (
    (4, "Reporting Period:"),
    (5, "Primary Contact Name:"),
    (6, "Email:"),
    (7, "Phone Number:"),
    (8, "HRSA 340B ID:"),
    (
        13,
        "National Provider Identifier(s) associated with this Covered Entity "
        "(DO NOT REPORT Contract Pharmacies)",
    ),
    (15, "Section 1: Dispensed Drugs (billed through in-house Covered Entity Pharmacies)"),
    (17, "Aggregate Acquisition Cost for all 340B drugs dispensed by the Covered Entity"),
    (18, "Aggregate Payments Received for all 340B drugs dispensed by the Covered Entity"),
    (19, "Total number of Prescriptions dispensed by the Covered Entity (340B and non-340B)"),
    (20, "Total number of Prescriptions dispensed by the Covered Entity (340B)"),
    (21, "Percentage of total prescriptions that were 340B"),
    (23, "Section 2: Dispensed Drugs (billed through Contract Pharmacies)"),
    (
        26,
        "Aggregate Acquisition Cost for all 340B drugs dispensed by all Contract Pharmacies "
        "on behalf of the Covered Entity above:",
    ),
    (
        27,
        "Aggregate Payments Received for all 340B drugs dispensed by all Contract Pharmacies "
        "on behalf of the Covered Entity above:",
    ),
    (
        28,
        "Total number of Prescriptions filled by all Contract Pharmacies on behalf of the "
        "Covered Entity (340B and non-340B):",
    ),
    (
        29,
        "Total number of 340B Prescriptions filled by all Contract Pharmacies on behalf of "
        "the Covered Entity:",
    ),
    (30, "Percentage of total Covered-Entity associated prescriptions that were 340B:"),
    (33, "Section 3: Administered Drugs"),
    (35, "Aggregate Acquisition Cost for all 340B drugs administered by the Covered Entity"),
    (36, "Aggregate Payments Received for all 340B drugs administered by the Covered Entity"),
    (39, "Total number of Prescriptions administered by the Covered Entity (340B and non-340B)"),
    (40, "Total number of Prescriptions administered by the Covered Entity (340B)"),
    (41, "Percentage of total prescriptions that were 340B"),
    (43, "Section 4: Administrative Costs of the 340B Program"),
    (45, "Payments to External Entities:"),
    (
        46,
        "Total Payments made to Contract Pharmacies by the Covered Entity (includes dispensing "
        "fees and profit sharing arrangements):",
    ),
    (47, "Total Payments to 340B Third Party Administrators:"),
    (48, "Total Payments to 340B Consulting Entities (including audit support):"),
    (49, "340B Software and Information Technology Costs:"),
    (50, "Other Payments to External Entities:"),
    (52, "Internal Costs to Administer the 340B Program"),
    (53, "Staffing Costs (340B dedicated):"),
    (54, "Information Technology Costs:"),
    (55, "Other internal costs:"),
    (57, "Section 5: Information Regarding the Covered Entity's Contract Pharmacies"),
    (59, "Covered Entity's total number of Contract Pharmacies:"),
    (61, "Section 6: Detailed Accounting of Covered Entity's Expenditures from 340B Profits"),
    (64, "Programs or Services funded/purchased with 340B funds:"),
)
_ANCHOR_ROWS = tuple(row for row, _ in ANCHORS)
_SECTION_HEADERS = {16: 17, 25: 26, 34: 35}  # header row -> first row below it

# Cells whose rows are the contact person's: never copied, never transcribed.
_CONTACT_LABELS = ("primary contact", "email", "e-mail", "phone")

# Where a header of section 6 begins a run of cells.
_EQUIPMENT = "equipment purchased"
_OTHER_USES = "other uses of 340b"
_NARRATIVE = "(narrative)"
_ALTERNATIVE = "if covered entity cannot provide"

_PAYER_COLUMNS_CF = ("C", "D", "E", "F", "G")
_PAYER_COLUMNS_ADMIN = ("D", "E", "F", "G", "H")


def squash(text: str) -> str:
    """Collapse runs of white space (including line breaks) to single spaces."""
    return " ".join(text.split())


def _norm(text: str | None) -> str:
    return squash(text or "").casefold().rstrip(": ").strip()


def _same_label(found: str | None, wanted: str) -> bool:
    if not found:
        return False
    a, b = _norm(found), _norm(wanted)
    return a == b or (len(b) > 25 and difflib.SequenceMatcher(None, a, b).ratio() >= 0.93)


@dataclass(frozen=True, slots=True)
class OhioLine:
    """One cell of a workbook and the line of the form it is read as."""

    schedule: str
    line: str
    row_kind: RowKind
    unit: str
    cell: Cell
    # The row's label and the column's heading as the workbook prints them.
    label: str
    heading: str

    @property
    def ref(self) -> str:
        """The cell's address."""
        return self.cell.ref


@dataclass(frozen=True, slots=True)
class Layout:
    """What was found in one template sheet."""

    lines: tuple[OhioLine, ...]
    # True for the earlier layout that lists contract pharmacies one by one.
    earlier: bool
    # Addresses of the contact cells (never copied).
    contact_refs: frozenset[str]
    # Template rows this sheet has no row for (their cells are not transcribed).
    missing_rows: tuple[int, ...]


def is_template_sheet(sheet: Sheet) -> bool:
    """Say whether a sheet carries the template (its title cell says so)."""
    cell = sheet.get("B2")
    return cell is not None and TEMPLATE_TITLE in cell.value


def template_sheet(sheets: tuple[Sheet, ...]) -> int | None:
    """Return the 1-based position of the first sheet that carries the template, or None."""
    for position, sheet in enumerate(sheets, start=1):
        if is_template_sheet(sheet):
            return position
    return None


def _offsets(sheet: Sheet) -> dict[int, int]:
    """Find, for each anchor row of the template, how many rows lower the workbook prints it."""
    labels: dict[int, str] = {}
    for cell in sheet.cells:
        if cell.ref.startswith("B") and cell.ref[1:].isdigit():
            labels[row_number(cell.ref)] = cell.value
    found: dict[int, int] = {}
    offset = 0
    for template_row, text in ANCHORS:
        narrow = [0, 1, -1, 2, -2, 3, -3, 4, -4, 5, -5, 6, -6]
        wide = [d for d in range(-80, 81) if d not in narrow]
        for delta in narrow + wide:
            actual = template_row + offset + delta
            label = labels.get(actual)
            if label is None:
                continue
            ok = _same_label(label, text) if delta in narrow else _norm(label) == _norm(text)
            if ok:
                offset += delta
                found[template_row] = offset
                break
    return found


def _row_offset(found: dict[int, int], template_row: int) -> int | None:
    """Return the offset of a template row, or None when it cannot be told."""
    if template_row in found:
        return found[template_row]
    before = [r for r in found if r < template_row]
    after = [r for r in found if r > template_row]
    if not before:
        return found[min(after)] if after else None
    previous = found[max(before)]
    if after and found[min(after)] != previous:
        return None
    return previous


def _text(cells: dict[str, Cell], ref: str) -> str:
    cell = cells.get(ref)
    return squash(cell.value) if cell is not None else ""


def _contacts(cells: dict[str, Cell]) -> frozenset[str]:
    """Return the addresses of the contact person's cells: columns C onward of the contact rows."""
    rows = {
        row_number(ref)
        for ref, cell in cells.items()
        if ref.startswith("B")
        and 3 <= row_number(ref) <= 12
        and _norm(cell.value).startswith(_CONTACT_LABELS)
    }
    return frozenset(ref for ref in cells if row_number(ref) in rows and column_number(ref) >= 3)


def _classify(heading: str) -> str | None:
    """Say which payer column a heading names: a payer key, ``indeterminate`` or ``total``."""
    text = _norm(heading)
    for words, key in _HEADINGS:
        if any(w in text for w in words):
            return key
    return None


_HEADINGS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("indeterminate",), OH_INDETERMINATE),
    (("commerc", "private"), "commercial"),
    (("medicare",), "medicare"),
    (("medicaid",), "medicaid"),
    (("other third", "third-party", "third party"), "other_third_party"),
    (("uninsured", "self-pay", "self pay"), "uninsured"),
    (("total",), OH_TOTAL),
)


def _columns(
    cells: dict[str, Cell],
    header_row: int,
    default: tuple[str, ...],
    total_column: str,
    indeterminate: bool,
) -> list[tuple[str, str, RowKind]]:
    """Read which column holds which payer from the table's heading row.

    Where the heading row names no payer at all, the template's own columns are used.
    """
    found: dict[str, str] = {}
    for ref in sorted(cells, key=column_number):
        if row_number(ref) != header_row or not 3 <= column_number(ref) <= 12:
            continue
        key = _classify(cells[ref].value)
        if key is not None and key not in found.values():
            found[ref.rstrip("0123456789")] = key
    if not found:
        keys = [k for k, _ in OH_PAYERS]
        found = dict(zip(default, keys, strict=True))
        if indeterminate:
            found["H"] = OH_INDETERMINATE
        found[total_column] = OH_TOTAL
    return [
        (column, key, RowKind.TOTAL if key == OH_TOTAL else RowKind.DETAIL)
        for column, key in sorted(found.items(), key=lambda kv: column_number(kv[0] + "1"))
    ]


def _table(  # noqa: PLR0913, PLR0917
    cells: dict[str, Cell],
    found: dict[int, int],
    rows: tuple[tuple[str, int, str], ...],
    header: int,
    letters: tuple[str, ...],
    total_column: str,
    indeterminate_column: str | None,
    contacts: frozenset[str],
) -> tuple[list[OhioLine], list[int]]:
    """Read one of the template's three tables."""
    lines: list[OhioLine] = []
    missing: list[int] = []
    first_row = _SECTION_HEADERS[header]
    header_offset = _row_offset(found, first_row)
    heading_row = first_row - 1 + (header_offset if header_offset is not None else 0)
    spec = _columns(cells, heading_row, letters, total_column, indeterminate_column is not None)
    for schedule, template_row, unit in rows:
        anchor = {37: 36, 38: 36}.get(template_row, template_row)
        offset = _row_offset(found, anchor)
        if offset is None:
            missing.append(template_row)
            continue
        row = template_row + offset
        label = _text(cells, f"B{row}") or _text(cells, f"B{anchor + offset}")
        if schedule.startswith("administered_payments"):
            label = squash(f"{label} - {_text(cells, f'C{row}')}")
        named = {column for column, _, _ in spec}
        for column, key, kind in spec:
            cell = cells.get(f"{column}{row}")
            if cell is None:
                continue
            heading = _text(cells, f"{column}{heading_row}")
            lines.append(OhioLine(schedule, key, kind, unit, cell, label, heading))
        # Anything else a filer typed on the row (a note, an extra column) is read under the
        # row's own schedule, so a small count there is withheld like the others.
        for ref in sorted(cells, key=column_number):
            column = ref.rstrip("0123456789")
            if row_number(ref) != row or column_number(ref) < 3 or column in named:
                continue
            blank = cells[ref].value.strip() in ("", "-") and not cells[ref].formula
            if ref in contacts or blank:
                continue
            heading = _text(cells, f"{column}{heading_row}")
            lines.append(
                OhioLine(
                    schedule,
                    f"{OH_EXTRA_PREFIX}{column}",
                    RowKind.DETAIL,
                    unit,
                    cells[ref],
                    label,
                    heading,
                )
            )
    return lines, missing


def map_sheet(sheet: Sheet) -> Layout:
    """Give every figure and answer on a template sheet a line key of the Ohio form."""
    cells = {cell.ref: cell for cell in sheet.cells}
    found = _offsets(sheet)
    contacts = _contacts(cells)
    lines: list[OhioLine] = []
    missing: list[int] = []

    # Whether this is the earlier layout: its contract pharmacies are listed one by one, so none
    # of Section 2's own labels is found.
    section_two = [r for r in (26, 27, 28, 29, 30) if r in found]
    earlier = not section_two

    for rows, header, letters, total_column, indeterminate in (
        (OH_IN_HOUSE_ROWS, 16, _PAYER_COLUMNS_CF, "H", None),
        (OH_CONTRACT_ROWS, 25, _PAYER_COLUMNS_CF, "I", "H"),
        (OH_ADMINISTERED_ROWS, 34, _PAYER_COLUMNS_ADMIN, "I", None),
    ):
        if header == 25 and earlier:
            missing.extend(row for _, row, _ in rows)
            continue
        table, gone = _table(
            cells, found, rows, header, letters, total_column, indeterminate, contacts
        )
        lines.extend(table)
        missing.extend(gone)
    if earlier:
        # The earlier layout stores each percentage as a fraction of one, not as a percentage.
        lines = [ln for ln in lines if ln.schedule not in OH_PERCENT_SCHEDULES]

    lines.extend(_costs(cells, found, missing))
    lines.extend(_identity(cells, found))
    lines.extend(_explanation(cells, found))
    uses, anchor_row = _uses(cells, found)
    lines.extend(uses)
    if not earlier:
        lines.extend(_others(cells, found, lines, contacts, sheet, anchor_row))
    return Layout(tuple(lines), earlier, contacts, tuple(sorted(set(missing))))


def _costs(cells: dict[str, Cell], found: dict[int, int], missing: list[int]) -> list[OhioLine]:
    lines: list[OhioLine] = []
    for template_row, key in OH_COSTS:
        offset = _row_offset(found, template_row)
        if offset is None:
            missing.append(template_row)
            continue
        cell = cells.get(f"C{template_row + offset}")
        if cell is not None:
            label = _text(cells, f"B{template_row + offset}")
            lines.append(OhioLine(OH_COSTS_SCHEDULE, key, RowKind.DETAIL, USD, cell, label, ""))
    offset = _row_offset(found, 59)
    if offset is None:
        missing.append(59)
    else:
        cell = cells.get(f"C{59 + offset}")
        if cell is not None:
            lines.append(
                OhioLine(
                    OH_PHARMACY_SCHEDULE,
                    OH_PHARMACY_COUNT,
                    RowKind.DETAIL,
                    COUNT,
                    cell,
                    _text(cells, f"B{59 + offset}"),
                    "",
                )
            )
    return lines


def _identity(cells: dict[str, Cell], found: dict[int, int]) -> list[OhioLine]:
    lines: list[OhioLine] = []
    offset = _row_offset(found, 4)
    if offset is not None:
        cell = cells.get(f"C{4 + offset}")
        if cell is not None:
            label = _text(cells, f"B{4 + offset}")
            lines.append(
                OhioLine(
                    OH_IDENTITY_SCHEDULE,
                    "reporting_period",
                    RowKind.DETAIL,
                    NO_FIGURE,
                    cell,
                    label,
                    "",
                )
            )
    offset = _row_offset(found, 8)
    if offset is not None and 8 in found:
        id_row = 8 + offset
        label = _text(cells, f"B{id_row}")
        cell = cells.get(f"C{id_row}")
        if cell is not None:
            lines.append(
                OhioLine(
                    OH_IDENTITY_SCHEDULE, "hrsa_id", RowKind.DETAIL, NO_FIGURE, cell, label, ""
                )
            )
        # The template splits the ID into a lettered prefix (D) and a number (E) two rows below.
        for column, key in (("D", "id_prefix"), ("E", "id_number")):
            heading = _text(cells, f"{column}{id_row + 1}")
            cell = cells.get(f"{column}{id_row + 2}")
            if cell is not None and heading.rstrip(":").casefold() in ("lettered prefix", "number"):
                lines.append(
                    OhioLine(
                        OH_IDENTITY_SCHEDULE, key, RowKind.DETAIL, NO_FIGURE, cell, label, heading
                    )
                )
    offset = _row_offset(found, 13)
    if offset is not None and 13 in found:
        row = 13 + offset
        for ref, cell in sorted(cells.items(), key=lambda kv: column_number(kv[0])):
            if row_number(ref) != row or column_number(ref) < 3:
                continue
            number = column_number(ref) - 2
            heading = _text(cells, f"{ref.rstrip('0123456789')}{row - 1}")
            lines.append(
                OhioLine(
                    OH_IDENTITY_SCHEDULE,
                    f"npi_{number}",
                    RowKind.DETAIL,
                    NO_FIGURE,
                    cell,
                    _text(cells, f"B{row}"),
                    heading,
                )
            )
    return lines


def _explanation(cells: dict[str, Cell], found: dict[int, int]) -> list[OhioLine]:
    if 26 not in found:
        return []
    offset = found[26]
    row = 32 + offset
    cell = cells.get(f"I{row}")
    if cell is None:
        return []
    return [
        OhioLine(
            OH_EXPLANATION_SCHEDULE,
            OH_EXPLANATION_LINE,
            RowKind.DETAIL,
            NO_FIGURE,
            cell,
            _text(cells, f"H{row}"),
            "",
        )
    ]


def _uses(  # noqa: PLR0912
    cells: dict[str, Cell], found: dict[int, int]
) -> tuple[list[OhioLine], int]:
    """Read Section 6: the programs, the equipment, other uses and the narratives, in order.

    Returns the lines and the row where the section ends (used to find stray cells).
    """
    if 64 not in found:
        return [], 0
    start = found[64] + 64
    last = max(row_number(ref) for ref in cells)
    lines: list[OhioLine] = []
    mode = "programs"
    counts = {"programs": 0, "equipment": 0}
    end = start
    for row in range(start + 1, last + 1):
        label = _text(cells, f"B{row}")
        key = _norm(label)
        if key.startswith(_EQUIPMENT):
            mode, end = "equipment", row
            continue
        if key.startswith(_OTHER_USES):
            mode, end = "other", row
        elif key.startswith(_NARRATIVE):
            mode, end = "narrative", row
        elif key.startswith(_ALTERNATIVE):
            mode, end = "alternative", row
        c, d = cells.get(f"C{row}"), cells.get(f"D{row}")
        if mode in ("programs", "equipment"):
            if c is None and d is None:
                continue
            counts[mode] += 1
            n = counts[mode]
            prefix = "program" if mode == "programs" else "equipment"
            if c is not None:
                lines.append(
                    OhioLine(
                        OH_USES_SCHEDULE,
                        f"{prefix}_{n}_description",
                        RowKind.DETAIL,
                        NO_FIGURE,
                        c,
                        label,
                        "",
                    )
                )
            if d is not None:
                lines.append(
                    OhioLine(
                        OH_USES_SCHEDULE, f"{prefix}_{n}_amount", RowKind.DETAIL, USD, d, label, ""
                    )
                )
            end = row
        elif mode == "other":
            if c is not None:
                lines.append(
                    OhioLine(
                        OH_USES_SCHEDULE,
                        "other_uses_description",
                        RowKind.DETAIL,
                        NO_FIGURE,
                        c,
                        label,
                        "",
                    )
                )
            if d is not None:
                lines.append(
                    OhioLine(
                        OH_USES_SCHEDULE, "other_uses_amount", RowKind.DETAIL, USD, d, label, ""
                    )
                )
            mode = "after_other"
        elif mode in ("narrative", "alternative"):
            line = "narrative" if mode == "narrative" else "alternative_narrative"
            if c is not None:
                lines.append(
                    OhioLine(OH_USES_SCHEDULE, line, RowKind.DETAIL, NO_FIGURE, c, label, "")
                )
            mode = "after_" + mode
    return lines, end


def _structural(cells: dict[str, Cell]) -> frozenset[str]:
    """Addresses of cells that only repeat the template (its labels, headings and row numbers)."""
    out: set[str] = set()
    for ref, cell in cells.items():
        text = _norm(cell.value)
        column = ref.rstrip("0123456789")
        numbering = column == "A" and re.fullmatch(r"\d{1,2}(\.0+)?|n/a", text) is not None
        numbered = re.fullmatch(r"npi\d{1,3}|program/service \d{1,3}:?|item \d{1,3}:?", text)
        if numbering or text in _TEMPLATE_TEXTS or numbered:
            out.add(ref)
    return frozenset(out)


def _others(  # noqa: PLR0913, PLR0917
    cells: dict[str, Cell],
    found: dict[int, int],
    lines: list[OhioLine],
    contacts: frozenset[str],
    sheet: Sheet,
    anchor_row: int,
) -> list[OhioLine]:
    """Give every other cell that holds something a line of the schedule ``other_cells``."""
    taken = {ln.ref for ln in lines} | contacts | _structural(cells)
    out: list[OhioLine] = []
    for cell in sheet.cells:
        if cell.ref in taken:
            continue
        if cell.value.strip() in ("", "-") and not cell.formula:
            continue
        # Title cells of the template (rows 1 to 3) are structural.
        if row_number(cell.ref) <= 3:
            continue
        out.append(
            OhioLine(OTHER_SCHEDULE, f"cell_{cell.ref}", RowKind.DETAIL, NO_FIGURE, cell, "", "")
        )
    return out


# Every piece of text the template prints (its labels and headings), folded for comparison.
_TEMPLATE_TEXTS = frozenset(
    _norm(t)
    for t in (
        "Ohio Department of Health",
        "ORC 3701.88 340B Covered Entity Reporting Template",
        "Data Element",
        "Lettered Prefix:",
        "Number:",
        "Commercial Insurance/Private Insurance:",
        "Commerical Insurance/Private Insurance",
        "Medicare:",
        "Medicare",
        "Medicaid (all states):",
        "Medicaid (all states)",
        "Other Third-Party Payor:",
        "Other Third-Party Payor",
        "Uninsured/Self-Pay:",
        "Uninsured/Self-Pay",
        "TOTAL:",
        "TOTAL",
        "Indeterminate (Explain)",
        '(Required if "Indeterminate" used above) Explanation:',
        "Actual Payments",
        "Estimated Payments*",
        "Detailed Description of Item:",
        "Expenditures from 340B funds:",
        "Equipment purchased with 340B Funds:",
        "Other uses of 340B funds not otherwise listed above:",
        *(text for _, text in ANCHORS),
        "Primary Contact:",
        "(Narrative) Provide additional detail/context as necessary:",
        "If Covered Entity cannot provide a detailed accounting as requested above, provide a "
        "detailed narrative regarding how 340B funds/profits are used.",
    )
)
