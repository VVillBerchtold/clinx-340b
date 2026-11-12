"""The error every check in the package raises when the data break a rule."""

from __future__ import annotations


class DataError(ValueError):
    """A source or transcription file does not meet the dataset's rules."""
