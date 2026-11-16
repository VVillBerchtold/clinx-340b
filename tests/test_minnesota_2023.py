"""Minnesota's 2023-data tables (Appendix Table 5 and 6), tested on a made-up report.

Nothing here is a real report. The made-up state has two entities that together make up the
whole statewide figure.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

import pytest

from filings340b.build import build_outputs
from filings340b.errors import DataError
from filings340b.forms import MN_FORM
from filings340b.load import load_filings
from filings340b.model import Basis, Check, Filing
from filings340b.tieout import checks

Maker = Callable[..., Path]
HEADER = (
    "schedule,line,row_kind,label_as_filed,name_as_filed,description_as_filed,"
    "ndc_as_filed,amount_as_filed,claims_as_filed,answer_as_filed,page,verification,note"
)
GROUPS = (
    "general_acute_care",
    "critical_access",
    "other_hospitals",
    "disease_specific_grantees",
    "safety_net_grantees",
    "total",
)
PAYERS = ("commercial", "medicare", "mhcp", "other", "total")
GENERAL = ("600,000", "200,000", "100,000", "100,000", "1,000,000")
PAGES = "\f" * 41 + "Table 5\n\f" + "\f" + "\f" + "Table 6\n\f"


def _entity_rows(net: str, share: str) -> list[str]:
    return [
        "table_5,scope,detail,Alpha,,Scope,,,,Dispensed Only,42,text_and_image,",
        f'table_5,net_revenue,detail,Alpha,,Net,,"{net}",,,42,text_and_image,',
        f"table_5,pct_of_statewide,detail,Alpha,,Share,,{share},,,42,text_and_image,",
        "table_5,pct_mhcp,detail,Alpha,,MHCP,,10%,,,42,text_and_image,",
    ]


def _statewide_rows(stated: str) -> list[str]:
    rows: list[str] = []
    for group in GROUPS:
        cells = GENERAL if group in {"general_acute_care", "total"} else ("0",) * 5
        kind = "total" if group == "total" else "detail"
        if group != "total":
            rows.append(f"table_6,{group}_major_type,detail,{group},,Type,,,,Hospital,45,x,")
        for payer, cell in zip(PAYERS, cells, strict=True):
            rows.append(f'table_6,{group}_{payer},{kind},{group},,{payer},,"{cell}",,,45,x,')
    rows.append(f"page_note,note_1,detail,{stated},,,,,,,42,x,")
    return [r.replace(",x,", ",text_and_image,") for r in rows]


def _meta(key: str, kind: str, entity: str, name: str) -> str:
    printed = '\n[printed]\nentity_type_as_filed = "Hospital"\ncity_as_filed = "Town"\n'
    return f"""\
filing_id = "zn-2023-{key}"
entity_id = "{entity}"
state = "ZN"
reporting_year = 2023
entity_type = "{"state_total" if key == "statewide" else "hospital"}"
record_kind = "{kind}"
source_file = "report.pdf"
form = "{MN_FORM}"
form_revision = "Made-up report"

