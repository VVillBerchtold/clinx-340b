# Changelog

This project follows [semantic versioning](https://semver.org/). A corrected figure is a patch release and names the filing, schedule and line.

## 0.4.0 (tagged `v0.4.0`, 12 November 2026)

The first tagged release, and the one ClinX.org is built from. A claim count of 1 to 5 is no longer republished. Described first; 0.3.0 follows it.

### Added (0.4.0)

- `line_items.csv` and the JSON file: a column `claims_withheld`, placed after `claims`. It is empty on every row except those whose count is left out: `fewer_than_6` or `beside_small`. See METHODS.md section 9.
- `src/filings340b/smallcounts.py`: the rule, with its limits (1 and 5) set in one place. The build stops, naming the filing and schedule, if a `total` or `below_threshold` row has a count of 1 to 5, or if no row can be left out beside a single small count.
- `tests/test_small_counts.py`.

### Changed (0.4.0)

- 310 Rhode Island Schedule G rows (`fewer_than_6`) have empty `claims_as_filed` and `claims` in `line_items.csv` and in the JSON file. No `beside_small` row arises. Their other fields, every other row, and every other file are unchanged. Vermont and Minnesota rows gain only the empty `claims_withheld` column.
- The working files no longer hold these counts either; see the next section.
- `dataset_version` in the JSON file is 0.4.0.
- The Rhode Island pin on `line_items.csv` since 0.1.0 no longer includes the two claim columns; the tests of the new rule cover them.

### The README reads in plain words

The README now opens with what the dataset is and why it can be trusted, a table of the states, the four files to start with, and a picture of how a figure gets from a PDF into the dataset. No data and no method changed.

### Working files hold no small counts (no change to `data/`)

The small-number rule now covers every table file in the repository. No file in `data/` changes, and the version number is the same.

- `transcriptions/ri/2025/*.csv` and `verification/ri/2025/*.image-read.csv`: a last column `claims_withheld`. On the 310 left-out rows the claim cell is empty and the column holds `fewer_than_6`. Every other cell is as it was. Vermont and Minnesota files have no left-out row and no new column.
- The counts are kept in `private/small-counts.csv`, which is in `.gitignore` and is not committed.
- `verification/ri/2025/claim-sums.csv`: the sum of the claim counts of each Schedule G, for a run without the private file.
- `filings340b seal`: moves the small counts of a newly transcribed filing into the private file and writes the sums. Safe to run twice.
- `check`, `tieout` and `textcheck` print one line that says whether they ran with or without the private small counts. Without them, the text check and the image-read comparison skip the left-out cells and say how many.
- `src/filings340b/sealing.py`, `src/filings340b/seal.py`, `src/filings340b/errors.py` (`DataError` moved here; `load.py` still imports it), `tests/test_sealing.py`.
- `tools/apply_image_read.py` writes the columns of the file it reads.

Version 0.3.0 (not tagged). Adds Minnesota. No Rhode Island or Vermont value, row or order changes; the only change to their rows is the new columns listed below. Version 0.2.0 (also not tagged) is described after it.

### Added (Minnesota, 0.3.0)

- Minnesota, data year 2024: the Minnesota Department of Health's report to the legislature ("340B Covered Entity Report, 2025", cover date February 27, 2026). It is the State's published figures about the entities it names, one net 340B revenue figure and one percentage each, not the entities' own filings. 27 records: one for each of the 26 rows of Appendix Table 6.1, and one statewide record (`mn-2024-statewide`) holding the six rows of Appendix Table 6.2 and the report's running text around the two tables as six `page_note` rows. 70 rows, each citing its PDF page (42 to 45).
- The report PDF with its SHA-256 and the text of pages 42 to 45 (the other pages are left empty in the text file, because they name people).
- A separate reader's image read of pages 42 to 45, compared with the transcription as printed (`tools/compare_mn_image_read.py`); the two agree on every name, type, city and figure.
- A Minnesota form with rules across its records: `table_6_1.rows=stated_entities`, `table_6_1.sum=table_6_2.top_unadjusted`, the two Table 6.2 sums (`form`), and the percentage comparisons on each entity row and on Table 6.2 (`comparison`). Seven differences recorded as printed.
- Minnesota has no measures and is not in the chart.
- `tools/extract_text.py --pages N-M` keeps the text of only those pages.
- `filings340b tieout` and `textcheck` take records that share one PDF page into account.

### Added columns (0.3.0; Rhode Island and Vermont rows gain these, their other values are unchanged)

- `filings.csv`: `record_kind` (`filing` for Rhode Island and Vermont; `state_report_row` and `state_report_totals` for Minnesota).
- `entities.csv`: `entity_type_as_filed` and `city_as_filed`, blank for Rhode Island and Vermont. New `entity_type` values: `other` and `state_total` (Minnesota only).

### Changed (0.3.0)

- `dataset_version` in the JSON file is 0.3.0.
- `tieout.checks` takes all filings as a second argument, for rules that compare records. Rhode Island's and Vermont's rules are unchanged.
- Tests pin every Vermont table to its 0.2.0 values, as Rhode Island's are pinned to 0.1.0. The Rhode Island chart is byte-for-byte what it was.

## 0.2.0 (not tagged)

Adds Vermont. No Rhode Island figure, row or order changes; the only change to the Rhode Island rows is the new columns listed below.

### Added (Vermont)

- Vermont, fiscal year 2025: the 13 hospital financial reports ("340B Program Financial Reporting Detail", as submitted to the Green Mountain Care Board in 2026), 157 rows, each citing its PDF page. The page marks itself draft; that notice is kept in `filings.csv`.
- The 26 Vermont PDFs (13 financial, 13 narrative) with their SHA-256, the page address that lists each, and the text of the 13 financial pages. The narratives are listed in `attachments.csv` (kind `narrative`) with address, SHA-256 and page count, and are not transcribed.
- A separate reader's image read of the 13 pages, compared with the transcription as printed (`tools/compare_vt_image_read.py`); the two agree on every row.
- A Vermont form with four rules and the same three measures as Rhode Island, worked on Vermont's rows; four differences recorded as filed (Gifford Medical Center net revenue and operating margin, Porter Medical Center payments, University of Vermont Medical Center expenses).
- `forms.py`: each filing names its form. Rhode Island's and Vermont's rules, rows and units are kept apart.

### Added columns (Rhode Island rows gain these; their other values are unchanged)

- `line_items.csv`: `unit` (`usd`, `percent`, `count` or `none`). Rhode Island's rows are `usd`, and Schedule I rows `none`.
- `discrepancies.csv`: `unit`. Rhode Island's claim-count rules are `count`, the others `usd`.
- `filings.csv`: `form`, `status_as_filed`, `status_notice_as_filed`, `period_as_filed`, `submission_as_filed`, `cover_page_url`. The last five are blank for Rhode Island.
- `attachments.csv`: `document_file`, `document_url`, `document_cover_page_url`, `document_sha256`, `document_bytes`, blank for Rhode Island.

### Changed

- The meta file of each Rhode Island filing names its form, `ri-oag-340b`. It was assumed before.
- `N/R` is read as a cell with no figure, like `N/A`.
- `dataset_version` in the JSON file is 0.2.0.
- The chart stays Rhode Island's and is byte-for-byte what it was.
- Tests pin every Rhode Island table and both charts to their 0.1.0 values.

### Added (Rhode Island, 0.1.0 content)

- Rhode Island, calendar year 2025: the 14 filings on Form RIOAG-340B (seven health centers, seven hospital filings), 2,989 rows across Schedules A to I, each citing its PDF page.
- The archived PDFs with their SHA-256, and the text each PDF carries.
- An independent read of every filing's page images, and the comparison that marks a row as checked.
- Sums and comparisons for the form, each marked `form` or `comparison`; 22 differences recorded as filed.
- Measures: gross margin, external cost, external share of margin, and Schedule E spending by category.
- Normalized vendor names beside the names as filed.
- A deterministic build (`filings340b build`) and a check that the published files are what the sources rebuild to (`filings340b check`).
