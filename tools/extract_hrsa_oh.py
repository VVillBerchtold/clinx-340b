"""Make the small extract of HRSA's public covered entity list that names Ohio's filers.

Ohio's workbooks print no entity name, only a 340B ID. This tool looks each ID up in a saved
copy of HRSA's public list of covered entities and writes what that list holds for it to
``reference/hrsa-oh-extract.csv`` (one row per ID a file name carries), with the source of
the list in
``reference/hrsa-oh-extract.source.toml``. The names in the extract are HRSA's, kept apart
from anything a workbook says. An ID that HRSA's list does not hold gets an empty name.

Usage:
    python tools/extract_hrsa_oh.py <saved HRSA list .json> <folder of Ohio originals>

The saved list is a JSON file with the keys ``entities``, ``taken_on``, ``source_bytes`` and
``source_sha256`` (the day the list was saved, and the size and SHA-256 of the export it was
made from). Only entities whose street address is in Ohio are read, one at a time, so the
whole file is never held in memory.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

from filings340b.ohio_transcribe import (
    HrsaMatch,
    entity_id_of,
    hrsa_index,
    ids_in_file_name,
    match_hrsa,
    transcribe_file,
)

COLUMNS = (
    "entity_id",
    "file_name",
    "position",
    "id_in_file_name",
    "id_as_typed",
    "match",
    "hrsa_id_340b",
    "hrsa_name",
    "hrsa_subdivision_name",
    "hrsa_entity_type",
    "hrsa_city",
    "hrsa_participating",
)


def ohio_entities(path: Path) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Read the Ohio entities of a saved HRSA list, and the facts the file states about itself."""
    text = path.read_text(encoding="utf-8")
    start = text.index("[", text.index('"entities"')) + 1
    decoder = json.JSONDecoder()
    found: list[dict[str, object]] = []
    position = start
    while True:
        while text[position] in " \n\r\t,":
            position += 1
        if text[position] == "]":
            break
        entity, position = decoder.raw_decode(text, position)
        if (entity.get("street") or {}).get("state") == "OH":
            found.append(entity)
    tail = json.loads("{" + text[position + 1 :].lstrip(" \n\r\t,"))
    return found, tail


def _typed_ids(typed: str) -> list[str]:
    return re.findall(r"[A-Za-z]+\s*\d+(?:-\d+)?", typed.replace("_", " "))


def lookup(
    file_ids: tuple[str, ...], typed: str, index: dict[str, list[dict[str, object]]]
) -> list[HrsaMatch]:
    """Look up every ID of a file name, falling back on the typed ID for a one-ID file."""
    matches = [match_hrsa(one, index) for one in file_ids]
    if len(matches) == 1 and matches[0].entity is None:
        for guess in _typed_ids(typed):
            second = match_hrsa(re.sub(r"\s+", "", guess), index)
            if second.entity is not None:
                return [
                    HrsaMatch(
                        second.id_as_given, second.entity, "found by the ID typed in the workbook"
                    )
                ]
    return matches


def _record(
    entity_id: str, file_name: str, position: int, found: HrsaMatch, typed: str
) -> dict[str, str]:
    entity = found.entity or {}
    street: dict[str, object] = entity.get("street") or {}  # type: ignore[assignment]
    return {
        "entity_id": entity_id,
        "file_name": file_name,
        "position": str(position),
        "id_in_file_name": found.id_as_given,
        "id_as_typed": typed,
        "match": found.how,
        "hrsa_id_340b": str(entity.get("id_340b", "")),
        "hrsa_name": str(entity.get("name", "")),
        "hrsa_subdivision_name": str(entity.get("subdivision_name") or ""),
        "hrsa_entity_type": str(entity.get("entity_type", "")),
        "hrsa_city": str(street.get("city", "")),
        "hrsa_participating": "" if not entity else str(bool(entity.get("participating"))).lower(),
    }


def main() -> int:
    """Run from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("hrsa_list", type=Path)
    parser.add_argument("originals", type=Path)
    parser.add_argument("--out", type=Path, default=Path("reference"))
    args = parser.parse_args()
    entities, facts = ohio_entities(args.hrsa_list)
    index = hrsa_index(entities)
    records: list[dict[str, str]] = []
    for path in sorted(args.originals.glob("*.xlsx")):
        done = transcribe_file(path)
        file_ids = ids_in_file_name(path.stem)
        matches = lookup(file_ids, done.typed_id, index)
        records.extend(
            _record(
                entity_id_of(found, (found.id_as_given,)), path.name, number, found, done.typed_id
            )
            for number, found in enumerate(matches, start=1)
        )
    args.out.mkdir(exist_ok=True)
    with (args.out / "hrsa-oh-extract.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
    source = (
        "# HRSA's public list of covered entities, as used for the names of Ohio's filers.\n"
        "# It was saved on the day below from the export with the size and SHA-256 given.\n"
        'source = "HRSA Office of Pharmacy Affairs Information System (OPAIS) entity list"\n'
        f'list_date = "{facts["taken_on"]}"\n'
        f"export_bytes = {facts['source_bytes']}\n"
        f'export_sha256 = "{facts["source_sha256"]}"\n'
        f"ohio_entities_in_list = {len(entities)}\n"
    )
    (args.out / "hrsa-oh-extract.source.toml").write_text(source, encoding="utf-8")
    missing = sum(1 for r in records if not r["hrsa_name"])
    print(f"{len(records)} IDs written, {missing} not found in HRSA's list")
    return 0


if __name__ == "__main__":
    sys.exit(main())
