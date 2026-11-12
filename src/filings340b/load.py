"""Load the archived sources and the checked transcriptions from disk."""

from __future__ import annotations

import csv
import hashlib
import tomllib
from pathlib import Path

from filings340b.errors import DataError
from filings340b.forms import (
    KIND_FILING,
    MN_FORM,
    PERCENT,
    Form,
    UnknownFormError,
    form_of,
    mn_entity_type,
)
from filings340b.model import (
    Attachment,
    Filing,
    FilingMeta,
    Row,
    RowKind,
    SourceFile,
    Verification,
)
from filings340b.money import parse_amount, parse_count
from filings340b.sealing import MARKER, REASONS, restore

ATTACHMENT_KINDS = frozenset(
    {
        "cover_letter",
        "notes",
        "appendix",
        "supplemental_detail",
        "blank_page",
        # A separate PDF the state lists beside the filing (Vermont's narrative documents).
        "narrative",
        "other",
    }
)
ROW_COLUMNS = (
    "schedule",
    "line",
    "row_kind",
    "label_as_filed",
    "name_as_filed",
    "description_as_filed",
    "ndc_as_filed",
    "amount_as_filed",
    "claims_as_filed",
    "answer_as_filed",
    "page",
    "verification",
    "note",
)
# A file that withholds a claim count has this column after the others.
SEALED_COLUMNS = (*ROW_COLUMNS, MARKER)


