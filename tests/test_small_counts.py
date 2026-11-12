"""The small-number rule: made-up rows first, then the built data."""

from __future__ import annotations

import csv
import io
import json
import re
from decimal import Decimal
from pathlib import Path

import pytest
from conftest import ROWS, Maker

from filings340b.build import build_outputs
from filings340b.errors import DataError
from filings340b.load import load_filings
from filings340b.model import Row, RowKind, Verification
from filings340b.smallcounts import (
    BESIDE_SMALL,
    FEWER_THAN,
    SMALL_HIGHEST,
    SMALL_LOWEST,
    withheld_rows,
)

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "private" / "small-counts.csv"


def row(
    line: str,
    claims: int | None,
    kind: RowKind = RowKind.DETAIL,
    schedule: str = "G",
    filing: str = "zz-1",
) -> Row:
    return Row(
        filing_id=filing,
        schedule=schedule,
        line=line,
        row_kind=kind,
        label_as_filed="",
        name_as_filed="",
        description_as_filed="",
        ndc_as_filed="",
        amount_as_filed="",
        amount=Decimal(0),
        claims_as_filed="" if claims is None else str(claims),
        claims=claims,
        answer_as_filed="",
        page=1,
        verification=Verification.TEXT_AND_IMAGE,
        note="",
    )


def keys(result: dict[tuple[str, str, str], str]) -> dict[str, str]:
    return {line: reason for (_, _, line), reason in result.items()}


def test_the_limits_are_one_and_five() -> None:
    assert (SMALL_LOWEST, SMALL_HIGHEST) == (1, 5)
    assert FEWER_THAN == "fewer_than_6"


def test_counts_one_to_five_are_withheld_and_others_are_not() -> None:
    rows = [row(str(n), n) for n in (0, 1, 2, 3, 4, 5, 6, 7, 100)] + [row("blank", None)]
    # Counts 1, 2, 3, 4, 5 sum to 15, between k and 5k, so no neighbour is added.
    assert keys(withheld_rows(rows)) == {str(n): FEWER_THAN for n in (1, 2, 3, 4, 5)}


def test_a_group_with_no_small_row_is_untouched() -> None:
    assert withheld_rows([row("1", 0), row("2", 6), row("3", None)]) == {}


def test_groups_are_kept_apart_by_filing_and_schedule() -> None:
    rows = [row("1", 2, filing="a"), row("2", 9, filing="a")]
    rows += [row("1", 9, filing="b"), row("1", 9, schedule="C")]
    result = withheld_rows(rows)
    assert {k[:2] for k in result} == {("a", "G")}
    assert keys(result) == {"1": FEWER_THAN, "2": BESIDE_SMALL}


def test_the_rule_is_not_limited_to_schedule_g() -> None:
    rows = [row("1", 2, schedule="C"), row("2", 3, schedule="C"), row("3", 40, schedule="C")]
    assert keys(withheld_rows(rows)) == {"1": FEWER_THAN, "2": FEWER_THAN}


def test_two_small_rows_between_the_limits_add_nothing() -> None:
    # k = 2, S = 5: S is neither 2 nor 10.
    assert keys(withheld_rows([row("1", 2), row("2", 3), row("3", 6)])) == {
        "1": FEWER_THAN,
        "2": FEWER_THAN,
    }


@pytest.mark.parametrize("counts", [[1], [3], [5], [1, 1], [5, 5], [1, 1, 1], [5, 5, 5, 5]])
def test_the_guard_withholds_the_smallest_larger_row(counts: list[int]) -> None:
    rows = [row(f"s{i}", c) for i, c in enumerate(counts)]
    rows += [row("b", 12), row("c", 7), row("d", 30), row("z", 0)]
    result = keys(withheld_rows(rows))
    assert result["c"] == BESIDE_SMALL
    assert sum(1 for v in result.values() if v == BESIDE_SMALL) == 1
    assert sum(1 for v in result.values() if v == FEWER_THAN) == len(counts)


def test_the_guard_breaks_a_tie_on_the_lowest_line_number() -> None:
    rows = [row("1", 3), row("10", 8), row("9", 8), row("2", 8), row("3", 20)]
    # k = 1, so the guard applies; three rows share 8; line 2 comes first.
    assert keys(withheld_rows(rows)) == {"1": FEWER_THAN, "2": BESIDE_SMALL}


