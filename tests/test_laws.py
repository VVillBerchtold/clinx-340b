"""The table of state laws, tested on a made-up law. Nothing here is a real law."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
from datetime import date
from pathlib import Path
from types import ModuleType

import pytest
from conftest import Maker

from filings340b.build import build_outputs
from filings340b.errors import DataError
from filings340b.laws import COLUMNS, date_forms, load_laws, load_not_listed

KINDS = (
    "kind,label,description\n"
    "contract-pharmacy,Contract pharmacy access,Limits what a drug maker may do.\n"
    "reporting,Reporting,Requires figures to be reported.\n"
)
HOSTS = (
    "host,state,owner\n"
    "example.invalid,RI,A made-up legislature\n"
    "history.example.invalid,RI,A made-up legislature\n"
)
# The second saved page: a bill history that prints the day the law was signed.
HISTORY = "H 1. 06/01/2025 Signed by Governor.\n"
# The saved page: the sentence the row quotes runs over a line break.
PAGE = (
    "An Act about made-up things.\n"
    "Section 1. A manufacturer shall not deny a 340B drug to a pharmacy\n"
    "under contract with a covered entity.\n"
    "Section 2. This act takes effect July 1, 2025.\n"
)
QUOTE = "A manufacturer shall not deny a 340B drug to a pharmacy under contract"


def a_row(**changes: str) -> dict[str, str]:
    row = {
        "law_id": "ri-2025-h1",
        "state": "RI",
        "kinds": "contract-pharmacy",
        "title": "Made-Up Act",
        "citation": "R.I. Gen. Laws 0-0-0",
        "bill": "H 1",
        "session_year": "2025",
        "act": "Chapter 1",
        "signed_date": "",
        "effective_date": "2025-07-01",
        "binds": "drug manufacturers",
        "summary": "A drug maker may not hold back a 340B drug from a contract pharmacy.",
        "limits": "",
        "enforcement": "",
        "quote": QUOTE,
        "source_url": "https://example.invalid/law",
        "source_form": "web page",
        "source_text": "sources/laws/ri/ri-2025-h1.txt",
        "source_sha256": hashlib.sha256(PAGE.encode()).hexdigest(),
        "more_url": "",
        "more_text": "",
        "more_sha256": "",
        "source_note": "",
        "retrieved": "2026-01-01",
    }
    return {**row, **changes}


def write_laws(root: Path, rows: list[dict[str, str]], page: str = PAGE) -> Path:
    (root / "laws").mkdir(exist_ok=True)
    (root / "laws" / "kinds.csv").write_text(KINDS, encoding="utf-8")
    (root / "laws" / "hosts.csv").write_text(HOSTS, encoding="utf-8")
    handle = io.StringIO()
    writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    (root / "laws" / "laws.csv").write_text(handle.getvalue(), encoding="utf-8")
    folder = root / "sources" / "laws" / "ri"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "ri-2025-h1.txt").write_text(page, encoding="utf-8")
    return root


def test_a_repository_with_no_laws_table_builds_no_laws_file(make_repo: Maker) -> None:
    outputs = build_outputs(make_repo())
    assert "state-laws.csv" not in outputs
    assert "340b-state-laws.json" not in outputs


def test_a_clean_row_is_published_in_both_files(make_repo: Maker) -> None:
    outputs = build_outputs(write_laws(make_repo(), [a_row()]))
    (row,) = csv.DictReader(io.StringIO(outputs["state-laws.csv"].decode("utf-8")))
    assert row == a_row()
    document = json.loads(outputs["340b-state-laws.json"])
    assert [k["kind"] for k in document["kinds"]] == ["contract-pharmacy", "reporting"]
    (law,) = document["laws"]
    assert law["kinds"] == ["contract-pharmacy"]
    assert law["quote"] == QUOTE
    assert all(set(site) == {"host", "state", "owner"} for site in document["sites"])
    assert [site["host"] for site in document["sites"] if site["state"] == law["state"]]


def test_two_kinds_are_a_list_in_the_json_file(make_repo: Maker) -> None:
    root = write_laws(make_repo(), [a_row(kinds="contract-pharmacy|reporting")])
    document = json.loads(build_outputs(root)["340b-state-laws.json"])
    assert document["laws"][0]["kinds"] == ["contract-pharmacy", "reporting"]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"quote": "A manufacturer shall not refuse a 340B drug to a pharmacy"}, "word for word"),
        ({"quote": "under contract with a covered entity."}, "itself names"),
        ({"quote": "a 340B drug"}, "single-spaced"),
        ({"quote": QUOTE.replace("deny a", "deny  a")}, "single-spaced"),
        ({"source_sha256": "0" * 64}, "SHA-256"),
        ({"kinds": "payer"}, "kinds"),
        ({"kinds": "reporting|contract-pharmacy"}, "in the order"),
        ({"kinds": ""}, "kinds"),
        ({"state": "ZZ"}, "not a state"),
        ({"law_id": "ri-2024-h1"}, "law_id"),
        ({"session_year": "1980", "law_id": "ri-1980-h1"}, "not a year"),
        ({"signed_date": "June 1, 2025"}, "YYYY-MM-DD"),
        ({"signed_date": "2025-06-01"}, "not printed"),
        ({"effective_date": "2025-07-02"}, "not printed"),
        ({"source_url": "https://copy.example.invalid/law"}, "not listed"),
        ({"more_text": "sources/laws/ri/ri-2025-h1.more.txt"}, "are empty"),
        ({"retrieved": ""}, "retrieved"),
        ({"summary": "A drug maker may not hold back a 340B drug"}, "full sentences"),
        ({"summary": "The earlier act failed to say so."}, "say what the text says"),
        ({"limits": "Ends in 2027 because of a sunset."}, "say what the text says"),
        ({"enforcement": "A fine for a mistake."}, "say what the text says"),
        ({"source_url": "http://example.invalid/law"}, "https"),
        ({"more_url": "example.invalid"}, "https"),
        ({"source_form": "screenshot"}, "source_form"),
        ({"source_text": "sources/laws/ri/other.txt"}, "the saved text is"),
    ],
)
def test_a_row_that_breaks_a_rule_stops_the_build(
    make_repo: Maker, changes: dict[str, str], message: str
) -> None:
    root = write_laws(make_repo(), [a_row(**changes)])
    with pytest.raises(DataError, match=message):
        load_laws(root)


def test_a_saved_text_that_does_not_name_the_program_stops_the_build(make_repo: Maker) -> None:
    page = "An Act about made-up things.\nA manufacturer shall not deny a drug.\n"
    row = a_row(source_sha256=hashlib.sha256(page.encode()).hexdigest())
    with pytest.raises(DataError, match="does not name the 340B program"):
        load_laws(write_laws(make_repo(), [row], page))


def test_the_federal_section_counts_as_naming_the_program(make_repo: Maker) -> None:
    page = (
        "A covered entity is one defined in Section 256b of Title 42 of the United States Code.\n"
    )
    row = a_row(
        quote="A covered entity is one defined in Section 256b of Title 42",
        effective_date="",
        source_sha256=hashlib.sha256(page.encode()).hexdigest(),
    )
    laws, _ = load_laws(write_laws(make_repo(), [row], page))
    assert len(laws) == 1


def with_history(root: Path, **changes: str) -> dict[str, str]:
    """Save the bill history beside the law's page and return a row that names it."""
    path = root / "sources" / "laws" / "ri" / "ri-2025-h1.more.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(HISTORY, encoding="utf-8")
    row = {
        "signed_date": "2025-06-01",
        "more_url": "https://history.example.invalid/h1",
        "more_text": "sources/laws/ri/ri-2025-h1.more.txt",
        "more_sha256": hashlib.sha256(HISTORY.encode()).hexdigest(),
    }
    return a_row(**{**row, **changes})


