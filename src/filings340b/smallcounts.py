"""The small-number rule for published claim counts.

A detail row whose claim count is 1 to 5 is not republished: its claim fields are
left empty in the published files and ``claims_withheld`` says why. The same cells
are empty in the working files; ``sealing.py`` keeps the counts in a private file, and
the checks and the tie-out rules work on them when that file is there.

The limits are set here and nowhere else.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable

from filings340b.errors import DataError
from filings340b.model import Row, RowKind

# A count from SMALL_LOWEST to SMALL_HIGHEST (both included) is small.
SMALL_LOWEST = 1
SMALL_HIGHEST = 5

# Values of the ``claims_withheld`` column.
FEWER_THAN = f"fewer_than_{SMALL_HIGHEST + 1}"
BESIDE_SMALL = "beside_small"
# A percentage (Ohio's) that, with the counts printed beside it, would give a small count away.
REVEALS_SMALL = "reveals_small"

RowKey = tuple[str, str, str]


def is_small(count: int | None) -> bool:
    """Say whether a claim count is one the rule withholds."""
    return count is not None and SMALL_LOWEST <= count <= SMALL_HIGHEST


def _line_order(line: str) -> tuple[int, int, str]:
    """Order line numbers as a reader does: 2 before 10, numbered lines before the rest."""
    match = re.match(r"(\d+)(.*)", line)
    if match:
        return (0, int(match.group(1)), match.group(2))
    return (1, 0, line)


def withheld_rows(  # noqa: PLR0912
    rows: Iterable[Row], *, lenient: bool = False, apart: Callable[[str], bool] | None = None
) -> dict[RowKey, str]:
    """Return (filing, schedule, line) -> reason for every row whose count is not published.

    Stops with a DataError, naming the filing and schedule, when a total or
    below-threshold row has a small count, or when the subtraction guard needs a
    neighbouring row and the schedule has none.

    ``lenient`` is for a state whose filers fill in the totals themselves (Ohio's):
    a small count on a total row is withheld like any other, and where the guard has no
    neighbouring row to withhold the printed total is withheld in its place. Nothing stops.
    ``apart`` says which lines are not part of the schedule's total (Ohio's "indeterminate"
    column, and a cell a filer typed beside the template's columns): a small count there is
    withheld by itself and takes no part in the guard.
    """
    outside = apart or (lambda _line: False)
    groups: dict[tuple[str, str], list[Row]] = {}
    for row in rows:
        groups.setdefault((row.filing_id, row.schedule), []).append(row)
    out: dict[RowKey, str] = {}
    for (filing_id, schedule), group in groups.items():
        where = f"{filing_id} schedule {schedule}"
        for row in group:
            if row.row_kind is not RowKind.DETAIL and is_small(row.claims):
                if not lenient:
                    raise DataError(
                        f"{where}: a {row.row_kind.value} row has a claim count the small-number "
                        "rule covers; a person must decide how to publish it"
                    )
                out[(filing_id, schedule, row.line)] = FEWER_THAN
        for row in group:
            if outside(row.line) and is_small(row.claims):
                out[(filing_id, schedule, row.line)] = FEWER_THAN
        parts = [r for r in group if not outside(r.line)]
        small = [r for r in parts if r.row_kind is RowKind.DETAIL and is_small(r.claims)]
        if not small:
            continue
        for row in small:
            out[(filing_id, schedule, row.line)] = FEWER_THAN
        k = len(small)
        total = sum(r.claims or 0 for r in small)
        # One small row is always the printed total minus the others; several are
        # when each one is 1 or each one is 5.
        if k == 1 or total == k * SMALL_LOWEST or total == k * SMALL_HIGHEST:
            printed = [
                r
                for r in parts
                if r.row_kind is RowKind.TOTAL
                and r.claims is not None
                and (filing_id, schedule, r.line) not in out
            ]
            if lenient and not printed:
                # No total is published, so nothing can be subtracted from it.
                continue
            neighbours = [
                r
                for r in parts
                if r.row_kind is RowKind.DETAIL
                and r.claims is not None
                and r.claims > SMALL_HIGHEST
            ]
            if neighbours:
                chosen = min(neighbours, key=lambda r: (r.claims or 0, _line_order(r.line)))
                out[(filing_id, schedule, chosen.line)] = BESIDE_SMALL
            elif lenient:
                for row in printed:
                    out[(filing_id, schedule, row.line)] = BESIDE_SMALL
            else:
                raise DataError(
                    f"{where}: the withheld counts could be worked out from the printed total "
                    "and no other row can be withheld beside them; a person must decide"
                )
    return out
