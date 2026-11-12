"""Minnesota's form, tested on a made-up report. Nothing here is a real report."""

from __future__ import annotations

import csv
import io
from decimal import Decimal

import pytest
from conftest import Maker

from filings340b.build import build_outputs
from filings340b.cli import main
from filings340b.errors import DataError
from filings340b.forms import form_of, mn_entity_type
from filings340b.load import load_filings
from filings340b.model import Basis, Check, Filing
from filings340b.textcheck import check_filing, text_file_for
from filings340b.tieout import checks, measures


def table(outputs: dict[str, bytes], name: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(outputs[name].decode("utf-8"))))


def all_checks(filings: tuple[Filing, ...]) -> dict[tuple[str, str], Check]:
    return {(c.filing_id, c.rule): c for f in filings for c in checks(f, filings)}


def test_every_rule_holds_on_the_clean_report(make_mn_repo: Maker) -> None:
    filings = load_filings(make_mn_repo())
    assert len(filings) == 4
    found = all_checks(filings)
    # One per entity, then on the statewide record: 2 + 2 + 6.
    assert len(found) == 3 + 10
    assert all(c.applicable and c.passed for c in found.values())
    basis = {rule: c.basis for (_, rule), c in found.items()}
    assert basis["table_6_1.rows=stated_entities"] is Basis.FORM
    assert basis["table_6_1.sum=table_6_2.top_unadjusted"] is Basis.FORM
    assert basis["table_6_2.unadjusted_rows=total"] is Basis.FORM
    assert basis["table_6_2.adjusted_rows=total"] is Basis.FORM
    assert basis["pct_of_statewide=net_revenue/total_unadjusted"] is Basis.COMPARISON
    assert basis["table_6_2.top_adjusted.pct_of_total=net_revenue/total_adjusted"] is (
        Basis.COMPARISON
    )
    units = {rule: c.unit for (_, rule), c in found.items()}
    assert units["table_6_1.rows=stated_entities"] == "count"
    assert units["pct_of_statewide=net_revenue/total_unadjusted"] == "percent"


def test_rules_that_need_other_records_do_not_apply_without_them(make_mn_repo: Maker) -> None:
    filings = load_filings(make_mn_repo())
    alpha = next(f for f in filings if f.meta.filing_id == "zm-2024-alpha")
    (alone,) = checks(alpha)
    assert not alone.applicable


def test_a_stated_count_that_differs_from_the_rows_printed_is_recorded(
    make_mn_repo: Maker,
) -> None:
    edits = {"statewide": ("identified 3 Covered", "identified 4 Covered")}
    found = all_checks(load_filings(make_mn_repo(edits)))
    c = found[("zm-2024-statewide", "table_6_1.rows=stated_entities")]
    assert (c.expected, c.filed, c.difference, c.unit) == (
        Decimal(3),
        Decimal(4),
        Decimal(1),
        "count",
    )
    with pytest.raises(DataError, match=r"table_6_1\.rows=stated_entities"):
        build_outputs(make_mn_repo(edits))


def test_the_rows_of_table_6_1_are_added_beside_the_first_row_of_table_6_2(
    make_mn_repo: Maker,
) -> None:
    edits = {"beta": ('"300,000"', '"300,001"')}
    found = all_checks(load_filings(make_mn_repo(edits)))
    c = found[("zm-2024-statewide", "table_6_1.sum=table_6_2.top_unadjusted")]
    assert (c.expected, c.filed, c.difference) == (
        Decimal(1000001),
        Decimal(1000000),
        Decimal(-1),
    )


def test_table_6_2_adds_up_for_unadjusted_and_adjusted(make_mn_repo: Maker) -> None:
    edits = {"statewide": ('"300,000"', '"300,002"')}
    found = all_checks(load_filings(make_mn_repo(edits)))
    assert found[("zm-2024-statewide", "table_6_2.unadjusted_rows=total")].passed
    c = found[("zm-2024-statewide", "table_6_2.adjusted_rows=total")]
    assert (c.expected, c.filed) == (Decimal(1500002), Decimal(1500000))


