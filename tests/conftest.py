"""A small made-up repository to test the engine on. Nothing here is a real filing."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

import pytest

HEADER = (
    "schedule,line,row_kind,label_as_filed,name_as_filed,description_as_filed,"
    "ndc_as_filed,amount_as_filed,claims_as_filed,answer_as_filed,page,verification,note"
)

# A made-up filing whose every rule holds: 1,000.00 received, 400.00 cost,
# 100.00 + 50.00 external, 25.00 administration, 425.00 net.
ROWS = [
    "A,1,detail,Acquisition cost,,,,400.00,,,2,text_and_image,",
    'A,2,detail,Payments received,,,,"1,000.00",,,2,text_and_image,',
    "A,3,detail,Contract pharmacies,,,,100.00,,,2,text_and_image,",
    "A,4,detail,Outside vendors,,,,50.00,,,2,text_and_image,",
    "A,5,detail,Administration,,,,25.00,,,2,text_and_image,",
    "A,6,detail,Net revenue,,,,425.00,,,2,text_and_image,",
    "B,1,detail,,Example Wholesale,,,400.00,,,3,text_and_image,",
    "B,total,total,Total,,,,400.00,,,3,text_and_image,",
    "C,1,detail,Commercial Insurance,,,,600.00,60,,3,text_and_image,",
    "C,2,detail,Medicare,,,,400.00,40,,3,text_and_image,",
    'C,total,total,Total,,,,"1,000.00",100,,3,text_and_image,',
    "D,1,detail,,Example Pharmacy #12,,,100.00,,,3,text_and_image,",
    "D,total,total,Total,,,,100.00,,,3,text_and_image,",
    "E,1,detail,,Example Administrator,Third party administrator,,50.00,,,3,text_and_image,",
    "E,total,total,Total,,,,50.00,,,3,text_and_image,",
    "F,1,detail,Wages,,,,25.00,,,3,text_and_image,",
    "F,total,total,Total,,,,25.00,,,3,text_and_image,",
    "G,1,detail,,EXAMPLEDRUG 10MG,,00000000001,300.00,100,,3,text_and_image,",
    "G,total,total,Total,,,,300.00,100,,3,text_and_image,",
    "H,1,detail,Health Services Expansion,,,,-,,,3,text_and_image,",
    "H,9,detail,Charity Care/Uncompensated Care,,,,425.00,,,3,text_and_image,",
    "H,total,total,Total,,,,425.00,,,3,text_and_image,",
    "I,1,detail,Self-audit conducted?,,,,,,YES,3,text_and_image,",
]

PAGE_TWO = "Schedule A\n 1  400.00\n 2  1,000.00\n 3  100.00\n 4  50.00\n 5  25.00\n 6  425.00\n"
PAGE_THREE = (
    "List items of $5,000 or more.\n"
    "B 1 Example Wholesale 400.00\n total 400.00\n"
    "C 1 600.00 60\n C 2 400.00 40\n total 1,000.00 100\n"
    "D 1 Example Pharmacy #12 100.00\n total 100.00\n"
    "E 1 Example Administrator 50.00\n total 50.00\n"
    "F 1 Wages 25.00\n total 25.00\n"
    "G 1 EXAMPLEDRUG 10MG 00000000001 300.00 100\n total 300.00 100\n"
    "H 9 425.00\n total 425.00\n"
)

META = """\
filing_id = "zz-2025-example"
entity_id = "zz-example"
state = "ZZ"
reporting_year = 2025
entity_type = "health_center"
source_file = "example.pdf"
form = "ri-oag-340b"
form_revision = "Example form"

[cover]
name_as_filed = "Example Health Center"
corporate_address_as_filed = "1 Example Street"
opais_ids_as_filed = "CH000000"
recertification_date_as_filed = "01/01/2026"
reporting_basis_as_filed = "Accrual"

