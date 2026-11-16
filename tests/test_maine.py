"""Maine's form, tested on a made-up report. Nothing here is a real report."""

from __future__ import annotations

import csv
import hashlib
import io
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

import pytest

from filings340b.build import build_outputs
from filings340b.cli import main
from filings340b.errors import DataError
from filings340b.forms import ME_FORM, form_of, me_unit
from filings340b.load import load_filings
from filings340b.model import Basis, Check
from filings340b.textcheck import check_filing, text_file_for
from filings340b.tieout import checks, measures

FID = "zf-2024-statewide"
HEADER = (
    "schedule,line,row_kind,label_as_filed,name_as_filed,description_as_filed,"
    "ndc_as_filed,amount_as_filed,claims_as_filed,answer_as_filed,page,verification,note"
)
Maker = Callable[..., Path]

# A made-up report of four hospitals. The tile says $10.0M was spent on drugs. The costly table's
# acquisition cost rows add up to 1,560,000, which is 15.6% of that; the frequent table's add up
# to 240,000, which is 2.4%. Each table's hospital counts add up to 12, which is 3 times 4.
ROWS = [
    "summary,hospitals_reporting,detail,4 hospitals sent data.,,,,4,,,2,text_and_image,",
    "summary,acquisition_cost,detail,The hospitals spent $10.0M on drugs.,,,,,,$10.0M,2,"
    "text_and_image,",
    "summary,pct_of_drug_spend,detail,The hospitals spent $10.0M on drugs.,,,,50.0%,,,2,"
    "text_and_image,",
    "summary,estimated_savings,detail,Savings were $5.0M.,,,,,,$5.0M,2,text_and_image,",
    "top3_costly,pct_of_acquisition_cost,detail,The costly drugs were 15.6% of the total.,,,,"
    "15.6%,,,3,text_and_image,",
    "top3_costly,00000000001_acquisition_cost,detail,Drug One,Class A,Total Cost,00000000001,"
    '"1,000,000",,,3,'
    "text_and_image,",
    "top3_costly,00000000001_estimated_savings,detail,Drug One,Class A,Total Savings,"
    '00000000001,"400,000",,,3,'
    "text_and_image,",
    "top3_costly,00000000001_hospitals,detail,Drug One,Class A,Hospitals,00000000001,7,,,3,"
    "text_and_image,",
    "top3_costly,00000000002_acquisition_cost,detail,Drug Two,Class B,Total Cost,00000000002,"
    '"560,000",,,3,text_and_image,',
    "top3_costly,00000000002_estimated_savings,detail,Drug Two,Class B,Total Savings,00000000002,"
    '"100,000",,,3,text_and_image,',
    "top3_costly,00000000002_hospitals,detail,Drug Two,Class B,Hospitals,00000000002,5,,,3,"
    "text_and_image,",
    "top3_frequent,pct_of_acquisition_cost,detail,The frequent drugs were 2.4% of the total.,,,,"
    "2.4%,,,4,text_and_image,",
    "top3_frequent,00000000003_acquisition_cost,detail,Drug Three,Class C,Total Cost,00000000003,"
    '"200,000",,,4,text_and_image,',
    "top3_frequent,00000000003_estimated_savings,detail,Drug Three,Class C,Total Savings,"
    '00000000003,"50,000",,,4,text_and_image,',
    "top3_frequent,00000000003_hospitals,detail,Drug Three,Class C,Hospitals,00000000003,6,,,4,"
    "text_and_image,",
    "top3_frequent,00000000004_acquisition_cost,detail,Drug Four,Class C,Total Cost,00000000004,"
    '"40,000",,,4,text_and_image,',
    "top3_frequent,00000000004_estimated_savings,detail,Drug Four,Class C,Total Savings,"
    '00000000004,"10,000",,,4,text_and_image,',
    "top3_frequent,00000000004_hospitals,detail,Drug Four,Class C,Hospitals,00000000004,6,,,4,"
    "text_and_image,",
    "page_note,note_1,detail,A made-up heading,,,,,,,3,text_and_image,",
]
PAGES = (
    "Cover\n\f"
    "4 hospitals sent data. The hospitals spent $10.0M on drugs. 50.0% Savings were $5.0M.\n\f"
    "A made-up heading. The costly drugs were 15.6% of the total.\n"
    "Drug One 00000000001 $1,000,000 $400,000 7\n"
    "Drug Two 00000000002 $560,000 $100,000 5\n\f"
    "The frequent drugs were 2.4% of the total.\n"
    "Drug Three 00000000003 $200,000 $50,000 6\n"
    "Drug Four 00000000004 $40,000 $10,000 6\n\f"
)
META = """\
filing_id = "zf-2024-statewide"
entity_id = "zf-statewide"
state = "ZF"
reporting_year = 2024
entity_type = "state_total"
record_kind = "state_report_totals"
source_file = "report.pdf"
form = "me-mhdo-340b-report"
form_revision = "Made-up report"

[cover]
name_as_filed = ""
corporate_address_as_filed = ""
opais_ids_as_filed = ""
recertification_date_as_filed = ""
reporting_basis_as_filed = ""

[printed]
period_as_filed = "a made-up year"
"""


