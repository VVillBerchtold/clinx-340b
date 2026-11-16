"""Checks on Ohio's workbook filings: what is published, what is withheld, what is private.

Ohio's covered entities file Excel workbooks. These tests cover the reader, the small pieces
(file-name IDs, masking, comparing two reads), and the committed files: no contact detail, no
small count that can be worked out, two reads for every row, and names kept apart from HRSA's.
"""

from __future__ import annotations

import csv
import importlib.util
import re
import zipfile
from decimal import Decimal
from pathlib import Path

import pytest

from filings340b.forms import OH_FORM, form_of, oh_unit
from filings340b.imageread import same_cell
from filings340b.load import ORIGINALS, load_filings
from filings340b.masking import EMAIL, PHONE, mask
from filings340b.model import Filing, Verification
from filings340b.money import parse_workbook_amount, parse_workbook_count
from filings340b.ohio_recovery import recover, too_few
from filings340b.ohio_template import map_sheet, template_sheet
from filings340b.ohio_transcribe import (
    column_of,
    filing_id_of,
    hrsa_index,
    ids_in_file_name,
    match_hrsa,
)
from filings340b.sealing import read_private
from filings340b.workbook import read_workbook

ROOT = Path(__file__).resolve().parents[1]
OHIO = ROOT / "sources" / "oh" / "2025"


def _published() -> list[Path]:
    return [
        *sorted((OHIO / "cells").glob("*.csv")),
        OHIO / "manifest.csv",
        OHIO / "workbook-contents.csv",
        OHIO / "workbook-objects.csv",
        *sorted((ROOT / "transcriptions" / "oh").glob("*/*")),
        *sorted((ROOT / "verification" / "oh").glob("*/*")),
        ROOT / "reference" / "hrsa-oh-extract.csv",
        ROOT / "reference" / "discrepancy_notes.csv",
        *(ROOT / "data" / n for n in ("line_items.csv", "entities.csv", "filings.csv")),
        ROOT / "data" / "discrepancies.csv",
        ROOT / "data" / "340b-state-filings.json",
    ]


@pytest.fixture(scope="module")
def ohio() -> tuple[Filing, ...]:
    return tuple(f for f in load_filings(ROOT) if f.meta.form == OH_FORM)


