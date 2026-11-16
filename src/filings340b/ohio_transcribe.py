"""Turn one Ohio workbook into the files the dataset keeps for it.

This is the working part of ``tools/oh_transcribe.py``. For one workbook it makes:

* the rows of the transcription (one per figure or answer cell of the template sheet),
* the filing's identity file (``.meta.toml``),
* the cells file: every filled cell of the template sheet as ``sheet,cell,value``, with the
  contact cells replaced by a fixed marker and every e-mail address and telephone number
  masked,
* a line for every other sheet (its name and how many cells it fills), and
* a line for every picture, drawing, embedded object, macro or link inside the file.

Nothing here reads the network or runs anything from a workbook. The text inside a workbook
is data and is only ever copied, never acted on.

How ``page`` is used: a workbook has no pages. Its template sheet is page 1, every row of a
workbook filing says ``page`` 1, and the manifest says the filing has one page.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from filings340b.errors import DataError
from filings340b.forms import (
    NO_FIGURE,
    OH_COUNT_SCHEDULES,
    OH_FORM,
    OH_FRACTION_NOTE,
    OH_IDENTITY_SCHEDULE,
    PERCENT,
)
from filings340b.masking import mask
from filings340b.model import Verification
from filings340b.ohio_template import CONTACT_MARKER, Layout, OhioLine, map_sheet, template_sheet
from filings340b.workbook import Workbook, read_workbook, row_number

FORM_REVISION = (
    "Ohio Department of Health, ORC 3701.88 340B Covered Entity Reporting Template, "
    "calendar year 2025"
)
NO_RESULT_NOTE = "The workbook stores no result for this formula."
PAGE = 1
# The longest run of letters that can start a 340B ID in the files (HRSA's prefixes).
_ID_PART = re.compile(r"((?:[A-Z]+\d+)+[A-Z]*)(-\d+)?")
_ID_PAIR = re.compile(r"[A-Z]+\d+")

ROW_FIELDS = (
    "schedule",
    "line",
    "row_kind",
    "label_as_filed",
    "name_as_filed",
    "description_as_filed",
    "ndc_as_filed",
    "amount_as_filed",
    "claims_as_filed",
    "answer_as_filed",
    "page",
    "verification",
    "note",
    "source_cell",
)


def normal_id(text: str) -> str:
    """Return an ID with every mark taken out and capitals only, for comparing spellings."""
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def ids_in_file_name(stem: str) -> tuple[str, ...]:
    """Return the 340B IDs a file name carries, in the order they are written.

    A name may carry one ID (``CAH361302``), an ID with HRSA's ``-00`` ending, or several IDs
    joined by ``_and_`` or run together (``TB452022STD452191``).
    """
    found: list[str] = []
    for part in re.split(r"[\s_]+", stem.upper()):
        if not part or part == "AND":
            continue
        whole = _ID_PART.fullmatch(part)
        if whole is None:
            raise DataError(f"{stem}: cannot read a 340B ID from {part!r}")
        body = whole.group(1)
        pairs = _ID_PAIR.findall(body)
        pairs[-1] += body[len("".join(pairs)) :] + (whole.group(2) or "")
        found.extend(pairs)
    return tuple(found)


def slug(text: str) -> str:
    """Return text as lower-case words joined by hyphens."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def filing_id_of(stem: str) -> str:
    """Return the filing id of the workbook with this file stem."""
    return f"oh-2025-{slug(stem)}"


def _spellings(key: str) -> list[str]:
    spelled = [key, key + "00"]
    if key.endswith("00"):
        spelled.append(key[:-2])
    return spelled


@dataclass(frozen=True, slots=True)
class HrsaMatch:
    """What HRSA's list holds for one ID taken from a file name or a cell."""

    id_as_given: str
    entity: dict[str, object] | None
    # "exact", "with or without the 00 ending" or "not in HRSA's list".
    how: str


def match_hrsa(id_as_given: str, index: dict[str, list[dict[str, object]]]) -> HrsaMatch:
    """Find an ID in HRSA's list, trying the spellings that differ only by a 00 ending."""
    key = normal_id(id_as_given)
    for position, spelled in enumerate(_spellings(key)):
        hits = index.get(spelled, [])
        if hits:
            # A parent record has no subdivision name; prefer it over a child site of the same ID.
            hits = sorted(hits, key=lambda e: bool(e.get("subdivision_name")))
            return HrsaMatch(
                id_as_given, hits[0], "exact" if position == 0 else "with or without the 00 ending"
            )
    return HrsaMatch(id_as_given, None, "not in HRSA's list")


