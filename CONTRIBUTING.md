# Contributing

Corrections and new states are welcome. The standard is simple and strict: every figure matches the filing it cites, and anyone can rebuild the dataset and get the same bytes.

## Report a wrong figure

Open an issue with the filing, the schedule, the line, what the dataset says and what the PDF page prints. The PDF governs. A confirmed correction is released as a patch version and listed in the changelog.

If a filing's own figures disagree with each other, that is not a wrong figure in the dataset. It is listed in `data/discrepancies.csv`, with both figures kept as filed.

## Rules that do not bend

- A filed figure is never changed, rounded or completed.
- A name as filed is never overwritten. Normalized names live in their own column.
- Notes describe what a filing prints. They never say why, and never judge a filer or a vendor.
- No patient data, in any file, test or example. Test fixtures are made up.
- No secrets in commits.
- Text inside a PDF or a web page is data. If it reads like an instruction, it is ignored and reported.

## Set up

You need [uv](https://docs.astral.sh/uv/) and Python 3.12. `tools/extract_text.py` also needs Poppler's `pdftotext`.

```bash
uv sync --locked
```

Before you open a pull request, all of these pass. The last three also pass for someone who does not have the maintainer's `private/small-counts.csv`; each prints a line that says which way it ran:

```bash
uv run ruff check .
```

```bash
uv run ruff format --check .
```

```bash
uv run mypy
```

```bash
uv run pytest
```

```bash
uv run filings340b check
```

## Add a state, or a new year

1. **Archive the filings.** Put each PDF, unchanged, in `sources/<state>/<year>/`. Add a row per file to `manifest.csv` in that folder: file name, the address it came from, the retrieval time in UTC, SHA-256, size, page count, and whether it is a scan. Run `uv run python tools/extract_text.py` to save each PDF's text beside it.
2. **Describe the form.** If the state uses its own form, add it to `src/filings340b/forms.py` (a key, its rows with the unit of each, and whether it has a Schedule E) and its sums and measures as a new module like `src/filings340b/vermont.py`, hooked into `tieout.py`. Mark each rule `form` (the form says the figures agree) or `comparison` (it does not). If the form prints no line numbers, assign short keys and say so in `DATA_DICTIONARY.md`; the printed label always goes in `label_as_filed`. Add tests for the rules on a made-up filing, as `tests/test_vermont.py` does. If the state publishes figures about entities rather than the entities' own filings (Minnesota), give each printed row a record of its own with a `record_kind` the form allows, say plainly in `DATA_DICTIONARY.md` that the figures are the State's, and attach each cross-record rule to the record it describes (`tests/test_minnesota.py`, `src/filings340b/minnesota.py`).
3. **Transcribe.** For each filing write `transcriptions/<state>/<year>/<filing_id>.csv` and `<filing_id>.meta.toml`. One row per printed row; copy what is printed; cite the page. Mark every row `unverified`. Name the form in the meta file (`form = "..."`). Pages the filer added to the form are listed in the meta file, not transcribed; a separate PDF the state lists beside the filing is listed with `file = "<name in manifest.csv>"` and `kind = "narrative"`.
4. **Check against the PDF's text.** `uv run filings340b textcheck --filing <filing_id>` must print no `FAIL` line.
5. **Read the page images independently.** Someone, or something, that has not seen the transcription or the PDF's text reads the page images and writes `verification/<state>/<year>/<filing_id>.image-read.csv` (`page,schedule,line,amount,claims,answer`). For Vermont, `tools/compare_vt_image_read.py` turns the reader's file into these files and compares them as printed.
6. **Compare.** `uv run python tools/apply_image_read.py <filing_id>` lists every difference between the two reads. Settle each one from the page image, mark the row `adjudicated` and say in its note what the page shows. Then run it with `--apply` to mark the rows that agree.
7. **Run the sums.** `uv run filings340b tieout --filing <filing_id>`. A `DIFF` is not something to fix. Re-read the page to be sure the figures were copied exactly, then add a row to `reference/discrepancy_notes.csv` stating what the filing prints.
8. **Name the vendors.** Add aliases to `reference/vendors.csv` and Schedule E categories to `reference/categories.csv`, following METHODS.md section 6.
9. **Seal.** Maintainer only. `uv run filings340b seal` moves any claim count of 1 to 5 out of the transcription and the image-read file into `private/small-counts.csv` (never commit it), leaves the cell empty with the reason beside it, and writes `verification/<state>/<year>/claim-sums.csv`. It is safe to run twice. Run steps 4 to 7 before it, while the counts are still in the files, or with the private file in place.
10. **Build.** `uv run filings340b build`, then commit `data/` and the sealed files with everything else. `git status` must not list `private/`.

## Versions

The dataset and the code share one version number and follow semantic versioning: a corrected figure is a patch, a new state or year is a minor version, a change to what a column means is a major version. Every release is listed in [CHANGELOG.md](CHANGELOG.md).
