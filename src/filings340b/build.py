"""Rebuild every published file from the archived sources and checked transcriptions.

The output is a pure function of the committed inputs: no clock, no network,
no ordering that depends on the machine. Running it twice gives identical bytes.
"""

from __future__ import annotations

import csv
import io
import json
from decimal import Decimal
from pathlib import Path

from filings340b import __version__
from filings340b.chart import Bar, charts
from filings340b.errors import DataError
from filings340b.forms import RI_FORM, form_of
from filings340b.load import load_filings
from filings340b.model import PUBLISHABLE, Filing
from filings340b.money import plain
from filings340b.sealing import withheld_for
from filings340b.tieout import checks, measures

Table = list[dict[str, str]]

# Schedules whose rows name a payee; these get a normalized vendor name.
PAYEE_SCHEDULES = frozenset("BDE")

# What a Schedule E payment is for, taken only from the filer's own words on the row.
CATEGORIES = frozenset(
    {"third_party_administrator", "referral_capture", "consulting_audit", "other"}
)


def _read_table(path: Path) -> Table:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _key(text: str) -> str:
    """Fold case and spacing so one printed spelling matches one alias."""
    return " ".join(text.casefold().split())


def _vendor_lookup(vendors: Table) -> dict[str, str]:
    return {_key(v["alias_as_filed"]): v["normalized_name"] for v in vendors}


def _category_lookup(
    categories: Table, filings: tuple[Filing, ...]
) -> dict[tuple[str, str, str], str]:
    known = {(r.filing_id, r.schedule, r.line) for f in filings for r in f.rows}
    out: dict[tuple[str, str, str], str] = {}
    for c in categories:
        key = (c["filing_id"], c["schedule"], c["line"])
        if key not in known:
            raise DataError(f"categories.csv: no row {key[0]} schedule {key[1]} line {key[2]}")
        if c["category"] not in CATEGORIES:
            raise DataError(f"categories.csv: {c['category']!r} is not a known category")
        out[key] = c["category"]
    return out


def _check_notes(notes: Table, filings: tuple[Filing, ...]) -> None:
    """Refuse a note that no longer matches a difference, so stale notes cannot linger."""
    open_rules = {
        (c.filing_id, c.rule)
        for f in filings
        for c in checks(f, filings)
        if c.applicable and not c.passed
    }
    for n in notes:
        if (n["filing_id"], n["rule"]) not in open_rules:
            raise DataError(
                f"discrepancy_notes.csv: {n['filing_id']} rule {n['rule']} "
                "has a note but the rule holds or does not apply"
            )


def _entities(filings: tuple[Filing, ...]) -> Table:
    seen: dict[str, dict[str, str]] = {}
    for filing in filings:
        meta = filing.meta
        seen.setdefault(
            meta.entity_id,
            {
                "entity_id": meta.entity_id,
                "state": meta.state,
                "entity_type": meta.entity_type,
                "name_as_filed": meta.name_as_filed,
                "opais_ids_as_filed": meta.opais_ids_as_filed,
                "entity_type_as_filed": meta.entity_type_as_filed,
                "city_as_filed": meta.city_as_filed,
            },
        )
    return [seen[key] for key in sorted(seen)]


def _filings(filings: tuple[Filing, ...]) -> Table:
    return [
        {
            "filing_id": f.meta.filing_id,
            "entity_id": f.meta.entity_id,
            "state": f.meta.state,
            "reporting_year": str(f.meta.reporting_year),
            "form_revision": f.meta.form_revision,
            "reporting_basis_as_filed": f.meta.reporting_basis_as_filed,
            "recertification_date_as_filed": f.meta.recertification_date_as_filed,
            "corporate_address_as_filed": f.meta.corporate_address_as_filed,
            "source_url": f.source.source_url,
            "source_file": f.source.file_name,
            "retrieved_at": f.source.retrieved_at,
            "pdf_sha256": f.source.sha256,
            "pdf_bytes": str(f.source.size_bytes),
            "page_count": str(f.source.page_count),
            "scanned": "true" if f.source.scanned else "false",
            "form": f.meta.form,
            "status_as_filed": f.meta.status_as_filed,
            "status_notice_as_filed": f.meta.status_notice_as_filed,
            "period_as_filed": f.meta.period_as_filed,
            "submission_as_filed": f.meta.submission_as_filed,
            "cover_page_url": f.source.cover_page_url,
            "record_kind": f.meta.record_kind,
        }
        for f in filings
    ]