def test_a_date_printed_on_the_second_saved_page_is_accepted(make_repo: Maker) -> None:
    root = make_repo()
    laws, _ = load_laws(write_laws(root, [with_history(root)]))
    assert laws[0]["signed_date"] == "2025-06-01"


def test_a_second_page_that_changed_stops_the_build(make_repo: Maker) -> None:
    root = make_repo()
    row = with_history(root, more_sha256="0" * 64)
    with pytest.raises(DataError, match="SHA-256"):
        load_laws(write_laws(root, [row]))


def test_a_date_is_found_however_the_page_prints_it() -> None:
    forms = date_forms(date(2024, 9, 1))
    for printed in ("september 1, 2024", "sept. 1, 2024", "9/1/2024", "09/01/24", "1 sep 2024"):
        assert printed in forms
    assert "1st day of september, 2024" in forms
    assert "13th day of may 2025" in date_forms(date(2025, 5, 13))
    assert "22nd day of june, 2021" in date_forms(date(2021, 6, 22))


def write_not_listed(root: Path, body: str) -> Path:
    path = root / "laws" / "not-listed.csv"
    path.write_text("state,name,reason,source_url\n" + body, encoding="utf-8")
    return root


def test_what_was_left_out_is_published_with_its_reason(make_repo: Maker) -> None:
    root = write_laws(make_repo(), [a_row()])
    write_not_listed(root, "RI,H 2 (2025),The saved page does not name the program.,\n")
    outputs = build_outputs(root)
    (row,) = csv.DictReader(io.StringIO(outputs["state-laws-not-listed.csv"].decode("utf-8")))
    assert row["name"] == "H 2 (2025)"
    assert json.loads(outputs["340b-state-laws.json"])["not_listed"] == [row]


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("ZZ,H 2,Not read.,\n", "a state and a name"),
        ("RI,H 2,Not read,\n", "full sentence"),
        ("RI,H 2,The lead was wrong.,\n", "say what was found"),
        ("RI,H 2,Not read.,https://copy.example.invalid/h2\n", "not listed"),
        ("RI,H 3,Not read.,\nRI,H 2,Not read.,\n", "in order"),
    ],
)
def test_a_left_out_row_that_breaks_a_rule_stops_the_build(
    make_repo: Maker, body: str, message: str
) -> None:
    root = write_not_listed(write_laws(make_repo(), [a_row()]), body)
    with pytest.raises(DataError, match=message):
        load_not_listed(root)


