"""The engine's rules, tested on a made-up filing."""

from __future__ import annotations

import csv
import io
from decimal import Decimal
from pathlib import Path

import pytest
from conftest import ROWS, Maker

from filings340b.build import build_outputs, stale_outputs, write_outputs
from filings340b.cli import main
from filings340b.errors import DataError
from filings340b.load import load_filings
from filings340b.model import Basis
from filings340b.money import parse_amount, parse_count, plain
from filings340b.textcheck import MONEY, check_filing, text_file_for
from filings340b.tieout import checks, measures


def table(outputs: dict[str, bytes], name: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(outputs[name].decode("utf-8"))))


def swap(old: str, new: str) -> list[str]:
    assert any(old in row for row in ROWS)
    return [row.replace(old, new) for row in ROWS]


@pytest.mark.parametrize(
    ("printed", "value"),
    [
        ("1,408,968.83", Decimal("1408968.83")),
        ("$ 3,996,714", Decimal("3996714")),
        ("0.00", Decimal("0.00")),
        ("-", Decimal(0)),
        (chr(0x2013), Decimal(0)),
        ("(1,234.50)", Decimal("-1234.50")),
        ("-12.00", Decimal("-12.00")),
        ("", None),
        ("   ", None),
        ("N/A", None),
    ],
)
def test_amount_is_read_as_printed(printed: str, value: Decimal | None) -> None:
    assert parse_amount(printed) == value


def test_amount_keeps_the_filed_scale() -> None:
    assert plain(parse_amount("3,996,714")) == "3996714"
    assert plain(parse_amount("46,815.00")) == "46815.00"


@pytest.mark.parametrize("bad", ["12,34", "1.2.3", "abc", "1,2345.00", "$"])
def test_malformed_amount_is_refused(bad: str) -> None:
    if bad == "$":
        assert parse_amount(bad) is None
        return
    with pytest.raises(ValueError, match="not an amount"):
        parse_amount(bad)


def test_counts() -> None:
    assert parse_count("39,738") == 39738
    assert parse_count("4641") == 4641
    assert parse_count("") is None
    with pytest.raises(ValueError, match="not a count"):
        parse_count("12.5")


def test_every_rule_holds_on_the_clean_filing(make_repo: Maker) -> None:
    (filing,) = load_filings(make_repo())
    results = checks(filing)
    assert [c.rule for c in results if c.applicable and not c.passed] == []
    assert sum(1 for c in results if c.applicable) >= 14


def test_measures(make_repo: Maker) -> None:
    (filing,) = load_filings(make_repo())
    values = {name: value for name, _, value in measures(filing)}
    assert values["gross_margin"] == Decimal("600.00")
    assert values["external_cost"] == Decimal("150.00")
    assert values["external_share_of_margin"] == Decimal("0.250000")


def test_build_is_deterministic_and_check_passes(make_repo: Maker) -> None:
    root = make_repo()
    assert build_outputs(root) == build_outputs(root)
    assert stale_outputs(root) != []
    write_outputs(root)
    assert stale_outputs(root) == []
    assert write_outputs(root) == []
    assert main(["check", "--root", str(root)]) == 0


def test_check_notices_an_edited_output(make_repo: Maker) -> None:
    root = make_repo()
    write_outputs(root)
    target = root / "data" / "line_items.csv"
    target.write_bytes(target.read_bytes().replace(b"400.00", b"400.01", 1))
    assert stale_outputs(root) == ["line_items.csv"]
    assert main(["check", "--root", str(root)]) == 1


def test_outputs_keep_filed_text_and_add_normalized_names(make_repo: Maker) -> None:
    outputs = build_outputs(make_repo())
    items = table(outputs, "line_items.csv")
    pharmacy = next(r for r in items if r["schedule"] == "D" and r["line"] == "1")
    assert pharmacy["name_as_filed"] == "Example Pharmacy #12"
    assert pharmacy["normalized_vendor"] == "Example Pharmacy"
    vendor = next(r for r in items if r["schedule"] == "E" and r["line"] == "1")
    assert vendor["category"] == "third_party_administrator"
    received = next(r for r in items if r["schedule"] == "A" and r["line"] == "2")
    assert (received["amount_as_filed"], received["amount"]) == ("1,000.00", "1000.00")
    dash = next(r for r in items if r["schedule"] == "H" and r["line"] == "1")
    assert (dash["amount_as_filed"], dash["amount"]) == ("-", "0")
    assert table(outputs, "discrepancies.csv") == []
    assert table(outputs, "attachments.csv")[0]["kind"] == "cover_letter"
    assert outputs["340b-state-filings.json"].endswith(b"}\n")


def test_a_difference_must_be_recorded_before_it_can_be_published(make_repo: Maker) -> None:
    rows = swap("H,total,total,Total,,,,425.00", "H,total,total,Total,,,,500.00")
    with pytest.raises(DataError, match=r"H\.rows=total"):
        build_outputs(make_repo(rows))
    notes = (
        "zz-2025-example,H.rows=total,Printed total differs from the rows.\n"
        "zz-2025-example,H.total=A6,Printed total differs from line 6.\n"
    )
    found = table(build_outputs(make_repo(rows, notes)), "discrepancies.csv")
    assert {(d["rule"], d["difference"]) for d in found} == {
        ("H.rows=total", "75.00"),
        ("H.total=A6", "75.00"),
    }
    assert all(d["filed"] == "500.00" for d in found)