[[attachments]]
pages = "4"
kind = "cover_letter"
title_as_filed = "Letter"
note = "Made up."
"""

Maker = Callable[..., Path]


@pytest.fixture
def make_repo(tmp_path: Path) -> Maker:
    """Return a function that writes the made-up repository and returns its folder."""

    def make(rows: list[str] | None = None, notes: str = "") -> Path:
        sources = tmp_path / "sources" / "zz" / "2025"
        (sources / "text").mkdir(parents=True, exist_ok=True)
        pdf = b"%PDF-made-up\n"
        (sources / "example.pdf").write_bytes(pdf)
        (sources / "manifest.csv").write_text(
            "file_name,source_url,retrieved_at,sha256,size_bytes,page_count,scanned\n"
            f"example.pdf,https://example.invalid/example.pdf,2026-01-01T00:00:00Z,"
            f"{hashlib.sha256(pdf).hexdigest()},{len(pdf)},4,false\n",
            encoding="utf-8",
        )
        (sources / "text" / "example.txt").write_text(
            "Cover\n\f" + PAGE_TWO + "\f" + PAGE_THREE + "\fA letter mentioning 9,999.99\n\f",
            encoding="utf-8",
        )
        folder = tmp_path / "transcriptions" / "zz" / "2025"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "zz-2025-example.meta.toml").write_text(META, encoding="utf-8")
        body = "\n".join([HEADER, *(ROWS if rows is None else rows)]) + "\n"
        (folder / "zz-2025-example.csv").write_text(body, encoding="utf-8")
        reference = tmp_path / "reference"
        reference.mkdir(exist_ok=True)
        (reference / "vendors.csv").write_text(
            "normalized_name,vendor_type,alias_as_filed\n"
            "Example Pharmacy,contract_pharmacy,Example Pharmacy #12\n",
            encoding="utf-8",
        )
        (reference / "categories.csv").write_text(
            "filing_id,schedule,line,category\nzz-2025-example,E,1,third_party_administrator\n",
            encoding="utf-8",
        )
        (reference / "discrepancy_notes.csv").write_text(
            "filing_id,rule,note\n" + notes, encoding="utf-8"
        )
        return tmp_path

    return make


# A made-up Vermont-style filing (state ZV, not a real place): every rule holds.
# Channels 100.00 + 200.00 + 0.00 + 50.00 = 350.00 received; 100.00 acquisition;
# expenses 10.00 + 20.00 + 5.00 = 35.00; net revenue 215.00; margin 215 / 350 = 61.43%.
VT_HEADER = HEADER
VT_ROWS = [
    "payments,in_house_pharmacy,detail,In-House Pharmacy Dispensed,,,,100.00,,,1,text_and_image,",
    "payments,contract_pharmacy,detail,Contract Pharmacy Dispensed,,,,200.00,,,1,text_and_image,",
    "payments,administered_paid_separately,detail,Administered Drugs Paid Separately,,,,"
    "0.00,,,1,text_and_image,",
    "payments,administered_bundled,detail,Administered Drugs Bundled Payments,,,,"
    "50.00,,,1,text_and_image,",
    "payments,total,total,Total 340B Payments Received,,,,350.00,,,1,text_and_image,",
    "acquisition,cost,detail,340B Prescription Drug Acquisition Costs,,,,100.00,,,1,"
    "text_and_image,",
    "expenses,contract_pharmacies,detail,Payments Made to Contract Pharmacies,,,,10.00,,,1,"
    "text_and_image,",
    "expenses,internal,detail,Internal 340B Program Expenses,,,,20.00,,,1,text_and_image,",
    "expenses,outside_vendors,detail,Payments Made to Outside Vendors,,,,5.00,,,1,text_and_image,",
    "expenses,total,total,Total 340B Expenses,,,,35.00,,,1,text_and_image,",
    "result,net_revenue,detail,340B Net Revenue,,,,215.00,,,1,text_and_image,"
    "Printed note: (made up)",
    "result,operating_margin,detail,340B Operating Margin,,,,61.43%,,,1,text_and_image,",
]
VT_PAGE = """\
Example Hospital
FY2025 340B Program Financial Reporting Detail
In-House Pharmacy Dispensed $100.00
Contract Pharmacy Dispensed $200.00
Administered Drugs Paid Separately $0.00
Administered Drugs Bundled Payments $50.00
Total 340B Payments Received $350.00
340B Prescription Drug Acquisition Costs $100.00
Payments Made to Contract Pharmacies $10.00
Internal 340B Program Expenses $20.00
Payments Made to Outside Vendors $5.00
Total 340B Expenses $35.00
340B Net Revenue $215.00
340B Operating Margin 61.43%
\f"""

VT_META = """\
filing_id = "zv-2025-example"
entity_id = "zv-example"
state = "ZV"
reporting_year = 2025
entity_type = "hospital"
source_file = "financial.pdf"
form = "vt-gmcb-340b-financial"
form_revision = "FY2025 340B Program Financial Reporting Detail"