def test_a_missing_saved_text_stops_the_build(make_repo: Maker) -> None:
    root = write_laws(make_repo(), [a_row()])
    (root / "sources" / "laws" / "ri" / "ri-2025-h1.txt").unlink()
    with pytest.raises(DataError, match="is missing"):
        load_laws(root)


def test_a_saved_text_no_row_names_stops_the_build(make_repo: Maker) -> None:
    root = write_laws(make_repo(), [a_row()])
    (root / "sources" / "laws" / "ri" / "left-over.txt").write_text("340B\n", encoding="utf-8")
    with pytest.raises(DataError, match="no row names"):
        load_laws(root)


def test_a_law_listed_twice_stops_the_build(make_repo: Maker) -> None:
    with pytest.raises(DataError, match="listed twice"):
        load_laws(write_laws(make_repo(), [a_row(), a_row()]))


def test_other_columns_stop_the_build(make_repo: Maker) -> None:
    root = write_laws(make_repo(), [a_row()])
    path = root / "laws" / "laws.csv"
    path.write_text(path.read_text(encoding="utf-8").replace("law_id,", "id,", 1), encoding="utf-8")
    with pytest.raises(DataError, match="columns"):
        load_laws(root)


def _tool() -> ModuleType:
    path = Path(__file__).parent.parent / "tools" / "save_law_text.py"
    spec = importlib.util.spec_from_file_location("save_law_text", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_margin_numbers_come_off_a_numbered_bill_only() -> None:
    tidy = _tool().tidy
    numbered = " 1  A manufacturer shall not deny a 340B\n 2  drug to a pharmacy.\n 3  Section 2.\n"
    assert tidy(numbered, from_pdf=True) == (
        "A manufacturer shall not deny a 340B drug to a pharmacy.\nSection 2.\n"
    )
    plain = "A drug bought under\n42 U.S.C. 256b is a 340B drug.\nIt is defined there.\n"
    assert "under 42 U.S.C. 256b" in tidy(plain, from_pdf=True)


def test_contact_details_and_curly_marks_do_not_reach_the_saved_text() -> None:
    tidy = _tool().tidy
    text = tidy(
        "Call (401) 555-0100 or write to a.member@example.invalid — “340B”.", from_pdf=False
    )
    assert "555" not in text
    assert "@" not in text
    assert '- "340B".' in text
    toll_free = tidy("Call 1-800-555-0100 or 1 (800) 555-0199 for help.", from_pdf=False)
    assert "555" not in toll_free
    assert "800" not in toll_free


def test_a_section_number_reads_the_same_however_the_page_typed_its_hyphens(tmp_path: Path) -> None:
    tool = _tool()
    assert tool.tidy("G.S. 58\u201056A\u201150 and 58\u201251\u201537", from_pdf=False) == (
        "G.S. 58-56A-50 and 58-51-37\n"
    )
    page = tmp_path / "page"
    # A page in the Windows character set: byte 0x96 is its dash.
    page.write_bytes(b"<p>Pharmacy. \x96 A 340B pharmacy.</p>")
    assert tool.page_text(page) == ("web page", "Pharmacy. - A 340B pharmacy.\n")


def test_a_web_page_is_saved_as_the_words_a_reader_sees(tmp_path: Path) -> None:
    page = tmp_path / "page"
    page.write_bytes(
        b"<html><style>p{}</style><p>An act.</p><script>x()</script>"
        b"<p>Section 1 names 340B drugs.</p></html>"
    )
    form, text = _tool().page_text(page)
    assert form == "web page"
    assert text == "An act.\nSection 1 names 340B drugs.\n"