@pytest.fixture
def make_me_repo(tmp_path: Path) -> Maker:
    """Return a function that writes a made-up Maine-style repository.

    ``edits`` is a list of (old, new) text replaced in the record's rows; ``notes`` is the text
    of ``discrepancy_notes.csv`` after its header.
    """

    def make(edits: list[tuple[str, str]] | None = None, notes: str = "") -> Path:
        sources = tmp_path / "sources" / "zf" / "2024"
        (sources / "text").mkdir(parents=True, exist_ok=True)
        pdf = b"%PDF-made-up statewide report\n"
        (sources / "report.pdf").write_bytes(pdf)
        (sources / "manifest.csv").write_text(
            "file_name,source_url,retrieved_at,sha256,size_bytes,page_count,scanned\n"
            f"report.pdf,https://example.invalid/report.pdf,2026-01-01T00:00:00Z,"
            f"{hashlib.sha256(pdf).hexdigest()},{len(pdf)},4,false\n",
            encoding="utf-8",
        )
        (sources / "text" / "report.txt").write_text(PAGES, encoding="utf-8")
        body = "\n".join([HEADER, *ROWS]) + "\n"
        for old, new in edits or []:
            assert old in body, old
            body = body.replace(old, new)
        folder = tmp_path / "transcriptions" / "zf" / "2024"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{FID}.meta.toml").write_text(META, encoding="utf-8")
        (folder / f"{FID}.csv").write_text(body, encoding="utf-8")
        reference = tmp_path / "reference"
        reference.mkdir(exist_ok=True)
        (reference / "vendors.csv").write_text(
            "normalized_name,vendor_type,alias_as_filed\n", encoding="utf-8"
        )
        (reference / "categories.csv").write_text(
            "filing_id,schedule,line,category\n", encoding="utf-8"
        )
        (reference / "discrepancy_notes.csv").write_text(
            "filing_id,rule,note\n" + notes, encoding="utf-8"
        )
        return tmp_path

    return make


def table(outputs: dict[str, bytes], name: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(outputs[name].decode("utf-8"))))


def found(root: Path) -> dict[str, Check]:
    (filing,) = load_filings(root)
    return {c.rule: c for c in checks(filing)}


SHARE = "top3_costly.pct_of_acquisition_cost=acquisition_cost.sum/summary.acquisition_cost"


def test_every_rule_holds_on_the_clean_report(make_me_repo: Maker) -> None:
    rules = found(make_me_repo())
    assert len(rules) == 4
    assert all(c.applicable and c.passed for c in rules.values())
    assert {c.basis for c in rules.values()} == {Basis.COMPARISON}
    assert rules[SHARE].unit == "percent"
    assert rules["top3_frequent.hospitals=3*summary.hospitals_reporting"].unit == "count"


def test_the_form_fixes_each_rows_unit_and_refuses_other_keys() -> None:
    assert form_of(ME_FORM).record_kinds == ("state_report_totals",)
    assert me_unit("summary", "hospitals_reporting") == "count"
    assert me_unit("summary", "acquisition_cost") == "none"
    assert me_unit("summary", "pct_of_drug_spend") == "percent"
    assert me_unit("top3_costly", "pct_of_acquisition_cost") == "percent"
    assert me_unit("top3_frequent", "00006302602_acquisition_cost") == "usd"
    assert me_unit("top3_frequent", "00006302602_estimated_savings") == "usd"
    assert me_unit("top3_costly", "00006302602_hospitals") == "count"
    for schedule, line in (
        ("top3_costly", "0000630260_hospitals"),
        ("top3_costly", "00006302602_claims"),
        ("top3_costly", "pct_of_acquisition_cost_extra"),
        ("summary", "00006302602_hospitals"),
        ("claims", "total_claims"),
    ):
        assert me_unit(schedule, line) is None