[cover]
name_as_filed = "Example Hospital"
corporate_address_as_filed = ""
opais_ids_as_filed = ""
recertification_date_as_filed = ""
reporting_basis_as_filed = ""

[printed]
status_as_filed = "draft"
status_notice_as_filed = "NOTE: Made up."
period_as_filed = "FY2025"
submission_as_filed = "As Submitted in 2026"

[[attachments]]
file = "narrative.pdf"
kind = "narrative"
title_as_filed = ""
note = "Made up."
"""


@pytest.fixture
def make_vt_repo(tmp_path: Path) -> Maker:
    """Return a function that writes a made-up Vermont-style repository."""

    def make(rows: list[str] | None = None, notes: str = "") -> Path:
        sources = tmp_path / "sources" / "zv" / "2025"
        (sources / "text").mkdir(parents=True, exist_ok=True)
        lines = ["file_name,source_url,retrieved_at,sha256,size_bytes,page_count,scanned"]
        lines[0] += ",document_kind,cover_page_url"
        for name, kind, pages in (
            ("financial.pdf", "financial", 1),
            ("narrative.pdf", "narrative", 3),
        ):
            pdf = f"%PDF-made-up {name}\n".encode()
            (sources / name).write_bytes(pdf)
            lines.append(
                f"{name},https://example.invalid/{name},2026-01-01T00:00:00Z,"
                f"{hashlib.sha256(pdf).hexdigest()},{len(pdf)},{pages},false,{kind},"
                f"https://example.invalid/document/{kind}"
            )
        (sources / "manifest.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (sources / "text" / "financial.txt").write_text(VT_PAGE, encoding="utf-8")
        folder = tmp_path / "transcriptions" / "zv" / "2025"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "zv-2025-example.meta.toml").write_text(VT_META, encoding="utf-8")
        body = "\n".join([VT_HEADER, *(VT_ROWS if rows is None else rows)]) + "\n"
        (folder / "zv-2025-example.csv").write_text(body, encoding="utf-8")
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


# A made-up Minnesota-style report (state ZM, not a real place). Table 6.1 prints three
# entities that add up to the first Table 6.2 row; every rule holds. The percentages
# are the entities' revenue over Table 6.2's Total, unadjusted (1,250,000).
MN_ENTITIES = (
    (
        "alpha",
        "Alpha Hospital",
        "Disproportionate Share Hospital",
        "Alphaville",
        "600,000",
        "48.0%",
    ),
    ("beta", "Beta Centre", "Treatment Center", "Betaville", "300,000", "24.0%"),
    ("gamma", "Gamma Hospital", "Critical Access Hospital", "St. Gamma", "100,000", "8.0%"),
)
MN_TOTALS = (
    ("top_unadjusted", "Top 3, unadjusted", "detail", "1,000,000", "80.0%", 3),
    ("remaining_unadjusted", "Remaining 5, unadjusted", "detail", "250,000", "20.0%", 3),
    ("total_unadjusted", "Total, unadjusted", "total", "1,250,000", "100%", 3),
    ("top_adjusted", "Top 3, adjusted", "detail", "1,200,000", "80.0%", 4),
    ("remaining_adjusted", "Remaining 5, adjusted", "detail", "300,000", "20.0%", 4),
    ("total_adjusted", "Total, adjusted", "total", "1,500,000", "100%", 4),
)
MN_NOTES = (
    (2, "MDH identified 3 Covered Entities that made up the top of the made-up total."),
    (2, "Appendix Table 6.1: Made-up table"),
    (3, "Source: Made-up analysis."),
)
MN_PAGES = (
    "Cover\n\f"
    "Appendix Table 6.1\n"
    "Alpha Hospital Disproportionate Share Hospital Alphaville 600,000 48.0%\n"
    "Beta Centre Treatment Center Betaville 300,000 24.0%\n"
    "Gamma Hospital Critical Access Hospital St. Gamma 100,000 8.0%\n"
    "\f"
    "Top 3, unadjusted 1,000,000 80.0%\n"
    "Remaining 5, unadjusted 250,000 20.0%\n"
    "Total, unadjusted 1,250,000 100%\n"
    "\f"
    "Top 3, adjusted 1,200,000 80.0%\n"
    "Remaining 5, adjusted 300,000 20.0%\n"
    "Total, adjusted 1,500,000 100%\n"
    "\f"
)


def _mn_meta(key: str, name: str, printed_type: str, city: str, kind: str) -> str:
    entity_type = "hospital" if "Hospital" in printed_type else "other"
    if kind == "state_report_totals":
        entity_type = "state_total"
    return (
        f'filing_id = "zm-2024-{key}"\nentity_id = "zm-{key}"\nstate = "ZM"\n'
        f'reporting_year = 2024\nentity_type = "{entity_type}"\nrecord_kind = "{kind}"\n'
        'source_file = "report.pdf"\nform = "mn-mdh-340b-report"\n'
        'form_revision = "Made-up report"\n\n[cover]\n'
        f'name_as_filed = "{name}"\ncorporate_address_as_filed = ""\nopais_ids_as_filed = ""\n'
        'recertification_date_as_filed = ""\nreporting_basis_as_filed = ""\n\n[printed]\n'
        f'entity_type_as_filed = "{printed_type}"\ncity_as_filed = "{city}"\n'
    )


def _mn_files() -> dict[str, tuple[str, list[str]]]:
    """Return {filing key: (meta text, csv rows)} for the made-up report."""
    files: dict[str, tuple[str, list[str]]] = {}
    for key, name, printed_type, city, net, pct in MN_ENTITIES:
        files[key] = (
            _mn_meta(key, name, printed_type, city, "state_report_row"),
            [
                f'table_6_1,net_revenue,detail,{name},,Net 340B Revenue ($),,"{net}",,,2,'
                "text_and_image,",
                f"table_6_1,pct_of_statewide,detail,{name},,% of Statewide Net 340B Revenue,,"
                f"{pct},,,2,text_and_image,",
            ],
        )
    rows: list[str] = []
    for dimension, label, kind, net, pct, page in MN_TOTALS:
        rows.append(
            f'table_6_2,{dimension}_net_revenue,{kind},"{label}",,Net 340B Revenue ($),,"{net}",,,'
            f"{page},text_and_image,"
        )
        rows.append(
            f'table_6_2,{dimension}_pct_of_total,{kind},"{label}",,% of Total,,{pct},,,{page},'
            "text_and_image,"
        )
    for number, (page, text) in enumerate(MN_NOTES, start=1):
        rows.append(f"page_note,note_{number},detail,{text},,,,,,,{page},text_and_image,")
    files["statewide"] = (_mn_meta("statewide", "", "", "", "state_report_totals"), rows)
    return files


@pytest.fixture
def make_mn_repo(tmp_path: Path) -> Maker:
    """Return a function that writes a made-up Minnesota-style repository.

    ``edits`` maps a record key (``alpha``, ``statewide``) to (old, new) text replaced in
    that record's rows; ``notes`` is the text of ``discrepancy_notes.csv`` after its header.
    """

    def make(edits: dict[str, tuple[str, str]] | None = None, notes: str = "") -> Path:
        sources = tmp_path / "sources" / "zm" / "2024"
        (sources / "text").mkdir(parents=True, exist_ok=True)
        pdf = b"%PDF-made-up report\n"
        (sources / "report.pdf").write_bytes(pdf)
        (sources / "manifest.csv").write_text(
            "file_name,source_url,retrieved_at,sha256,size_bytes,page_count,scanned\n"
            f"report.pdf,https://example.invalid/report.pdf,2026-01-01T00:00:00Z,"
            f"{hashlib.sha256(pdf).hexdigest()},{len(pdf)},4,false\n",
            encoding="utf-8",
        )
        (sources / "text" / "report.txt").write_text(MN_PAGES, encoding="utf-8")
        folder = tmp_path / "transcriptions" / "zm" / "2024"
        folder.mkdir(parents=True, exist_ok=True)
        for key, (meta, rows) in _mn_files().items():
            body = "\n".join([HEADER, *rows]) + "\n"
            if edits and key in edits:
                old, new = edits[key]
                assert old in body, (key, old)
                body = body.replace(old, new)
            (folder / f"zm-2024-{key}.meta.toml").write_text(meta, encoding="utf-8")
            (folder / f"zm-2024-{key}.csv").write_text(body, encoding="utf-8")
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
