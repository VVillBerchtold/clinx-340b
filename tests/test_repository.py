"""Checks on the real, committed data: what the repository promises about itself."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from decimal import Decimal
from pathlib import Path

import pytest

from filings340b.build import build_outputs, stale_outputs
from filings340b.forms import MN_FORM, RI_FORM, UNITS, VT_FORM, VT_LINES
from filings340b.imageread import compare, image_read_file, read_image_read, unsupported_marks
from filings340b.load import load_filings
from filings340b.model import PUBLISHABLE, Basis, Filing, Verification
from filings340b.textcheck import check_filing, text_file_for
from filings340b.tieout import checks

ROOT = Path(__file__).resolve().parents[1]

# Words the published notes must never use: the dataset describes what was
# filed and how it is calculated, and says nothing about why.
JUDGEMENT_WORDS = (
    "error",
    "mistake",
    "wrong",
    "incorrect",
    "fail",
    "should have",
    "because",
    "misstate",
    "overstate",
    "understate",
)


@pytest.fixture(scope="module")
def filings() -> tuple[Filing, ...]:
    return load_filings(ROOT)


def test_rhode_island_2025_has_its_fourteen_filings(filings: tuple[Filing, ...]) -> None:
    rhode_island = [f for f in filings if f.meta.state == "RI" and f.meta.reporting_year == 2025]
    assert len(rhode_island) == 14
    kinds = sorted(f.meta.entity_type for f in rhode_island)
    assert kinds == ["health_center"] * 7 + ["hospital"] * 7


def test_every_row_is_verified(filings: tuple[Filing, ...]) -> None:
    for filing in filings:
        for row in filing.rows:
            assert row.verification in PUBLISHABLE, (row.filing_id, row.schedule, row.line)


def test_scanned_filings_rely_on_two_image_reads(filings: tuple[Filing, ...]) -> None:
    for filing in filings:
        if filing.source.scanned:
            assert {r.verification for r in filing.rows} <= {
                Verification.TWO_IMAGE_READS,
                Verification.ADJUDICATED,
                Verification.UNREADABLE,
            }


def test_the_text_of_each_pdf_agrees_with_its_transcription(filings: tuple[Filing, ...]) -> None:
    for filing in filings:
        problems = check_filing(filing, text_file_for(ROOT, filing), filings)
        assert [p.detail for p in problems if p.fatal] == [], filing.meta.filing_id


def test_every_filing_has_an_image_read_that_agrees(filings: tuple[Filing, ...]) -> None:
    for filing in filings:
        path = image_read_file(ROOT, filing)
        assert path.exists(), path.name
        assert unsupported_marks(ROOT, filing) == []
        settled = {
            (r.schedule, r.line) for r in filing.rows if r.verification is Verification.ADJUDICATED
        }
        open_differences = [
            d for d in compare(filing, read_image_read(path)) if (d.schedule, d.line) not in settled
        ]
        assert open_differences == [], filing.meta.filing_id


def test_adjudicated_and_unreadable_rows_say_what_was_seen(filings: tuple[Filing, ...]) -> None:
    for filing in filings:
        for row in filing.rows:
            if row.verification in {Verification.ADJUDICATED, Verification.UNREADABLE}:
                assert row.note.strip(), (row.filing_id, row.schedule, row.line)


def test_published_files_are_what_the_sources_rebuild_to() -> None:
    assert stale_outputs(ROOT) == []
    assert build_outputs(ROOT) == build_outputs(ROOT)


def test_every_difference_is_recorded_with_a_neutral_note(filings: tuple[Filing, ...]) -> None:
    outputs = build_outputs(ROOT)
    recorded = list(csv.DictReader(io.StringIO(outputs["discrepancies.csv"].decode("utf-8"))))
    differing = {
        (c.filing_id, c.rule): c
        for f in filings
        for c in checks(f, filings)
        if c.applicable and not c.passed
    }
    assert {(d["filing_id"], d["rule"]) for d in recorded} == set(differing)
    for d in recorded:
        note = d["note"].casefold()
        assert note, d
        assert not [word for word in JUDGEMENT_WORDS if word in note], d
        check = differing[(d["filing_id"], d["rule"])]
        assert d["basis"] == check.basis.value
        if check.basis is Basis.COMPARISON:
            assert "does not say" in note, d


def test_names_as_filed_are_kept_beside_normalized_names() -> None:
    outputs = build_outputs(ROOT)
    items = list(csv.DictReader(io.StringIO(outputs["line_items.csv"].decode("utf-8"))))
    named = [r for r in items if r["normalized_vendor"]]
    assert named
    assert all(r["name_as_filed"] for r in named)
    vendors = list(csv.DictReader(io.StringIO(outputs["vendors.csv"].decode("utf-8"))))
    used = {" ".join(r["name_as_filed"].casefold().split()) for r in items}
    unused = [
        v["alias_as_filed"]
        for v in vendors
        if " ".join(v["alias_as_filed"].casefold().split()) not in used
    ]
    assert unused == []


def test_no_email_address_is_published_or_kept_as_text() -> None:
    address = re.compile(rb"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}")
    for name, content in build_outputs(ROOT).items():
        assert address.search(content) is None, name
    for folder in ("sources", "transcriptions", "verification", "reference"):
        for path in sorted((ROOT / folder).rglob("*")):
            if path.suffix in {".txt", ".csv", ".toml"}:
                assert address.search(path.read_bytes()) is None, path.name


def _rows(name: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(build_outputs(ROOT)[name].decode("utf-8"))))


# --- Rhode Island does not move -------------------------------------------------
#
# The digests are of the Rhode Island rows of each published table, restricted to
# the columns the 0.1.0 release had, in order, as read by a CSV reader. Later releases
# may add columns and states; they may not change one Rhode Island value, row or order.
# From 0.4.0 the two claim columns are left out of the line_items pin, because the
# small-number rule empties them on withheld rows; tests/test_small_counts.py covers them.
RI_COLUMNS_0_1_0 = {
    "attachments": ["filing_id", "first_page", "last_page", "kind", "title_as_filed", "note"],
    "discrepancies": [
        "filing_id",
        "rule",
        "basis",
        "description",
        "expected",
        "filed",
        "difference",
        "note",
    ],
    "entities": ["entity_id", "state", "entity_type", "name_as_filed", "opais_ids_as_filed"],
    "filings": [
        "filing_id",
        "entity_id",
        "state",
        "reporting_year",
        "form_revision",
        "reporting_basis_as_filed",
        "recertification_date_as_filed",
        "corporate_address_as_filed",
        "source_url",
        "source_file",
        "retrieved_at",
        "pdf_sha256",
        "pdf_bytes",
        "page_count",
        "scanned",
    ],
    "line_items": [
        "filing_id",
        "schedule",
        "line",
        "row_kind",
        "label_as_filed",
        "name_as_filed",
        "normalized_vendor",
        "category",
        "description_as_filed",
        "ndc_as_filed",
        "amount_as_filed",
        "amount",
        "answer_as_filed",
        "page",
        "verification",
        "note",
    ],
    "measures": ["filing_id", "measure", "formula", "value"],
    "vendors": ["normalized_name", "vendor_type", "alias_as_filed", "note"],
}
RI_DIGESTS_0_1_0 = {
    "attachments": ("13", "834b17ae51a6e7fed5cda4c19b86413afbc41b87554b50eb01155eb88f1ac1b7"),
    "discrepancies": ("22", "be19274addaa6f46ceb9eddf92e53b7d1946458a52fcb09392db05c0d4f409bb"),
    "entities": ("14", "754d1a133f9d655045393585a751925b8c7a2a8b0456f2e2312df63c7a45820f"),
    "filings": ("14", "b475221ae8af76ef5810b183aa94f843cd7f14c18b86ba9993a8edb91e32d203"),
    "line_items": ("2989", "73c301a27cbd286f0b5b4e1615d6b3c020b210f140b9021128778fa5bfc3b4ce"),
    "measures": ("98", "0e59928a5f8f50b0c59882528927c3a9f73b8cdcbf01ef7eb7bd0587a3ab2069"),
    "vendors": ("88", "cb24f359aa259e9ee23f72e1df4a9a6d4d673fb7ace34f6aa94715d0a74ab7aa"),
}
RI_CHART_DIGESTS_0_1_0 = {
    "external-share-light.svg": "07bbb9e93b818afd8cdb19ef639cad3d2e5f2e9c70b5d88d60dababf69cb0a37",
    "external-share-dark.svg": "71d93a040ea4742c4d883e7c82b280f81a9d6af60f125001b85bd1c9bb1c866d",
}


@pytest.mark.parametrize("name", sorted(RI_COLUMNS_0_1_0))
def test_rhode_island_values_have_not_changed_since_0_1_0(name: str) -> None:
    columns = RI_COLUMNS_0_1_0[name]
    kept = [
        [row[c] for c in columns]
        for row in _rows(f"{name}.csv")
        if row.get("filing_id", "ri-").startswith("ri-")
        and (name != "entities" or row["state"] == "RI")
    ]
    count, digest = RI_DIGESTS_0_1_0[name]
    assert len(kept) == int(count)
    document = json.dumps([columns, *kept], ensure_ascii=False)
    assert hashlib.sha256(document.encode()).hexdigest() == digest


def test_the_rhode_island_chart_is_unchanged_and_has_no_vermont_filing() -> None:
    outputs = build_outputs(ROOT)
    for name, digest in RI_CHART_DIGESTS_0_1_0.items():
        assert hashlib.sha256(outputs[name]).hexdigest() == digest, name


def test_the_published_rhode_island_finding_still_reads_the_same() -> None:
    entities = {e["entity_id"]: e["entity_type"] for e in _rows("entities.csv")}
    filings = {f["filing_id"]: f for f in _rows("filings.csv")}
    totals: dict[str, dict[str, Decimal]] = {}
    for m in _rows("measures.csv"):
        filing = filings[m["filing_id"]]
        if filing["state"] != "RI" or m["measure"] not in {"gross_margin", "external_cost"}:
            continue
        kind = entities[filing["entity_id"]]
        bucket = totals.setdefault(kind, {"gross_margin": Decimal(0), "external_cost": Decimal(0)})
        bucket[m["measure"]] += Decimal(m["value"])
    centers, hospitals = totals["health_center"], totals["hospital"]
    assert round(centers["gross_margin"] / 1_000_000, 1) == Decimal("47.8")
    assert round(centers["external_cost"] / 1_000_000, 1) == Decimal("17.6")
    assert round(centers["external_cost"] / centers["gross_margin"] * 100, 1) == Decimal("36.8")
    assert round(hospitals["external_cost"] / hospitals["gross_margin"] * 100, 1) == Decimal("12.9")


def test_every_row_and_difference_has_a_unit() -> None:
    for name in ("line_items.csv", "discrepancies.csv"):
        assert {r["unit"] for r in _rows(name)} <= set(UNITS), name
    filings = {f["filing_id"]: f for f in _rows("filings.csv")}
    for row in _rows("line_items.csv"):
        state = filings[row["filing_id"]]["state"]
        if state == "RI":
            assert row["unit"] == ("none" if row["schedule"] == "I" else "usd"), row
    for d in _rows("discrepancies.csv"):
        if d["rule"].endswith(".claims=total") or d["rule"] == "C.claims=G.claims":
            assert d["unit"] == "count", d


# --- Vermont, fiscal year 2025 --------------------------------------------------
VERMONT_KEYS = (
    "central-vermont",
    "copley",
    "gifford",
    "grace-cottage",
    "mt-ascutney",
    "north-country",
    "northeastern-vermont",
    "northwestern",
    "porter",
    "rutland",
    "southwestern-vermont",
    "springfield",
    "uvm-medical-center",
)


def _vermont(filings: tuple[Filing, ...]) -> list[Filing]:
    return [f for f in filings if f.meta.state == "VT"]


def test_vermont_2025_has_its_thirteen_hospital_reports(filings: tuple[Filing, ...]) -> None:
    found = _vermont(filings)
    assert [f.meta.filing_id for f in found] == [f"vt-2025-{k}" for k in VERMONT_KEYS]
    for f in found:
        assert f.meta.form == VT_FORM
        assert (f.meta.entity_type, f.meta.reporting_year, f.source.page_count) == (
            "hospital",
            2025,
            1,
        )
        assert [(r.schedule, r.line) for r in f.rows if r.schedule != "page_note"] == [
            (s, k) for s, k, _, _ in VT_LINES
        ]
        assert all(r.page == 1 for r in f.rows)


def test_vermont_filings_print_their_status_and_period(filings: tuple[Filing, ...]) -> None:
    published = {f["filing_id"]: f for f in _rows("filings.csv")}
    notice = (
        "NOTE: This is draft and may be adjusted for accuracy in the final GMCB dashboard "
        "publication."
    )
    for f in _vermont(filings):
        row = published[f.meta.filing_id]
        assert row["status_as_filed"] == "draft"
        assert row["status_notice_as_filed"] == notice
        assert row["period_as_filed"] == "FY2025"
        assert row["form_revision"] == "FY2025 340B Program Financial Reporting Detail"
        # The page prints none of these; they are blank, never filled in.
        for blank in (
            "reporting_basis_as_filed",
            "recertification_date_as_filed",
            "corporate_address_as_filed",
        ):
            assert row[blank] == "", blank
        assert row["cover_page_url"].startswith("https://gmcboard.vermont.gov/document/")
    entities = {e["entity_id"]: e for e in _rows("entities.csv")}
    for f in _vermont(filings):
        assert entities[f.meta.entity_id]["opais_ids_as_filed"] == ""
    for row in published.values():
        if row["state"] == "RI":
            assert row["status_as_filed"] == row["period_as_filed"] == ""


def test_vermont_narratives_are_listed_as_attachments_not_transcribed(
    filings: tuple[Filing, ...],
) -> None:
    folder = ROOT / "sources" / "vt" / "2025"
    manifest = list(csv.DictReader((folder / "manifest.csv").open(newline="", encoding="utf-8")))
    assert sorted(r["document_kind"] for r in manifest) == ["financial"] * 13 + ["narrative"] * 13
    for record in manifest:
        digest = hashlib.sha256((folder / record["file_name"]).read_bytes()).hexdigest()
        assert digest == record["sha256"], record["file_name"]
        assert record["cover_page_url"].startswith("https://gmcboard.vermont.gov/document/")
    attachments = [a for a in _rows("attachments.csv") if a["filing_id"].startswith("vt-")]
    assert len(attachments) == 13
    by_file = {r["file_name"]: r for r in manifest}
    for a in attachments:
        record = by_file[a["document_file"]]
        assert a["kind"] == "narrative"
        assert (a["document_sha256"], a["document_url"]) == (record["sha256"], record["source_url"])
        assert (a["first_page"], a["last_page"]) == ("1", record["page_count"])
    # Only the financial pages are transcribed and have extracted text kept.
    assert len(list((folder / "text").glob("*.txt"))) == 13


def test_vermont_has_four_recorded_differences_and_no_others() -> None:
    found = {
        (d["filing_id"], d["rule"]): (d["expected"], d["filed"], d["difference"], d["unit"])
        for d in _rows("discrepancies.csv")
        if d["filing_id"].startswith("vt-")
    }
    assert found == {
        ("vt-2025-gifford", "net_revenue=payments-acquisition-expenses"): (
            "2800632.00",
            "2880632.00",
            "80000.00",
            "usd",
        ),
        ("vt-2025-gifford", "operating_margin=net_revenue/payments"): (
            "91.16",
            "88.63",
            "-2.53",
            "percent",
        ),
        ("vt-2025-porter", "payments.rows=total"): ("9824294.00", "9824295.00", "1.00", "usd"),
        ("vt-2025-uvm-medical-center", "expenses.rows=total"): (
            "13142032.00",
            "13142031.00",
            "-1.00",
            "usd",
        ),
    }


# Worked by hand from each page's printed figures, not from the engine.
VERMONT_MEASURES = {
    "central-vermont": ("35572668.00", "1926305.00", "0.054151"),
    "copley": ("2177726.00", "25200.00", "0.011572"),
    "gifford": ("2996906.00", "171297.00", "0.057158"),
    "grace-cottage": ("2377638.00", "22174.00", "0.009326"),
    "mt-ascutney": ("1108042.00", "291256.00", "0.262856"),
    "north-country": ("2465622.00", "1195380.00", "0.484819"),
    "northeastern-vermont": ("3037010.00", "704252.00", "0.231890"),
    "northwestern": ("-3627.00", "318511.00", ""),
    "porter": ("6208356.00", "911831.00", "0.146872"),
    "rutland": ("8636709.00", "0.00", "0.000000"),
    "southwestern-vermont": ("14921010.00", "2591250.00", "0.173665"),
    "springfield": ("3856221.00", "65698.00", "0.017037"),
    "uvm-medical-center": ("344260471.00", "12613818.00", "0.036640"),
}


def test_vermont_measures_match_the_figures_worked_by_hand() -> None:
    values = {(m["filing_id"], m["measure"]): m["value"] for m in _rows("measures.csv")}
    for key, (margin, external, share) in VERMONT_MEASURES.items():
        fid = f"vt-2025-{key}"
        assert values[(fid, "gross_margin")] == margin, fid
        assert values[(fid, "external_cost")] == external, fid
        assert values[(fid, "external_share_of_margin")] == share, fid
    assert not [k for k in values if k[0].startswith("vt-") and "schedule_e" in k[1]]


def test_vermont_image_reads_agree_exactly_as_printed(filings: tuple[Filing, ...]) -> None:
    # Stricter than the shared comparison: a parenthesis, minus sign or percent mark counts.
    for f in _vermont(filings):
        read = read_image_read(image_read_file(ROOT, f))
        for row in f.rows:
            seen = read.get((row.schedule, row.line))
            if row.schedule == "page_note":
                assert seen is None
                continue
            assert seen is not None, (f.meta.filing_id, row.line)
            assert seen["amount"] == row.amount_as_filed, (f.meta.filing_id, row.line)
            assert row.verification is Verification.TEXT_AND_IMAGE


def test_no_person_or_phone_number_is_in_vermonts_files() -> None:
    phone = re.compile(rb"\b\d{3}[-. ]\d{3}[-. ]\d{4}\b")
    for folder in ("transcriptions/vt", "verification/vt", "sources/vt/2025/text"):
        for path in sorted((ROOT / folder).rglob("*")):
            if path.is_file():
                assert phone.search(path.read_bytes()) is None, path.name
    for name in ("filings.csv", "line_items.csv", "attachments.csv", "entities.csv"):
        for row in _rows(name):
            if str(row.get("filing_id", "")).startswith("vt-"):
                assert phone.search(json.dumps(row).encode()) is None, row


def test_all_three_forms_are_in_use(filings: tuple[Filing, ...]) -> None:
    assert {f.meta.form for f in filings} == {RI_FORM, VT_FORM, MN_FORM}


# --- Vermont does not move either -----------------------------------------------
#
# Pinned at 0.2.0: the Vermont rows of each published table, restricted to the columns that
# release had, in order. Later releases may add columns and states; they may not change one
# Vermont value, row or order.
VT_COLUMNS_0_2_0 = {
    "attachments": [
        "filing_id",
        "first_page",
        "last_page",
        "kind",
        "title_as_filed",
        "note",
        "document_file",
        "document_url",
        "document_cover_page_url",
        "document_sha256",
        "document_bytes",
    ],
    "discrepancies": [
        "filing_id",
        "rule",
        "basis",
        "description",
        "expected",
        "filed",
        "difference",
        "unit",
        "note",
    ],
    "entities": ["entity_id", "state", "entity_type", "name_as_filed", "opais_ids_as_filed"],
    "filings": [
        "filing_id",
        "entity_id",
        "state",
        "reporting_year",
        "form_revision",
        "reporting_basis_as_filed",
        "recertification_date_as_filed",
        "corporate_address_as_filed",
        "source_url",
        "source_file",
        "retrieved_at",
        "pdf_sha256",
        "pdf_bytes",
        "page_count",
        "scanned",
        "form",
        "status_as_filed",
        "status_notice_as_filed",
        "period_as_filed",
        "submission_as_filed",
        "cover_page_url",
    ],
    "line_items": [
        "filing_id",
        "schedule",
        "line",
        "row_kind",
        "label_as_filed",
        "name_as_filed",
        "normalized_vendor",
        "category",
        "description_as_filed",
        "ndc_as_filed",
        "amount_as_filed",
        "amount",
        "unit",
        "claims_as_filed",
        "claims",
        "answer_as_filed",
        "page",
        "verification",
        "note",
    ],
    "measures": ["filing_id", "measure", "formula", "value"],
}
VT_DIGESTS_0_2_0 = {
    "attachments": ("13", "5f99f7fa11d0bb3a6ec8a93b2bd2e5bb117996390ecc1c2183c36b18b8855c7d"),
    "discrepancies": ("4", "8ed7c55f6149cd5c74e0cbbfa5690b5ae184a4a8fe80802f1779e2db3e3b89aa"),
    "entities": ("13", "da152999f536ed80e019e05f4747dd748ceb6fa3dbb1afb92c76ab2025cbf22b"),
    "filings": ("13", "159dd6a3df700052e4a404ecaaf94a48ac9e7be3411cff1434ece8a521b3f0e5"),
    "line_items": ("157", "302d4b735cb56638ff57a8d41f132a3689dba818ad20ccf74b790137dbee89a9"),
    "measures": ("39", "a4200f2eaa271e4123f91b34bb32548b28db82fdf78692d70a1c9223c3bcf631"),
}


@pytest.mark.parametrize("name", sorted(VT_COLUMNS_0_2_0))
def test_vermont_values_have_not_changed_since_0_2_0(name: str) -> None:
    columns = VT_COLUMNS_0_2_0[name]
    kept = [
        [row[c] for c in columns]
        for row in _rows(f"{name}.csv")
        if row.get("filing_id", "").startswith("vt-")
        or (name == "entities" and row["state"] == "VT")
    ]
    count, digest = VT_DIGESTS_0_2_0[name]
    assert len(kept) == int(count)
    document = json.dumps([columns, *kept], ensure_ascii=False)
    assert hashlib.sha256(document.encode()).hexdigest() == digest


def test_every_filing_has_a_record_kind() -> None:
    kinds = {f["filing_id"]: f["record_kind"] for f in _rows("filings.csv")}
    assert {k for fid, k in kinds.items() if fid[:2] in {"ri", "vt"}} == {"filing"}
    assert {k for fid, k in kinds.items() if fid.startswith("mn-")} == {
        "state_report_row",
        "state_report_totals",
    }
    assert sum(1 for k in kinds.values() if k == "state_report_totals") == 1


# --- Minnesota, 2024 data (the report titled 2025) -----------------------------
# Worked by hand from the printed pages 42 to 44 of the report: name, type, city, net
# 340B revenue, % of statewide net 340B revenue, page. Order is the printed order.
DSH = "Disproportionate Share Hospital"
MINNESOTA_ROWS = (
    (
        "fairview-umn-medical-center",
        "M Health Fairview - University of Minnesota Medical Center",
        DSH,
        "Minneapolis",
        "334,683,472",
        "26.1%",
        42,
    ),
    (
        "abbott-northwestern",
        "Abbott Northwestern Hospital",
        DSH,
        "Minneapolis",
        "153,985,063",
        "12.0%",
        42,
    ),
    ("hennepin-healthcare", "Hennepin Healthcare", DSH, "Minneapolis", "99,659,845", "7.8%", 42),
    ("essentia-duluth", "Essentia Health Duluth", DSH, "Duluth", "76,920,741", "6.0%", 42),
    ("united-hospital", "United Hospital", DSH, "St. Paul", "63,398,615", "5.0%", 42),
    (
        "centracare-st-cloud",
        "CentraCare - St. Cloud Hospital",
        DSH,
        "St. Cloud",
        "52,235,397",
        "4.1%",
        42,
    ),
    ("north-memorial", "North Memorial Health", DSH, "Robbinsdale", "49,955,943", "3.9%", 42),
    ("regions-hospital", "Regions Hospital", DSH, "St. Paul", "47,883,168", "3.7%", 42),
    ("mercy-hospital", "Mercy Hospital", DSH, "Coon Rapids", "46,090,233", "3.6%", 43),
    (
        "essentia-st-josephs",
        "Essentia Health - St. Joseph's Medical Center",
        "Sole Community Hospital",
        "Brainerd",
        "25,242,064",
        "2.0%",
        43,
    ),
    (
        "new-ulm",
        "New Ulm Medical Center",
        "Critical Access Hospital",
        "New Ulm",
        "22,683,681",
        "1.8%",
        43,
    ),
    ("sanford-bemidji", "Sanford Bemidji Medical Center", DSH, "Bemidji", "19,103,068", "1.5%", 43),
    ("cambridge", "Cambridge Medical Center", DSH, "Cambridge", "17,034,720", "1.3%", 43),
    ("essentia-virginia", "Essentia Health Virginia", DSH, "Virginia", "16,253,994", "1.3%", 43),
    (
        "grand-itasca",
        "Grand Itasca Clinic and Hospital",
        "Sole Community Hospital",
        "Grand Rapids",
        "16,237,511",
        "1.3%",
        43,
    ),
    (
        "gillette-childrens",
        "Gillette Children's Specialty Healthcare",
        "Children's Hospital",
        "St. Paul",
        "15,000,119",
        "1.2%",
        43,
    ),
    (
        "fairview-blood-clotting",
        "M Health Fairview - Center for Blood and Clotting Disorders",
        "CHD Treatment Center",
        "Minneapolis",
        "12,863,206",
        "1.0%",
        43,
    ),
    ("range-regional", "Range Regional Health Services", DSH, "Hibbing", "12,596,018", "1.0%", 43),
    (
        "fairview-st-johns",
        "M Health Fairview - St. John's Hospital",
        DSH,
        "Maplewood",
        "10,770,611",
        "0.8%",
        43,
    ),
    ("faribault", "Faribault Medical Center", DSH, "Faribault", "10,697,207", "0.8%", 44),
    (
        "cuyuna",
        "Cuyuna Regional Medical Center",
        "Critical Access Hospital",
        "Crosby",
        "9,126,893",
        "0.7%",
        44,
    ),
    ("st-lukes-duluth", "St. Luke's Hospital of Duluth", DSH, "Duluth", "9,107,003", "0.7%", 44),
    (
        "mayo-albert-lea",
        "Mayo Clinic Health System in Albert Lea",
        "Sole Community Hospital",
        "Albert Lea",
        "8,948,445",
        "0.7%",
        44,
    ),
    ("ccm-health", "CCM Health", "Critical Access Hospital", "Montevideo", "7,855,856", "0.6%", 44),
    (
        "childrens-minnesota",
        "Children\u2019s Minnesota",
        "Children's Hospital",
        "Minneapolis",
        "7,040,712",
        "0.6%",
        44,
    ),
    (
        "centracare-rice-memorial",
        "CentraCare - Rice Memorial Hospital",
        DSH,
        "Willmar",
        "7,029,723",
        "0.5%",
        44,
    ),
)
MINNESOTA_TOTALS = (
    ("top_unadjusted", "Top 25, unadjusted", "1,152,403,307", "90.3%", 44),
    ("remaining_unadjusted", "Remaining 156, unadjusted", "123,840,474", "9.7%", 44),
    ("total_unadjusted", "Total, unadjusted", "1,276,243,781", "100%", 44),
    ("top_adjusted", "Top 25, adjusted", "1,199,240,413", "89.5%", 45),
    ("remaining_adjusted", "Remaining 156, adjusted", "141,030,552", "10.5%", 45),
    ("total_adjusted", "Total, adjusted", "1,340,270,964", "100%", 45),
)
MINNESOTA_NOTES = (
    (
        42,
        "MDH identified 25 Covered Entities that together generated the top 90% of statewide "
        "net 340B revenue in Minnesota in 2024. In contrast to 2023 data reporting, all "
        "entities listed in Appendix Table 6.1 reported on both dispensed and administered "
        "drugs, meaning these data should be considered relatively complete. These net 340B "
        "revenue figures are not adjusted to account for the estimated missing administered "
        "drug reimbursements by Covered Entities.",
    ),
    (42, "Appendix Table 6.1: Top net 340B revenue by Covered Entity, unadjusted"),
    (
        44,
        "Source: MDH, Health Economics Program analysis of 2023 and 2024 data reported by "
        "Covered Entities under the Minnesota 340B Covered Entity Report.",
    ),
    (
        44,
        "Appendix Table 6.2 displays the total net 340B revenue for the Covered Entities "
        "presented in Appendix Table 6.1 (above) as well as the remaining 156 Covered "
        "Entities included in analysis, both with the net 340B amount unadjusted and "
        "adjusted for the estimated missing reimbursements for administered drugs.",
    ),
    (44, "Appendix Table 6.2: Top net 340B revenue, unadjusted and adjusted"),
    (
        45,
        "Source: MDH, Health Economics Program analysis of 2024 data reported by Covered "
        "Entities under the Minnesota 340B Covered Entity Report",
    ),
)


def _minnesota(filings: tuple[Filing, ...]) -> list[Filing]:
    return [f for f in filings if f.meta.state == "MN"]


def test_minnesota_2024_has_a_record_for_each_printed_row_and_one_statewide(
    filings: tuple[Filing, ...],
) -> None:
    found = {f.meta.filing_id: f for f in _minnesota(filings)}
    assert sorted(found) == sorted(
        [f"mn-2024-{k}" for k, *_ in MINNESOTA_ROWS] + ["mn-2024-statewide"]
    )
    assert len(MINNESOTA_ROWS) == 26
    for f in found.values():
        assert (f.meta.form, f.meta.reporting_year, f.source.page_count) == (MN_FORM, 2024, 51)
        assert f.source.source_url == "https://www.health.mn.gov/data/340b/docs/2025report.pdf"
        assert f.meta.form_revision == "340B Covered Entity Report, 2025"
    for key, name, printed_type, city, net, pct, page in MINNESOTA_ROWS:
        f = found[f"mn-2024-{key}"]
        assert f.meta.record_kind == "state_report_row"
        assert (f.meta.name_as_filed, f.meta.entity_type_as_filed, f.meta.city_as_filed) == (
            name,
            printed_type,
            city,
        )
        assert f.meta.entity_type == ("hospital" if "Hospital" in printed_type else "other")
        assert [(r.schedule, r.line, r.amount_as_filed, r.page) for r in f.rows] == [
            ("table_6_1", "net_revenue", net, page),
            ("table_6_1", "pct_of_statewide", pct, page),
        ]
        assert all(r.verification is Verification.TEXT_AND_IMAGE for r in f.rows)


def test_minnesota_statewide_record_holds_table_6_2_and_the_text_around_the_tables(
    filings: tuple[Filing, ...],
) -> None:
    (statewide,) = [f for f in filings if f.meta.filing_id == "mn-2024-statewide"]
    assert (statewide.meta.entity_id, statewide.meta.entity_type) == ("mn-statewide", "state_total")
    assert statewide.meta.record_kind == "state_report_totals"
    figures = [
        (r.line, r.label_as_filed, r.amount_as_filed, r.page)
        for r in statewide.rows
        if r.schedule == "table_6_2"
    ]
    expected = []
    for key, label, net, pct, page in MINNESOTA_TOTALS:
        expected += [
            (f"{key}_net_revenue", label, net, page),
            (f"{key}_pct_of_total", label, pct, page),
        ]
    assert figures == expected
    notes = [(r.page, r.label_as_filed) for r in statewide.rows if r.schedule == "page_note"]
    assert notes == list(MINNESOTA_NOTES)
    assert all(r.verification is Verification.TEXT_AND_IMAGE for r in statewide.rows)


def test_minnesota_has_the_differences_it_has_and_no_others() -> None:
    found = {
        (d["filing_id"], d["rule"]): (
            d["expected"],
            d["filed"],
            d["difference"],
            d["unit"],
            d["basis"],
        )
        for d in _rows("discrepancies.csv")
        if d["filing_id"].startswith("mn-")
    }
    pct = "pct_of_statewide=net_revenue/total_unadjusted"
    assert found == {
        ("mn-2024-statewide", "table_6_1.rows=stated_entities"): (
            "26",
            "25",
            "-1",
            "count",
            "form",
        ),
        ("mn-2024-statewide", "table_6_1.sum=table_6_2.top_unadjusted"): (
            "1152403308",
            "1152403307",
            "-1",
            "usd",
            "form",
        ),
        ("mn-2024-statewide", "table_6_2.adjusted_rows=total"): (
            "1340270965",
            "1340270964",
            "-1",
            "usd",
            "form",
        ),
        ("mn-2024-abbott-northwestern", pct): ("12.1", "12.0", "-0.1", "percent", "comparison"),
        ("mn-2024-centracare-rice-memorial", pct): ("0.6", "0.5", "-0.1", "percent", "comparison"),
        ("mn-2024-fairview-umn-medical-center", pct): (
            "26.2",
            "26.1",
            "-0.1",
            "percent",
            "comparison",
        ),
        ("mn-2024-regions-hospital", pct): ("3.8", "3.7", "-0.1", "percent", "comparison"),
    }


def test_minnesota_has_no_measures() -> None:
    assert not [m for m in _rows("measures.csv") if m["filing_id"].startswith("mn-")]
    assert not [
        m
        for m in _rows("measures.csv")
        if m["measure"] == "schedule_e_other" and m["filing_id"].startswith("mn-")
    ]


def test_nothing_in_minnesotas_files_calls_a_row_a_rank_or_a_place() -> None:
    words = re.compile(r"\b(rank|ranks|ranked|ranking|top[- ]?ten|place|placed|position)\b", re.I)
    columns = {"entity_type", "line", "schedule", "row_kind"}
    for name in ("entities.csv", "filings.csv", "line_items.csv", "discrepancies.csv"):
        for row in _rows(name):
            if str(row.get("filing_id", row.get("entity_id", ""))).startswith(("mn-", "zm-")):
                for column, value in row.items():
                    # The report's own words ("Top 25") are kept as printed, in label columns.
                    if column in columns or column.endswith("_as_filed"):
                        continue
                    assert not words.search(value), (name, column, value)


def test_minnesota_sources_and_the_figures_the_page_text_carries() -> None:
    folder = ROOT / "sources" / "mn" / "2024"
    (record,) = list(csv.DictReader((folder / "manifest.csv").open(newline="", encoding="utf-8")))
    assert (
        hashlib.sha256((folder / record["file_name"]).read_bytes()).hexdigest() == record["sha256"]
    )
    assert record["sha256"] == "8356e3d1240f33187a3a609f27c342a7b8b2c1e5a70b2903fed10350b045c18e"
    text = (folder / "text" / "2025report.txt").read_text(encoding="utf-8").split("\f")
    # Only the pages the dataset transcribes keep their text; the rest of the report names
    # people and offices, and is left empty.
    assert [i + 1 for i, page in enumerate(text[:51]) if page.strip()] == [42, 43, 44, 45]


def test_minnesota_second_read_agrees_on_every_name_type_and_city() -> None:
    folder = ROOT / "verification" / "mn" / "2024"
    read = list(
        csv.DictReader(
            (folder / "mn-2024-table-6-1.second-read.csv").open(newline="", encoding="utf-8")
        )
    )
    assert [
        (r["name"], r["type"], r["city"], r["net_revenue"], r["percent"], r["page"]) for r in read
    ] == [
        (name, printed_type, city, net, pct, str(page))
        for _, name, printed_type, city, net, pct, page in MINNESOTA_ROWS
    ]
    totals = list(
        csv.DictReader(
            (folder / "mn-2024-table-6-2.second-read.csv").open(newline="", encoding="utf-8")
        )
    )
    assert [(r["dimension"], r["net_revenue"], r["percent"], r["page"]) for r in totals] == [
        (label, net, pct, str(page)) for _, label, net, pct, page in MINNESOTA_TOTALS
    ]


def test_minnesota_image_reads_agree_exactly_as_printed(filings: tuple[Filing, ...]) -> None:
    for f in _minnesota(filings):
        read = read_image_read(image_read_file(ROOT, f))
        for row in f.rows:
            seen = read.get((row.schedule, row.line))
            if row.schedule == "page_note":
                assert seen is None
                continue
            assert seen is not None, (f.meta.filing_id, row.line)
            assert seen["amount"] == row.amount_as_filed, (f.meta.filing_id, row.line)
            assert seen["page"] == str(row.page)


def test_no_person_email_or_phone_number_is_in_minnesotas_files() -> None:
    phone = re.compile(rb"\b\d{3}[-. ]\d{3}[-. ]\d{4}\b")
    for folder in ("transcriptions/mn", "verification/mn", "sources/mn/2024/text"):
        for path in sorted((ROOT / folder).rglob("*")):
            if path.is_file():
                assert phone.search(path.read_bytes()) is None, path.name
    for name in ("filings.csv", "line_items.csv", "attachments.csv", "entities.csv"):
        for row in _rows(name):
            if str(row.get("filing_id", row.get("entity_id", ""))).startswith("mn-"):
                assert phone.search(json.dumps(row).encode()) is None, row
