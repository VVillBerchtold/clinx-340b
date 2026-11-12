"""The records the dataset is made of."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum


class RowKind(StrEnum):
    """What a transcribed row is on its schedule."""

    DETAIL = "detail"
    # The form's one line for items each below its listing threshold.
    BELOW_THRESHOLD = "below_threshold"
    TOTAL = "total"


class Verification(StrEnum):
    """How a transcribed row was checked against the filing."""

    # Matches the PDF's own text and an independent read of the page image.
    TEXT_AND_IMAGE = "text_and_image"
    # Scanned page: two independent reads of the page image agree.
    TWO_IMAGE_READS = "two_image_reads"
    # The reads disagreed and a third look at the page image settled it.
    ADJUDICATED = "adjudicated"
    # The page cannot be read with confidence; the value is left blank.
    UNREADABLE = "unreadable"
    # Not yet checked. The build refuses to publish these.
    UNVERIFIED = "unverified"


PUBLISHABLE = frozenset(
    {
        Verification.TEXT_AND_IMAGE,
        Verification.TWO_IMAGE_READS,
        Verification.ADJUDICATED,
        Verification.UNREADABLE,
    }
)


@dataclass(frozen=True, slots=True)
class SourceFile:
    """One archived filing, as retrieved."""

    file_name: str
    source_url: str
    retrieved_at: str
    sha256: str
    size_bytes: int
    page_count: int
    scanned: bool
    # Only some manifests record these (Vermont's): what the document is, and the
    # state's cover page for it. Blank when the manifest has no such column.
    document_kind: str = ""
    cover_page_url: str = ""


@dataclass(frozen=True, slots=True)
class Attachment:
    """Material a filer added to the state form, archived but not transcribed.

    Usually a run of pages inside the filing's own PDF. When ``document`` is set it
    is a separate PDF listed in the same manifest, and the pages are that PDF's.
    """

    first_page: int
    last_page: int
    kind: str
    title_as_filed: str
    note: str
    document: SourceFile | None = None

    def covers(self, page: int) -> bool:
        """Say whether a page of the filing's own PDF is part of this attachment."""
        return self.document is None and self.first_page <= page <= self.last_page


@dataclass(frozen=True, slots=True)
class FilingMeta:
    """A filing's identity and its cover page, as filed."""

    filing_id: str
    entity_id: str
    state: str
    reporting_year: int
    entity_type: str
    source_file: str
    form: str
    form_revision: str
    name_as_filed: str
    corporate_address_as_filed: str
    opais_ids_as_filed: str
    recertification_date_as_filed: str
    reporting_basis_as_filed: str
    attachments: tuple[Attachment, ...] = ()
    # What the page prints about its own status and period (Vermont's pages do;
    # Rhode Island's form does not). Blank when not printed.
    status_as_filed: str = ""
    status_notice_as_filed: str = ""
    period_as_filed: str = ""
    submission_as_filed: str = ""
    # "schedule:line" of rows with a figure the PDF's text layer leaves out.
    text_layer_gaps: frozenset[str] = frozenset()
    # What the record is: an entity's own ``filing``, or a row (``state_report_row``) or the
    # totals (``state_report_totals``) that a State published about entities (Minnesota).
    record_kind: str = "filing"
    # Minnesota's table prints each entity's type and city; kept exactly as printed.
    entity_type_as_filed: str = ""
    city_as_filed: str = ""


@dataclass(frozen=True, slots=True)
class Row:
    """One printed row of one schedule."""

    filing_id: str
    schedule: str
    line: str
    row_kind: RowKind
    label_as_filed: str
    name_as_filed: str
    description_as_filed: str
    ndc_as_filed: str
    amount_as_filed: str
    amount: Decimal | None
    claims_as_filed: str
    claims: int | None
    answer_as_filed: str
    page: int
    verification: Verification
    note: str
    # Why the claim count is not kept in the working files; empty when it is kept.
    claims_withheld: str = ""


class Basis(StrEnum):
    """Why two figures are set side by side."""

    # The form itself says the two figures agree (a total row, "Supports Schedule A, Line 1").
    FORM = "form"
    # The form does not say so. The two figures describe related things and are shown together.
    COMPARISON = "comparison"


@dataclass(frozen=True, slots=True)
class Check:
    """The result of one tie-out rule on one filing."""

    filing_id: str
    rule: str
    basis: Basis
    description: str
    expected: Decimal | None
    filed: Decimal | None
    # The unit both figures are in: "usd", "percent" or "count".
    unit: str = "usd"

    @property
    def applicable(self) -> bool:
        """A rule applies only when the filing prints both sides."""
        return self.expected is not None and self.filed is not None

    @property
    def difference(self) -> Decimal | None:
        """Filed minus expected."""
        if self.expected is None or self.filed is None:
            return None
        return self.filed - self.expected

    @property
    def passed(self) -> bool:
        """True when both sides are printed and equal."""
        return self.applicable and self.difference == 0


@dataclass(frozen=True, slots=True)
class Filing:
    """A filing with its rows."""

    meta: FilingMeta
    source: SourceFile
    rows: tuple[Row, ...]
    # Schedule -> sum of the rows' claim counts, taken from the committed results file
    # when the private counts are not there. Empty otherwise.
    claim_sums: Mapping[str, int] = field(default_factory=dict)
    # (schedule, line) -> the second reader's count text for a withheld row, when the
    # private counts are there.
    held_reads: Mapping[tuple[str, str], str] = field(default_factory=dict)

    def schedule(self, letter: str) -> tuple[Row, ...]:
        """Rows of one schedule, in filed order."""
        return tuple(r for r in self.rows if r.schedule == letter)
