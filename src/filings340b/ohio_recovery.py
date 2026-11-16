"""Try to work out Ohio's withheld prescription counts from what the dataset publishes.

The small-number rule uses this to decide what else to withhold, and ``tests/test_ohio.py``
uses it to check the published files. It plays a reader who has the published line items of
one filing and the template's own arithmetic (a total is the sum of the payer cells, a
percentage is the 340B prescriptions over all prescriptions). For each withheld count it
keeps the set of whole numbers the published figures still allow, and narrows the sets by
each rule until nothing changes. A count whose set has shrunk to one number, or to one of the
small numbers 1 to 5 alone, has been recovered.

A rule that the filing itself does not satisfy is left out: a reader cannot rely on it.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterable
from decimal import Decimal

from filings340b.forms import OH_FRACTION_NOTE, OH_PAYERS, OH_TOTAL
from filings340b.model import Row

PAYERS = tuple(key for key, _ in OH_PAYERS)
SMALL = frozenset(range(1, 6))
MAX_COMBINATIONS = 6000
LARGE_LIMIT = 60

Cell = tuple[str, str]
# A domain is the set of values a cell may still hold; None means any count of 0 or 6 or more.
Domain = frozenset[int] | None


def _allowed(reason: str, value: int) -> bool:
    if reason == "fewer_than_6":
        return value in SMALL
    return value >= 0 and value not in SMALL


def start_domains(rows: list[dict[str, str]]) -> dict[Cell, Domain]:
    """Return what each prescription count cell may hold, as a reader sees it."""
    out: dict[Cell, Domain] = {}
    for row in rows:
        if not row["schedule"].endswith(("_rx_all", "_rx_340b")):
            continue
        cell = (row["schedule"], row["line"])
        if row["claims_withheld"] == "fewer_than_6":
            out[cell] = SMALL
        elif row["claims_withheld"] == "beside_small":
            out[cell] = None
        elif row["claims"] != "":
            out[cell] = frozenset({int(row["claims"])})
    return out


def _sum_equations(
    domains: dict[Cell, Domain],
) -> list[tuple[list[Cell], Cell]]:
    out = []
    for place in ("in_house", "contract", "administered"):
        for measure in ("rx_all", "rx_340b"):
            schedule = f"{place}_{measure}"
            parts = [(schedule, key) for key in PAYERS]
            total = (schedule, OH_TOTAL)
            if total in domains and all(p in domains for p in parts):
                out.append((parts, total))
    return out


def _combinations(domains: list[Domain]) -> list[tuple[int, ...]] | None:
    if any(d is None for d in domains):
        return None
    sizes = 1
    for d in domains:
        sizes *= len(d or ())
    if sizes > MAX_COMBINATIONS:
        return None
    return list(itertools.product(*(sorted(d or ()) for d in domains)))


def _narrow(old: Domain, implied: set[int]) -> Domain:
    """Keep what the rule allows; a large cell becomes a set only when the rule pins it down."""
    implied = {v for v in implied if v >= 0}
    if old is None:
        kept = {v for v in implied if v not in SMALL}
        return frozenset(kept) if len(kept) <= LARGE_LIMIT else None
    kept = implied & set(old)
    return frozenset(kept)


def _apply_sum(
    domains: dict[Cell, Domain], parts: list[Cell], total: Cell
) -> dict[Cell, Domain] | None:
    cells = [*parts, total]
    narrowed: dict[Cell, Domain] = {}
    for cell in cells:
        others = [c for c in cells if c != cell]
        combos = _combinations([domains[c] for c in others])
        if combos is None:
            continue
        implied: set[int] = set()
        for combo in combos:
            values = dict(zip(others, combo, strict=True))
            if cell == total:
                implied.add(sum(values[p] for p in parts))
            else:
                implied.add(values[total] - sum(values[p] for p in parts if p != cell))
        result = _narrow(domains[cell], implied)
        if result is not None and not result:
            return None
        narrowed[cell] = result
    return narrowed


def _close(n: int, d: int, pct: Decimal, scale: int) -> bool:
    return abs(Decimal(n) * scale - pct * d) <= Decimal("0.000001") * max(1, d)


def _ratio_equations(
    rows: list[dict[str, str]],
) -> list[tuple[Cell, Cell, Decimal, int]]:
    out = []
    for row in rows:
        if not row["schedule"].endswith("_rx_pct") or row["amount"] == "":
            continue
        if row["claims_withheld"]:
            continue
        place = row["schedule"].removesuffix("_rx_pct")
        scale = 1 if OH_FRACTION_NOTE in row["note"] else 100
        out.append(
            (
                (f"{place}_rx_340b", row["line"]),
                (f"{place}_rx_all", row["line"]),
                Decimal(row["amount"]),
                scale,
            )
        )
    return out


def _apply_ratio(
    domains: dict[Cell, Domain], numerator: Cell, denominator: Cell, pct: Decimal, scale: int
) -> dict[Cell, Domain] | None:
    top, bottom = domains.get(numerator), domains.get(denominator)
    if numerator not in domains or denominator not in domains:
        return {}
    narrowed: dict[Cell, Domain] = {}
    if bottom is not None and len(bottom) <= LARGE_LIMIT:
        implied = {n for d in bottom for n in _near(pct * d / scale) if _close(n, d, pct, scale)}
        result = _narrow(top, implied)
        if result is not None and not result:
            return None
        narrowed[numerator] = result
    if top is not None and pct != 0 and len(top) <= LARGE_LIMIT:
        implied = {
            d for n in top for d in _near(Decimal(n) * scale / pct) if _close(n, d, pct, scale)
        }
        result = _narrow(bottom, implied)
        if result is not None and not result:
            return None
        narrowed[denominator] = result
    return narrowed


def _near(value: Decimal) -> list[int]:
    base = int(value)
    return [base - 1, base, base + 1, base + 2]


def recover(rows: list[dict[str, str]]) -> dict[Cell, Domain]:
    """Return, for each withheld count cell, the values a reader cannot yet rule out."""
    domains = start_domains(rows)
    sums = _sum_equations(domains)
    ratios = _ratio_equations(rows)
    for _ in range(12):
        changed = False
        for parts, total in sums:
            narrowed = _apply_sum(domains, parts, total)
            if narrowed is None:
                continue
            for cell, domain in narrowed.items():
                if domain != domains[cell]:
                    domains[cell], changed = domain, True
        for numerator, denominator, pct, scale in ratios:
            narrowed = _apply_ratio(domains, numerator, denominator, pct, scale)
            if narrowed is None:
                continue
            for cell, domain in narrowed.items():
                if domain != domains[cell]:
                    domains[cell], changed = domain, True
        if not changed:
            break
    withheld = {
        (row["schedule"], row["line"])
        for row in rows
        if row["claims_withheld"] in {"fewer_than_6", "beside_small"}
    }
    return {cell: domains[cell] for cell in withheld if cell in domains}


def published_view(
    rows: Iterable[Row], withheld: dict[tuple[str, str, str], str]
) -> list[dict[str, str]]:
    """Return the rows as the published line items show them, given what is withheld."""
    out = []
    for row in rows:
        reason = withheld.get((row.filing_id, row.schedule, row.line), "")
        hidden_figure = reason == "reveals_small"
        out.append(
            {
                "schedule": row.schedule,
                "line": row.line,
                "claims": "" if reason or row.claims is None else str(row.claims),
                "claims_withheld": reason,
                "amount": "" if hidden_figure or row.amount is None else format(row.amount, "f"),
                "note": row.note,
            }
        )
    return out


def too_few(rows: list[dict[str, str]]) -> list[Cell]:
    """List the withheld counts that a reader can narrow down to a single number."""
    return sorted(
        cell for cell, domain in recover(rows).items() if domain is not None and len(domain) < 2
    )
