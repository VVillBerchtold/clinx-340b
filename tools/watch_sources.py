"""Look at the states' source pages and say when a list of reports changed.

In plain words: each state posts its 340B reports on a page of its own. This tool asks for each
page in `watch/sources.csv` once, writes down what it saw in `watch/seen/<key>.json`, and
compares that with the copy saved the time before. It prints what was added, removed or
changed. It never changes the dataset: anything new still has to be read and entered.

How it behaves towards a site:

- It gives its name on every request, `ClinX Open Data Reader`, with the address of the page
  that explains how ClinX reads public files. It never calls itself a browser.
- One request for each page, at least two seconds apart, and one more try after a failure.
- A site's certificate is always checked. Some state servers leave out the intermediate
  certificate that links theirs to a trusted root; `watch/certs/` holds those public
  intermediates so the check can still be made.
- If a site answers with a check for robots, the tool reports that it was turned away and stops
  there for that page.

A page that cannot be read never counts as a change and never erases what was seen before.

Run it:  python3 -I tools/watch_sources.py
Options: --only KEY (one source), --offline FOLDER (read saved pages named by key, for tests),
         --report FILE and --summary FILE (what the daily workflow reads).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CLIENT = "ClinX Open Data Reader (+https://clinx.org/methods/)"
PAUSE_SECONDS = 2.0
TIMEOUT_SECONDS = 45
HOWS = ("links", "text", "ohio-collection", "file")
UNREADABLE_DAYS_BEFORE_AN_ISSUE = 3
SHOWN_AT_MOST = 40

Seen = dict[str, Any]


@dataclass(frozen=True)
class Source:
    """One row of watch/sources.csv: a page to look at and how to read it."""

    key: str
    state: str
    what: str
    url: str
    how: str
    pattern: str


@dataclass(frozen=True)
class Answer:
    """What came back for one request: the status, the headers in lower case, the bytes."""

    status: int
    headers: dict[str, str]
    body: bytes


class NotReadError(Exception):
    """The page could not be read. The message says why, in plain words."""


def read_sources(path: Path) -> list[Source]:
    """Read the hand-kept list of pages, and stop with a plain message if a row is wrong."""
    sources: list[Source] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for number, row in enumerate(csv.DictReader(handle), start=2):
            source = Source(
                key=(row.get("key") or "").strip(),
                state=(row.get("state") or "").strip(),
                what=(row.get("what") or "").strip(),
                url=(row.get("url") or "").strip(),
                how=(row.get("how") or "").strip(),
                pattern=row.get("pattern") or "",
            )
            if not re.fullmatch(r"[a-z0-9-]+", source.key):
                raise SystemExit(f"{path.name} line {number}: the key must be lower-case words")
            if source.how not in HOWS:
                raise SystemExit(f"{path.name} line {number}: how must be one of {', '.join(HOWS)}")
            if not source.url.startswith("https://"):
                raise SystemExit(f"{path.name} line {number}: the address must start with https://")
            if any(other.key == source.key for other in sources):
                raise SystemExit(f"{path.name} line {number}: the key {source.key} is used twice")
            sources.append(source)
    return sources


# ---------------------------------------------------------------- asking a site for a page


def make_context(certs: Path) -> ssl.SSLContext:
    """Build the usual checks, plus any public intermediate certificates kept in watch/certs/."""
    context = ssl.create_default_context()
    if certs.is_dir():
        for extra in sorted(certs.iterdir()):
            if extra.suffix.lower() in {".pem", ".crt", ".cer"}:
                context.load_verify_locations(cafile=str(extra))
    return context


def ask(url: str, context: ssl.SSLContext) -> Answer:
    """Ask for one address once, under the tool's own name. Only https addresses are asked for."""
    if not url.startswith("https://"):
        raise NotReadError("the address does not start with https://")
    request = urllib.request.Request(url, headers={"User-Agent": CLIENT, "Accept": "*/*"})  # noqa: S310
    try:
        with urllib.request.urlopen(  # noqa: S310
            request, timeout=TIMEOUT_SECONDS, context=context
        ) as reply:
            headers = {name.lower(): value for name, value in reply.headers.items()}
            return Answer(reply.status, headers, reply.read())
    except urllib.error.HTTPError as error:
        headers = {name.lower(): value for name, value in error.headers.items()}
        return Answer(error.code, headers, error.read())