def test_the_guard_ignores_total_and_below_threshold_rows_as_neighbours() -> None:
    rows = [
        row("1", 2),
        row("under_5000", 9, RowKind.BELOW_THRESHOLD),
        row("total", 9, RowKind.TOTAL),
        row("2", 50),
    ]
    assert keys(withheld_rows(rows)) == {"1": FEWER_THAN, "2": BESIDE_SMALL}


def test_the_guard_with_no_larger_row_stops_and_names_filing_and_schedule() -> None:
    rows = [row("1", 2, filing="ri-x"), row("2", 0, filing="ri-x")]
    with pytest.raises(DataError) as stop:
        withheld_rows(rows)
    assert "ri-x schedule G" in str(stop.value)


@pytest.mark.parametrize("kind", [RowKind.TOTAL, RowKind.BELOW_THRESHOLD])
@pytest.mark.parametrize("count", [1, 5])
def test_a_small_count_on_a_total_or_below_threshold_row_stops_the_build(
    kind: RowKind, count: int
) -> None:
    rows = [row("1", 40, filing="ri-y"), row("last", count, kind, filing="ri-y")]
    with pytest.raises(DataError) as stop:
        withheld_rows(rows)
    message = str(stop.value)
    assert "ri-y schedule G" in message
    assert str(count) not in message


@pytest.mark.parametrize("count", [0, 6, 7, None])
def test_total_and_below_threshold_rows_outside_the_limits_pass(count: int | None) -> None:
    rows = [
        row("1", 40),
        row("under", count, RowKind.BELOW_THRESHOLD),
        row("t", count, RowKind.TOTAL),
    ]
    assert withheld_rows(rows) == {}


def _small_filing() -> list[str]:
    """The made-up filing with Schedule G split into a row of 4 claims and a row of 96."""
    out = [r for r in ROWS if not r.startswith("G,1,")]
    at = out.index("G,total,total,Total,,,,300.00,100,,3,text_and_image,")
    out[at:at] = [
        "G,1,detail,,SMALLDRUG 5MG,,00000000002,100.00,4,,3,text_and_image,",
        "G,2,detail,,EXAMPLEDRUG 10MG,,00000000001,200.00,96,,3,text_and_image,",
    ]
    return out


def test_the_build_stops_on_a_small_total_in_a_made_up_filing(make_repo: Maker) -> None:
    rows = [
        r.replace("G,total,total,Total,,,,300.00,100", "G,total,total,Total,,,,300.00,3")
        for r in ROWS
    ]
    with pytest.raises(DataError, match="zz-2025-example schedule G"):
        build_outputs(make_repo(rows))


def test_the_build_withholds_the_small_row_and_its_neighbour_in_a_made_up_filing(
    make_repo: Maker,
) -> None:
    outputs = build_outputs(make_repo(_small_filing()))
    items = list(csv.DictReader(io.StringIO(outputs["line_items.csv"].decode())))
    by_line = {i["line"]: i for i in items if i["schedule"] == "G"}
    assert by_line["1"]["claims_withheld"] == FEWER_THAN
    assert by_line["2"]["claims_withheld"] == BESIDE_SMALL
    for line in ("1", "2"):
        assert by_line[line]["claims"] == by_line[line]["claims_as_filed"] == ""
    assert by_line["1"]["amount"] == "100.00"
    assert by_line["1"]["name_as_filed"] == "SMALLDRUG 5MG"
    assert by_line["total"]["claims"] == "100"
    assert by_line["total"]["claims_withheld"] == ""
    document = json.loads(outputs["340b-state-filings.json"])
    assert {r["claims_withheld"] for r in document["line_items"] if r["schedule"] == "G"} == {
        FEWER_THAN,
        BESIDE_SMALL,
        "",
    }


# --- The built data ---------------------------------------------------------------------

EXPECTED_WITHHELD = 310


@pytest.fixture(scope="module")
def built() -> dict[str, bytes]:
    return build_outputs(ROOT)


def _items(built: dict[str, bytes]) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(built["line_items.csv"].decode("utf-8"))))