def _rows(name: str) -> list[dict[str, str]]:
    with (ROOT / "data" / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _ohio_line_items() -> dict[str, list[dict[str, str]]]:
    out: dict[str, list[dict[str, str]]] = {}
    for record in _rows("line_items.csv"):
        if record["filing_id"].startswith("oh-"):
            out.setdefault(record["filing_id"], []).append(record)
    return out


def _minimal_workbook(path: Path) -> None:
    """Write a tiny workbook: text, a number, a formula with no result, an error, a percent."""
    main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    parts = {
        "xl/workbook.xml": (
            f'<workbook xmlns="{main}" xmlns:r="{rel}"><sheets>'
            '<sheet name="One" sheetId="1" r:id="rId1"/>'
            '<sheet name="Two" sheetId="2" state="hidden" r:id="rId2"/></sheets></workbook>'
        ),
        "xl/_rels/workbook.xml.rels": (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Target="worksheets/sheet2.xml"/></Relationships>'
        ),
        "xl/sharedStrings.xml": f'<sst xmlns="{main}"><si><t>Hello</t></si></sst>',
        "xl/styles.xml": (
            f'<styleSheet xmlns="{main}"><cellXfs><xf numFmtId="0"/><xf numFmtId="9"/></cellXfs>'
            "</styleSheet>"
        ),
        "xl/worksheets/sheet1.xml": (
            f'<worksheet xmlns="{main}"><sheetData><row r="1">'
            '<c r="A1" t="s"><v>0</v></c><c r="B1"><v>602.56000000000006</v></c>'
            '<c r="C1"><f>SUM(B1)</f></c><c r="D1" t="e"><v>#DIV/0!</v></c>'
            '<c r="E1" s="1"><v>0.25</v></c></row></sheetData></worksheet>'
        ),
        "xl/worksheets/sheet2.xml": f'<worksheet xmlns="{main}"><sheetData/></worksheet>',
        "xl/media/image1.png": "not a picture",
    }
    with zipfile.ZipFile(path, "w") as archive:
        for name, text in parts.items():
            archive.writestr(name, text)


def test_the_reader_keeps_values_as_stored(tmp_path: Path) -> None:
    path = tmp_path / "small.xlsx"
    _minimal_workbook(path)
    book = read_workbook(path)
    assert [(s.name, s.state, len(s.cells)) for s in book.sheets] == [
        ("One", "visible", 5),
        ("Two", "hidden", 0),
    ]
    cells = {c.ref: c for c in book.sheets[0].cells}
    assert cells["A1"].value == "Hello"
    assert cells["B1"].value == "602.56000000000006"
    assert cells["C1"].formula and cells["C1"].no_result
    assert cells["D1"].kind == "error" and cells["D1"].value == "#DIV/0!"
    assert cells["E1"].percent_format and not cells["B1"].percent_format
    assert book.objects == (("xl/media/image1.png", "picture"),)


def test_a_file_name_names_its_340b_ids() -> None:
    assert ids_in_file_name("CAH361302") == ("CAH361302",)
    assert ids_in_file_name("CAH361315-00") == ("CAH361315-00",)
    assert ids_in_file_name("DSH360059_and_FQHCLA415") == ("DSH360059", "FQHCLA415")
    assert ids_in_file_name("TB452022STD452191") == ("TB452022", "STD452191")
    assert ids_in_file_name("CH05157BC") == ("CH05157BC",)
    assert filing_id_of("CAH361315-00") == "oh-2025-cah361315-00"


def test_hrsa_spellings_that_differ_by_a_00_ending_match() -> None:
    index = hrsa_index([{"id_340b": "CAH361300-00", "name": "A"}, {"id_340b": "FP1", "name": "B"}])
    assert match_hrsa("CAH36130000", index).how == "exact"
    assert match_hrsa("CAH361300", index).how == "with or without the 00 ending"
    missing = match_hrsa("XX9", index)
    assert missing.entity is None
    assert missing.how == "not in HRSA's list"


def test_two_reads_agree_when_numbers_match_to_fifteen_digits() -> None:
    assert same_cell("602.56000000000006", "602.56")
    assert same_cell("#DIV/0!", "#DIV/0!")
    assert not same_cell("602.56", "602.57")
    assert not same_cell("Yes", "yes")
    assert not same_cell("1", "")


def test_a_cell_with_words_has_no_amount_and_a_count_is_whole() -> None:
    assert parse_workbook_amount("N/A") is None
    assert parse_workbook_amount("#DIV/0!") is None
    assert parse_workbook_amount("-") is None
    assert parse_workbook_amount("1,234.50") == Decimal("1234.50")
    assert parse_workbook_amount("602.56000000000006") == Decimal("602.56000000000006")
    assert parse_workbook_count("8.0") == 8
    assert parse_workbook_count("8.5") is None


def test_the_pharmacy_count_is_not_a_claim_count() -> None:
    assert column_of("contract_pharmacies", "count") == "amount"
    assert column_of("in_house_rx_all", "count") == "claims"
    assert column_of("identity", "none") == "answer"
    assert oh_unit("in_house_rx_all", "total") == "count"
    assert oh_unit("in_house_rx_all", "cell_J") == "count"
    assert oh_unit("in_house_rx_all", "nonsense") is None


def test_masking_uses_the_patterns_of_the_text_extractor() -> None:
    path = ROOT / "tools" / "extract_text.py"
    spec = importlib.util.spec_from_file_location("extract_text", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert (EMAIL.pattern, PHONE.pattern) == (module.EMAIL.pattern, module.PHONE.pattern)
    assert mask("write to a.b@example.org or call 614-555-0100") == (
        "write to [email address in the workbook] or call [phone number in the workbook]"
    )


def test_ohio_has_a_filing_for_every_workbook(ohio: tuple[Filing, ...]) -> None:
    assert len(ohio) == 241
    assert form_of(OH_FORM).workbook
    assert all(f.meta.record_kind == "filing" and f.source.page_count == 1 for f in ohio)
    assert len({f.source.file_name for f in ohio}) == 241
    entities = {r["entity_id"] for r in _rows("entities.csv") if r["state"] == "OH"}
    assert len(entities) == 242


def test_a_workbook_that_names_two_ids_is_one_filing_for_both(ohio: tuple[Filing, ...]) -> None:
    (both,) = [f for f in ohio if f.source.file_name == "DSH360059_and_FQHCLA415.xlsx"]
    assert both.meta.entity_id == "oh-dsh360059"
    assert both.meta.other_entity_ids == ("oh-fqhcla415",)
    ids = {r["entity_id"] for r in _rows("entities.csv")}
    assert {"oh-dsh360059", "oh-fqhcla415"} <= ids


def test_names_come_from_hrsa_and_are_kept_apart_from_the_filing() -> None:
    entities = [r for r in _rows("entities.csv") if r["state"] == "OH"]
    assert all(r["name_as_filed"] == "" for r in entities)
    unnamed = [r for r in entities if not r["hrsa_name"]]
    assert unnamed
    assert all(r["hrsa_match"] == "not in HRSA's list" for r in unnamed)
    assert all(r["hrsa_list_date"] == "2026-11-11" for r in entities)
    others = [r for r in _rows("entities.csv") if r["state"] != "OH"]
    assert all(
        not (r["hrsa_name"] or r["hrsa_id_spelling"] or r["hrsa_list_date"] or r["hrsa_match"])
        for r in others
    )


def test_every_row_has_two_reads(ohio: tuple[Filing, ...]) -> None:
    ok = {Verification.TWO_FILE_READS, Verification.ADJUDICATED}
    assert all(r.verification in ok for f in ohio for r in f.rows)
    adjudicated = [r for f in ohio for r in f.rows if r.verification is Verification.ADJUDICATED]
    assert adjudicated
    assert all(r.note for r in adjudicated)
    for f in ohio:
        path = ROOT / "verification" / "oh" / "2025" / f"{f.meta.filing_id}.file-read.csv"
        assert path.exists()


def test_no_committed_ohio_file_holds_an_email_address_or_a_phone_number() -> None:
    for path in _published():
        text = path.read_text(encoding="utf-8")
        assert not EMAIL.search(text), path.name
        assert not PHONE.search(text), path.name


def test_no_committed_ohio_file_holds_a_contact_cell_when_the_originals_are_here() -> None:
    folder = OHIO / ORIGINALS
    originals = sorted(folder.glob("*.xlsx")) if folder.exists() else []
    if not originals:
        pytest.skip("the original workbooks are not on this machine")
    text = "\n".join(path.read_text(encoding="utf-8") for path in _published())
    text = " ".join(text.split()).lower()
    for original in originals:
        book = read_workbook(original)
        position = template_sheet(book.sheets)
        assert position is not None
        sheet = book.sheets[position - 1]
        layout = map_sheet(sheet)
        for cell in sheet.cells:
            if cell.ref in layout.contact_refs:
                value = " ".join(cell.value.split()).lower()
                if len(value) >= 4:
                    assert value not in text, f"{original.name} {cell.ref}"


def test_the_published_files_do_not_give_a_withheld_count_away() -> None:
    withheld = 0
    for filing_id, rows in _ohio_line_items().items():
        for record in rows:
            if record["claims_withheld"]:
                withheld += 1
                assert record["claims"] == ""
                assert record["claims_as_filed"] == ""
                if record["claims_withheld"] == "reveals_small":
                    assert record["amount"] == ""
                    assert record["amount_as_filed"] == ""
        assert too_few(rows) == [], filing_id
    assert withheld > 0


def test_every_withheld_count_is_still_one_of_several_values_for_a_reader() -> None:
    held = read_private(ROOT)
    if held is None:
        pytest.skip("the private small counts are not on this machine")
    checked = 0
    for filing_id, rows in _ohio_line_items().items():
        for (schedule, line), domain in recover(rows).items():
            true = int(Decimal(held[(filing_id, schedule, line)].claims_as_filed))
            assert domain is None or true in domain, (filing_id, schedule, line)
            assert domain is None or len(domain) >= 2, (filing_id, schedule, line)
            checked += 1
    assert checked > 100


def test_a_withheld_cell_is_a_marker_in_the_cells_file() -> None:
    held = read_private(ROOT)
    if held is None:
        pytest.skip("the private small counts are not on this machine")
    marker = re.compile(r"^\[withheld: (fewer_than_6|beside_small|reveals_small)\]$")
    names = {r["filing_id"]: r["source_file"] for r in _rows("filings.csv")}
    sources = {
        (r["filing_id"], r["schedule"], r["line"]): r["source_cell"]
        for r in _rows("line_items.csv")
        if r["filing_id"].startswith("oh-")
    }
    checked = 0
    for filing_id, schedule, line in held:
        if not filing_id.startswith("oh-"):
            continue
        stem = names[filing_id].removesuffix(".xlsx")
        with (OHIO / "cells" / f"{stem}.csv").open(newline="", encoding="utf-8") as handle:
            cells = {r["cell"]: r["value"] for r in csv.DictReader(handle)}
        assert marker.match(cells[sources[(filing_id, schedule, line)]]), (filing_id, line)
        checked += 1
    assert checked > 100


def test_a_prescription_count_outside_the_form_is_never_a_small_number() -> None:
    """The earlier layout lists contract pharmacies in blocks that are not lines of the form."""
    for filing_id, rows in _ohio_line_items().items():
        stem = next(
            r["source_file"] for r in _rows("filings.csv") if r["filing_id"] == filing_id
        ).removesuffix(".xlsx")
        known = {r["source_cell"] for r in rows}
        with (OHIO / "cells" / f"{stem}.csv").open(newline="", encoding="utf-8") as handle:
            cells = {r["cell"]: r["value"] for r in csv.DictReader(handle)}
        for cell, value in cells.items():
            row = cell.lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
            label = cells.get(f"C{row}", "").lower()
            small = re.fullmatch(r"[1-5](\.0+)?", value.strip())
            if small and cell not in known and label.startswith("total number of"):
                pytest.fail(f"{filing_id} {cell} is a small prescription count outside the form")


def test_ohio_notes_state_cell_values_only() -> None:
    path = ROOT / "reference" / "discrepancy_notes.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        notes = [r for r in csv.DictReader(handle) if r["filing_id"].startswith("oh-")]
    assert notes
    assert all("holds" in note["note"] for note in notes)
