"""Extract the text layer of every archived PDF, one text file per filing.

Usage: python tools/extract_text.py sources/ri/2025
       python tools/extract_text.py sources/mn/2024 --pages 42-45

Needs ``pdftotext`` from Poppler on the PATH. The text files are committed so
the text check runs anywhere without a PDF tool; this script exists so anyone
can regenerate them and see that they come from the archived PDFs.

One thing is changed on the way: an email address is replaced with a marker.
The filings are signed by named people, and the PDFs keep their details; the
searchable text here does not need them.

With ``--pages N-M`` only those pages keep their text; every other page is left
empty (the form feeds that separate pages stay, so page numbers do not move).
Minnesota's report is a 51-page document that names people and offices on pages the
dataset does not use, so only the pages it transcribes are kept as text.
"""

from __future__ import annotations

import csv
import re
import shutil
import subprocess
import sys
from pathlib import Path

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
EMAIL_MARKER = "[email address in the PDF]"


def extract(folder: Path, pages: tuple[int, int] | None = None) -> list[str]:
    """Write ``text/<name>.txt`` for each PDF in the folder's manifest, narratives excepted.

    With ``pages`` set, only that run of pages (first, last) keeps its text.
    """
    tool = shutil.which("pdftotext")
    if tool is None:
        raise SystemExit("pdftotext (Poppler) is not installed")
    out = folder / "text"
    out.mkdir(exist_ok=True)
    written: list[str] = []
    with (folder / "manifest.csv").open(newline="", encoding="utf-8") as handle:
        # A manifest may list a narrative document the dataset does not transcribe
        # (``document_kind`` = ``narrative``); its text is not extracted or kept.
        names = [
            record["file_name"]
            for record in csv.DictReader(handle)
            if record.get("document_kind", "") != "narrative"
        ]
    for name in names:
        target = out / (Path(name).stem + ".txt")
        # Fixed arguments, no shell; the PDF is passed as data.
        subprocess.run(  # noqa: S603
            [tool, "-layout", "-enc", "UTF-8", str(folder / name), str(target)],
            check=True,
        )
        text = target.read_text(encoding="utf-8")
        if pages is not None:
            kept = text.split("\f")
            text = "\f".join(
                page if pages[0] <= number <= pages[1] else ""
                for number, page in enumerate(kept, start=1)
            )
        target.write_text(EMAIL.sub(EMAIL_MARKER, text), encoding="utf-8")
        written.append(target.name)
    return written


def main() -> int:
    """Run from the command line."""
    args = sys.argv[1:]
    pages: tuple[int, int] | None = None
    if len(args) == 3 and args[1] == "--pages":
        first, _, last = args[2].partition("-")
        pages = (int(first), int(last or first))
        args = args[:1]
    if len(args) != 1:
        raise SystemExit(__doc__)
    for name in extract(Path(args[0]), pages):
        print(name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