def test_an_entity_percent_is_compared_at_the_printed_precision(make_mn_repo: Maker) -> None:
    # 600,000 / 1,250,000 is exactly 48%: 48% holds at no decimals, 48.1% does not.
    held = all_checks(load_filings(make_mn_repo({"alpha": ("48.0%", "48%")})))
    assert held[("zm-2024-alpha", "pct_of_statewide=net_revenue/total_unadjusted")].passed
    found = all_checks(load_filings(make_mn_repo({"alpha": ("48.0%", "48.1%")})))
    c = found[("zm-2024-alpha", "pct_of_statewide=net_revenue/total_unadjusted")]
    assert (c.expected, c.filed, c.difference) == (Decimal("48.0"), Decimal("48.1"), Decimal("0.1"))
    assert c.basis is Basis.COMPARISON


def test_a_percent_in_table_6_2_is_compared_with_its_own_total(make_mn_repo: Maker) -> None:
    old = 'Top 3, adjusted",,% of Total,,80.0%'
    edits = {"statewide": (old, old.replace("80.0%", "80.1%"))}
    found = all_checks(load_filings(make_mn_repo(edits)))
    rule = "table_6_2.top_adjusted.pct_of_total=net_revenue/total_adjusted"
    c = found[("zm-2024-statewide", rule)]
    assert (c.expected, c.filed) == (Decimal("80.0"), Decimal("80.1"))
    other = "table_6_2.top_unadjusted.pct_of_total=net_revenue/total_unadjusted"
    assert found[("zm-2024-statewide", other)].passed


def test_a_difference_needs_a_note_and_a_comparison_note_says_so(make_mn_repo: Maker) -> None:
    edits = {"alpha": ("48.0%", "48.1%")}
    with pytest.raises(DataError, match=r"no record in discrepancy_notes\.csv"):
        build_outputs(make_mn_repo(edits))
    notes = (
        "zm-2024-alpha,pct_of_statewide=net_revenue/total_unadjusted,"
        '"The report does not say which total its percentages use."\n'
    )
    outputs = build_outputs(make_mn_repo(edits, notes))
    (d,) = table(outputs, "discrepancies.csv")
    assert (d["basis"], d["unit"], d["difference"]) == ("comparison", "percent", "0.1")


def test_minnesota_has_no_measures_and_the_chart_stays_rhode_island_only(
    make_mn_repo: Maker,
) -> None:
    root = make_mn_repo()
    for filing in load_filings(root):
        assert measures(filing) == ()
    outputs = build_outputs(root)
    assert table(outputs, "measures.csv") == []
    assert b"Alpha" not in outputs["external-share-light.svg"]


def test_records_are_told_apart_and_type_and_city_are_kept_as_printed(
    make_mn_repo: Maker,
) -> None:
    outputs = build_outputs(make_mn_repo())
    kinds = {f["filing_id"]: f["record_kind"] for f in table(outputs, "filings.csv")}
    assert kinds == {
        "zm-2024-alpha": "state_report_row",
        "zm-2024-beta": "state_report_row",
        "zm-2024-gamma": "state_report_row",
        "zm-2024-statewide": "state_report_totals",
    }
    entities = {e["entity_id"]: e for e in table(outputs, "entities.csv")}
    assert (entities["zm-alpha"]["entity_type"], entities["zm-alpha"]["city_as_filed"]) == (
        "hospital",
        "Alphaville",
    )
    assert entities["zm-alpha"]["entity_type_as_filed"] == "Disproportionate Share Hospital"
    assert entities["zm-beta"]["entity_type"] == "other"
    assert entities["zm-beta"]["entity_type_as_filed"] == "Treatment Center"
    assert entities["zm-gamma"]["city_as_filed"] == "St. Gamma"
    assert entities["zm-statewide"]["entity_type"] == "state_total"
    assert entities["zm-statewide"]["name_as_filed"] == ""


