"""Make the committed files for Ohio's workbooks from the downloaded originals.

Ohio's Department of Health posts each covered entity's report as an Excel workbook. The
workbooks name a staff member and give an e-mail address and a telephone number, so they are
kept on the machine that downloaded them (in ``sources/oh/2025/originals/``, which git
ignores) and never committed. This tool reads them and writes what the dataset keeps:

* ``sources/oh/2025/manifest.csv``: the state's address, retrieval time, SHA-256 and size of
  every workbook;
* ``sources/oh/2025/cells/<name>.csv``: the template sheet's cells (sheet, cell, value), with
  contact cells, e-mail addresses and telephone numbers masked;
* ``sources/oh/2025/workbook-contents.csv`` and ``workbook-objects.csv``: every sheet of every
  workbook by name and how many cells it fills, and every picture or object found inside;
* ``transcriptions/oh/2025/<filing id>.csv`` and ``.meta.toml``: the rows of the form.

Run ``tools/extract_hrsa_oh.py`` first (the entity of a filing is named from its extract),
then this tool, then ``tools/oh_second_read.py``, then ``filings340b seal``. The counts of 1 to
5 are in the files until ``seal`` moves them out: commit nothing before it has run.

Usage:
    python tools/oh_transcribe.py <downloaded manifest .csv> [--root <repository>]

The downloaded manifest lists, for each workbook, ``file``, ``source_url``, ``bytes``,
``sha256`` and ``retrieved_at``.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections.abc import Sequence
from pathlib import Path

from filings340b.load import sha256_of
from filings340b.masking import mask
from filings340b.ohio_transcribe import ROW_FIELDS, Transcribed, meta_text, transcribe_file

SOURCE_COLUMNS = (
    "file_name",
    "source_url",
    "retrieved_at",
    "sha256",
    "size_bytes",
    "page_count",
    "scanned",
)


def _write(
    path: Path, header: tuple[str, ...], rows: Sequence[Sequence[str] | dict[str, str]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        for row in rows:
            writer.writerow(row.values() if isinstance(row, dict) else row)


def _extract_by_file(root: Path) -> dict[str, list[dict[str, str]]]:
    with (root / "reference" / "hrsa-oh-extract.csv").open(newline="", encoding="utf-8") as handle:
        out: dict[str, list[dict[str, str]]] = {}
        for record in csv.DictReader(handle):
            out.setdefault(record["file_name"], []).append(record)
    return out


def main() -> int:
    """Run from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("downloaded_manifest", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    folder = args.root / "sources" / "oh" / "2025"
    originals = folder / "originals"
    extract = _extract_by_file(args.root)
    with args.downloaded_manifest.open(newline="", encoding="utf-8") as handle:
        downloaded = {r["file"]: r for r in csv.DictReader(handle)}
    manifest: list[tuple[str, ...]] = []
    contents: list[tuple[str, ...]] = []
    objects: list[tuple[str, ...]] = []
    for name in sorted(downloaded):
        record = downloaded[name]
        path = originals / name
        actual = sha256_of(path)
        if actual != record["sha256"] or path.stat().st_size != int(record["bytes"]):
            raise SystemExit(f"{name}: the file is not the one the download manifest records")
        done: Transcribed = transcribe_file(path)
        manifest.append(
            (
                name,
                record["source_url"],
                record["retrieved_at"],
                actual,
                record["bytes"],
                "1",
                "false",
            )
        )
        _write(folder / "cells" / f"{path.stem}.csv", ("sheet", "cell", "value"), list(done.cells))
        contents.extend(
            (name, str(number), sheet, state, str(filled), "true" if template else "false")
            for number, sheet, state, filled, template in done.contents
        )
        objects.extend((name, part, what) for part, what in done.objects)
        found = extract[name]
        first = found[0]
        other = [r["entity_id"] for r in found[1:]]
        text = meta_text(
            done,
            entity_id=first["entity_id"],
            source_file=name,
            typed_ids=mask(done.typed_id),
            other_entity_ids=other,
        )
        base = args.root / "transcriptions" / "oh" / "2025" / done.filing_id
        base.parent.mkdir(parents=True, exist_ok=True)
        (base.parent / f"{done.filing_id}.meta.toml").write_text(text, encoding="utf-8")
        _write(base.parent / f"{done.filing_id}.csv", ROW_FIELDS, list(done.rows))
    _write(folder / "manifest.csv", SOURCE_COLUMNS, manifest)
    _write(
        folder / "workbook-contents.csv",
        (
            "file_name",
            "sheet_number",
            "sheet_name",
            "sheet_state",
            "filled_cells",
            "template_sheet",
        ),
        contents,
    )
    _write(folder / "workbook-objects.csv", ("file_name", "part", "kind"), objects)
    print(f"{len(manifest)} workbooks, {len(objects)} objects inside them")
    return 0


if __name__ == "__main__":
    sys.exit(main())