[cover]
name_as_filed = "{name}"
corporate_address_as_filed = ""
opais_ids_as_filed = ""
recertification_date_as_filed = ""
reporting_basis_as_filed = ""
{"" if key == "statewide" else printed}"""


@pytest.fixture
def make_mn23_repo(tmp_path: Path) -> Maker:
    """Return a function that writes a made-up 2023-style Minnesota repository."""

    def make(
        edits: dict[str, tuple[str, str]] | None = None,
        notes: str = "",
        stated: str = "There were 2 Covered Entities that together generated the top 100% "
        "of statewide net 340B revenue",
    ) -> Path:
        sources = tmp_path / "sources" / "zn" / "2023"
        (sources / "text").mkdir(parents=True, exist_ok=True)
        pdf = b"%PDF-made-up 2023 report\n"
        (sources / "report.pdf").write_bytes(pdf)
        (sources / "manifest.csv").write_text(
            "file_name,source_url,retrieved_at,sha256,size_bytes,page_count,scanned\n"
            "report.pdf,https://example.invalid/report.pdf,2026-01-01T00:00:00Z,"
            f"{hashlib.sha256(pdf).hexdigest()},{len(pdf)},45,false\n",
            encoding="utf-8",
        )
        (sources / "text" / "report.txt").write_text(PAGES, encoding="utf-8")
        records = {
            "alpha": ("state_report_row", "zn-alpha", "Alpha", _entity_rows("600,000", "60%")),
            "beta": ("state_report_row", "zn-beta", "Beta", _entity_rows("400,000", "40%")),
            "statewide": ("state_report_totals", "zn-statewide", "", _statewide_rows(stated)),
        }
        folder = tmp_path / "transcriptions" / "zn" / "2023"
        folder.mkdir(parents=True, exist_ok=True)
        for key, (kind, entity, name, rows) in records.items():
            body = "\n".join([HEADER, *rows]) + "\n"
            if edits and key in edits:
                old, new = edits[key]
                assert old in body, (key, old)
                body = body.replace(old, new)
            (folder / f"zn-2023-{key}.meta.toml").write_text(
                _meta(key, kind, entity, name), encoding="utf-8"
            )
            (folder / f"zn-2023-{key}.csv").write_text(body, encoding="utf-8")
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


def found(root: Path) -> dict[tuple[str, str], Check]:
    filings: tuple[Filing, ...] = load_filings(root)
    return {(c.filing_id, c.rule): c for f in filings for c in checks(f, filings)}


def test_every_rule_holds_on_the_clean_report(make_mn23_repo: Maker) -> None:
    rules = found(make_mn23_repo())
    # One per entity, then on the statewide record: 1 + 5 + 6 + 1.
    assert len(rules) == 2 + 13
    assert all(c.applicable and c.passed for c in rules.values())
    basis = {rule: c.basis for (_, rule), c in rules.items()}
    assert basis["table_5.rows=stated_entities"] is Basis.FORM
    assert basis["table_6.column_medicare.rows=total"] is Basis.FORM
    assert basis["table_6.row_critical_access.payers=total"] is Basis.FORM
    assert basis["pct_of_statewide=net_revenue/table_6.total_total"] is Basis.COMPARISON
    assert basis["table_5.sum/table_6.total_total=stated_share"] is Basis.COMPARISON


def test_a_stated_count_that_differs_from_the_rows_is_recorded(make_mn23_repo: Maker) -> None:
    stated = "There were 3 Covered Entities that together generated the top 100% of statewide "
    rules = found(make_mn23_repo(stated=stated + "net 340B revenue"))
    c = rules[("zn-2023-statewide", "table_5.rows=stated_entities")]
    assert (c.expected, c.filed, c.difference, c.unit) == (
        Decimal(2),
        Decimal(3),
        Decimal(1),
        "count",
    )
    with pytest.raises(DataError, match=r"table_5\.rows=stated_entities"):
        build_outputs(make_mn23_repo(stated=stated + "net 340B revenue"))


def test_a_column_that_is_one_off_is_recorded_and_needs_a_note(make_mn23_repo: Maker) -> None:
    old = 'general_acute_care_other,detail,general_acute_care,,other,,"100,000"'
    edits = {"statewide": (old, old.replace("100,000", "100,001"))}
    rules = found(make_mn23_repo(edits))
    row = rules[("zn-2023-statewide", "table_6.row_general_acute_care.payers=total")]
    assert (row.expected, row.filed, row.difference) == (
        Decimal(1000001),
        Decimal(1000000),
        Decimal(-1),
    )
    with pytest.raises(DataError, match="no record in discrepancy_notes"):
        build_outputs(make_mn23_repo(edits))


def test_an_entity_share_is_compared_at_the_precision_printed(make_mn23_repo: Maker) -> None:
    assert found(make_mn23_repo({"alpha": ("60%", "60.0%")}))[
        ("zn-2023-alpha", "pct_of_statewide=net_revenue/table_6.total_total")
    ].passed
    c = found(make_mn23_repo({"alpha": ("60%", "61%")}))[
        ("zn-2023-alpha", "pct_of_statewide=net_revenue/table_6.total_total")
    ]
    assert (c.expected, c.filed, c.unit) == (Decimal(60), Decimal(61), "percent")


def test_the_stated_share_is_compared_with_the_table_5_rows(make_mn23_repo: Maker) -> None:
    stated = "There were 2 Covered Entities that together generated the top 90% of statewide "
    c = found(make_mn23_repo(stated=stated + "net 340B revenue"))[
        ("zn-2023-statewide", "table_5.sum/table_6.total_total=stated_share")
    ]
    assert (c.expected, c.filed, c.unit) == (Decimal(100), Decimal(90), "percent")


def test_a_row_the_2023_tables_do_not_have_is_refused(make_mn23_repo: Maker) -> None:
    edits = {"alpha": ("table_5,pct_mhcp", "table_5,pct_other")}
    with pytest.raises(DataError, match="is not on form"):
        load_filings(make_mn23_repo(edits))