def turned_away(answer: Answer) -> bool:
    """Say whether the answer is a check for robots. The tool never answers one."""
    if answer.headers.get("cf-mitigated", "").lower() == "challenge":
        return True
    if answer.status in (403, 429, 503):
        start = answer.body[:4000].decode("utf-8", "replace").lower()
        return any(sign in start for sign in ("captcha", "just a moment", "are you a robot"))
    return False


class Fetcher:
    """Reads a page from the site, or from a folder of saved pages when testing."""

    def __init__(
        self, certs: Path, offline: Path | None = None, pause: float = PAUSE_SECONDS
    ) -> None:
        """Read from the sites, or from `offline`, a folder of saved pages named by key."""
        self.offline = offline
        self.pause = pause
        self.context = None if offline else make_context(certs)
        self.asked_before = False

    def get(self, key: str, url: str, part: int | None = None) -> bytes:
        """Give the bytes of one page, or raise NotReadError saying why it could not be read."""
        if self.offline is not None:
            name = key if part is None else f"{key}.{part}"
            found = sorted(self.offline.glob(f"{name}.*"))
            found = [path for path in found if path.stem == name]
            if not found:
                raise NotReadError("no saved page for it in the offline folder")
            return found[0].read_bytes()
        if self.context is None:
            raise NotReadError("no way to reach the site was set up")
        last = "no answer"
        for attempt in (1, 2):
            if self.asked_before:
                time.sleep(self.pause if attempt == 1 else self.pause * 3)
            self.asked_before = True
            try:
                answer = ask(url, self.context)
            except ssl.SSLCertVerificationError as error:
                raise NotReadError(
                    f"the site's certificate could not be checked ({error.reason})"
                ) from error
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as error:
                last = f"no answer ({type(error).__name__})"
                continue
            if turned_away(answer):
                raise NotReadError("the site turned us away with a check for robots; left alone")
            if answer.status == 200:
                return answer.body
            last = f"the site answered {answer.status}"
            if answer.status < 500:
                break
        raise NotReadError(last)


# ---------------------------------------------------------------- what is on a page


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[tuple[str, str]] = []
        self._href: str | None = None
        self._words: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._close()
            self._href = dict(attrs).get("href")
            self._words = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._close()

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._words.append(data)

    def _close(self) -> None:
        if self._href:
            self.found.append((self._href, " ".join("".join(self._words).split())))
        self._href = None
        self._words = []


