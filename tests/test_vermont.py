"""Vermont's form, tested on a made-up filing. Nothing here is a real filing."""

from __future__ import annotations

import csv
import io
from decimal import Decimal

import pytest
from conftest import VT_ROWS, Maker

from filings340b.build import build_outputs
from filings340b.cli import main
from filings340b.errors import DataError
from filings340b.forms import UnknownFormError, form_of
from filings340b.load import load_filings
from filings340b.model import Basis
from filings340b.money import parse_amount
from filings340b.textcheck import check_filing, text_file_for
from filings340b.tieout import checks, measures


def table(outputs: dict[str, bytes], name: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(outputs[name].decode("utf-8"))))


def swap(old: str, new: str) -> list[str]:
    assert any(old in row for row in VT_ROWS)
    return [row.replace(old, new) for row in VT_ROWS]


def test_every_rule_holds_on_the_clean_filing(make_vt_repo: Maker) -> None:
    (filing,) = load_filings(make_vt_repo())
    results = checks(filing)
    assert len(results) == 4
    assert all(c.applicable and c.passed for c in results)
    basis = {c.rule: c.basis for c in results}
    assert basis["payments.rows=total"] is Basis.FORM
    assert basis["expenses.rows=total"] is Basis.FORM
    assert basis["net_revenue=payments-acquisition-expenses"] is Basis.FORM
    assert basis["operating_margin=net_revenue/payments"] is Basis.COMPARISON
    assert {c.rule: c.unit for c in results}["operating_margin=net_revenue/payments"] == "percent"


def test_measures_use_vermonts_rows(make_vt_repo: Maker) -> None:
    (filing,) = load_filings(make_vt_repo())
    found = {name: (formula, value) for name, formula, value in measures(filing)}
    assert found["gross_margin"][1] == Decimal("250.00")
    assert found["external_cost"][1] == Decimal("15.00")
    assert found["external_share_of_margin"][1] == Decimal("0.060000")
    assert (
        "Total 340B Payments Received minus 340B Prescription Drug Acquisition Costs"
        in (found["gross_margin"][0])
    )
    assert (
        "Payments Made to Contract Pharmacies plus Payments Made to Outside Vendors"
        in (found["external_cost"][0])
    )


def test_the_share_is_blank_when_the_margin_is_not_above_zero(make_vt_repo: Maker) -> None:
    rows = swap(
        "340B Prescription Drug Acquisition Costs,,,,100.00",
        "340B Prescription Drug Acquisition Costs,,,,350.00",
    )
    (filing,) = load_filings(make_vt_repo(rows))
    found = {name: value for name, _, value in measures(filing)}
    assert found["gross_margin"] == Decimal("0.00")
    assert found["external_share_of_margin"] is None


def test_a_payment_total_that_differs_is_recorded_before_it_can_be_published(
    make_vt_repo: Maker,
) -> None:
    rows = swap("Total 340B Payments Received,,,,350.00", "Total 340B Payments Received,,,,351.00")
    with pytest.raises(DataError, match=r"payments\.rows=total"):
        build_outputs(make_vt_repo(rows))
    notes = (
        "zv-2025-example,payments.rows=total,Rows differ from the total.\n"
        "zv-2025-example,net_revenue=payments-acquisition-expenses,Net revenue differs.\n"
        "zv-2025-example,operating_margin=net_revenue/payments,"
        '"The page does not say how the margin is calculated."\n'
    )
    found = table(build_outputs(make_vt_repo(rows, notes)), "discrepancies.csv")
    by_rule = {d["rule"]: d for d in found}
    assert by_rule["payments.rows=total"]["difference"] == "1.00"
    assert by_rule["payments.rows=total"]["unit"] == "usd"
    assert by_rule["net_revenue=payments-acquisition-expenses"]["difference"] == "-1.00"
    margin = by_rule["operating_margin=net_revenue/payments"]
    assert (margin["basis"], margin["unit"]) == ("comparison", "percent")
    assert (margin["expected"], margin["filed"], margin["difference"]) == (
        "61.25",
        "61.43",
        "0.18",
    )


def test_the_margin_is_compared_at_the_printed_precision(make_vt_repo: Maker) -> None:
    # 215 / 350 is 61.4285...: 61.43 holds at two places; 61.4 holds at one; 61.42 does not.
    (filing,) = load_filings(make_vt_repo(swap("61.43%", "61.4%")))
    assert all(c.passed for c in checks(filing))
    (filing,) = load_filings(make_vt_repo(swap("61.43%", "61.42%")))
    failing = [c for c in checks(filing) if c.applicable and not c.passed]
    assert [c.rule for c in failing] == ["operating_margin=net_revenue/payments"]


