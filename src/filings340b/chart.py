"""Draw the one chart the repository shows: the external share of margin, per filing.

The chart is written as plain SVG text from the same tables the dataset
publishes, so it rebuilds byte for byte and can never drift from the data.
Filings are listed alphabetically inside their peer group; nothing is ranked.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from xml.sax.saxutils import escape

GROUPS = (("health_center", "Health centers"), ("hospital", "Hospitals"))

WIDTH = 860
LABEL_X = 0
BAR_X = 350
BAR_WIDTH = 420  # the length of a bar at AXIS_MAX
AXIS_MAX = Decimal("0.5")
ROW = 30
BAR_HEIGHT = 16
RADIUS = 4
FONT = "system-ui, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"


@dataclass(frozen=True, slots=True)
class Theme:
    """The colors of one rendering of the chart."""

    name: str
    text: str
    muted: str
    grid: str
    bar: str


THEMES = (
    Theme("light", "#0b0b0b", "#52514e", "#e3e2de", "#2a78d6"),
    Theme("dark", "#f0efec", "#c3c2b7", "#3a3a37", "#3987e5"),
)


@dataclass(frozen=True, slots=True)
class Bar:
    """One filing's bar."""

    group: str
    name_as_filed: str
    share: Decimal | None


def percent(share: Decimal) -> str:
    """Write a share as a percentage with one decimal place."""
    return f"{(share * 100).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}%"


def _bar_path(x: int, y: int, length: Decimal) -> str:
    """Return a bar that is square at the baseline and rounded at its data end."""
    w = max(length, Decimal(RADIUS)).quantize(Decimal("0.1"))
    r, h = RADIUS, BAR_HEIGHT
    return f"M{x} {y}h{w - r}a{r} {r} 0 0 1 {r} {r}v{h - 2 * r}a{r} {r} 0 0 1 -{r} {r}h-{w - r}z"


def _text(x: object, y: object, body: str, fill: str, extra: str = "") -> str:
    return f'<text x="{x}" y="{y}" fill="{fill}"{extra}>{escape(body)}</text>'


def render(bars: list[Bar], theme: Theme) -> str:
    """Return the chart as SVG text in one theme."""
    lines: list[str] = []
    y = 8
    ticks = [Decimal(n) / 10 for n in range(6)]
    body: list[str] = []
    for key, heading in GROUPS:
        members = sorted(
            (b for b in bars if b.group == key), key=lambda b: b.name_as_filed.casefold()
        )
        if not members:
            continue
        y += 22
        body.append(_text(LABEL_X, y, heading, theme.text, ' font-weight="600"'))
        y += 10
        for bar in members:
            middle = y + ROW // 2
            body.append(_text(LABEL_X, middle + 4, bar.name_as_filed, theme.muted))
            if bar.share is None:
                body.append(_text(BAR_X, middle + 4, "not calculated", theme.muted))
            else:
                length = min(bar.share, AXIS_MAX) / AXIS_MAX * BAR_WIDTH
                top = middle - BAR_HEIGHT // 2
                body.append(f'<path d="{_bar_path(BAR_X, top, length)}" fill="{theme.bar}"/>')
                tip = (Decimal(BAR_X) + max(length, Decimal(RADIUS)) + 8).quantize(Decimal("0.1"))
                body.append(_text(tip, middle + 4, percent(bar.share), theme.text))
            y += ROW
        y += 6
    axis_y = y + 6
    for tick in ticks:
        x = BAR_X + int(tick / AXIS_MAX * BAR_WIDTH)
        lines.append(f'<path d="M{x} 36V{axis_y}" stroke="{theme.grid}" stroke-width="1"/>')
        lines.append(
            _text(
                x,
                axis_y + 16,
                percent(tick).replace(".0", ""),
                theme.muted,
                ' text-anchor="middle"',
            )
        )
    height = axis_y + 28
    head = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {height}" '
        f'width="{WIDTH}" height="{height}" role="img" aria-labelledby="t d" '
        f'font-family="{FONT}" font-size="13">'
    )
    title = (
        '<title id="t">External share of margin, Rhode Island 340B filings, 2025</title>'
        '<desc id="d">For each filing: Schedule A lines 3 and 4 added together, divided by '
        "line 2 minus line 1. Listed alphabetically within health centers and hospitals.</desc>"
    )
    return "\n".join([head, title, *lines, *body, "</svg>"]) + "\n"


def charts(bars: list[Bar]) -> dict[str, bytes]:
    """Return the chart files, keyed by file name."""
    return {
        f"external-share-{theme.name}.svg": render(bars, theme).encode("utf-8") for theme in THEMES
    }
