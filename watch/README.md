# The daily watch on the states' source pages

Each state posts its 340B reports on a page of its own, and nothing announces a new one. This
folder lets a small program look every day and say when a list changed.

- `sources.csv` is the list of pages, kept by hand: the page, what is on it, and how to read it
  (the links of one kind, the words in one part of the page, Ohio's collection list, or one
  file's size and SHA-256).
- `seen/` holds what the program saw the last time it looked, one small file for each page. An
  unchanged page gives an unchanged file.
- `certs/` holds public intermediate certificates for state servers that leave theirs out. The
  check of a site's certificate is never switched off.
- `unreadable-days.json` counts the days in a row a page could not be read.

`tools/watch_sources.py` does the looking and `.github/workflows/watch.yml` runs it every day.
When a list changes, the workflow saves the new copy and opens an issue that says what was
added, removed or replaced. It changes nothing in the dataset: anything new still has to be
read and entered. A page that cannot be read is never counted as a change. A site that answers
with a check for robots is left alone.

The program gives its name on every request, `ClinX Open Data Reader`, with the address of the
page that explains how ClinX reads public files, and asks for one page at a time.

Not every state can be watched this way. Colorado's health care department turns programs away,
so its page is read in a browser from time to time.
