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
