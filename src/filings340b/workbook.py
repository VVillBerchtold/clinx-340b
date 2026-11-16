"""Read an Excel workbook (.xlsx) with the standard library only.

Ohio's covered entities file their 340B report as an Excel workbook, so the working copy
of a filing is not a PDF's saved text but the list of cells that the workbook stores. This
module reads those cells. It reads the file as a zip of XML parts, runs no macro, follows
no link and opens nothing outside the file. A value is returned exactly as the file stores
it: a number as its stored digits, text as its stored text, a formula cell as its stored result.

It is one of two independent reads of every Ohio workbook. The other is made by a different
program (see ``tools/oh_second_read.py``).
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from filings340b.errors import DataError

_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PACKAGE_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"

# A part larger than this (uncompressed) is refused; the real workbooks are far smaller.
MAX_PART_BYTES = 64 * 1024 * 1024

# Parts that are pictures, drawings, embedded objects, macros or links to other files.
_OBJECT_PARTS = (
    (re.compile(r"^xl/media/"), "picture"),
    (re.compile(r"^xl/drawings/(?!_rels/)"), "drawing"),
    (re.compile(r"^xl/embeddings/"), "embedded object"),
    (re.compile(r"^xl/(activeX|ctrlProps)/"), "form control"),
    (re.compile(r"vbaProject"), "macro"),
    (re.compile(r"^xl/externalLinks/(?!_rels/)"), "link to another file"),
    (re.compile(r"^xl/charts/(?!_rels/)"), "chart"),
)

_CELL_REF = re.compile(r"^([A-Z]{1,3})([1-9][0-9]*)$")


@dataclass(frozen=True, slots=True)
class Cell:
    """One cell that holds a value or a formula."""

    ref: str
    # The value exactly as stored: stored digits, stored text, or a formula's stored result.
    value: str
    # "number", "text", "boolean", "error" or "date".
    kind: str
    # True when the cell holds a formula (its stored result, if any, is ``value``).
    formula: bool
    # True when the cell holds a formula and the file stores no result for it.
    no_result: bool
    # True when the cell's number format shows the number as a percentage (0.25 shows as 25%).
    percent_format: bool = False


@dataclass(frozen=True, slots=True)
class Sheet:
    """One sheet: its name, whether it is visible, and its filled cells in file order."""

    name: str
    state: str
    cells: tuple[Cell, ...]

    def get(self, ref: str) -> Cell | None:
        """Return the cell at an address such as ``C17``, or None."""
        for cell in self.cells:
            if cell.ref == ref:
                return cell
        return None


@dataclass(frozen=True, slots=True)
class Workbook:
    """A workbook's sheets in order, and the parts that are not cells."""

    sheets: tuple[Sheet, ...]
    # (part name, what it is) for every picture, drawing, embedded object, macro or link.
    objects: tuple[tuple[str, str], ...]


def column_number(ref: str) -> int:
    """Return the column of an address as a number: A is 1, Z is 26, AA is 27."""
    match = _CELL_REF.match(ref)
    if match is None:
        raise DataError(f"not a cell address: {ref!r}")
    number = 0
    for letter in match.group(1):
        number = number * 26 + ord(letter) - 64
    return number


def row_number(ref: str) -> int:
    """Return the row of an address as a number."""
    match = _CELL_REF.match(ref)
    if match is None:
        raise DataError(f"not a cell address: {ref!r}")
    return int(match.group(2))


def _text_of(item: ET.Element) -> str:
    """Join the text runs of a shared string, leaving out the phonetic guide runs."""
    parts: list[str] = []
    for child in item:
        if child.tag == f"{_MAIN}t":
            parts.append(child.text or "")
        elif child.tag == f"{_MAIN}r":
            parts.extend(t.text or "" for t in child if t.tag == f"{_MAIN}t")
    return "".join(parts)


def _part(archive: zipfile.ZipFile, name: str) -> bytes:
    try:
        info = archive.getinfo(name)
    except KeyError as error:
        raise DataError(f"the workbook has no part {name}") from error
    if info.file_size > MAX_PART_BYTES:
        raise DataError(f"the workbook part {name} is larger than {MAX_PART_BYTES} bytes")
    return archive.read(name)