def test_a_cell_printing_n_r_has_no_figure_and_adds_nothing(make_vt_repo: Maker) -> None:
    rows = swap(
        "Administered Drugs Paid Separately,,,,0.00", "Administered Drugs Paid Separately,,,,N/R"
    )
    (filing,) = load_filings(make_vt_repo(rows))
    row = next(r for r in filing.rows if r.line == "administered_paid_separately")
    assert (row.amount_as_filed, row.amount) == ("N/R", None)
    assert all(c.passed for c in checks(filing))
    assert parse_amount("N/R") is None


def test_a_negative_net_revenue_and_margin_are_read_with_their_marks(make_vt_repo: Maker) -> None:
    rows = [r.replace("61.43%", "-61.43%") for r in swap("215.00,,,1", "(215.00),,,1")]
    (filing,) = load_filings(make_vt_repo(rows))
    values = {r.line: r.amount for r in filing.rows}
    assert values["net_revenue"] == Decimal("-215.00")
    assert values["operating_margin"] == Decimal("-61.43")


def test_units_filing_status_and_attachments_are_published(make_vt_repo: Maker) -> None:
    outputs = build_outputs(make_vt_repo())
    units = {(r["schedule"], r["line"]): r["unit"] for r in table(outputs, "line_items.csv")}
    assert units[("payments", "total")] == "usd"
    assert units[("result", "operating_margin")] == "percent"
    (filing,) = table(outputs, "filings.csv")
    assert filing["form"] == "vt-gmcb-340b-financial"
    assert filing["status_as_filed"] == "draft"
    assert filing["status_notice_as_filed"] == "NOTE: Made up."
    assert filing["period_as_filed"] == "FY2025"
    assert filing["cover_page_url"] == "https://example.invalid/document/financial"
    assert filing["corporate_address_as_filed"] == ""
    (attachment,) = table(outputs, "attachments.csv")
    assert (attachment["kind"], attachment["first_page"], attachment["last_page"]) == (
        "narrative",
        "1",
        "3",
    )
    assert attachment["document_file"] == "narrative.pdf"
    assert len(attachment["document_sha256"]) == 64
    measure_names = {m["measure"] for m in table(outputs, "measures.csv")}
    assert measure_names == {"gross_margin", "external_cost", "external_share_of_margin"}


def test_the_chart_stays_rhode_island_only(make_vt_repo: Maker) -> None:
    outputs = build_outputs(make_vt_repo())
    assert b"Example Hospital" not in outputs["external-share-light.svg"]


def test_text_check_passes_on_the_clean_filing(make_vt_repo: Maker) -> None:
    root = make_vt_repo()
    (filing,) = load_filings(root)
    assert check_filing(filing, text_file_for(root, filing)) == []
    assert main(["tieout", "--root", str(root)]) == 0


def test_a_changed_narrative_is_refused(make_vt_repo: Maker) -> None:
    root = make_vt_repo()
    (root / "sources" / "zv" / "2025" / "narrative.pdf").write_bytes(b"%PDF-other\n")
    with pytest.raises(DataError, match="not the recorded hash"):
        load_filings(root)


def test_a_line_that_is_not_on_the_form_is_refused(make_vt_repo: Maker) -> None:
    rows = [*VT_ROWS, "payments,bonus,detail,Bonus,,,,1.00,,,1,text_and_image,"]
    with pytest.raises(DataError, match="is not on form"):
        load_filings(make_vt_repo(rows))
    letter = [*VT_ROWS, "A,1,detail,Acquisition,,,,1.00,,,1,text_and_image,"]
    with pytest.raises(DataError, match="is not on form"):
        load_filings(make_vt_repo(letter))


def test_a_filing_must_name_a_known_form(make_vt_repo: Maker) -> None:
    root = make_vt_repo()
    meta = root / "transcriptions" / "zv" / "2025" / "zv-2025-example.meta.toml"
    good = meta.read_text(encoding="utf-8")
    meta.write_text(good.replace("vt-gmcb-340b-financial", "no-such-form"), encoding="utf-8")
    with pytest.raises(DataError, match="unknown form"):
        load_filings(root)
    meta.write_text(good.replace('form = "vt-gmcb-340b-financial"\n', ""), encoding="utf-8")
    with pytest.raises(DataError, match="must name its form"):
        load_filings(root)
    with pytest.raises(UnknownFormError):
        form_of("no-such-form")
