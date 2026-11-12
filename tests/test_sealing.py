"""Withheld claim counts: the guard over every table file, then both ways of running.

The counts in the made-up filings are made up. These tests do not need the private file
and pass with it or without it.
"""

from __future__ import annotations

import csv
import io
import shutil
from pathlib import Path

import pytest
from conftest import ROWS, Maker

from filings340b.build import build_outputs
from filings340b.errors import DataError
from filings340b.imageread import Difference, compare, image_read_file, read_image_read
from filings340b.load import load_filings
from filings340b.seal import seal
from filings340b.sealing import (
    PRIVATE_FILE,
    describe_run,
    read_private,
    withheld_for,
    write_private,
)
from filings340b.smallcounts import SMALL_HIGHEST, SMALL_LOWEST
from filings340b.textcheck import check_filing, text_file_for
from filings340b.tieout import checks

ROOT = Path(__file__).resolve().parents[1]
CLAIM_COLUMNS = ("claims", "claims_as_filed")


def small_claim_cells(root: Path) -> list[str]:
    """Name every cell under the table folders that shows a claim count of 1 to 5."""
    found: list[str] = []
    for folder in ("transcriptions", "verification", "data"):
        for path in sorted((root / folder).rglob("*.csv")):
            with path.open(newline="", encoding="utf-8") as handle:
                for number, record in enumerate(csv.DictReader(handle), start=2):
                    for column in CLAIM_COLUMNS:
                        text = (record.get(column) or "").replace(",", "").strip()
                        if text.isdigit() and SMALL_LOWEST <= int(text) <= SMALL_HIGHEST:
                            found.append(f"{path.relative_to(root)} row {number} {column}")
    return found


def test_no_table_file_shows_a_claim_count_of_one_to_five() -> None:
    assert small_claim_cells(ROOT) == []


def test_private_counts_are_never_tracked() -> None:
    assert "private/" in (ROOT / ".gitignore").read_text().splitlines()


def test_the_guard_finds_a_small_count_in_a_made_up_file(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "line_items.csv").write_text("claims,claims_as_filed\n7,4\n,\n", "utf-8")
    (tmp_path / "transcriptions").mkdir()
    (tmp_path / "verification").mkdir()
    (tmp_path / "verification" / "x.csv").write_text("claims\n5\n", "utf-8")
    assert small_claim_cells(tmp_path) == [
        "verification/x.csv row 2 claims",
        "data/line_items.csv row 2 claims_as_filed",
    ]


# --- A made-up filing ---------------------------------------------------------------------


def _filing_rows() -> list[str]:
    """Schedule G split into two detail rows: 4 claims and 96 claims, 100 in all."""
    out = [r for r in ROWS if not r.startswith("G,1,")]
    at = out.index("G,total,total,Total,,,,300.00,100,,3,text_and_image,")
    out[at:at] = [
        "G,1,detail,,SMALLDRUG 5MG,,00000000002,100.00,4,,3,text_and_image,",
        "G,2,detail,,EXAMPLEDRUG 10MG,,00000000001,200.00,96,,3,text_and_image,",
    ]
    return out


IMAGE_READ = (
    "page,schedule,line,amount,claims,answer\n"
    "3,G,1,100.00,4,\n"
    "3,G,2,200.00,96,\n"
    "3,G,total,300.00,100,\n"
)


def _unsealed(make_repo: Maker) -> Path:
    root = make_repo(_filing_rows())
    path = root / "verification" / "zz" / "2025" / "zz-2025-example.image-read.csv"
    path.parent.mkdir(parents=True)
    path.write_text(IMAGE_READ, encoding="utf-8")
    text = root / "sources" / "zz" / "2025" / "text" / "example.txt"
    text.write_text(
        text.read_text("utf-8").replace(
            "G 1 EXAMPLEDRUG 10MG 00000000001 300.00 100\n",
            "G 1 SMALLDRUG 5MG 00000000002 100.00 4\n G 2 EXAMPLEDRUG 00000000001 200.00 96\n",
        ),
        "utf-8",
    )
    return root


@pytest.fixture
def sealed(make_repo: Maker) -> Path:
    root = _unsealed(make_repo)
    seal(root)
    return root


def _tree(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes()
        for folder in ("private", "transcriptions", "verification")
        for p in sorted((root / folder).rglob("*"))
        if p.is_file()
    }


def _away(root: Path) -> Path:
    """Take the private file out of the made-up repository; return where it went."""
    kept = root / "kept-private.csv"
    shutil.move(root / PRIVATE_FILE, kept)
    return kept


def _g_only(found: list[Difference]) -> list[Difference]:
    """The made-up image read holds Schedule G only."""
    return [d for d in found if d.schedule == "G"]