def _attachments(filings: tuple[Filing, ...]) -> Table:
    return [
        {
            "filing_id": f.meta.filing_id,
            "first_page": str(a.first_page),
            "last_page": str(a.last_page),
            "kind": a.kind,
            "title_as_filed": a.title_as_filed,
            "note": a.note,
            "document_file": a.document.file_name if a.document else "",
            "document_url": a.document.source_url if a.document else "",
            "document_cover_page_url": a.document.cover_page_url if a.document else "",
            "document_sha256": a.document.sha256 if a.document else "",
            "document_bytes": str(a.document.size_bytes) if a.document else "",
        }
        for f in filings
        for a in f.meta.attachments
    ]


def _line_items(
    filings: tuple[Filing, ...],
    vendors: dict[str, str],
    categories: dict[tuple[str, str, str], str],
) -> Table:
    out: Table = []
    withheld = withheld_for(filings)
    for filing in filings:
        for row in filing.rows:
            reason = withheld.get((row.filing_id, row.schedule, row.line), "")
            payee = row.schedule in PAYEE_SCHEDULES
            out.append(
                {
                    "filing_id": row.filing_id,
                    "schedule": row.schedule,
                    "line": row.line,
                    "row_kind": row.row_kind.value,
                    "label_as_filed": row.label_as_filed,
                    "name_as_filed": row.name_as_filed,
                    "normalized_vendor": vendors.get(_key(row.name_as_filed), "") if payee else "",
                    "category": categories.get((row.filing_id, row.schedule, row.line), ""),
                    "description_as_filed": row.description_as_filed,
                    "ndc_as_filed": row.ndc_as_filed,
                    "amount_as_filed": row.amount_as_filed,
                    "amount": plain(row.amount),
                    "unit": form_of(filing.meta.form).unit_of(row.schedule, row.line),
                    "claims_as_filed": "" if reason else row.claims_as_filed,
                    "claims": "" if row.claims is None or reason else str(row.claims),
                    "claims_withheld": reason,
                    "answer_as_filed": row.answer_as_filed,
                    "page": str(row.page),
                    "verification": row.verification.value,
                    "note": row.note,
                }
            )
    return out


def _discrepancies(filings: tuple[Filing, ...], notes: Table) -> Table:
    noted = {(n["filing_id"], n["rule"]): n["note"] for n in notes}
    out: Table = []
    for filing in filings:
        for check in checks(filing, filings):
            if not check.applicable or check.passed:
                continue
            key = (check.filing_id, check.rule)
            if key not in noted:
                raise DataError(
                    f"{check.filing_id}: rule {check.rule} does not hold "
                    f"(filed {check.filed}, expected {check.expected}) and has no "
                    "record in discrepancy_notes.csv"
                )
            out.append(
                {
                    "filing_id": check.filing_id,
                    "rule": check.rule,
                    "basis": check.basis.value,
                    "description": check.description,
                    "expected": plain(check.expected),
                    "filed": plain(check.filed),
                    "difference": plain(check.difference),
                    "unit": check.unit,
                    "note": noted[key],
                }
            )
    return out


