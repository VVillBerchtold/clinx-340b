"""The daily watch on the states' source pages (tools/watch_sources.py), tested without the network.

Every page here is invented for the test. The saved copies under watch/seen/ are checked too:
each must be exactly what the tool would write, so a hand edit is caught.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "watch_sources", ROOT / "tools" / "watch_sources.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["watch_sources"] = module
    spec.loader.exec_module(module)
    return module


watch = _load()

PAGE = """<html><head><style>a { color: red }</style><script>var x = "report.pdf";</script></head>
<body><nav><a href="/about.html">About</a></nav>
<h2>Reports</h2>
<a href="docs/2025report.pdf">Report for 2025 (PDF)</a>
<a href="/data/docs/2024report.pdf#page=2">Report for
   2024 (PDF)</a>
<h2>Coming</h2><p>Coming   soon!</p><h2>Other things</h2><p>Not watched.</p>
</body></html>"""


def _source(key: str, how: str, pattern: str = "") -> object:
    return watch.Source(
        key, "Testland", "the test page", "https://example.gov/data/list.html", how, pattern
    )


def _setup(tmp_path: Path, pages: dict[str, bytes]) -> tuple[Path, Path, Path]:
    offline = tmp_path / "offline"
    offline.mkdir(exist_ok=True)
    for name, body in pages.items():
        (offline / name).write_bytes(body)
    return offline, tmp_path / "seen", tmp_path / "days.json"


def _run(
    sources: list[object], offline: Path, seen: Path, days: Path, today: str = "2026-11-16"
) -> dict[str, Any]:
    result: dict[str, Any] = watch.run(
        sources, watch.Fetcher(ROOT / "watch" / "certs", offline=offline), seen, days, today
    )
    return result


def test_links_are_resolved_filtered_and_sorted() -> None:
    seen = watch.see_links(PAGE.encode(), "https://example.gov/data/list.html", r"\.pdf$")
    assert seen == {
        "links": [
            {
                "address": "https://example.gov/data/docs/2024report.pdf",
                "text": "Report for 2024 (PDF)",
            },
            {
                "address": "https://example.gov/data/docs/2025report.pdf",
                "text": "Report for 2025 (PDF)",
            },
        ]
    }


def test_a_page_with_no_watched_link_is_not_read() -> None:
    with pytest.raises(watch.NotReadError):
        watch.see_links(
            b"<html><body><a href='/x.html'>x</a></body></html>", "https://example.gov/", r"\.pdf$"
        )


def test_text_between_two_markers() -> None:
    assert watch.see_text(PAGE.encode(), "Coming~~Other things") == {"text": "soon!"}
    with pytest.raises(watch.NotReadError):
        watch.see_text(PAGE.encode(), "No such heading~~Other things")


def test_first_look_then_unchanged_gives_the_same_bytes(tmp_path: Path) -> None:
    offline, seen, days = _setup(tmp_path, {"t-links.html": PAGE.encode()})
    sources = [_source("t-links", "links", r"\.pdf$")]
    first = _run(sources, offline, seen, days)
    assert first["first"] == ["t-links"] and first["changed"] == [] and first["issues"] == []
    saved = (seen / "t-links.json").read_bytes()
    second = _run(sources, offline, seen, days)
    assert second["first"] == [] and second["changed"] == [] and second["unreadable"] == []
    assert (seen / "t-links.json").read_bytes() == saved
    assert b"2026" not in saved.replace(b"2025report", b"").replace(b"2024report", b"").replace(
        b"2024 (", b""
    )


def test_a_new_link_and_a_removed_link_are_reported(tmp_path: Path) -> None:
    offline, seen, days = _setup(tmp_path, {"t-links.html": PAGE.encode()})
    sources = [_source("t-links", "links", r"\.pdf$")]
    _run(sources, offline, seen, days)
    later = PAGE.replace("docs/2025report.pdf", "docs/2026report.pdf").replace(
        "for 2025", "for 2026"
    )
    (offline / "t-links.html").write_text(later)
    result = _run(sources, offline, seen, days)
    assert result["changed"] == ["t-links"]
    body = result["issues"][0]["body"]
    assert "Added: https://example.gov/data/docs/2026report.pdf" in body
    assert "Removed: https://example.gov/data/docs/2025report.pdf" in body
    assert result["issues"][0]["title"] == "Testland: the test page changed"


def test_changed_words_are_reported(tmp_path: Path) -> None:
    offline, seen, days = _setup(tmp_path, {"t-text.html": PAGE.encode()})
    sources = [_source("t-text", "text", "Coming~~Other things")]
    _run(sources, offline, seen, days)
    (offline / "t-text.html").write_text(
        PAGE.replace("Coming   soon!", "Report for 2025 is posted.")
    )
    result = _run(sources, offline, seen, days)
    assert (
        "Was: soon!" in result["report"] and "Now: Report for 2025 is posted." in result["report"]
    )


def test_a_replaced_file_is_reported_by_size_and_sum(tmp_path: Path) -> None:
    offline, seen, days = _setup(tmp_path, {"t-file.bin": b"first"})
    sources = [_source("t-file", "file")]
    _run(sources, offline, seen, days)
    (offline / "t-file.bin").write_bytes(b"second!")
    result = _run(sources, offline, seen, days)
    assert result["changed"] == ["t-file"]
    assert "Was: 5 bytes" in result["report"] and "Now: 7 bytes" in result["report"]


def _ohio_page(files: list[tuple[str, int]], cursor: str | None, total: int) -> bytes:
    assets = [
        {
            "display_name": name,
            "bytes": size,
            "version": 1,
            "uploaded_at": "2026-10-01T00:00:00Z",
            "owner": "x",
        }
        for name, size in files
    ]
    return json.dumps({"assets": assets, "next_cursor": cursor, "total_count": total}).encode()


def test_ohio_list_is_read_in_pages_and_keeps_no_owner(tmp_path: Path) -> None:
    pages = {
        "t-oh.1.json": _ohio_page([("B2", 20), ("A1", 10)], "next", 3),
        "t-oh.2.json": _ohio_page([("C3", 30)], None, 3),
    }
    offline, seen, days = _setup(tmp_path, pages)
    sources = [_source("t-oh", "ohio-collection")]
    _run(sources, offline, seen, days)
    saved = json.loads((seen / "t-oh.json").read_text())
    assert [item["name"] for item in saved["seen"]["files"]] == ["A1", "B2", "C3"]
    assert "owner" not in (seen / "t-oh.json").read_text()
    (offline / "t-oh.2.json").write_bytes(_ohio_page([("C3", 31), ("D4", 40)], None, 4))
    result = _run(sources, offline, seen, days)
    assert "The list held 3 files and now holds 4." in result["report"]
    assert (
        "Added: D4 (40 bytes" in result["report"]
        and "Replaced: C3 (was 30 bytes" in result["report"]
    )


def test_a_list_that_gives_fewer_files_than_it_says_is_not_read(tmp_path: Path) -> None:
    offline, seen, days = _setup(tmp_path, {"t-oh.1.json": _ohio_page([("A1", 10)], None, 2)})
    result = _run([_source("t-oh", "ohio-collection")], offline, seen, days)
    assert result["unreadable"][0]["key"] == "t-oh" and not (seen / "t-oh.json").exists()


def test_an_unreadable_page_keeps_the_saved_copy_and_is_raised_on_the_third_day(
    tmp_path: Path,
) -> None:
    offline, seen, days = _setup(tmp_path, {"t-links.html": PAGE.encode()})
    sources = [_source("t-links", "links", r"\.pdf$")]
    _run(sources, offline, seen, days)
    saved = (seen / "t-links.json").read_bytes()
    (offline / "t-links.html").unlink()
    one = _run(sources, offline, seen, days, "2026-11-17")
    again = _run(sources, offline, seen, days, "2026-11-17")
    two = _run(sources, offline, seen, days, "2026-11-18")
    three = _run(sources, offline, seen, days, "2026-11-19")
    four = _run(sources, offline, seen, days, "2026-11-20")
    assert (seen / "t-links.json").read_bytes() == saved
    assert all(r["changed"] == [] and r["issues"] == [] for r in (one, again, two, three, four))
    assert [r["unreadable_issue"] is not None for r in (one, again, two, three, four)] == [
        False, False, False, True, False,
    ]  # fmt: skip
    (offline / "t-links.html").write_text(PAGE)
    _run(sources, offline, seen, days, "2026-11-21")
    assert json.loads(days.read_text()) == {}


def test_a_check_for_robots_is_recognised_and_an_ordinary_refusal_is_not() -> None:
    assert watch.turned_away(watch.Answer(403, {"cf-mitigated": "challenge"}, b""))
    assert watch.turned_away(watch.Answer(503, {}, b"<title>Just a moment...</title>"))
    assert not watch.turned_away(watch.Answer(403, {}, b"<h1>Forbidden</h1>"))
    assert not watch.turned_away(watch.Answer(200, {}, b"a page about captcha rules"))


def test_the_tool_names_itself_and_never_as_a_browser() -> None:
    assert watch.CLIENT == "ClinX Open Data Reader (+https://clinx.org/methods/)"
    code = (ROOT / "tools" / "watch_sources.py").read_text()
    assert "Mozilla" not in code and "verify_mode" not in code and "CERT_NONE" not in code


def test_no_tool_in_the_repository_calls_itself_a_browser() -> None:
    for path in sorted((ROOT / "tools").glob("*.py")):
        assert "Mozilla" not in path.read_text(), f"{path.name} names a browser"
    law_tool = (ROOT / "tools" / "save_law_text.py").read_text()
    assert f'CLIENT = "{watch.CLIENT}"' in law_tool


def test_the_sources_list_and_the_saved_copies_agree() -> None:
    sources = watch.read_sources(ROOT / "watch" / "sources.csv")
    assert len(sources) >= 8
    for source in sources:
        path = ROOT / "watch" / "seen" / f"{source.key}.json"
        assert path.exists(), f"no saved copy for {source.key}"
        record = json.loads(path.read_text())
        assert record["address"] == source.url and record["how"] == source.how
        assert path.read_text() == watch.saved_form(source, record["seen"])