def test_the_entity_type_follows_the_printed_type(make_mn_repo: Maker) -> None:
    assert mn_entity_type("Children's Hospital", "state_report_row") == "hospital"
    assert mn_entity_type("CHD Treatment Center", "state_report_row") == "other"
    assert mn_entity_type("", "state_report_totals") == "state_total"
    root = make_mn_repo()
    meta = root / "transcriptions" / "zm" / "2024" / "zm-2024-beta.meta.toml"
    meta.write_text(
        meta.read_text(encoding="utf-8").replace(
            'entity_type = "other"', 'entity_type = "hospital"'
        ),
        encoding="utf-8",
    )
    with pytest.raises(DataError, match="entity_type must be 'other'"):
        load_filings(root)


def test_a_record_kind_the_form_does_not_allow_is_refused(make_mn_repo: Maker) -> None:
    root = make_mn_repo()
    meta = root / "transcriptions" / "zm" / "2024" / "zm-2024-alpha.meta.toml"
    meta.write_text(
        meta.read_text(encoding="utf-8").replace("state_report_row", "filing"), encoding="utf-8"
    )
    with pytest.raises(DataError, match="record_kind 'filing' is not allowed"):
        load_filings(root)


def test_units_and_the_figures_as_printed(make_mn_repo: Maker) -> None:
    outputs = build_outputs(make_mn_repo())
    rows = {(r["filing_id"], r["line"]): r for r in table(outputs, "line_items.csv")}
    net = rows[("zm-2024-alpha", "net_revenue")]
    assert (net["amount_as_filed"], net["amount"], net["unit"]) == ("600,000", "600000", "usd")
    pct = rows[("zm-2024-alpha", "pct_of_statewide")]
    assert (pct["amount_as_filed"], pct["amount"], pct["unit"]) == ("48.0%", "48.0", "percent")
    whole = rows[("zm-2024-statewide", "total_unadjusted_pct_of_total")]
    assert (whole["amount_as_filed"], whole["amount"], whole["row_kind"]) == (
        "100%",
        "100",
        "total",
    )
    note = rows[("zm-2024-statewide", "note_3")]
    assert (note["schedule"], note["unit"], note["amount"]) == ("page_note", "none", "")
    assert note["label_as_filed"] == "Source: Made-up analysis."


def test_a_line_that_is_not_on_the_form_is_refused(make_mn_repo: Maker) -> None:
    edits = {"alpha": ("pct_of_statewide", "rank")}
    with pytest.raises(DataError, match="is not on form"):
        load_filings(make_mn_repo(edits))
    assert form_of("mn-mdh-340b-report").knows("table_6_1", "net_revenue")
    assert not form_of("mn-mdh-340b-report").knows("A", "1")


def test_text_check_pools_the_records_that_share_a_page(make_mn_repo: Maker) -> None:
    root = make_mn_repo()
    filings = load_filings(root)
    for filing in filings:
        assert check_filing(filing, text_file_for(root, filing), filings) == []
    # Alone, a record cannot account for the other rows printed on its page.
    alpha = next(f for f in filings if f.meta.filing_id == "zm-2024-alpha")
    alone = check_filing(alpha, text_file_for(root, alpha))
    assert any("is printed here but no row carries it" in p.detail for p in alone)
    assert main(["textcheck", "--root", str(root)]) == 0
    assert main(["tieout", "--root", str(root)]) == 0


def test_text_check_finds_a_row_left_out(make_mn_repo: Maker) -> None:
    root = make_mn_repo()
    path = root / "sources" / "zm" / "2024" / "text" / "report.txt"
    path.write_text(
        path.read_text(encoding="utf-8").replace("St. Gamma", "Delta 999,999 1.0%\nSt. Gamma"),
        encoding="utf-8",
    )
    filings = load_filings(root)
    problems = [
        p for f in filings for p in check_filing(f, text_file_for(root, f), filings) if p.fatal
    ]
    assert problems