def test_a_row_the_form_does_not_know_is_refused(make_me_repo: Maker) -> None:
    root = make_me_repo([("00000000003_hospitals", "0000000003_hospitals")])
    with pytest.raises(DataError, match="is not on form"):
        load_filings(root)


@pytest.mark.parametrize(("printed", "holds"), [("15.5%", True), ("15.7%", True), ("15.8%", False)])
def test_a_share_inside_the_range_the_rounded_total_allows_agrees(
    make_me_repo: Maker, printed: str, holds: bool
) -> None:
    c = found(make_me_repo([(",15.6%,,,3,", f",{printed},,,3,")]))[SHARE]
    assert c.applicable
    assert c.passed is holds
    if not holds:
        # The share at the printed total itself: 1,560,000 over 10,000,000.
        assert (c.expected, c.filed, c.unit) == (Decimal("15.6"), Decimal("15.8"), "percent")


def test_hospital_counts_that_do_not_make_three_each_are_recorded(make_me_repo: Maker) -> None:
    root = make_me_repo([("00000000001,7,,,3", "00000000001,8,,,3")])
    c = found(root)["top3_costly.hospitals=3*summary.hospitals_reporting"]
    assert (c.expected, c.filed, c.difference, c.unit) == (
        Decimal(12),
        Decimal(13),
        Decimal(1),
        "count",
    )
    with pytest.raises(DataError, match=r"hospitals=3\*summary"):
        build_outputs(root)
    note = "top3_costly.hospitals=3*summary.hospitals_reporting,The column adds up to 13.\n"
    outputs = build_outputs(
        make_me_repo([("00000000001,7,,,3", "00000000001,8,,,3")], FID + "," + note)
    )
    (d,) = table(outputs, "discrepancies.csv")
    assert (d["filing_id"], d["basis"], d["unit"], d["difference"]) == (
        FID,
        "comparison",
        "count",
        "1",
    )


def test_rules_do_not_apply_when_a_figure_is_missing(make_me_repo: Maker) -> None:
    root = make_me_repo(
        [
            (
                "summary,hospitals_reporting,detail,4 hospitals sent data.,,,,4,",
                "summary,hospitals_reporting,detail,4 hospitals sent data.,,,,N/A,",
            )
        ]
    )
    rules = found(root)
    assert not rules["top3_costly.hospitals=3*summary.hospitals_reporting"].applicable
    assert rules[SHARE].applicable


def test_the_report_has_no_measures(make_me_repo: Maker) -> None:
    (filing,) = load_filings(make_me_repo())
    assert measures(filing) == ()
    assert not table(build_outputs(make_me_repo()), "measures.csv")


def test_every_published_row_has_its_unit(make_me_repo: Maker) -> None:
    items = table(build_outputs(make_me_repo()), "line_items.csv")
    units = {(r["schedule"], r["line"]): r["unit"] for r in items}
    assert units[("summary", "hospitals_reporting")] == "count"
    assert units[("summary", "acquisition_cost")] == "none"
    assert units[("top3_costly", "00000000001_acquisition_cost")] == "usd"
    assert units[("top3_costly", "00000000001_hospitals")] == "count"
    assert units[("top3_frequent", "pct_of_acquisition_cost")] == "percent"
    ndc = {r["ndc_as_filed"] for r in items if r["schedule"] == "top3_costly"}
    assert ndc == {"", "00000000001", "00000000002"}


def test_the_made_up_text_agrees_with_the_made_up_rows(make_me_repo: Maker) -> None:
    root = make_me_repo()
    (filing,) = load_filings(root)
    assert [p for p in check_filing(filing, text_file_for(root, filing)) if p.fatal] == []


def test_a_figure_the_page_does_not_print_is_caught(make_me_repo: Maker) -> None:
    root = make_me_repo([('"1,000,000"', '"1,000,001"')])
    (filing,) = load_filings(root)
    problems = [p.detail for p in check_filing(filing, text_file_for(root, filing)) if p.fatal]
    assert any("1,000,001 is not printed on this page" in p for p in problems)
    assert any("1,000,000 is printed here but no row carries it" in p for p in problems)


def test_the_command_line_runs_the_rules(
    make_me_repo: Maker, capsys: pytest.CaptureFixture[str]
) -> None:
    root = make_me_repo()
    assert main(["tieout", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert out.count("ok   zf-2024-statewide") == 4
    assert "DIFF" not in out
