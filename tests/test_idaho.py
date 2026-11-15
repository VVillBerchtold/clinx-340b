"""Idaho's form, tested on a made-up report. Nothing here is a real report."""

from __future__ import annotations

import csv
import io
from decimal import Decimal

import pytest
from conftest import Maker

from filings340b.build import build_outputs
from filings340b.cli import main
from filings340b.errors import DataError
from filings340b.forms import ID_CELLS, form_of
from filings340b.load import load_filings
from filings340b.model import Basis, Check
from filings340b.textcheck import check_filing, text_file_for
from filings340b.tieout import checks, measures

FID = "zd-2025-statewide"
MARGIN_RULE = "savings_use.total=payments_received.total-acquisition_cost.total"


def table(outputs: dict[str, bytes], name: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(outputs[name].decode("utf-8"))))


def found(root: object) -> dict[str, Check]:
    (filing,) = load_filings(root)  # type: ignore[arg-type]
    return {c.rule: c for c in checks(filing)}


def test_every_rule_holds_on_the_clean_report(make_id_repo: Maker) -> None:
    rules = found(make_id_repo())
    # Five tables add up; 4 x 7 + 10 percentages; the submissions percentage; four tiles;
    # four chart labels; savings beside the margin.
    assert len(rules) == 5 + 38 + 1 + 4 + 4 + 1
    assert all(c.applicable and c.passed for c in rules.values())
    form = {rule for rule, c in rules.items() if c.basis is Basis.FORM}
    assert form == {
        "acquisition_cost.rows=total",
        "payments_received.rows=total",
        "contract_pharmacy_payments.rows=total",
        "claims.rows=total",
        "savings_use.rows=total",
    }
    assert rules["claims.rows=total"].unit == "count"
    assert rules["payments_received.rows=total"].unit == "usd"
    assert rules["claims.medicare_pct=medicare/total"].unit == "percent"
    assert rules["key_highlights.covered_entities=submissions.received"].unit == "count"
    assert rules[MARGIN_RULE].basis is Basis.COMPARISON


def test_a_table_whose_rows_do_not_add_to_its_total_is_recorded(make_id_repo: Maker) -> None:
    old = 'claims,medicaid_claims,detail,Medicaid,,Total Claims,,"20,000"'
    edits = (old, old.replace("20,000", "20,393"))
    c = found(make_id_repo(edits))["claims.rows=total"]
    assert (c.expected, c.filed, c.difference, c.unit) == (
        Decimal(200393),
        Decimal(200000),
        Decimal(-393),
        "count",
    )
    with pytest.raises(DataError, match=r"no record in discrepancy_notes\.csv"):
        build_outputs(make_id_repo(edits))


def test_a_percentage_is_compared_at_the_printed_precision(make_id_repo: Maker) -> None:
    old = "savings_use,access_barriers_pct,detail,Programs addressing barriers to healthcare access"
    row = old + ",,% of Total Savings,,5.0%"
    rules = found(make_id_repo((row, row.replace("5.0%", "5.1%"))))
    c = rules["savings_use.access_barriers_pct=access_barriers/total"]
    assert (c.expected, c.filed, c.difference) == (Decimal("5.0"), Decimal("5.1"), Decimal("0.1"))
    assert c.basis is Basis.COMPARISON
    assert rules["savings_use.other_uses_pct=other_uses/total"].passed


def test_a_tile_is_compared_with_its_table_total_rounded_the_same_way(
    make_id_repo: Maker,
) -> None:
    rule = "key_highlights.payments_received=payments_received.total"
    c = found(make_id_repo(("$20.0M", "$20.1M")))[rule]
    assert (c.expected, c.filed) == (Decimal(20_000_000), Decimal(20_100_000))
    # A tile that is not a figure in millions is left alone: the rule does not apply.
    assert not found(make_id_repo(("$20.0M", "about 20 million")))[rule].applicable


def test_a_chart_label_is_compared_to_the_whole_dollar(make_id_repo: Maker) -> None:
    old = 'Payments to Contract Pharmacies,,,,"$1,000,000"'
    rules = found(make_id_repo((old, old.replace("$1,000,000", "$1,000,001"))))
    rule = "key_financial_metrics.contract_pharmacy_payments=contract_pharmacy_payments.total"
    assert rules[rule].difference == Decimal(1)


