"""State laws that name the 340B program: check the hand-kept table and build its files.

``laws/laws.csv`` is kept by hand, one row for each enacted law. A row names the
legislature's own page for the law and carries one sentence copied from that page.
The text of the page, as saved on the day it was read, sits under ``sources/laws/``.
A row may name a second official page (the bill's history page, say); its text is
saved beside the first.

A row is published only when all of this holds:

* each saved text is the file the row names, byte for byte (its SHA-256 is in the row);
* the first saved text names the 340B program, or cites its section of federal law;
* the row's sentence is in that text word for word, and itself names the program;
* a signing date or an effective date in the row is printed in one of the saved texts;
* each page is on a site listed in ``laws/hosts.csv`` for that state: a legislature,
  a state code publisher or another state office, never a third party's copy.

So a law is never in the table on someone's say-so: the words are on the official page.
``laws/not-listed.csv`` names what was read and left out, and why.
"""

from __future__ import annotations

import csv
import hashlib
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from filings340b.errors import DataError

Table = list[dict[str, str]]

LAWS_FILE = Path("laws") / "laws.csv"
KINDS_FILE = Path("laws") / "kinds.csv"
HOSTS_FILE = Path("laws") / "hosts.csv"
NOT_LISTED_FILE = Path("laws") / "not-listed.csv"
TEXT_FOLDER = Path("sources") / "laws"

# The columns of laws/laws.csv, in order. The published CSV has the same columns.
COLUMNS = [
    "law_id",
    "state",
    "kinds",
    "title",
    "citation",
    "bill",
    "session_year",
    "act",
    "signed_date",
    "effective_date",
    "binds",
    "summary",
    "limits",
    "enforcement",
    "quote",
    "source_url",
    "source_form",
    "source_text",
    "source_sha256",
    "more_url",
    "more_text",
    "more_sha256",
    "source_note",
    "retrieved",
]
KIND_COLUMNS = ["kind", "label", "description"]
HOST_COLUMNS = ["host", "state", "owner"]
NOT_LISTED_COLUMNS = ["state", "name", "reason", "source_url"]

_MONTH_LIST = (
    "january february march april may june july august september october november december"
)

# The fifty states and the District of Columbia, by postal abbreviation.
_STATE_LIST = (
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT "
    "NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY"
)
STATES = frozenset(_STATE_LIST.split())

# How the saved text was made from the official page.
SOURCE_FORMS = frozenset({"web page", "pdf", "scanned pdf"})

# The program by name ("340B", "340(b)") or by its section of federal law (42 U.S.C. 256b).
NAMES_PROGRAM = re.compile(r"340\s?\(?[Bb]\)?(?![0-9A-Za-z])|256b")

LAW_ID = re.compile(r"^[a-z]{2}-\d{4}-[a-z0-9]+(?:-[a-z0-9]+)*$")
SHORTEST_QUOTE = 20
FIRST_YEAR = 1992  # the year the federal program began

# Words a summary does not use. The table says what a law's text says, and no more.
JUDGEMENT = re.compile(
    r"\b(error|mistake|wrong|incorrect|fail\w*|should have|because|misstate\w*|overstate\w*"
    r"|understate\w*)\b",
    re.IGNORECASE,
)

_MONTHS = _MONTH_LIST.split()


def _read(path: Path, columns: list[str]) -> Table:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != columns:
            raise DataError(f"{path}: the columns are not {', '.join(columns)}")
        return list(reader)


def _one_space(text: str) -> str:
    return " ".join(text.split())