def test_no_published_row_has_a_claim_count_of_one_to_five(built: dict[str, bytes]) -> None:
    for item in _items(built):
        for column in ("claims", "claims_as_filed"):
            if item[column]:
                assert not SMALL_LOWEST <= int(item[column].replace(",", "")) <= SMALL_HIGHEST
    document = json.loads(built["340b-state-filings.json"])
    for item in document["line_items"]:
        if item["claims"]:
            assert not SMALL_LOWEST <= int(item["claims"]) <= SMALL_HIGHEST


def test_exactly_the_small_schedule_g_rows_are_marked_and_the_guard_adds_none(
    built: dict[str, bytes],
) -> None:
    marked = [i for i in _items(built) if i["claims_withheld"]]
    assert len(marked) == EXPECTED_WITHHELD
    assert {i["claims_withheld"] for i in marked} == {FEWER_THAN}
    assert {(i["schedule"], i["row_kind"]) for i in marked} == {("G", "detail")}
    assert all(i["claims"] == "" == i["claims_as_filed"] for i in marked)
    # The working files mark the same rows. With the private counts back in memory, every
    # one of them is a count of 1 to 5 and no other detail row is.
    keys_marked = {(i["filing_id"], i["schedule"], i["line"]) for i in marked}
    in_files = {
        (r.filing_id, r.schedule, r.line)
        for f in load_filings(ROOT)
        for r in f.rows
        if r.claims_withheld
    }
    assert in_files == keys_marked
    if PRIVATE.exists():
        small = {
            (r.filing_id, r.schedule, r.line)
            for f in load_filings(ROOT)
            for r in f.rows
            if r.row_kind is RowKind.DETAIL and r.claims is not None and 1 <= r.claims <= 5
        }
        assert small == keys_marked
    assert len(keys_marked) == EXPECTED_WITHHELD


def test_every_filing_with_small_rows_has_two_or_more_and_stays_between_the_limits() -> None:
    for filing in load_filings(ROOT):
        for letter in "CG":
            marked = [r for r in filing.schedule(letter) if r.claims_withheld]
            if marked:
                assert len(marked) >= 2
            if marked and PRIVATE.exists():
                total = sum(r.claims or 0 for r in marked)
                assert len(marked) < total < 5 * len(marked)


def test_totals_and_below_threshold_rows_are_published_as_filed(built: dict[str, bytes]) -> None:
    filed = {(r.filing_id, r.schedule, r.line): r for f in load_filings(ROOT) for r in f.rows}
    seen = 0
    for item in _items(built):
        source = filed[(item["filing_id"], item["schedule"], item["line"])]
        if item["row_kind"] in ("total", "below_threshold"):
            assert item["claims_withheld"] == ""
            assert item["claims_as_filed"] == source.claims_as_filed
            assert item["claims"] == ("" if source.claims is None else str(source.claims))
            seen += 1
    assert seen > 100


def test_the_rows_of_other_kinds_and_counts_keep_their_claims(built: dict[str, bytes]) -> None:
    filed = {(r.filing_id, r.schedule, r.line): r for f in load_filings(ROOT) for r in f.rows}
    for item in _items(built):
        if not item["claims_withheld"]:
            source = filed[(item["filing_id"], item["schedule"], item["line"])]
            assert item["claims_as_filed"] == source.claims_as_filed
            assert item["claims"] == ("" if source.claims is None else str(source.claims))


def test_vermont_and_minnesota_rows_only_gain_an_empty_column(built: dict[str, bytes]) -> None:
    for item in _items(built):
        if not item["filing_id"].startswith("ri-"):
            assert item["claims_withheld"] == ""
            assert item["claims"] == item["claims_as_filed"] == ""


def test_the_new_column_sits_right_after_claims(built: dict[str, bytes]) -> None:
    header = built["line_items.csv"].decode().splitlines()[0].split(",")
    assert header[header.index("claims") + 1] == "claims_withheld"


def test_no_note_or_description_quotes_a_single_small_count(built: dict[str, bytes]) -> None:
    # Digits 1 to 5 standing alone as a number in a note, description or formula.
    lone = re.compile(r"(?<![\w.,$#@-])[1-5](?![\w.,%])")
    for name, columns in (
        ("discrepancies.csv", ("description", "note")),
        ("measures.csv", ("formula",)),
    ):
        for record in csv.DictReader(io.StringIO(built[name].decode("utf-8"))):
            for column in columns:
                text = record[column]
                if "claim" in text.lower():
                    assert not lone.search(text), (name, record["filing_id"], text)
