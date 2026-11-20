"""Save the text of a law's official page under ``sources/laws/``, and print its SHA-256.

Usage: python tools/save_law_text.py ri-2025-h5634 https://webserver.rilegislature.gov/...
       python tools/save_law_text.py or-2024-hb4149 https://... --flow
       python tools/save_law_text.py tn-2025-sb1414 https://... --ocr
       python tools/save_law_text.py ca-2023-sb786 https://... --from-file saved-page.txt
       python tools/save_law_text.py wv-2024-sb325 https://... --more

The page is fetched with ``curl``. A PDF is turned into text with ``pdftotext`` (Poppler);
a web page has its markup taken off. The build does not need any of these tools: it reads
the saved text. This script exists so anyone can make a saved text again and compare.

The tool gives its own name on every request, ``ClinX Open Data Reader``, with the address
of the page that explains how ClinX reads public files. A site that refuses a plain fetch
under that name is read by a person in a browser and saved with ``--from-file``.

What is changed on the way, and nothing else:

* runs of spaces and line breaks become one space, and the text is then broken into
  lines after a full stop, a semicolon or a colon, so the file can be read and compared;
* a bill printed with a line number in the margin loses those numbers (only when most
  lines carry one), so a sentence that runs over two lines stays one sentence;
* curly quotation marks and long dashes become plain ones;
* an email address or a telephone number is replaced with a marker. Legislature pages
  print the contact details of members and staff; the saved text does not need them.

``--more`` saves the row's second official page (its ``more_url``) beside the first, as
``<law_id>.more.txt``. That file opens with two lines marked ``[ClinX]``, made from the
law's row in ``laws/laws.csv``: which law the page belongs to, the address it was read
from, and why it is kept (a second page can be another document, such as an older act).
A reader who finds the file on its own can then tell what it is. The build takes the lines
off before it reads the page's words.

``--flow`` reads a PDF in reading order instead of keeping its layout: use it for a law
printed in two columns. ``--ocr`` reads a scanned PDF with Tesseract (300 dots per inch);
the row's ``source_form`` is then ``scanned pdf``. ``--from-file`` takes a page saved by
hand, for a site that refuses a plain fetch; the address is still recorded in the row.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import re
import shutil
import subprocess
import tempfile
import unicodedata
from html.parser import HTMLParser
from pathlib import Path

from filings340b.laws import LAWS_FILE, more_header

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
EMAIL_MARKER = "[email address on the page]"
# A North American number: three digits (in brackets or not), three, then four.
PHONE = re.compile(r"(?<![\d-])(?:1[-. ])?\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}(?![\d-])")
PHONE_MARKER = "[phone number on the page]"

# Curly quotation marks, the hyphens and dashes that are not the keyboard's, and the soft
# hyphen, each with its plain form. A section number reads "58-56A-1" however the page typed it.
MARKS = (
    ("\u2019", "'"),
    ("\u2018", "'"),
    ("\u201c", '"'),
    ("\u201d", '"'),
    ("\u2010", "-"),
    ("\u2011", "-"),
    ("\u2012", "-"),
    ("\u2013", "-"),
    ("\u2014", "-"),
    ("\u2015", "-"),
    ("\u00ad", ""),
)

MARGIN_NUMBER = re.compile(r"^\s*\d{1,3}(\s+|$)")
# Markup whose content is not text on the page, and markup that ends a line.
UNSEEN = frozenset({"script", "style", "noscript"})
BREAKS = frozenset({"p", "br", "div", "tr", "li", "h1", "h2", "h3", "h4", "td"})
# The name this tool gives on every request. It never calls itself a browser.
CLIENT = "ClinX Open Data Reader (+https://clinx.org/methods/)"


class _PageText(HTMLParser):
    """Collect the text a reader sees on a web page."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._unseen = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in UNSEEN:
            self._unseen += 1
        if tag in BREAKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in UNSEEN and self._unseen:
            self._unseen -= 1

    def handle_data(self, data: str) -> None:
        if not self._unseen:
            self.parts.append(data)


def _tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise SystemExit(f"{name} is not installed")
    return path


def _run(command: list[str]) -> bytes:
    # Fixed arguments, no shell; the page or file is passed as data.
    return subprocess.run(command, check=True, capture_output=True).stdout  # noqa: S603