def test_savings_are_shown_beside_the_margin_and_a_difference_needs_a_note(
    make_id_repo: Maker,
) -> None:
    old = 'savings_use,total_amount,total,TOTAL,,Amount Applied,,"$10,000,000.00"'
    edits = (old, old.replace("10,000,000.00", "10,500,000.00"))
    rules = found(make_id_repo(edits))
    c = rules[MARGIN_RULE]
    assert (c.expected, c.filed, c.difference) == (
        Decimal("10000000.00"),
        Decimal("10500000.00"),
        Decimal("500000.00"),
    )
    failing = sorted(rule for rule, check in rules.items() if not check.passed)
    notes = "".join(f'{FID},{rule},"What the report prints, side by side."\n' for rule in failing)
    outputs = build_outputs(make_id_repo(edits, notes))
    listed = {d["rule"]: d for d in table(outputs, "discrepancies.csv")}
    assert set(listed) == set(failing)
    assert (listed[MARGIN_RULE]["basis"], listed[MARGIN_RULE]["unit"]) == ("comparison", "usd")


def test_the_record_is_a_statewide_total_with_no_measures(make_id_repo: Maker) -> None:
    root = make_id_repo()
    (filing,) = load_filings(root)
    assert measures(filing) == ()
    outputs = build_outputs(root)
    assert table(outputs, "measures.csv") == []
    (record,) = table(outputs, "filings.csv")
    assert (record["record_kind"], record["period_as_filed"]) == (
        "state_report_totals",
        "A made-up year",
    )
    (entity,) = table(outputs, "entities.csv")
    assert (entity["entity_id"], entity["entity_type"]) == ("zd-statewide", "state_total")


def test_units_and_the_cells_as_printed(make_id_repo: Maker) -> None:
    rows = {
        (r["schedule"], r["line"]): r
        for r in table(build_outputs(make_id_repo()), "line_items.csv")
    }
    assert len(rows) == len(ID_CELLS) + 2
    paid = rows[("payments_received", "total_amount")]
    assert (paid["amount_as_filed"], paid["amount"], paid["unit"], paid["row_kind"]) == (
        "$20,000,000.00",
        "20000000.00",
        "usd",
        "total",
    )
    claims = rows[("claims", "commercial_claims")]
    assert (claims["amount_as_filed"], claims["amount"], claims["unit"]) == (
        "80,000",
        "80000",
        "count",
    )
    assert (claims["label_as_filed"], claims["description_as_filed"]) == (
        "Commercial",
        "Total Claims",
    )
    # A rounded tile is text, never a figure the dataset worked out.
    tile = rows[("key_highlights", "payments_received")]
    assert (tile["amount"], tile["unit"], tile["answer_as_filed"]) == ("", "none", "$20.0M")
    # One printed cell, "8 (100%)", is a count row and a percentage row.
    count, share = rows[("submissions", "complete_count")], rows[("submissions", "complete_pct")]
    assert (count["amount"], count["unit"]) == ("8", "count")
    assert (share["amount_as_filed"], share["amount"], share["unit"]) == ("100%", "100", "percent")
    note = rows[("page_note", "note_2")]
    assert (note["unit"], note["label_as_filed"]) == ("none", "Source: Made-up analysis.")


def test_only_a_statewide_record_and_only_known_lines_are_allowed(make_id_repo: Maker) -> None:
    form = form_of("id-sco-340b-report")
    assert form.record_kinds == ("state_report_totals",)
    assert form.knows("claims", "uninsured_claims")
    assert form.knows("page_note", "note_9")
    assert not form.knows("claims", "uninsured_amount")
    with pytest.raises(DataError, match="is not on form"):
        load_filings(make_id_repo(("claims,other_claims", "claims,tricare_claims")))
    root = make_id_repo()
    meta = root / "transcriptions" / "zd" / "2025" / f"{FID}.meta.toml"
    meta.write_text(
        meta.read_text(encoding="utf-8").replace("state_report_totals", "state_report_row"),
        encoding="utf-8",
    )
    with pytest.raises(DataError, match="is not allowed on id-sco-340b-report"):
        load_filings(root)


def test_text_check_passes_and_finds_a_figure_no_row_carries(make_id_repo: Maker) -> None:
    root = make_id_repo()
    (filing,) = load_filings(root)
    assert check_filing(filing, text_file_for(root, filing)) == []
    assert main(["textcheck", "--root", str(root)]) == 0
    assert main(["tieout", "--root", str(root)]) == 0
    path = text_file_for(root, filing)
    path.write_text(
        path.read_text(encoding="utf-8").replace("Full compliance", "Full compliance 123,456.78"),
        encoding="utf-8",
    )
    problems = [p for p in check_filing(filing, path) if p.fatal]
    assert any("123,456.78 is printed here but no row carries it" in p.detail for p in problems)