def test_unverified_rows_cannot_be_published(make_repo: Maker) -> None:
    rows = swap("400.00,,,2,text_and_image,", "400.00,,,2,unverified,")
    with pytest.raises(DataError, match="not verified"):
        build_outputs(make_repo(rows))


def test_adjudicated_rows_need_a_note(make_repo: Maker) -> None:
    rows = swap("400.00,,,2,text_and_image,", "400.00,,,2,adjudicated,")
    with pytest.raises(DataError, match="must say why"):
        load_filings(make_repo(rows))


def test_a_changed_pdf_is_refused(make_repo: Maker) -> None:
    root = make_repo()
    (root / "sources" / "zz" / "2025" / "example.pdf").write_bytes(b"%PDF-other\n")
    with pytest.raises(DataError, match="not the recorded hash"):
        load_filings(root)


def test_duplicate_lines_and_attachment_pages_are_refused(make_repo: Maker) -> None:
    with pytest.raises(DataError, match="appears twice"):
        load_filings(make_repo([*ROWS, ROWS[0]]))
    rows = swap("YES,3,text_and_image", "YES,4,text_and_image")
    with pytest.raises(DataError, match="attachment"):
        load_filings(make_repo(rows))


def test_text_check_passes_on_the_clean_filing(make_repo: Maker) -> None:
    root = make_repo()
    (filing,) = load_filings(root)
    assert check_filing(filing, text_file_for(root, filing)) == []
    assert main(["textcheck", "--root", str(root)]) == 0


def test_text_check_catches_a_mistyped_figure(make_repo: Maker) -> None:
    root = make_repo(swap("00000000001,300.00,100", "00000000001,300.00,101"))
    (filing,) = load_filings(root)
    problems = check_filing(filing, text_file_for(root, filing))
    assert [p.detail for p in problems if p.fatal] == [
        "schedule G line 1: claims 101 is not printed on this page"
    ]


def test_text_check_catches_a_missing_row(make_repo: Maker) -> None:
    rows = [r for r in ROWS if not r.startswith(("C,1,", "C,2,"))]
    root = make_repo(rows)
    (filing,) = load_filings(root)
    fatal = [p.detail for p in check_filing(filing, text_file_for(root, filing)) if p.fatal]
    assert fatal == ["600.00 is printed here but no row carries it"]
    assert main(["textcheck", "--root", str(root)]) == 1


def test_money_pattern_ignores_drug_codes_and_strengths() -> None:
    text = "JARDIANCE 597015230, 597015290 2150680,2148480 0.5 ML 111-115 kg 02/02/2026 5-19.3-6"
    assert MONEY.findall(text) == []
    assert MONEY.findall("$ 32,042,093.78 USD 4641 and 273,031 and 0.25") == [
        "32,042,093.78",
        "273,031",
        "0.25",
    ]


def test_tieout_command_runs(make_repo: Maker, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["tieout", "--root", str(make_repo())]) == 0
    assert "DIFF" not in capsys.readouterr().out


def test_missing_text_is_reported(make_repo: Maker) -> None:
    root = make_repo()
    (filing,) = load_filings(root)
    missing = Path(root / "nowhere.txt")
    assert check_filing(filing, missing)[0].fatal


def test_comparisons_are_not_presented_as_rules_of_the_form(make_repo: Maker) -> None:
    (filing,) = load_filings(make_repo())
    basis = {c.rule: c.basis for c in checks(filing)}
    assert basis["H.total=A6"] is Basis.COMPARISON
    assert basis["C.claims=G.claims"] is Basis.COMPARISON
    assert basis["B.total=A1"] is Basis.FORM
    assert basis["A6=A2-A1-A3-A4-A5"] is Basis.FORM
    rows = swap("H,total,total,Total,,,,425.00", "H,total,total,Total,,,,500.00")
    notes = (
        "zz-2025-example,H.rows=total,Printed total differs from the rows.\n"
        "zz-2025-example,H.total=A6,Shown side by side.\n"
    )
    found = table(build_outputs(make_repo(rows, notes)), "discrepancies.csv")
    assert {d["rule"]: d["basis"] for d in found} == {
        "H.rows=total": "form",
        "H.total=A6": "comparison",
    }


def test_a_note_for_a_rule_that_holds_is_refused(make_repo: Maker) -> None:
    notes = "zz-2025-example,B.total=A1,Left over from an earlier draft.\n"
    with pytest.raises(DataError, match="has a note but the rule holds"):
        build_outputs(make_repo(notes=notes))


def test_categories_must_be_known_and_point_at_a_real_row(make_repo: Maker) -> None:
    root = make_repo()
    path = root / "reference" / "categories.csv"
    good = path.read_text(encoding="utf-8")
    path.write_text(good.replace("third_party_administrator", "favourite"), encoding="utf-8")
    with pytest.raises(DataError, match="not a known category"):
        build_outputs(root)
    path.write_text(good.replace(",E,1,", ",E,7,"), encoding="utf-8")
    with pytest.raises(DataError, match="no row"):
        build_outputs(root)


def test_category_spend_is_summed_from_schedule_e(make_repo: Maker) -> None:
    found = table(build_outputs(make_repo()), "measures.csv")
    value = {m["measure"]: m["value"] for m in found}
    assert value["schedule_e_third_party_administrator"] == "50.00"
    assert value["schedule_e_referral_capture"] == "0"
    assert value["external_share_of_margin"] == "0.250000"