def _a_date(value: str, where: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise DataError(f"{where}: {value!r} is not a date written YYYY-MM-DD") from error


def date_forms(day: date) -> list[str]:
    """Return the ways an official page prints a date, in lower case."""
    month = _MONTHS[day.month - 1]
    short = "sept" if month == "september" else month[:3]
    y, m, d = day.year, day.month, day.day
    nth = f"{d}{'th' if 11 <= d <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(d % 10, 'th')}"
    return [
        f"{nth} day of {month}, {y}",
        f"{nth} day of {month} {y}",
        f"{month} {d}, {y}",
        f"{month} {d:02d}, {y}",
        f"{month} {d} {y}",
        f"{d} {month} {y}",
        f"{month[:3]} {d}, {y}",
        f"{month[:3]}. {d}, {y}",
        f"{short}. {d}, {y}",
        f"{d} {month[:3]} {y}",
        f"{m}/{d}/{y}",
        f"{m:02d}/{d:02d}/{y}",
        f"{m}/{d}/{y % 100:02d}",
        f"{m:02d}/{d:02d}/{y % 100:02d}",
        f"{m}-{d}-{y % 100:02d}",
        f"{m:02d}-{d:02d}-{y}",
        f"{m}-{d}-{y}",
        day.isoformat(),
    ]


def load_kinds(root: Path) -> Table:
    """Return the kinds of law the table sorts laws into, in the order they are listed."""
    kinds = _read(root / KINDS_FILE, KIND_COLUMNS)
    names = [k["kind"] for k in kinds]
    if len(set(names)) != len(names):
        raise DataError(f"{KINDS_FILE}: a kind is listed twice")
    for kind in kinds:
        if not kind["label"] or not kind["description"]:
            raise DataError(f"{KINDS_FILE}: {kind['kind']} needs a label and a description")
    return kinds


def load_hosts(root: Path) -> dict[str, set[str]]:
    """Return, for each official site, the states whose laws may cite it."""
    hosts: dict[str, set[str]] = {}
    for row in _read(root / HOSTS_FILE, HOST_COLUMNS):
        if row["state"] not in STATES:
            raise DataError(f"{HOSTS_FILE}: {row['state']!r} is not a state")
        if not row["host"] or row["host"] != row["host"].lower() or not row["owner"]:
            raise DataError(f"{HOSTS_FILE}: {row['host']!r} needs a lower-case host and an owner")
        hosts.setdefault(row["host"], set()).add(row["state"])
    return hosts


def _check_address(where: str, url: str, state: str, hosts: dict[str, set[str]]) -> None:
    if not url.startswith("https://"):
        raise DataError(f"{where}: {url!r} is not an https address")
    host = urlsplit(url).hostname or ""
    if state not in hosts.get(host, set()):
        raise DataError(f"{where}: {host} is not listed in {HOSTS_FILE} for {state}")


def _check_identity(row: dict[str, str], kinds: list[str]) -> None:
    law = row["law_id"]
    state = row["state"]
    if state not in STATES:
        raise DataError(f"{law}: {state!r} is not a state")
    if not LAW_ID.match(law) or not law.startswith(f"{state.lower()}-{row['session_year']}-"):
        raise DataError(f"{law}: a law_id is the state, the session year and the bill")
    if not row["session_year"].isdigit() or int(row["session_year"]) < FIRST_YEAR:
        raise DataError(f"{law}: session_year {row['session_year']!r} is not a year")
    listed = row["kinds"].split("|")
    if not row["kinds"] or any(k not in kinds for k in listed):
        raise DataError(f"{law}: kinds {row['kinds']!r} are not all in {KINDS_FILE}")
    if listed != sorted(set(listed), key=kinds.index):
        raise DataError(f"{law}: kinds are listed once each, in the order of {KINDS_FILE}")


def _check_words(row: dict[str, str]) -> None:
    law = row["law_id"]
    if not row["retrieved"] or _a_date(row["retrieved"], f"{law} retrieved") is None:
        raise DataError(f"{law}: retrieved is the day the official page was read")
    if not row["summary"].endswith("."):
        raise DataError(f"{law}: the summary is one or two full sentences")
    for column in ("summary", "limits", "enforcement", "binds", "source_note"):
        word = JUDGEMENT.search(row[column])
        if word:
            raise DataError(f"{law}: {column} uses {word.group(0)!r}; say what the text says")
    if row["source_form"] not in SOURCE_FORMS:
        raise DataError(f"{law}: source_form is one of {', '.join(sorted(SOURCE_FORMS))}")


def _saved(root: Path, law: str, expected: str, named: str, digest: str) -> str:
    """Return a saved text on one line, after checking it is the file the row names."""
    if named != expected:
        raise DataError(f"{law}: the saved text is {expected}, not {named!r}")
    path = root / expected
    if not path.is_file():
        raise DataError(f"{law}: the saved text {expected} is missing")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != digest:
        raise DataError(f"{law}: {expected} is not the file whose SHA-256 the row names")
    return _one_space(content.decode("utf-8"))


def _check_source(root: Path, row: dict[str, str]) -> None:
    law = row["law_id"]
    folder = TEXT_FOLDER / row["state"].lower()
    text = _saved(
        root, law, (folder / f"{law}.txt").as_posix(), row["source_text"], row["source_sha256"]
    )
    if not NAMES_PROGRAM.search(text):
        raise DataError(f"{law}: the saved text does not name the 340B program")
    quote = _one_space(row["quote"])
    if quote != row["quote"] or len(quote) < SHORTEST_QUOTE:
        raise DataError(f"{law}: the quote is a sentence from the page, single-spaced")
    if not NAMES_PROGRAM.search(quote):
        raise DataError(f"{law}: the quote itself names the 340B program")
    if quote not in text:
        raise DataError(f"{law}: the quote is not in the saved text word for word")
    if row["more_url"]:
        more = (folder / f"{law}.more.txt").as_posix()
        text += " " + _saved(root, law, more, row["more_text"], row["more_sha256"])
    elif row["more_text"] or row["more_sha256"]:
        raise DataError(f"{law}: more_text and more_sha256 are empty where more_url is")
    printed = text.lower()
    for column in ("signed_date", "effective_date"):
        day = _a_date(row[column], f"{law} {column}")
        if day is not None and not any(form in printed for form in date_forms(day)):
            raise DataError(f"{law}: {column} {row[column]} is not printed in the saved text")


def load_laws(root: Path) -> tuple[Table, Table]:
    """Return (laws, kinds) after every check. Both are empty where no laws table is kept."""
    if not (root / LAWS_FILE).is_file():
        return [], []
    kinds = load_kinds(root)
    hosts = load_hosts(root)
    laws = _read(root / LAWS_FILE, COLUMNS)
    names = [k["kind"] for k in kinds]
    seen: set[str] = set()
    for row in laws:
        law = row["law_id"]
        if law in seen:
            raise DataError(f"{law}: listed twice in {LAWS_FILE}")
        seen.add(law)
        _check_identity(row, names)
        _check_words(row)
        _check_address(f"{law} source_url", row["source_url"], row["state"], hosts)
        if row["more_url"]:
            _check_address(f"{law} more_url", row["more_url"], row["state"], hosts)
        _check_source(root, row)
    order = [(r["state"], r["session_year"], r["law_id"]) for r in laws]
    if order != sorted(order):
        raise DataError(f"{LAWS_FILE}: rows are kept in order of state, session year and law_id")
    kept = {p.relative_to(root).as_posix() for p in (root / TEXT_FOLDER).rglob("*.txt")}
    named = {r["source_text"] for r in laws} | {r["more_text"] for r in laws if r["more_text"]}
    extra = sorted(kept - named)
    if extra:
        raise DataError(f"{TEXT_FOLDER}: no row names {', '.join(extra)}")
    return laws, kinds


def load_not_listed(root: Path) -> Table:
    """Return what was read and left out of the table, each with its reason."""
    if not (root / NOT_LISTED_FILE).is_file():
        return []
    rows = _read(root / NOT_LISTED_FILE, NOT_LISTED_COLUMNS)
    hosts = load_hosts(root)
    for row in rows:
        where = f"{NOT_LISTED_FILE}: {row['state']} {row['name']}"
        if row["state"] not in STATES or not row["name"]:
            raise DataError(f"{where}: a row needs a state and a name")
        if not row["reason"].endswith("."):
            raise DataError(f"{where}: the reason is a full sentence")
        word = JUDGEMENT.search(row["reason"])
        if word:
            raise DataError(f"{where}: the reason uses {word.group(0)!r}; say what was found")
        if row["source_url"]:
            _check_address(where, row["source_url"], row["state"], hosts)
    order = [(r["state"], r["name"]) for r in rows]
    if order != sorted(set(order)):
        raise DataError(f"{NOT_LISTED_FILE}: rows are kept in order of state and name, once each")
    return rows


def load_sites(root: Path) -> Table:
    """Return the official sites the laws link to, each with the office that publishes it."""
    load_hosts(root)
    rows = _read(root / HOSTS_FILE, HOST_COLUMNS)
    return sorted(rows, key=lambda r: (r["state"], r["host"]))


def laws_document(
    laws: Table, kinds: Table, not_listed: Table, sites: Table, version: str
) -> dict[str, object]:
    """Return the JSON file's content: the kinds, each law (kinds as a list), then the sites."""
    return {
        "dataset_version": version,
        "license": "CC-BY-4.0",
        "kinds": kinds,
        "laws": [{**row, "kinds": row["kinds"].split("|")} for row in laws],
        "not_listed": not_listed,
        "sites": sites,
    }