def _rows_of(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_seal_moves_the_counts_into_the_private_file(sealed: Path) -> None:
    assert read_private(sealed) is not None
    held = read_private(sealed) or {}
    assert {k[1:]: (v.claims_as_filed, v.image_read_claims) for k, v in held.items()} == {
        ("G", "1"): ("4", "4"),
        ("G", "2"): ("96", "96"),
    }
    rows = {
        r["line"]: r
        for r in _rows_of(sealed / "transcriptions/zz/2025/zz-2025-example.csv")
        if r["schedule"] == "G"
    }
    assert rows["1"]["claims_as_filed"] == "" and rows["1"]["claims_withheld"] == "fewer_than_6"
    assert rows["2"]["claims_as_filed"] == "" and rows["2"]["claims_withheld"] == "beside_small"
    assert rows["total"]["claims_as_filed"] == "100" and rows["total"]["claims_withheld"] == ""
    assert rows["1"]["amount_as_filed"] == "100.00"
    reads = {
        r["line"]: r
        for r in _rows_of(sealed / "verification/zz/2025/zz-2025-example.image-read.csv")
    }
    assert reads["1"]["claims"] == "" and reads["1"]["claims_withheld"] == "fewer_than_6"
    assert reads["total"]["claims"] == "100"
    sums = _rows_of(sealed / "verification/zz/2025/claim-sums.csv")
    assert sums == [{"filing_id": "zz-2025-example", "schedule": "G", "claim_sum": "100"}]
    assert small_claim_cells(sealed) == []


def test_seal_is_safe_to_run_twice(sealed: Path) -> None:
    first = _tree(sealed)
    assert seal(sealed).startswith("sealed 2 withheld counts: 0 emptied")
    assert _tree(sealed) == first


def test_seal_changes_no_published_byte(make_repo: Maker) -> None:
    root = _unsealed(make_repo)
    before = build_outputs(root)
    seal(root)
    with_private = build_outputs(root)
    _away(root)
    assert with_private == before
    assert build_outputs(root) == before


def test_without_the_private_file_the_sum_comes_from_the_results_file(sealed: Path) -> None:
    _away(sealed)
    (filing,) = load_filings(sealed)
    assert dict(filing.claim_sums) == {"G": 100}
    assert [r.claims for r in filing.schedule("G")] == [None, None, 100]
    by_rule = {c.rule: c for c in checks(filing)}
    assert by_rule["G.claims=total"].passed
    assert describe_run(sealed, [filing]) == (
        "Run without the private small counts: 1 claim sums were taken from "
        "verification/zz/2025/claim-sums.csv; 2 withheld cells were not re-read."
    )


def test_with_the_private_file_every_sum_is_recomputed(sealed: Path) -> None:
    (filing,) = load_filings(sealed)
    assert dict(filing.claim_sums) == {}
    assert [r.claims for r in filing.schedule("G")] == [4, 96, 100]
    assert describe_run(sealed, [filing]) == (
        "Run with the private small counts: every sum was recomputed."
    )


def test_the_text_check_passes_in_both_ways(sealed: Path) -> None:
    (filing,) = load_filings(sealed)
    assert [
        p for p in check_filing(filing, text_file_for(sealed, filing), (filing,)) if p.fatal
    ] == []
    _away(sealed)
    (filing,) = load_filings(sealed)
    assert [
        p for p in check_filing(filing, text_file_for(sealed, filing), (filing,)) if p.fatal
    ] == []


def test_the_image_read_comparison_in_both_ways(sealed: Path) -> None:
    path = image_read_file(sealed, load_filings(sealed)[0])
    (filing,) = load_filings(sealed)
    assert _g_only(compare(filing, read_image_read(path))) == []
    # A second reader who saw another count is found when the counts are there.
    held = read_private(sealed) or {}
    key = ("zz-2025-example", "G", "1")
    held[key] = type(held[key])("4", "3")
    write_private(sealed, held)
    (filing,) = load_filings(sealed)
    assert [d.detail for d in _g_only(compare(filing, read_image_read(path)))] == [
        "claims: transcription '4', image read '3'"
    ]
    _away(sealed)
    (filing,) = load_filings(sealed)
    assert _g_only(compare(filing, read_image_read(path))) == []


def test_a_mark_on_one_side_only_is_a_difference(sealed: Path) -> None:
    path = image_read_file(sealed, load_filings(sealed)[0])
    text = path.read_text("utf-8").replace("G,1,100.00,,,fewer_than_6", "G,1,100.00,,,")
    path.write_text(text, "utf-8")
    _away(sealed)
    (filing,) = load_filings(sealed)
    assert [d.detail for d in _g_only(compare(filing, read_image_read(path)))] == [
        "claims: withheld in one and not in the other"
    ]


# --- The mismatch errors --------------------------------------------------------------------


def _change_private(root: Path, edit: str, replacement: str) -> None:
    path = root / PRIVATE_FILE
    path.write_text(path.read_text("utf-8").replace(edit, replacement), "utf-8")


def test_a_marked_row_with_no_private_count_stops_the_load(sealed: Path) -> None:
    _change_private(sealed, "zz-2025-example,G,1,4,4\n", "")
    with pytest.raises(DataError, match="zz-2025-example schedule G line 1: marked as withheld"):
        load_filings(sealed)


def test_a_private_count_with_no_marked_row_stops_the_load(sealed: Path) -> None:
    _change_private(
        sealed,
        "zz-2025-example,G,1,4,4\n",
        "zz-2025-example,G,1,4,4\nzz-2025-example,G,total,3,3\n",
    )
    with pytest.raises(DataError, match="not marked claims_withheld"):
        load_filings(sealed)


@pytest.mark.parametrize("wrong", ["9", "0", "", "x"])
def test_a_private_count_that_is_not_one_to_five_stops_a_fewer_than_row(
    sealed: Path, wrong: str
) -> None:
    _change_private(sealed, "zz-2025-example,G,1,4,4\n", f"zz-2025-example,G,1,{wrong},4\n")
    with pytest.raises(DataError, match="schedule G line 1: the private count"):
        load_filings(sealed)


def test_a_private_count_of_five_or_less_stops_a_beside_small_row(sealed: Path) -> None:
    _change_private(sealed, "zz-2025-example,G,2,96,96\n", "zz-2025-example,G,2,5,96\n")
    with pytest.raises(DataError, match="schedule G line 2: the private count is small"):
        load_filings(sealed)


def test_a_mark_the_rule_does_not_give_stops_the_build(sealed: Path) -> None:
    path = sealed / "transcriptions/zz/2025/zz-2025-example.csv"
    path.write_text(
        path.read_text("utf-8").replace(
            "C,1,detail,Commercial Insurance,,,,600.00,60,,3,text_and_image,,",
            "C,1,detail,Commercial Insurance,,,,600.00,,,3,text_and_image,,beside_small",
        ),
        "utf-8",
    )
    _change_private(
        sealed, "zz-2025-example,G,1,", "zz-2025-example,C,1,60,60\nzz-2025-example,G,1,"
    )
    filings = load_filings(sealed, check_sums=False)
    with pytest.raises(DataError, match="schedule C line 1: the claims_withheld mark"):
        withheld_for(filings)


def test_a_results_file_that_differs_from_the_counts_stops_the_run(sealed: Path) -> None:
    sums = sealed / "verification/zz/2025/claim-sums.csv"
    sums.write_text(sums.read_text("utf-8").replace(",100", ",101"), "utf-8")
    with pytest.raises(DataError, match=r"claim-sums\.csv does not match the counts"):
        load_filings(sealed)
    seal(sealed)
    assert load_filings(sealed)


def test_without_the_private_file_a_missing_sum_stops_the_load(sealed: Path) -> None:
    _away(sealed)
    (sealed / "verification/zz/2025/claim-sums.csv").unlink()
    with pytest.raises(DataError, match="no claim sum"):
        load_filings(sealed)


def test_without_the_private_file_a_sum_the_rows_cannot_make_stops_the_load(sealed: Path) -> None:
    _away(sealed)
    sums = sealed / "verification/zz/2025/claim-sums.csv"
    sums.write_text(sums.read_text("utf-8").replace(",100", ",3"), "utf-8")
    with pytest.raises(DataError, match="cannot match its rows"):
        load_filings(sealed)


def test_seal_needs_the_private_file_when_counts_are_already_withheld(sealed: Path) -> None:
    _away(sealed)
    with pytest.raises(DataError, match=r"small-counts\.csv is not there"):
        seal(sealed)


def test_a_marker_with_a_value_in_the_cell_stops_the_load(sealed: Path) -> None:
    path = sealed / "transcriptions/zz/2025/zz-2025-example.csv"
    text = path.read_text("utf-8").replace("00000000002,100.00,,", "00000000002,100.00,7,")
    path.write_text(text, "utf-8")
    with pytest.raises(DataError, match="must leave claims_as_filed empty"):
        load_filings(sealed)


def test_the_marker_files_keep_every_other_cell(make_repo: Maker) -> None:
    root = _unsealed(make_repo)
    before = io.StringIO((root / "transcriptions/zz/2025/zz-2025-example.csv").read_text("utf-8"))
    old = list(csv.reader(before))
    seal(root)
    new = list(
        csv.reader((root / "transcriptions/zz/2025/zz-2025-example.csv").open(encoding="utf-8"))
    )
    assert new[0][:-1] == old[0] and new[0][-1] == "claims_withheld"
    for was, now in zip(old[1:], new[1:], strict=True):
        assert now[:8] == was[:8] and now[9:-1] == was[9:]