def _without_margin_numbers(text: str) -> str:
    lines = text.splitlines()
    printed = [line for line in lines if line.strip()]
    numbered = [line for line in printed if MARGIN_NUMBER.match(line)]
    if not printed or len(numbered) * 2 < len(printed):
        return text
    return "\n".join(MARGIN_NUMBER.sub("", line) for line in lines)


def tidy(text: str, *, from_pdf: bool) -> str:
    """Return the text as it is saved: plain marks, one space, short lines, no contacts."""
    text = unicodedata.normalize("NFKC", html.unescape(text))
    for curly, plain in MARKS:
        text = text.replace(curly, plain)
    if from_pdf:
        text = _without_margin_numbers(text)
    text = " ".join(text.split())
    text = PHONE.sub(PHONE_MARKER, EMAIL.sub(EMAIL_MARKER, text))
    return re.sub(r'(?<=[.;:]) (?=[("A-Z])', "\n", text) + "\n"


def _scanned_text(pdf: Path) -> str:
    pages: list[str] = []
    with tempfile.TemporaryDirectory() as folder:
        _run([_tool("pdftoppm"), "-r", "300", "-png", str(pdf), str(Path(folder) / "page")])
        for image in sorted(Path(folder).glob("page*.png")):
            pages.append(_run([_tool("tesseract"), str(image), "-", "--psm", "6"]).decode("utf-8"))
    return "\n".join(pages)


def page_text(page: Path, *, flow: bool = False, ocr: bool = False) -> tuple[str, str]:
    """Return (source_form, saved text) for a fetched page."""
    data = page.read_bytes()
    if data.startswith(b"%PDF-"):
        if ocr:
            return "scanned pdf", tidy(_scanned_text(page), from_pdf=True)
        layout = [] if flow else ["-layout"]
        printed = _run([_tool("pdftotext"), *layout, "-enc", "UTF-8", str(page), "-"])
        return "pdf", tidy(printed.decode("utf-8", "replace"), from_pdf=True)
    if data[1:2] == b"\x00" and data[3:4] == b"\x00":
        # A page sent as two-byte text (South Dakota's code pages are).
        markup = data.decode("utf-16-le", "replace")
    else:
        try:
            markup = data.decode("utf-8")
        except UnicodeDecodeError:
            # Older state pages are in the Windows character set, where a dash is one byte.
            markup = data.decode("cp1252", "replace")
    reader = _PageText()
    reader.feed(markup)
    return "web page", tidy("".join(reader.parts), from_pdf=False)


def _row(root: Path, law_id: str, url: str) -> dict[str, str]:
    """Return the law's row, with ``more_url`` set to the address being saved."""
    path = root / LAWS_FILE
    rows = list(csv.DictReader(path.open(encoding="utf-8", newline=""))) if path.is_file() else []
    row = next((r for r in rows if r["law_id"] == law_id), {"law_id": law_id})
    return {**row, "more_url": url}


def save(  # noqa: PLR0913 - one switch for each way a page is read
    root: Path,
    law_id: str,
    page: Path,
    *,
    flow: bool = False,
    ocr: bool = False,
    more: bool = False,
    url: str = "",
) -> str:
    """Write the saved text for one law and return ``form sha256 path``."""
    form, text = page_text(page, flow=flow, ocr=ocr)
    if more:
        text = more_header(_row(root, law_id, url)) + text
    name = f"{law_id}.more.txt" if more else f"{law_id}.txt"
    target = root / "sources" / "laws" / law_id[:2] / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    return f"{form}\t{digest}\t{target.relative_to(root).as_posix()}"


def main() -> int:
    """Run from the command line."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("law_id")
    parser.add_argument("url")
    parser.add_argument("--from-file", type=Path, default=None)
    parser.add_argument("--flow", action="store_true")
    parser.add_argument("--ocr", action="store_true")
    parser.add_argument("--more", action="store_true")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    if not args.url.startswith("https://"):
        raise SystemExit("the address of an official page starts with https://")
    options = {"flow": args.flow, "ocr": args.ocr, "more": args.more, "url": args.url}
    if args.from_file is not None:
        print(save(args.root, args.law_id, args.from_file, **options))
        return 0
    with tempfile.TemporaryDirectory() as folder:
        page = Path(folder) / "page"
        _run([_tool("curl"), "-sS", "-L", "--compressed", "--max-time", "90", "-A", CLIENT,
              "-o", str(page), args.url])  # fmt: skip
        print(save(args.root, args.law_id, page, **options))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
