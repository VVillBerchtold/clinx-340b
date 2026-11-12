"""Check each transcription against the text layer of its own PDF.

Two questions are asked of every page that is not a scan:

* Is every transcribed amount and claim count printed on the page it cites?
* Is every amount printed on the page accounted for by a transcribed row?

The first catches a mistyped figure. The second catches a row that was left
out. Neither replaces the independent read of the page image; they are a
separate, mechanical line of evidence.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from filings340b.model import Filing, Row

# A printed figure that reads as money: grouped thousands, or two decimals.
MONEY = re.compile(r"(?<![\d,.])(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d{2})(?!\d|[,.]\d)")

# The state form prints its listing threshold in the instructions of each schedule.
FORM_FIGURES = frozenset({"5,000"})

_MARKS = str.maketrans("", "", "$ ()")


@dataclass(frozen=True, slots=True)
class Problem:
    """One thing the text layer and the transcription disagree on."""

    filing_id: str
    page: int
    fatal: bool
    detail: str


def page_texts(text_file: Path) -> list[str]:
    """Split an extracted text file into pages (form feed ends each page)."""
    pages = text_file.read_text(encoding="utf-8").split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    return pages


def core(as_filed: str) -> str:
    """Strip the presentation marks from a printed figure, keeping its digits as printed."""
    return as_filed.translate(_MARKS).lstrip("-")


def _printed(figure: str, text: str) -> int:
    pattern = r"(?<![\d,.])" + re.escape(figure) + r"(?!\d|[,.]\d)"
    return len(re.findall(pattern, text))


def _fields(row: Row) -> str:
    return "\n".join(
        (
            row.label_as_filed,
            row.name_as_filed,
            row.description_as_filed,
            row.ndc_as_filed,
            core(row.amount_as_filed),
            core(row.claims_as_filed),
            row.answer_as_filed,
        )
    )


def _figures(row: Row) -> list[tuple[str, str]]:
    found = []
    for what, as_filed in (("amount", row.amount_as_filed), ("claims", row.claims_as_filed)):
        figure = core(as_filed)
        if figure and any(ch.isdigit() for ch in figure):
            found.append((what, figure))
    return found


def _sharing(filing: Filing, everyone: tuple[Filing, ...]) -> tuple[Filing, ...]:
    """Return the filings that are rows of the same PDF (Minnesota's records share one report)."""
    return tuple(
        f
        for f in everyone
        if (f.meta.state, f.meta.reporting_year, f.source.file_name)
        == (filing.meta.state, filing.meta.reporting_year, filing.source.file_name)
    )


def check_filing(
    filing: Filing, text_file: Path, everyone: tuple[Filing, ...] = ()
) -> list[Problem]:
    """Compare one filing's rows with its extracted page text.

    Several records can be rows of one PDF page (Minnesota's). Pass ``everyone`` and a
    figure printed on the page counts as carried when any record of the same PDF carries it.
    """
    pool = tuple(r for f in _sharing(filing, everyone) for r in f.rows) or filing.rows
    fid = filing.meta.filing_id
    if filing.source.scanned:
        return []
    if not text_file.exists():
        return [Problem(fid, 0, True, f"no extracted text at {text_file.name}")]
    pages = page_texts(text_file)
    if len(pages) != filing.source.page_count:
        return [
            Problem(
                fid,
                0,
                True,
                f"extracted text has {len(pages)} pages, the PDF has {filing.source.page_count}",
            )
        ]
    problems: list[Problem] = []
    for number, text in enumerate(pages, start=1):
        if any(a.covers(number) for a in filing.meta.attachments):
            continue
        rows = [r for r in filing.rows if r.page == number]
        for row in rows:
            for what, figure in _figures(row):
                if not _printed(figure, text):
                    known_gap = f"{row.schedule}:{row.line}" in filing.meta.text_layer_gaps
                    problems.append(
                        Problem(
                            fid,
                            number,
                            not known_gap,
                            f"schedule {row.schedule} line {row.line}: {what} {figure} "
                            + (
                                "is missing from the text layer (listed gap; read from the image)"
                                if known_gap
                                else "is not printed on this page"
                            ),
                        )
                    )
        transcribed = "\n".join(_fields(r) for r in pool if r.page == number)
        printed = Counter(MONEY.findall(text))
        for figure, count in sorted(printed.items()):
            if figure in FORM_FIGURES:
                continue
            used = _printed(figure, transcribed)
            if used == 0:
                problems.append(
                    Problem(fid, number, True, f"{figure} is printed here but no row carries it")
                )
            elif used != count:
                problems.append(
                    Problem(
                        fid,
                        number,
                        False,
                        f"{figure} is printed {count} time(s) and transcribed {used} time(s)",
                    )
                )
    return problems


def text_file_for(root: Path, filing: Filing) -> Path:
    """Return where the extracted text of a filing's PDF is kept."""
    folder = root / "sources" / filing.meta.state.lower() / str(filing.meta.reporting_year)
    return folder / "text" / (Path(filing.source.file_name).stem + ".txt")
