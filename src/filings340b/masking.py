"""Replace e-mail addresses and telephone numbers in text with a marker.

The saved text of a PDF (``tools/extract_text.py``) and the saved cells of a workbook
(``tools/oh_transcribe.py``) never keep a person's e-mail address or telephone number, so
both use the same two patterns. The patterns are the ones ``extract_text.py`` uses; a test
checks that they have not drifted apart.
"""

from __future__ import annotations

import re

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# A North American number: three digits (in brackets or not), three, then four.
PHONE = re.compile(r"(?<![\d-])(?:1[-. ])?\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}(?![\d-])")
EMAIL_MARKER = "[email address in the workbook]"
PHONE_MARKER = "[phone number in the workbook]"


def mask(text: str) -> str:
    """Return the text with every e-mail address and telephone number replaced by its marker."""
    return PHONE.sub(PHONE_MARKER, EMAIL.sub(EMAIL_MARKER, text))
