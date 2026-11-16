"""Read amounts and counts exactly as a filing prints them.

A filed figure is never rounded or corrected here. Parsing only removes the
presentation marks (currency sign, thousands separators, accounting
parentheses) so the value can be summed; the printed text is stored beside it.
"""

from __future__ import annotations

import re
from decimal import Decimal

# An accounting-format zero prints as a lone dash.
_DASHES = frozenset({"-", chr(0x2013), chr(0x2014)})
# Words some filers print in an amount cell in place of a figure ("N/R" is Vermont's).
_NOT_A_FIGURE = frozenset({"N/A", "NA", "N/R"})
_AMOUNT = re.compile(r"^\d{1,3}(?:,\d{3})*(?:\.\d+)?$|^\d+(?:\.\d+)?$|^\.\d+$")
_COUNT = re.compile(r"^\d{1,3}(?:,\d{3})*$|^\d+$")


def parse_amount(as_filed: str) -> Decimal | None:
    """Return the value of an amount as printed, or None when the cell holds no figure.

    A blank cell and a cell that prints ``N/A`` or ``N/R`` have no value; the printed
    text is kept beside the value, so the two stay distinguishable.

    The scale is kept as filed: ``"3,996,714"`` stays a whole number and
    ``"1,408,968.83"`` keeps its cents.
    """
    text = as_filed.replace("$", "").replace(" ", "").strip()
    if not text or text.upper() in _NOT_A_FIGURE:
        return None
    if text in _DASHES:
        return Decimal(0)
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative, text = True, text[1:-1]
    elif text.startswith("-"):
        negative, text = True, text[1:]
    if not _AMOUNT.match(text):
        raise ValueError(f"not an amount as printed: {as_filed!r}")
    value = Decimal(text.replace(",", ""))
    return -value if negative else value


_PLAIN = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$")


def parse_workbook_amount(as_filed: str) -> Decimal | None:
    """Return the value of a workbook cell that should hold a figure, or None.

    A workbook cell holds a number as stored (``1408968.8300000001``, ``1.5E-05``) or text a
    person typed. A number or an amount typed as text (``$1,234.50``) has a value. Words
    (``N/A``, ``carved out``), an error (``#DIV/0!``), a lone dash and a blank have none: the
    text is kept as filed beside it. The template's own placeholder is a dash, so a dash is
    not read as zero here.
    """
    text = as_filed.replace("\xa0", "").strip()
    if text.replace(" ", "") in _DASHES:
        return None
    try:
        value = parse_amount(text)
    except ValueError:
        compact = text.replace(" ", "")
        if _PLAIN.match(compact):
            return Decimal(compact)
        return None
    return value


def parse_workbook_count(as_filed: str) -> int | None:
    """Return a prescription count stored in a workbook cell, or None when it holds no count.

    A count is a whole number, stored as digits or typed as text. Anything else (words, an
    error, a fraction, a dash) has no count; the text is kept as filed.
    """
    value = parse_workbook_amount(as_filed)
    if value is None or value != value.to_integral_value():
        return None
    return int(value)


def parse_count(as_filed: str) -> int | None:
    """Return a claim count as printed, or None when the cell is blank."""
    text = as_filed.replace(" ", "").strip()
    if not text:
        return None
    if text in _DASHES:
        return 0
    if not _COUNT.match(text):
        raise ValueError(f"not a count as printed: {as_filed!r}")
    return int(text.replace(",", ""))


def plain(value: Decimal | None) -> str:
    """Write a decimal without exponent notation; blank for None."""
    return "" if value is None else format(value, "f")