def sha256_of(path: Path) -> str:
    """Return the SHA-256 of a file's bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_manifest(folder: Path) -> dict[str, SourceFile]:
    """Read ``manifest.csv`` beside the archived PDFs, keyed by file name."""
    with (folder / "manifest.csv").open(newline="", encoding="utf-8") as handle:
        return {
            record["file_name"]: SourceFile(
                file_name=record["file_name"],
                source_url=record["source_url"],
                retrieved_at=record["retrieved_at"],
                sha256=record["sha256"],
                size_bytes=int(record["size_bytes"]),
                page_count=int(record["page_count"]),
                scanned=record["scanned"] == "true",
                document_kind=record.get("document_kind") or "",
                cover_page_url=record.get("cover_page_url") or "",
            )
            for record in csv.DictReader(handle)
        }


def verify_source(folder: Path, source: SourceFile) -> None:
    """Fail unless the archived PDF is byte-for-byte the file that was retrieved."""
    actual = sha256_of(folder / source.file_name)
    if actual != source.sha256:
        raise DataError(f"{source.file_name}: archived file hash {actual} is not the recorded hash")


def _attachment(
    where: str, record: dict[str, object], manifest: dict[str, SourceFile]
) -> Attachment:
    kind = str(record["kind"])
    if kind not in ATTACHMENT_KINDS:
        raise DataError(f"{where}: unknown attachment kind {kind!r}")
    if "file" in record:
        # A separate PDF listed in the manifest: it is the whole attachment.
        name = str(record["file"])
        if name not in manifest:
            raise DataError(f"{where}: attachment {name!r} is not in the source manifest")
        document = manifest[name]
        return Attachment(
            first_page=1,
            last_page=document.page_count,
            kind=kind,
            title_as_filed=str(record.get("title_as_filed", "")),
            note=str(record.get("note", "")),
            document=document,
        )
    pages = str(record["pages"])
    first, _, last = pages.partition("-")
    try:
        span = (int(first), int(last or first))
    except ValueError as error:
        raise DataError(f"{where}: attachment pages {pages!r} must be N or N-M") from error
    if span[0] > span[1]:
        raise DataError(f"{where}: attachment pages {pages!r} run backwards")
    return Attachment(
        first_page=span[0],
        last_page=span[1],
        kind=kind,
        title_as_filed=str(record.get("title_as_filed", "")),
        note=str(record.get("note", "")),
    )


def read_meta(path: Path, manifest: dict[str, SourceFile] | None = None) -> FilingMeta:
    """Read a filing's identity and cover page from its ``.meta.toml`` file.

    ``manifest`` is needed only when the file lists an attachment that is a
    separate PDF (``file = "..."``).
    """
    with path.open("rb") as handle:
        doc = tomllib.load(handle)
    cover = doc["cover"]
    printed = doc.get("printed", {})
    try:
        form_of(doc["form"])
    except KeyError as error:
        raise DataError(f"{path.name}: the file must name its form (form = ...)") from error
    except UnknownFormError as error:
        raise DataError(f"{path.name}: {error}") from error
    record_kind = str(doc.get("record_kind", KIND_FILING))
    if record_kind not in form_of(doc["form"]).record_kinds:
        raise DataError(f"{path.name}: record_kind {record_kind!r} is not allowed on {doc['form']}")
    if doc["form"] == MN_FORM:
        expected = mn_entity_type(printed.get("entity_type_as_filed", ""), record_kind)
        if doc["entity_type"] != expected:
            raise DataError(
                f"{path.name}: entity_type must be {expected!r} for the printed type "
                f"{printed.get('entity_type_as_filed', '')!r}"
            )
    return FilingMeta(
        filing_id=doc["filing_id"],
        entity_id=doc["entity_id"],
        state=doc["state"],
        reporting_year=int(doc["reporting_year"]),
        entity_type=doc["entity_type"],
        source_file=doc["source_file"],
        form=doc["form"],
        form_revision=doc["form_revision"],
        name_as_filed=cover["name_as_filed"],
        corporate_address_as_filed=cover["corporate_address_as_filed"],
        opais_ids_as_filed=cover["opais_ids_as_filed"],
        recertification_date_as_filed=cover["recertification_date_as_filed"],
        reporting_basis_as_filed=cover["reporting_basis_as_filed"],
        attachments=tuple(
            _attachment(path.name, a, manifest or {}) for a in doc.get("attachments", [])
        ),
        status_as_filed=printed.get("status_as_filed", ""),
        status_notice_as_filed=printed.get("status_notice_as_filed", ""),
        period_as_filed=printed.get("period_as_filed", ""),
        submission_as_filed=printed.get("submission_as_filed", ""),
        text_layer_gaps=frozenset(str(g) for g in doc.get("text_layer_gaps", [])),
        record_kind=record_kind,
        entity_type_as_filed=printed.get("entity_type_as_filed", ""),
        city_as_filed=printed.get("city_as_filed", ""),
    )


def _row(filing_id: str, number: int, record: dict[str, str], page_count: int, form: Form) -> Row:
    where = f"{filing_id} row {number}"
    if not form.knows(record["schedule"], record["line"]):
        raise DataError(
            f"{where}: schedule {record['schedule']!r} line {record['line']!r} "
            f"is not on form {form.key}"
        )
    printed = record["amount_as_filed"]
    if form.unit_of(record["schedule"], record["line"]) == PERCENT:
        # A percentage is printed with its sign; the number is read without it.
        printed = printed.strip().removesuffix("%")
    try:
        amount = parse_amount(printed)
        claims = parse_count(record["claims_as_filed"])
        page = int(record["page"])
        kind = RowKind(record["row_kind"])
        verification = Verification(record["verification"])
    except ValueError as error:
        raise DataError(f"{where}: {error}") from error
    if not 1 <= page <= page_count:
        raise DataError(f"{where}: page {page} is outside the {page_count}-page filing")
    withheld = record.get(MARKER, "")
    if withheld and withheld not in REASONS:
        raise DataError(f"{where}: {MARKER} must be one of {', '.join(sorted(REASONS))}")
    if withheld and record["claims_as_filed"].strip():
        raise DataError(f"{where}: a withheld claim count must leave claims_as_filed empty")
    needs_note = verification in {Verification.ADJUDICATED, Verification.UNREADABLE}
    if needs_note and not record["note"].strip():
        raise DataError(f"{where}: a row marked {verification.value} must say why in its note")
    return Row(
        filing_id=filing_id,
        schedule=record["schedule"],
        line=record["line"],
        row_kind=kind,
        label_as_filed=record["label_as_filed"],
        name_as_filed=record["name_as_filed"],
        description_as_filed=record["description_as_filed"],
        ndc_as_filed=record["ndc_as_filed"],
        amount_as_filed=record["amount_as_filed"],
        amount=amount,
        claims_as_filed=record["claims_as_filed"],
        claims=claims,
        answer_as_filed=record["answer_as_filed"],
        page=page,
        verification=verification,
        note=record["note"],
        claims_withheld=withheld,
    )


def read_rows(path: Path, filing_id: str, page_count: int, form: Form) -> tuple[Row, ...]:
    """Read one filing's transcription, checking every row's form."""
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) not in (ROW_COLUMNS, SEALED_COLUMNS):
            raise DataError(
                f"{path.name}: columns must be exactly {', '.join(ROW_COLUMNS)}, "
                f"with or without a last column {MARKER}"
            )
        rows = tuple(
            _row(filing_id, number, record, page_count, form)
            for number, record in enumerate(reader, start=2)
        )
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row.schedule, row.line)
        if key in seen:
            raise DataError(f"{filing_id}: schedule {row.schedule} line {row.line} appears twice")
        seen.add(key)
    return rows


def load_filings(
    root: Path, only: str | None = None, *, check_sums: bool = True
) -> tuple[Filing, ...]:
    """Load every transcribed filing under ``root`` (or just one), sorted by filing id.

    Withheld claim counts are put back from ``private/small-counts.csv`` when that file
    is there; see ``sealing.restore``. ``check_sums=False`` is for the ``seal`` command only.

    ``root`` is the repository folder. Each ``transcriptions/<state>/<year>``
    folder is paired with the ``sources/<state>/<year>`` folder of the same name.
    """
    filings: list[Filing] = []
    for meta_path in sorted((root / "transcriptions").glob("*/*/*.meta.toml")):
        if only is not None and meta_path.name != f"{only}.meta.toml":
            continue
        sources = root / "sources" / meta_path.parent.relative_to(root / "transcriptions")
        manifest = read_manifest(sources)
        meta = read_meta(meta_path, manifest)
        if meta.source_file not in manifest:
            raise DataError(f"{meta.filing_id}: {meta.source_file} is not in the source manifest")
        source = manifest[meta.source_file]
        verify_source(sources, source)
        for attachment in meta.attachments:
            if attachment.document is not None:
                verify_source(sources, attachment.document)
        rows_path = meta_path.with_name(meta_path.name.removesuffix(".meta.toml") + ".csv")
        rows = read_rows(rows_path, meta.filing_id, source.page_count, form_of(meta.form))
        for row in rows:
            if any(a.covers(row.page) for a in meta.attachments):
                raise DataError(
                    f"{meta.filing_id}: schedule {row.schedule} line {row.line} cites page "
                    f"{row.page}, which the filing's meta file lists as an attachment"
                )
        filings.append(Filing(meta, source, rows))
    ids = [filing.meta.filing_id for filing in filings]
    if len(ids) != len(set(ids)):
        raise DataError("two transcriptions share one filing_id")
    ordered = tuple(sorted(filings, key=lambda filing: filing.meta.filing_id))
    return restore(root, ordered, check_sums=check_sums)