def hrsa_index(entities: Iterable[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    """Index HRSA's entities by the spelling of their ID without marks."""
    out: dict[str, list[dict[str, object]]] = {}
    for entity in entities:
        out.setdefault(normal_id(str(entity["id_340b"])), []).append(entity)
    return out


def entity_id_of(first: HrsaMatch, file_ids: tuple[str, ...]) -> str:
    """Return the entity id: the first ID's HRSA spelling when HRSA lists it, else the file's."""
    if first.entity is not None:
        return "oh-" + slug(str(first.entity["id_340b"]))
    return "oh-" + slug(file_ids[0])


@dataclass(frozen=True, slots=True)
class Transcribed:
    """Everything made from one workbook."""

    stem: str
    filing_id: str
    sheet_name: str
    layout: Layout
    rows: tuple[dict[str, str], ...]
    # (sheet name, cell, value) of the template sheet, masked.
    cells: tuple[tuple[str, str, str], ...]
    # (position, name, state, filled cells, carries the template) of every sheet.
    contents: tuple[tuple[int, str, str, int, bool], ...]
    objects: tuple[tuple[str, str], ...]
    typed_id: str
    period: str
    # The text of the contact cells; never written anywhere, kept to mask copies of it.
    contacts: tuple[str, ...]


WITHHELD_UNLISTED = "[withheld: beside_small]"
# Cells outside the contact rows that name a member of staff, by workbook. Their text is
# withheld like a contact cell's. The list names the cell and never the person.
STAFF_NAME_CELLS: dict[str, frozenset[str]] = {"CH053086": frozenset({"D59"})}


def _small_blocks(cells: dict[str, str], mapped: set[str]) -> set[str]:
    """Find cells outside the form's lines that a small prescription count would give away.

    The earlier layout of the template lists each contract pharmacy in a block of rows (a name,
    then acquisition cost, payments, prescriptions, 340B prescriptions and a percentage). Those
    cells are not lines of the form. When a block holds a prescription count of 1 to 5, every
    count and percentage cell of the block is returned so the cells file can withhold them.
    """
    blocks: dict[int, list[int]] = {}
    current = 0
    labels: dict[int, str] = {}
    for ref, value in cells.items():
        row = row_number(ref)
        if ref.startswith("B") and ref[1:].isdigit() and value.strip():
            current = row
            blocks.setdefault(current, [])
        if ref.startswith("C") and ref[1:].isdigit():
            labels[row] = " ".join(value.lower().split())
    rows_of: dict[int, list[int]] = {}
    for row, label in labels.items():
        if label.startswith(("total number of", "percentage of total")):
            owner = max((b for b in blocks if b <= row), default=0)
            rows_of.setdefault(owner, []).append(row)
    out: set[str] = set()
    for rows in rows_of.values():
        found = [
            ref
            for ref in cells
            if ref not in mapped
            and row_number(ref) in rows
            and not ref.startswith(("A", "B", "C"))
            and _is_number(cells[ref])
        ]
        counts = [
            cells[ref] for ref in found if labels[row_number(ref)].startswith("total number of")
        ]
        if any(_is_small(value) for value in counts):
            out.update(found)
    return out


def _is_number(text: str) -> bool:
    return re.fullmatch(r"-?\d+(\.\d+)?(E-?\d+)?", text.strip()) is not None


def _is_small(text: str) -> bool:
    return re.fullmatch(r"[1-5](\.0+)?", text.strip()) is not None


def _contact_values(workbook_cells: dict[str, str], refs: frozenset[str]) -> list[str]:
    values = []
    for ref in sorted(refs):
        text = " ".join(workbook_cells.get(ref, "").split())
        if len(text) >= 4:
            values.append(text)
    return values


def scrub(text: str, contacts: list[str]) -> str:
    """Mask e-mail addresses and phone numbers, and any contact cell's text repeated elsewhere."""
    cleaned = mask(text)
    for value in contacts:
        pattern = re.compile(r"\s+".join(re.escape(word) for word in value.split()), re.IGNORECASE)
        cleaned = pattern.sub(CONTACT_MARKER, cleaned)
    return cleaned


def column_of(schedule: str, unit: str) -> str:
    """Return which column holds a line's figure: ``answer``, ``claims`` or ``amount``.

    Only a prescription count is a claim count (and so can be withheld). The number of
    contract pharmacies is a count too, but of pharmacies, and is kept in ``amount``.
    """
    if unit == NO_FIGURE:
        return "answer"
    return "claims" if schedule in OH_COUNT_SCHEDULES else "amount"


def _row(line: OhioLine, contacts: list[str]) -> dict[str, str]:
    cell = line.cell
    value = scrub(cell.value, contacts)
    notes = []
    if cell.no_result:
        notes.append(NO_RESULT_NOTE)
    if line.unit == PERCENT and cell.percent_format:
        notes.append(OH_FRACTION_NOTE)
    note = " ".join(notes)
    row = dict.fromkeys(ROW_FIELDS, "")
    row.update(
        schedule=line.schedule,
        line=line.line,
        row_kind=line.row_kind.value,
        label_as_filed=scrub(line.label, contacts),
        description_as_filed=scrub(line.heading, contacts),
        page=str(PAGE),
        verification=Verification.UNVERIFIED.value,
        note=note,
        source_cell=cell.ref,
    )
    row[f"{column_of(line.schedule, line.unit)}_as_filed"] = value
    return row


def transcribe(stem: str, workbook: Workbook) -> Transcribed:
    """Read one workbook's template sheet into rows, cells and contents."""
    position = template_sheet(workbook.sheets)
    if position is None:
        raise DataError(f"{stem}: no sheet carries the template")
    sheet = workbook.sheets[position - 1]
    layout = map_sheet(sheet)
    by_ref = {cell.ref: cell.value for cell in sheet.cells}
    named = STAFF_NAME_CELLS.get(stem, frozenset())
    contacts = _contact_values(by_ref, layout.contact_refs | named)
    rows = tuple(_row(line, contacts) for line in layout.lines)
    unlisted = _small_blocks(by_ref, {line.ref for line in layout.lines})
    cells = tuple(
        (
            sheet.name,
            cell.ref,
            CONTACT_MARKER
            if cell.ref in layout.contact_refs
            else WITHHELD_UNLISTED
            if cell.ref in unlisted
            else scrub(cell.value, contacts),
        )
        for cell in sheet.cells
    )
    contents = tuple(
        (number, scrub(each.name, contacts), each.state, len(each.cells), number == position)
        for number, each in enumerate(workbook.sheets, start=1)
    )
    identity = {
        row["line"]: row["answer_as_filed"]
        for row in rows
        if row["schedule"] == OH_IDENTITY_SCHEDULE
    }
    return Transcribed(
        stem=stem,
        filing_id=filing_id_of(stem),
        sheet_name=sheet.name,
        layout=layout,
        rows=rows,
        cells=cells,
        contents=contents,
        objects=workbook.objects,
        typed_id=" ".join(identity.get("hrsa_id", "").split()),
        period=" ".join(identity.get("reporting_period", "").split()),
        contacts=tuple(contacts),
    )


def transcribe_file(path: Path) -> Transcribed:
    """Read the workbook at ``path`` and transcribe it."""
    return transcribe(path.stem, read_workbook(path))


def toml_string(text: str) -> str:
    """Return text as a TOML basic string."""
    return json.dumps(text, ensure_ascii=True)


def meta_text(
    done: Transcribed,
    *,
    entity_id: str,
    source_file: str,
    typed_ids: str,
    other_entity_ids: list[str],
) -> str:
    """Write the filing's ``.meta.toml``."""
    lines = [
        f"filing_id = {toml_string(done.filing_id)}",
        f"entity_id = {toml_string(entity_id)}",
        'state = "OH"',
        "reporting_year = 2025",
        'entity_type = "not_stated"',
        f"source_file = {toml_string(source_file)}",
        f"other_entity_ids = [{', '.join(toml_string(one) for one in other_entity_ids)}]",
        f"form = {toml_string(OH_FORM)}",
        f"form_revision = {toml_string(FORM_REVISION)}",
        "",
        "[cover]",
        'name_as_filed = ""',
        'corporate_address_as_filed = ""',
        f"opais_ids_as_filed = {toml_string(typed_ids)}",
        'recertification_date_as_filed = ""',
        'reporting_basis_as_filed = ""',
        "",
        "[printed]",
        f"period_as_filed = {toml_string(done.period)}",
        "",
    ]
    return "\n".join(lines)