class _Text(HTMLParser):
    SKIP = frozenset({"script", "style", "noscript", "template"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.words: list[str] = []
        self._skipping = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP:
            self._skipping += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self._skipping:
            self._skipping -= 1

    def handle_data(self, data: str) -> None:
        if not self._skipping:
            self.words.append(data)


def _page(body: bytes) -> str:
    return body.decode("utf-8", "replace")


def see_links(body: bytes, base: str, pattern: str) -> Seen:
    """Collect the links whose address matches the pattern: each address once, with its text."""
    parser = _Links()
    parser.feed(_page(body))
    wanted = re.compile(pattern, re.IGNORECASE)
    texts: dict[str, set[str]] = {}
    for href, words in parser.found:
        address = urllib.parse.urldefrag(urllib.parse.urljoin(base, href.strip())).url
        if wanted.search(address):
            texts.setdefault(address, set()).update({words} if words else set())
    if not texts:
        raise NotReadError("the page was read but holds no link of the kind watched")
    links = [
        {"address": address, "text": " | ".join(sorted(texts[address]))}
        for address in sorted(texts)
    ]
    return {"links": links}


def see_text(body: bytes, pattern: str) -> Seen:
    """Take the words between two markers, written `start~~end`. The last start is used."""
    start, _, end = pattern.partition("~~")
    parser = _Text()
    parser.feed(_page(body))
    words = " ".join(" ".join(parser.words).split())
    begin = words.rfind(start)
    if not start or begin < 0:
        raise NotReadError("the part of the page that is watched was not found")
    begin += len(start)
    finish = words.find(end, begin) if end else len(words)
    if finish < 0:
        raise NotReadError("the end of the part that is watched was not found")
    return {"text": words[begin:finish].strip()}


def see_ohio_collection(fetcher: Fetcher, source: Source) -> Seen:
    """Read Ohio's public collection, which answers its list in pages.

    Each file is noted by name, size, version and upload time. Nothing about who keeps the
    collection is kept.
    """
    files: list[dict[str, Any]] = []
    cursor: str | None = None
    for part in range(1, 60):
        url = source.url + (f"&next_cursor={urllib.parse.quote(cursor)}" if cursor else "")
        try:
            data = json.loads(fetcher.get(source.key, url, part))
            for asset in data["assets"]:
                files.append({
                    "name": str(asset["display_name"]),
                    "bytes": int(asset["bytes"]),
                    "version": str(asset["version"]),
                    "uploaded": str(asset["uploaded_at"]),
                })  # fmt: skip
            total = int(data["total_count"])
            cursor = data.get("next_cursor")
        except (ValueError, KeyError, TypeError) as error:
            raise NotReadError(
                f"the list did not have the expected shape ({type(error).__name__})"
            ) from error
        if not cursor:
            break
    else:
        raise NotReadError("the list did not end after 59 pages")
    if len(files) != total:
        raise NotReadError(f"the list says {total} files and gave {len(files)}")
    files.sort(key=lambda item: (item["name"], item["version"]))
    return {"files": files}


def see_file(body: bytes) -> Seen:
    """Note one file by its size and its SHA-256."""
    return {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}


def look(fetcher: Fetcher, source: Source) -> Seen:
    """Read one source in the way its row says."""
    if source.how == "ohio-collection":
        return see_ohio_collection(fetcher, source)
    body = fetcher.get(source.key, source.url)
    if source.how == "links":
        return see_links(body, source.url, source.pattern)
    if source.how == "text":
        return see_text(body, source.pattern)
    return see_file(body)


# ---------------------------------------------------------------- comparing with last time


def _clip(lines: list[str]) -> list[str]:
    if len(lines) <= SHOWN_AT_MOST:
        return lines
    return [*lines[:SHOWN_AT_MOST], f"... and {len(lines) - SHOWN_AT_MOST} more"]


def differences(how: str, before: Seen, after: Seen) -> list[str]:
    """List, in plain lines, what is different. An empty list means nothing changed."""
    if before == after:
        return []
    if how == "links":
        old = {item["address"]: item["text"] for item in before.get("links", [])}
        new = {item["address"]: item["text"] for item in after.get("links", [])}
        lines = [
            f"Added: {address} ({new[address]})" for address in sorted(new.keys() - old.keys())
        ]
        lines += [
            f"Removed: {address} ({old[address]})" for address in sorted(old.keys() - new.keys())
        ]
        lines += [
            f'Link text changed: {address} (was "{old[address]}", now "{new[address]}")'
            for address in sorted(new.keys() & old.keys())
            if new[address] != old[address]
        ]
        return _clip(lines)
    if how == "ohio-collection":
        old_files = {item["name"]: item for item in before.get("files", [])}
        new_files = {item["name"]: item for item in after.get("files", [])}
        lines = [
            f"Added: {name} ({new_files[name]['bytes']} bytes, "
            f"uploaded {new_files[name]['uploaded']})"
            for name in sorted(new_files.keys() - old_files.keys())
        ]
        lines += [f"Removed: {name}" for name in sorted(old_files.keys() - new_files.keys())]
        lines += [
            f"Replaced: {name} (was {old_files[name]['bytes']} bytes, uploaded "
            f"{old_files[name]['uploaded']}; now {new_files[name]['bytes']} bytes, uploaded "
            f"{new_files[name]['uploaded']})"
            for name in sorted(new_files.keys() & old_files.keys())
            if new_files[name] != old_files[name]
        ]
        count = f"The list held {len(old_files)} files and now holds {len(new_files)}."
        return [count, *_clip(lines)]
    if how == "text":
        return [f"Was: {before.get('text', '')[:700]}", f"Now: {after.get('text', '')[:700]}"]
    return [
        f"Was: {before.get('bytes')} bytes, SHA-256 {before.get('sha256')}",
        f"Now: {after.get('bytes')} bytes, SHA-256 {after.get('sha256')}",
    ]


def saved_form(source: Source, seen: Seen) -> str:
    """Write the saved copy: the same bytes whenever the page is the same. No times, no dates."""
    record = {
        "key": source.key,
        "state": source.state,
        "what": source.what,
        "address": source.url,
        "how": source.how,
        "seen": seen,
    }
    return json.dumps(record, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


# ---------------------------------------------------------------- one run


def run(
    sources: list[Source],
    fetcher: Fetcher,
    seen_dir: Path,
    days_file: Path,
    today: str,
) -> dict[str, Any]:
    """Look at each source once and say what changed, what is new and what could not be read."""
    seen_dir.mkdir(parents=True, exist_ok=True)
    days: dict[str, dict[str, Any]] = (
        json.loads(days_file.read_text()) if days_file.exists() else {}
    )
    lines: list[str] = []
    changed: list[str] = []
    first: list[str] = []
    unreadable: list[dict[str, str]] = []
    issues: list[dict[str, str]] = []
    newly_stuck: list[str] = []

    for source in sources:
        target = seen_dir / f"{source.key}.json"
        try:
            seen = look(fetcher, source)
        except NotReadError as problem:
            unreadable.append({"key": source.key, "why": str(problem)})
            lines.append(f"COULD NOT BE READ  {source.key} ({source.state}): {problem}")
            entry = days.get(source.key, {"days": 0, "last": ""})
            if entry["last"] != today:
                entry = {"days": int(entry["days"]) + 1, "last": today, "why": str(problem)}
                if entry["days"] == UNREADABLE_DAYS_BEFORE_AN_ISSUE:
                    newly_stuck.append(source.key)
            days[source.key] = entry
            continue
        days.pop(source.key, None)
        if not target.exists():
            first.append(source.key)
            lines.append(f"FIRST LOOK         {source.key} ({source.state}): saved")
            target.write_text(saved_form(source, seen), encoding="utf-8")
            continue
        before: Seen = json.loads(target.read_text(encoding="utf-8")).get("seen", {})
        found = differences(source.how, before, seen)
        if not found:
            lines.append(f"unchanged          {source.key} ({source.state})")
            continue
        changed.append(source.key)
        lines.append(f"CHANGED            {source.key} ({source.state}): {source.what}")
        lines += [f"    {line}" for line in found]
        target.write_text(saved_form(source, seen), encoding="utf-8")
        body = "\n".join([
            f"The daily watch saw a change on {source.what}.",
            "",
            f"Page: {source.url}",
            "",
            *[f"- {line}" for line in found],
            "",
            "The watch changed nothing in the dataset. Anything new still has to be read and entered.",
        ])  # fmt: skip
        issues.append({"title": f"{source.state}: {source.what} changed", "body": body})

    if days or days_file.exists():
        days_file.write_text(json.dumps(days, indent=1, sort_keys=True) + "\n", encoding="utf-8")

    unreadable_issue = None
    if newly_stuck:
        rows = [f"- `{key}`: {days[key]['why']}" for key in newly_stuck]
        unreadable_issue = {
            "title": "Watch: a source page could not be read three days running",
            "body": "\n".join(
                ["The daily watch could not read:", "", *rows, "", "Nothing saved was changed."]
            ),
        }
    return {
        "changed": changed,
        "first": first,
        "unreadable": unreadable,
        "issues": issues,
        "unreadable_issue": unreadable_issue,
        "report": "\n".join(lines) + "\n",
    }


def main(argv: list[str] | None = None) -> int:
    """Look at every source, print what was found, and write the files the workflow reads."""
    parser = argparse.ArgumentParser(description="Look at the states' source pages.")
    parser.add_argument("--sources", type=Path, default=ROOT / "watch" / "sources.csv")
    parser.add_argument("--seen", type=Path, default=ROOT / "watch" / "seen")
    parser.add_argument("--days", type=Path, default=ROOT / "watch" / "unreadable-days.json")
    parser.add_argument("--certs", type=Path, default=ROOT / "watch" / "certs")
    parser.add_argument("--offline", type=Path, default=None)
    parser.add_argument("--only", default=None)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--summary", type=Path, default=None)
    args = parser.parse_args(argv)

    sources = read_sources(args.sources)
    if args.only:
        sources = [source for source in sources if source.key == args.only]
        if not sources:
            raise SystemExit(f"no source is named {args.only}")
    fetcher = Fetcher(args.certs, offline=args.offline)
    today = datetime.now(UTC).date().isoformat()
    result = run(sources, fetcher, args.seen, args.days, today)
    report = str(result.pop("report"))
    sys.stdout.write(report)
    if args.report:
        args.report.write_text(report, encoding="utf-8")
    if args.summary:
        args.summary.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