def _measures(filings: tuple[Filing, ...], categories: dict[tuple[str, str, str], str]) -> Table:
    out: Table = [
        {"filing_id": f.meta.filing_id, "measure": name, "formula": formula, "value": plain(value)}
        for f in filings
        for name, formula, value in measures(f)
    ]
    for filing in filings:
        if not form_of(filing.meta.form).has_spending_categories:
            continue
        for category in sorted(CATEGORIES):
            amounts = [
                row.amount
                for row in filing.schedule("E")
                if row.amount is not None
                and categories.get((row.filing_id, "E", row.line)) == category
            ]
            out.append(
                {
                    "filing_id": filing.meta.filing_id,
                    "measure": f"schedule_e_{category}",
                    "formula": f"Sum of Schedule E rows whose category is {category}",
                    "value": plain(sum(amounts, Decimal(0))),
                }
            )
    return sorted(out, key=lambda m: (m["filing_id"], m["measure"]))


def _bars(filings: tuple[Filing, ...]) -> list[Bar]:
    """Return the chart's bars: Rhode Island's only, by design, as its title and groups say."""
    out = []
    for filing in filings:
        if filing.meta.form != RI_FORM:
            continue
        share = next(v for name, _, v in measures(filing) if name == "external_share_of_margin")
        out.append(Bar(filing.meta.entity_type, filing.meta.name_as_filed, share))
    return out


def _refuse_unverified(filings: tuple[Filing, ...]) -> None:
    for filing in filings:
        for row in filing.rows:
            if row.verification not in PUBLISHABLE:
                raise DataError(
                    f"{row.filing_id} schedule {row.schedule} line {row.line}: "
                    "not verified against the filing, so it cannot be published"
                )


def _csv_bytes(table: Table, columns: list[str]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(table)
    return buffer.getvalue().encode("utf-8")


COLUMNS: dict[str, list[str]] = {
    "entities": [
        "entity_id",
        "state",
        "entity_type",
        "name_as_filed",
        "opais_ids_as_filed",
        "entity_type_as_filed",
        "city_as_filed",
    ],
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
        "record_kind",
    ],
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
        "claims_withheld",
        "answer_as_filed",
        "page",
        "verification",
        "note",
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
    "measures": ["filing_id", "measure", "formula", "value"],
    "vendors": ["normalized_name", "vendor_type", "alias_as_filed", "note"],
}


def build_outputs(root: Path) -> dict[str, bytes]:
    """Return every published file's bytes, keyed by its path under ``data/``."""
    filings = load_filings(root)
    _refuse_unverified(filings)
    reference = root / "reference"
    vendors = sorted(
        _read_table(reference / "vendors.csv"),
        key=lambda v: (v["normalized_name"], v["alias_as_filed"]),
    )
    categories = _category_lookup(_read_table(reference / "categories.csv"), filings)
    notes = _read_table(reference / "discrepancy_notes.csv")
    _check_notes(notes, filings)
    tables: dict[str, Table] = {
        "entities": _entities(filings),
        "filings": _filings(filings),
        "attachments": _attachments(filings),
        "line_items": _line_items(
            filings,
            _vendor_lookup(vendors),
            categories,
        ),
        "discrepancies": _discrepancies(filings, notes),
        "measures": _measures(filings, categories),
        "vendors": vendors,
    }
    outputs = {f"{name}.csv": _csv_bytes(tables[name], COLUMNS[name]) for name in COLUMNS}
    document = {"dataset_version": __version__, "license": "CC-BY-4.0", **tables}
    outputs.update(charts(_bars(filings)))
    outputs["340b-state-filings.json"] = (
        json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    ).encode("utf-8")
    return outputs


def write_outputs(root: Path) -> list[str]:
    """Rebuild ``data/`` in place and return the names of files that changed."""
    data = root / "data"
    data.mkdir(exist_ok=True)
    changed: list[str] = []
    for name, content in sorted(build_outputs(root).items()):
        path = data / name
        if not path.exists() or path.read_bytes() != content:
            path.write_bytes(content)
            changed.append(name)
    return changed


def stale_outputs(root: Path) -> list[str]:
    """Return the committed files in ``data/`` that a rebuild would change."""
    data = root / "data"
    return [
        name
        for name, content in sorted(build_outputs(root).items())
        if not (data / name).exists() or (data / name).read_bytes() != content
    ]