def _target(raw: str) -> str:
    return raw.lstrip("/") if raw.startswith("/") else "xl/" + raw


def _percent_styles(archive: zipfile.ZipFile) -> frozenset[int]:
    """Return the style numbers (the ``s`` of a cell) whose number format shows a percentage."""
    if "xl/styles.xml" not in archive.namelist():
        return frozenset()
    root = ET.fromstring(_part(archive, "xl/styles.xml"))  # noqa: S314
    custom = {
        int(node.get("numFmtId") or -1): node.get("formatCode") or ""
        for node in root.iter(f"{_MAIN}numFmt")
    }
    percent_formats = {9, 10} | {
        number for number, code in custom.items() if "%" in re.sub(r'"[^"]*"|\\.', "", code)
    }
    formats = root.find(f"{_MAIN}cellXfs")
    styles = list(formats) if formats is not None else []
    return frozenset(
        index
        for index, style in enumerate(styles)
        if int(style.get("numFmtId") or 0) in percent_formats
    )


def _cell(element: ET.Element, shared: list[str], percent: frozenset[int]) -> Cell | None:
    ref = element.get("r") or ""
    kind_code = element.get("t") or "n"
    value_node = element.find(f"{_MAIN}v")
    formula_node = element.find(f"{_MAIN}f")
    stored: str | None
    if kind_code == "inlineStr":
        inline = element.find(f"{_MAIN}is")
        stored = _text_of(inline) if inline is not None else None
        kind = "text"
    elif value_node is None or value_node.text is None:
        stored, kind = None, "number"
    elif kind_code == "s":
        stored, kind = shared[int(value_node.text)], "text"
    elif kind_code == "str":
        stored, kind = value_node.text, "text"
    elif kind_code == "b":
        stored, kind = value_node.text, "boolean"
    elif kind_code == "e":
        stored, kind = value_node.text, "error"
    elif kind_code == "d":
        stored, kind = value_node.text, "date"
    else:
        stored, kind = value_node.text, "number"
    has_formula = formula_node is not None
    if stored in (None, "") and not has_formula:
        return None
    return Cell(
        ref=ref,
        value=stored or "",
        kind=kind,
        formula=has_formula,
        no_result=has_formula and stored in (None, ""),
        percent_format=kind == "number" and int(element.get("s") or 0) in percent,
    )


def read_workbook(path: Path) -> Workbook:
    """Read every sheet's filled cells and list the parts that are not cells."""
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as error:
        raise DataError(f"{path.name}: not a workbook file") from error
    with archive:
        names = archive.namelist()
        percent = _percent_styles(archive)
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(_part(archive, "xl/sharedStrings.xml"))  # noqa: S314
            shared = [_text_of(item) for item in root.findall(f"{_MAIN}si")]
        book = ET.fromstring(_part(archive, "xl/workbook.xml"))  # noqa: S314
        rels = ET.fromstring(_part(archive, "xl/_rels/workbook.xml.rels"))  # noqa: S314
        targets = {
            r.get("Id"): r.get("Target") or "" for r in rels.findall(f"{_PACKAGE_REL}Relationship")
        }
        sheets: list[Sheet] = []
        listed = book.find(f"{_MAIN}sheets")
        for entry in listed if listed is not None else ():
            part = _target(targets[entry.get(f"{_REL}id") or ""])
            tree = ET.fromstring(_part(archive, part))  # noqa: S314
            cells = tuple(
                found
                for element in tree.iter(f"{_MAIN}c")
                if (found := _cell(element, shared, percent)) is not None
            )
            sheets.append(Sheet(entry.get("name") or "", entry.get("state") or "visible", cells))
        objects = tuple(
            (name, what)
            for name in sorted(names)
            for pattern, what in _OBJECT_PARTS
            if pattern.search(name)
        )
    return Workbook(tuple(sheets), objects)
