# Methods

This document says where every figure in the dataset comes from, how it was checked, and how each measure is calculated. It describes filings, reports and calculations. It makes no statement about why a filer's figures are what they are.

## 1. Sources

Rhode Island's Defending Affordable Prescription Drug Costs Act (R.I. Gen. Laws chapter 5-19.3) requires each 340B covered entity in the state to report yearly to the Auditor General, who posts the reports. The 14 reports for calendar year 2025 were retrieved from the Auditor General's website on 11 November 2026.

Each PDF is archived unchanged in `sources/ri/2025/`. `manifest.csv` records, for each file, the address it was retrieved from, the time, its size, its page count, whether it is a scan, and its SHA-256. The build stops if a PDF no longer matches its SHA-256.

The text each PDF carries is saved beside it in `sources/ri/2025/text/`, extracted with Poppler's `pdftotext` (`tools/extract_text.py`). One thing is changed in that text: an email address is replaced with a marker. The PDFs themselves are unchanged.

All 14 use state Form RIOAG-340B (Revised January 2026): a cover page and Schedules A to I. Thirteen carry a text layer. One (Wood River Health Services) is a scan.

**Vermont.** The Green Mountain Care Board posts, for each of 13 hospitals, two documents for fiscal year 2025: a one-page "FY2025 340B Program Financial Reporting Detail", marked "As Submitted to the Green Mountain Care Board in 2026", and a free-text "340B Narrative Reporting". The state page that lists them is <https://gmcboard.vermont.gov/node/24841>; each document has its own page at `https://gmcboard.vermont.gov/document/<name>`. The 26 PDFs were retrieved on 12 November 2026 (UTC; each time is in the manifest). They are archived unchanged in `sources/vt/2025/`. That `manifest.csv` has the columns Rhode Island's has, and two more: `document_kind` (`financial` or `narrative`) and `cover_page_url`. The build stops if a PDF, narratives included, no longer matches its SHA-256.

The 13 financial pages have a text layer; the text is saved beside them in `sources/vt/2025/text/`, extracted the same way. The narratives' text is not extracted or kept. The page prints this notice, quoted exactly: "NOTE: This is draft and may be adjusted for accuracy in the final GMCB dashboard publication." Every Vermont filing therefore carries the status `draft` in `filings.csv`. A later publication by the Board may differ; this dataset holds what the pages printed on the day they were retrieved.

The Vermont page prints no corporate address, 340B ID numbers, recertification date or reporting basis. Those columns are blank for Vermont; nothing is filled in from another source.

**Minnesota.** Minnesota is a different kind of source. Minn. Stat. 62J.461 has the Department of Health (MDH) collect data from covered entities and report on it yearly to the legislature. The entities' own reports to MDH are not public. What is public, and what this dataset holds, is what MDH printed in its report: "340B Covered Entity Report: Report to the Minnesota Legislature, 2025", cover date February 27, 2026, 51 pages, retrieved on 12 November 2026 (UTC; the time is in the manifest) from <https://www.health.mn.gov/data/340b/docs/2025report.pdf>. It is archived unchanged in `sources/mn/2024/`, with a `manifest.csv` of the same layout as Rhode Island's. The build stops if the PDF no longer matches its SHA-256.

The report is titled 2025 and covers the 2024 data year. The dataset's `reporting_year` is the data year, 2024; the title says 2025. The report's cover letter says that "reported data are not audited nor otherwise verifiable". So every Minnesota figure is a figure the State published about an entity, one per entity (its net 340B revenue, and that figure as a percentage of the statewide total), not a figure the entity filed. `filings.csv` marks this with `record_kind` (section 7).

Only Appendix 6 (PDF pages 42 to 45) is transcribed. The text layer of those four pages is saved in `sources/mn/2024/text/`. The other 47 pages are left empty in that file, because the report names individual people and offices on pages the dataset does not use (`tools/extract_text.py --pages 42-45`). The PDF is unchanged.

The Minnesota report prints no corporate address, 340B ID numbers, recertification date, reporting basis, status or period in the tables. Those columns are blank for Minnesota.

**Idaho.** Idaho is a third kind of source. Idaho Code § 41-351 has each covered entity report yearly to the State, keeps those reports confidential, and has the State Controller's Office publish a report that adds them together before November 15 of each year. What is public, and what this dataset holds, is that report: "Idaho 340B Drug Pricing Program, Inaugural Report, Calendar Year 2025", seven pages, linked as "340B Program Reporting" on the Transparent Idaho website (<https://transparent.idaho.gov/featured-resources>) and retrieved on 15 November 2026 (UTC; the time is in the manifest) from the address in `sources/id/2025/manifest.csv`. It is archived unchanged in `sources/id/2025/`. The report covers January 1 through December 31, 2025 and says it adds together 62 submissions. It names no covered entity, so the dataset has no Idaho row for any single entity.

The text layer of all seven pages is saved in `sources/id/2025/text/`. The report prints the State Controller's Office telephone number, fax number and e-mail address; in the saved text each is replaced with a marker (`tools/extract_text.py`). The PDF is unchanged.

## 2. What is transcribed

Every printed row of Schedules A to I, one row of data per printed row. For each row the dataset keeps:

- the text as filed (labels, names, the drug code cell, the amount, the claim count), copied without correction. A name the form cut off stays cut off. Spelling stays as filed;
- a parsed amount, at the scale filed (some filers report whole dollars, others cents);
- the PDF page the row is printed on;
- how the row was checked.

Rules for amounts:

| Printed in the amount cell | `amount_as_filed` | `amount` |
|---|---|---|
| A figure | the figure as printed | the same number |
| A figure in parentheses | as printed | negative |
| A lone dash | `-` | `0` |
| `N/A` | `N/A` | blank |
| Nothing | blank | blank |

A blank is never treated as zero.

What is not transcribed:

- The signer's name, title and email address on Schedule I. They are in the PDF.
- Pages a filer added to the form: cover letters, notes, appendices and supplemental listings. Each is listed in `data/attachments.csv` with its page range, so a reader knows it exists and where to find it.
- Notes a filer printed on a schedule page are kept in the `note` column of the row they sit beside, starting `Printed note:`.

**Vermont.** Each page is transcribed in full: the name printed at the top, the title, the submission line and the draft notice (in `filings.csv`, see DATA_DICTIONARY.md), and the 12 figure rows in printed order. The page prints no line numbers and no schedule letters. So `schedule` and `line` hold keys this dataset assigned (for example `payments` and `total`), and `label_as_filed` holds the label the page prints, unchanged. The keys are listed in DATA_DICTIONARY.md. They are ours: the state does not use them.

Further rules for Vermont's amounts, in addition to the table above:

| Printed in the amount cell | `amount_as_filed` | `amount` |
|---|---|---|
| `$764,691` (no cents) | `764,691` | `764691`, at the scale filed |
| `($397,702)` | `(397,702)` | `-397702` |
| `-33.30%` | `-33.30%` | `-33.30`, with `unit` `percent` |
| `N/R` | `N/R` | blank |

Every row has a `unit` (`usd`, `percent` or `none`), fixed by the form, so a percentage is never mixed with dollars. `N/R` is kept as printed and is not read as zero. The state's text below the figures, where a page has any, is kept word for word as a `page_note` row. One page has such a paragraph (Northwestern Medical Center); it is carried unchanged and not interpreted.

Not transcribed for Vermont: the narratives. Each is listed in `data/attachments.csv` with its address, SHA-256 and page count, kind `narrative`. They are free text, not a form. This dataset holds no person's name, email address or phone number.

**Minnesota.** Appendix Table 6.1 prints 26 rows, one per covered entity. Each printed row is one record (`mn-2024-<key>`, with a key this dataset assigns from the name) and has two figure rows, both on the page the row is printed on: `table_6_1` / `net_revenue` (the column "Net 340B Revenue ($)", unit `usd`) and `table_6_1` / `pct_of_statewide` (the column "% of Statewide Net 340B Revenue", unit `percent`). In both, `label_as_filed` is the entity name as printed and `description_as_filed` the column heading as printed. A name, type or city that wraps across lines in the table is joined with single spaces; nothing else is changed (the apostrophe in "Children’s Minnesota" is the one the page prints, and differs from the other apostrophes). The printed entity type and city are kept as printed in two new columns of `entities.csv` (`entity_type_as_filed`, `city_as_filed`). "As filed" means, for Minnesota, as printed in the State's report.

The existing `entity_type` column is `hospital` when the printed type contains the word Hospital (Disproportionate Share Hospital, Sole Community Hospital, Critical Access Hospital, Children's Hospital) and `other` for any other printed type (one row prints "CHD Treatment Center"). Nothing is read into an abbreviation. The build refuses a Minnesota record whose `entity_type` does not follow its printed type.

Appendix Table 6.2 prints six rows ("Top 25, unadjusted", "Remaining 156, unadjusted", "Total, unadjusted", and the same three "adjusted"), each with "Net 340B Revenue ($)" and "% of Total". They are kept as 12 figure rows under one statewide record, `mn-2024-statewide`, whose entity `mn-statewide` has `entity_type` `state_total` and is not a covered entity. The table starts on page 44 and the adjusted rows are on page 45. A "Total" row is `row_kind` `total`. The statewide record also holds the report's running text around the two tables as six `page_note` rows, word for word: the paragraph above Table 6.1; the title of Table 6.1; the "Source:" line under Table 6.1; the paragraph above Table 6.2; the title of Table 6.2; and the "Source:" line under Table 6.2. The two "Source:" lines differ (one names 2023 and 2024 data, the other 2024 data), and the second is printed without a final full stop; both are kept as printed. A page note is not interpreted, except that the rule in section 4 reads the number of entities from the first.

Amounts: `334,683,472` is `334683472`; `26.1%` is `26.1` with `unit` `percent`; `100%` is `100`. A percentage keeps its printed precision. The printed order of the table is kept nowhere in the data: each record is its own file, and published files are listed by `filing_id`, which is alphabetical. The report's order is not a field. Nothing in the dataset ranks the rows, and nothing calls a row a place in an order. The words "Top 25" and "Remaining 156" are labels as printed.

Not transcribed for Minnesota: the rest of the report, including its cover letter, its main text and its other appendices. Where the report's tables print an entity's name, that is the only name the dataset holds. This dataset holds no person's name, email address or phone number.

**Idaho.** The whole report is one record, `id-2025-statewide` (`record_kind` is `state_report_totals`, `entity_type` is `state_total`). Every cell the report prints in a table, a highlight tile or its chart is one row, under schedule and line keys this dataset assigns (DATA_DICTIONARY.md lists them): the four highlight tiles, the four labels of the chart, the submissions table, the four tables by payer type (acquisition cost, payments received, payments to contract pharmacies, number of claims) and the table of how savings were used. `label_as_filed` is the row's printed label and `description_as_filed` the column heading. Each printed percentage is a row of its own.

Three things are kept in a particular way, each said on the row. The two money tiles print rounded figures with a letter (`$812.9M`, `$430.6M`); they are kept as text in `answer_as_filed`, with no `amount`, so the dataset never turns a rounded figure into dollars. One cell of the submissions table prints a count and a percentage together, `62 (100%)`; it is two rows, the count and the percentage, and each row's `note` gives the cell as printed. The words in the Notes column of that table are rows with no figure.

Sentences of the report that state a figure, the chart's title and the labels of its value axis are `page_note` rows, exactly as printed (a wrapped line is joined with a space), so that every figure printed on a page is carried by a row. The period the report states is in `period_as_filed`. Not transcribed: the rest of the running text (the description of the federal program and of the statute, and the list of entity types).

## 3. How each figure was checked

Three separate checks stand behind every published figure. A row that has not passed them cannot be published: the build refuses it.

**Check 1: the PDF's own text.** `filings340b textcheck` reads the text layer of each PDF page and asks two questions. Is every transcribed amount and claim count printed on the page it cites? Is every amount printed on the page carried by a transcribed row? The first catches a mistyped figure; the second catches a row left out.

**Check 2: an independent read of the page image.** A second reader is shown only pictures of the pages, with no access to the PDF's text or to the first transcription, and writes down every amount, claim count and yes/no mark it sees. The result is kept in `verification/`. A row is marked as checked only when this read agrees with the transcription, figure for figure as printed.

**Check 3: the sums.** `filings340b tieout` runs the rules in section 4.

Both reads were made by software (a language model), not by a person, and each was run as a separate job. The second reader's instructions and file access were restricted to the page images, and the record of what each job opened was reviewed afterward. Anyone can repeat either check: the PDFs, the text, both reads and the code are all in this repository.

The `verification` column records the outcome for each row:

| Value | Meaning |
|---|---|
| `text_and_image` | The transcription matches the PDF's text and the independent read of the page image |
| `two_image_reads` | The page has no usable text (a scan, or a figure the text layer leaves out); two independent reads of the page image agree |
| `adjudicated` | The two reads differed; a further look at the page image settled it, and the row's note says what was seen |
| `unreadable` | The page cannot be read with confidence; the value is left blank |

In the Rhode Island 2025 release the two reads agreed on every one of the 2,989 rows. 2,887 are marked `text_and_image` and 102 `two_image_reads` (the 101 rows of the scanned filing, and one claim count that a PDF's text layer leaves out). No row needed adjudication and none is unreadable.

In the Vermont 2025 release a separate reader was given only the 13 page images and wrote down every figure row it saw, in printed order, with the label and the value as printed (`tools/compare_vt_image_read.py` keeps a normalised copy in `verification/vt/2025/`). The comparison for Vermont is stricter than the shared one: it also counts a parenthesis, a minus sign and a `%` sign, so a figure read as positive where the page prints it in parentheses would be a difference. The two reads agreed on all 157 rows (13 times 12 figure rows, and the one `page_note` row, whose text was matched with the reader's notes). All 157 are marked `text_and_image`. None was adjudicated and none is unreadable.

In the Minnesota 2024 release a separate reader was given only the page images of PDF pages 42 to 45, with no access to the PDF's text or to the transcription, and wrote down every cell of Table 6.1 (name, type, city, net revenue, percent) and Table 6.2 (dimension, net revenue, percent), with the running text around the tables. The image of page 45, where Table 6.2 continues, was read by a separate reader in a separate job. `tools/compare_mn_image_read.py` keeps a normalised copy of both reads in `verification/mn/2024/` and compares every name, type, city and figure with the transcription exactly as printed, apart from the `$` sign and runs of spaces (stricter than the shared comparison: a `%` sign, a comma or an apostrophe that differs is a difference). A record whose name, type or city differs from the read, or a figure the reader marked `?`, would stay `unverified` and unbuilt. The two reads agreed on all 26 Table 6.1 rows (name, type, city, both figures), on all six Table 6.2 rows (both figures; three rows on page 44 and three on page 45), and the six page notes were found word for word in the reader's notes. All 70 rows are marked `text_and_image`. None was adjudicated and none is unreadable. For Minnesota, `filings340b textcheck` pools the records that are rows of one PDF page: a figure printed on page 43 counts as carried when any record of the report carries it.

In the Idaho 2025 release a separate reader was given only the pictures of the seven pages, with no access to the PDF's text or to the transcription, and wrote down every cell of every table, tile and chart, with its row label and column heading, and the running text of each page. `tools/compare_id_image_read.py` pairs each row with the reader's cell on the same page with the same label and heading, compares the two exactly as printed apart from the `$` sign and spaces, lists any cell the reader wrote that no row carries, and keeps a normalised copy in `verification/id/2025/` beside the reader's own cell file (`id-2025-statewide.second-read.csv`). A `page_note` row counts as agreeing only when its exact text is in the reader's running text, is the heading the reader gave a chart, or is the reader's axis labels in order. The two reads agreed on all 105 rows (90 cells and 15 `page_note` rows), and the reader wrote no cell that is not carried. All 105 are marked `text_and_image`. None was adjudicated and none is unreadable.

Limits of these checks. Check 2 covers figures and marks: amounts, claim counts, and Schedule I answers. Names and labels come from the PDF's text, and for the scanned filing from one read of the image. Where a drug name is clipped by the form's cell, the dataset keeps the text the PDF holds.

**Workbooks (Ohio).** A workbook has no page image, so a figure is read twice by two different programs and the reads are compared cell by cell. The first read is `src/filings340b/workbook.py`, which opens the file as a zip of XML with the Python standard library and returns each cell as stored. The second is LibreOffice, which saves the template sheet as a CSV file (`tools/oh_second_read.py`). Two numbers agree when they differ by less than one part in 10^14, which is what a spreadsheet's 15 digits allow; any other value must match letter for letter. (The brief for this work named the Python package `openpyxl` for the second read; it could not be installed on the machine, so LibreOffice does that job.) Both reads were compared over 71,560 cells of the template sheets and the 40,878 rows of the transcriptions. Every row that agrees is marked `two_file_reads`. Three rows are marked `adjudicated`: in one workbook a percentage cell stores a rounded result, LibreOffice works the formula out again and gets the unrounded number, and the stored value is kept (the note on each row says so). The second read of each row is kept in `verification/oh/2025/<filing_id>.file-read.csv`. A template row is located by the label the workbook prints beside it and a column by its heading, because some filers inserted rows or moved a column; each row names the cell it came from in `source_cell`.

## 4. Sums and comparisons

Each rule sets two figures from one filing side by side. The `basis` column says why.

`form`: the form itself says the two figures agree.

| Rule | What it compares |
|---|---|
| `A6=A2-A1-A3-A4-A5` | Schedule A line 6 with line 2 minus lines 1, 3, 4 and 5 (the form's net revenue calculation) |
| `B.rows=total` … `H.rows=total` | The rows of a schedule with the total printed on it |
| `B.total=A1`, `C.total=A2`, `D.total=A3`, `E.total=A4`, `F.total=A5` | A schedule's total with the Schedule A line the form says it supports |
| `C.claims=total`, `G.claims=total` | The claim counts on a schedule with the claim total printed on it |

`comparison`: the form does not say the two figures agree. They describe related things and are shown together.

| Rule | What it compares |
|---|---|
| `H.total=A6` | The Schedule H total (programs supported by 340B net revenue) with Schedule A line 6 (net 340B revenue) |
| `C.claims=G.claims` | The claim total on Schedule G (drugs) with the claim total on Schedule C (reimbursements) |

A rule is applied only when the filing prints both figures.

**Vermont.** Four rules, run on every Vermont filing. A cell that prints `N/R` has no figure and adds nothing to a sum.

`form`: the page itself says the figures agree.

| Rule | What it compares |
|---|---|
| `payments.rows=total` | The four payment rows (by distribution channel) with Total 340B Payments Received |
| `expenses.rows=total` | The three expense rows with Total 340B Expenses |
| `net_revenue=payments-acquisition-expenses` | 340B Net Revenue with Total 340B Payments Received minus 340B Prescription Drug Acquisition Costs minus Total 340B Expenses (the page prints that calculation under 340B Net Revenue) |

`comparison`: the page does not say how the figure is calculated.

| Rule | What it compares |
|---|---|
| `operating_margin=net_revenue/payments` | 340B Operating Margin with 340B Net Revenue divided by Total 340B Payments Received, times 100, rounded half up to the number of decimal places the page prints the margin to. The difference is in percentage points (`unit` `percent`) |

When the two figures differ, nothing is changed. The difference is listed in `data/discrepancies.csv` with both figures, and a note that states what the filing prints. The build stops if a difference has no note, and stops if a note is left behind for a rule that now holds. The Rhode Island 2025 data lists 22 differences across 13 filings: eight under a `form` rule (five of them of 1.00 or less) and 14 under a `comparison`. The Vermont 2025 data lists four, in three filings: two under a `form` rule of 1.00 each (Porter Medical Center, University of Vermont Medical Center), one under a `form` rule of 80,000.00 (Gifford Medical Center, net revenue), and one `comparison` (Gifford Medical Center, operating margin). The other ten Vermont filings, and each of these three on its other rules, hold.

**Minnesota.** Rules compare figures across the report's records, so each is attached to the record it describes: the entity rows carry the percentage comparison, and the statewide record carries the rest. A rule is applied only when the report prints both figures.

`form`: the report's text states that the two figures agree.

| Rule | What it compares |
|---|---|
| `table_6_1.rows=stated_entities` | The number of rows Table 6.1 prints beside the number of Covered Entities the paragraph above it states (`unit` `count`) |
| `table_6_1.sum=table_6_2.top_unadjusted` | The Net 340B Revenue rows of Table 6.1 added together beside Table 6.2's "Top 25, unadjusted" |
| `table_6_2.unadjusted_rows=total`, `table_6_2.adjusted_rows=total` | The named group plus the remaining entities beside the total, for unadjusted and for adjusted |

`comparison`: the report does not say how the figure is calculated.

| Rule | What it compares |
|---|---|
| `pct_of_statewide=net_revenue/total_unadjusted` | On each entity row: the printed percentage beside its net revenue divided by Table 6.2's "Total, unadjusted", times 100, rounded half up to the number of decimal places the report prints. The report does not say which total its percentages use; this is one comparison, not a statement of how they were made. The difference is in percentage points |
| `table_6_2.<row>.pct_of_total=net_revenue/total_<unadjusted or adjusted>` | On the statewide record, for each of its six rows: the printed % of Total beside the row's net revenue divided by the total of its own kind (unadjusted rows by Total, unadjusted; adjusted rows by Total, adjusted), at the printed precision |

The Minnesota 2024 data lists seven differences: three under a `form` rule, all on the statewide record (Table 6.1 prints 26 rows where the paragraph above it states 25; the Table 6.1 rows add up to 1,152,403,308 where Table 6.2 prints 1,152,403,307; the adjusted rows add up to 1,340,270,965 where Table 6.2 prints 1,340,270,964), and four under the entity percentage `comparison` (Abbott Northwestern Hospital, CentraCare - Rice Memorial Hospital, M Health Fairview - University of Minnesota Medical Center and Regions Hospital, each 0.1 percentage points below the comparison). The other 22 entity rows hold, and so do the unadjusted rows of Table 6.2 and all six of its percentage comparisons.

**Idaho.** Every rule is on the one statewide record.

| Rule | Basis | What is compared |
|---|---|---|
| `<table>.rows=total` | `form` | For each of the four payer tables and the savings table: the rows above the TOTAL row added together, beside the TOTAL row |
| `<table>.<row>_pct=<row>/total` | `comparison` | Each printed percentage beside the row's figure divided by the table's TOTAL, times 100, at the printed precision |
| `submissions.complete_pct=complete/received` | `comparison` | The percentage printed beside Submissions with complete status, beside that count divided by Total submissions received |
| `key_highlights.total_claims=claims.total` and `key_highlights.covered_entities=submissions.received` | `comparison` | A count tile beside the table figure of the same name |
| `key_highlights.payments_received=payments_received.total` and `key_highlights.savings_to_community=savings_use.total` | `comparison` | A money tile, a rounded figure in millions, beside the table's TOTAL rounded the same way |
| `key_financial_metrics.<label>=<table>.total` | `comparison` | Each of the chart's four labels beside the table TOTAL of the same name, to the whole dollar |
| `savings_use.total=payments_received.total-acquisition_cost.total` | `comparison` | The TOTAL of 340B Savings Utilization beside payments received less acquisition cost, the difference the report's summary calls the gross program margin. The report does not say the two agree |

The percentage columns are not added up: each percentage is printed to one decimal.

The Idaho 2025 data lists three differences. Two are under a `form` rule: the six payer rows of Number of Claims by Payer Type add up to 1,916,602 where the TOTAL row prints 1,916,995, and the nine rows of 340B Savings Utilization add up to 430,646,947.35 where the TOTAL row prints 430,646,950.35. One is under a `comparison`: the savings TOTAL, 430,646,950.35, beside payments received less acquisition cost, 413,709,636.77. The other 50 rules hold.

Schedule G's amount total is not compared with Schedule A line 1. The form does not say they agree, and the filings describe Schedule G's amounts in more than one way.

**Ohio's rules.** The template does its own arithmetic, and `src/filings340b/ohio.py` checks each sum or ratio in each workbook: every table's TOTAL cell equals its five payer cells added (in the contract pharmacy tables the Indeterminate cell is not part of the total, as the template itself says); in the administered drugs table, total payments equal actual payments plus estimated payments; a percentage equals the 340B prescriptions over all prescriptions, times 100 (when the cell is formatted as a percentage the workbook stores a fraction of one and the rule compares against that). A workbook stores figures as binary floating-point numbers, so two figures within a thousandth of a dollar (a billionth of a percentage point) count as equal; the tolerance is recorded with each rule. A rule is not applied to a cell the small-number rule withholds, nor to a cell that holds words. Where a rule does not hold, `data/discrepancies.csv` shows both figures. The note for it in `reference/discrepancy_notes.csv` is written by `tools/oh_discrepancy_notes.py` from the two numbers and says only what the cells hold ("The total cell holds X. The five payer cells add to Y."). It gives no cause: the dataset does not know one. In this version 233 rules do not hold.

## 5. Measures

| Measure | Calculation |
|---|---|
| `gross_margin` | Schedule A line 2 minus line 1 |
| `external_cost` | Schedule A line 3 plus line 4 |
| `external_share_of_margin` | `external_cost` divided by `gross_margin`, to six decimal places; blank when the margin is not above zero |
| `schedule_e_third_party_administrator`, `schedule_e_referral_capture`, `schedule_e_consulting_audit`, `schedule_e_other` | The sum of the Schedule E rows in that category |

Measures use the Schedule A figures as filed, including where a supporting schedule's total differs from them.

**Vermont.** The same three measures, on Vermont's rows, with the formula text in `measures.csv` naming them:

| Measure | Calculation |
|---|---|
| `gross_margin` | Total 340B Payments Received minus 340B Prescription Drug Acquisition Costs |
| `external_cost` | Payments Made to Contract Pharmacies plus Payments Made to Outside Vendors |
| `external_share_of_margin` | `external_cost` divided by `gross_margin`, to six decimal places; blank when the margin is not above zero (the same rule as Rhode Island) |

**Minnesota has no measures.** Its tables print no acquisition cost and no payments to pharmacies or vendors, so `gross_margin`, `external_cost` and `external_share_of_margin` do not exist for it, and `measures.csv` has no Minnesota rows. Net revenue and its share of the statewide figure are the State's published figures, kept in `line_items.csv`, not measures calculated here.

**Idaho has no measures.** Its one record is a statewide total and the measures compare covered entities, so `measures.csv` has no Idaho rows. The report's own totals, and the margin its summary describes, are in `line_items.csv` and `discrepancies.csv` as printed.

Internal 340B Program Expenses is not part of `external_cost`. The Rhode Island Schedule E category measures do not exist for Vermont, which has no such schedule. One Vermont filing (Northwestern Medical Center) has a gross margin below zero, so its share is blank. The measures use the printed Total 340B Payments Received, including where a total differs from its rows. The chart in the README is Rhode Island's by design; Vermont's measures are in `data/measures.csv`; Minnesota has none.

**Why two filers' shares are not directly comparable.** A filer that dispenses through its own pharmacy carries the cost of dispensing in its own staffing and expenses. A filer that relies on contract pharmacies pays for dispensing on Schedule A line 3. The same activity therefore appears inside the margin for one filer and as an external cost for another. Line 3 also counts every pharmacy a filer lists on Schedule D, whoever owns it. Filers also differ in reporting basis (cash or accrual, shown in `data/filings.csv`) and in how they describe the period their figures cover; several print notes about this, which are kept. For these reasons the dataset lists filings alphabetically within health centers and hospitals and does not rank them.

The same holds for Vermont's hospitals: the filings are made by different hospitals in different ways, Vermont's page prints no reporting basis, and every page is marked draft. Nothing here ranks them.

## 6. Vendor names and categories

`normalized_vendor` gives one spelling for a company that filers name in different ways, so its rows can be added up. The name as filed is always kept beside it. A name is normalized only when the text as filed names one company. A row that names several companies together, or a category instead of a company, has no normalized name. `reference/vendors.csv` lists every alias and the reason for any mapping that is not a plain spelling difference.

`category` is given to Schedule E rows only, and only from the filer's own words on that row: `third_party_administrator`, `referral_capture`, `consulting_audit`, or `other` when the filer's words name none of these.

**Ohio.** Ohio is a fourth kind of source, and it is the first that is not a PDF. Ohio Revised Code 3701.88 has every 340B covered entity report to the Department of Health, and the Department posts each entity's report as an Excel workbook on its own template (the "ORC 3701.88 340B Covered Entity Reporting Template"). The 241 workbooks for calendar year 2025 were downloaded unchanged; `sources/oh/2025/manifest.csv` records the address, time, size and SHA-256 of each.

The workbooks are not in the repository. Each names a staff member and gives an e-mail address and a telephone number. They are kept on the maintainer's machine in `sources/oh/2025/originals/`, which git ignores, and every build step and every test works without that folder. Where a PDF's saved text stands in the other states, a plain CSV stands here: `sources/oh/2025/cells/<name>.csv` lists every filled cell of the template sheet (sheet, cell, value as stored). In it the three contact cells hold the marker `[contact detail withheld]`, any e-mail address or telephone number is replaced by a marker (the same two patterns as `tools/extract_text.py`, and a test checks they match), and a cell that the small-number rule withholds holds `[withheld: <reason>]`. A workbook's other sheets are not copied: `workbook-contents.csv` lists each by name and the number of cells it fills, and `workbook-objects.csv` lists every picture, drawing, embedded object, macro or link inside a workbook (84 in all). Nothing inside a workbook is run, followed or obeyed.

The workbooks print no entity name, only a 340B ID, and the dataset does not put a name from anywhere else in `name_as_filed`. The names in `entities.csv` columns `hrsa_name`, `hrsa_id_spelling`, `hrsa_list_date` and `hrsa_match` come from HRSA's public list of covered entities, read on 11 November 2026. The small extract of that list is `reference/hrsa-oh-extract.csv`, with the export's size and SHA-256 in `reference/hrsa-oh-extract.source.toml` (`tools/extract_hrsa_oh.py` makes both). The ID in the file name and the ID typed in the workbook are both kept: the typed one in `opais_ids_as_filed`, the file name's in `source_file` and in the entity's id. In 37 workbooks they differ. An ID that HRSA's list does not hold (four) keeps an empty name and says so in `hrsa_match`. A workbook that names two or three IDs is one filing for all of them: its first ID is the filing's entity and `other_entity_ids` in `filings.csv` lists the rest. Two entities have two workbooks each (DSH360059 and DSH360137), so 241 filings belong to 242 entities.

## 7. Rebuilding

`filings340b build` writes every file in `data/` from the archived PDFs' manifest, the transcriptions and the reference files. Each filing names its form (`form` in its `.meta.toml` file), and the form decides which rows may appear, their units, and which sums and measures apply; nothing is assumed from the state. Each record also has a `record_kind` (`meta.toml`, `record_kind`): `filing` for an entity's own filing (Rhode Island, Vermont; the default), `state_report_row` for a row the State published about one entity (each Minnesota Table 6.1 row), and `state_report_totals` for the one record that holds the State's totals and running text (`mn-2024-statewide`, and Idaho's only record, `id-2025-statewide`). The form says which kinds it allows. It uses no clock and no network, so the same inputs always give the same bytes. `filings340b check` rebuilds in memory and compares; continuous integration runs it on every change.

## 8. Versions

The dataset follows semantic versioning. A correction to a published figure is a patch release and is listed in the changelog with the filing, schedule and line. A new state or year is a minor release (0.8.0, not yet tagged, adds Ohio; 0.2.0 added Vermont, 0.3.0 added Minnesota, 0.5.0 added Idaho), and so is a new table (0.6.0 added the state laws). A change to a column's meaning is a major release.

## 9. Small claim counts

From version 0.4.0, a claim count of 1 to 5 is not republished. The reader sees `fewer_than_6` instead. The rule is set in one place, `src/filings340b/smallcounts.py`, and works on each filing and schedule on its own.

- A row of kind `detail` whose claim count is 1, 2, 3, 4 or 5 is small. In `data/line_items.csv` and in the JSON file, its `claims_as_filed` and `claims` are empty and `claims_withheld` is `fewer_than_6`. Its drug name, NDC text, amount, page, verification and every other field stay as filed.
- A count of 0, a blank count and a count of 6 or more are published as filed, and `claims_withheld` is empty.
- A small count could be worked out by subtraction from the printed total when a schedule has one small row, or when every small row is a 1 or every small row is a 5. In those cases the detail row with the smallest count of 6 or more is also left out, and its `claims_withheld` is `beside_small`. If two rows share that count, the one on the earlier line is used. If the schedule has no such row, the build stops with a message that names the filing and the schedule, and a person decides.
- If a `total` row or a `below_threshold` row has a claim count of 1 to 5, the build stops with a message that names the filing and the schedule, and a person decides. These rows are never left out silently.

The filing's PDF still prints each count, and every row links to its page. Each figure was read from the PDF and checked (section 3) before it was left out. The checks in section 4 publish only sums and printed totals; no single left-out count is published or can be read from a note, a description or a calculated figure.

The rule covers every table file in the repository, not only `data/`. In `transcriptions/` the `claims_as_filed` cell of a left-out row is empty, and in `verification/` the `claims` cell of the same row is empty. Each of those files has a last column, `claims_withheld`, that holds the same reason as the published files. The PDFs in `sources/` and the page text beside them are the State's public records and are not changed.

The left-out counts are kept in `private/small-counts.csv`: one row for each, with the count as transcribed and the count the second reader wrote. That file is never committed (it is in `.gitignore`). The checks run in one of two ways, and each of `check`, `tieout` and `textcheck` prints a line that says which:

- With the private file, the counts are put back in memory. Every sum is recomputed, the text check and the image-read comparison read every cell, and the rule and its subtraction check run on the real counts. The program stops if the file and the `claims_withheld` marks do not match one to one, or if a count in the file is not 1 to 5 on a `fewer_than_6` row. It also stops if `verification/<state>/<year>/claim-sums.csv` is not what the counts give.
- Without it (a clone of the public repository, and continuous integration), the build and `check` give the same `data/` byte for byte. The sum of a schedule's claim counts is read from `claim-sums.csv`, and the text check and the image-read comparison skip the left-out cells and say how many they skipped. The program stops if a sum in that file cannot match the visible rows.

`claim-sums.csv` has one row for each filing and schedule that has a left-out count: the sum of the claim counts of its rows, not counting the printed total. The maintainer's run rewrites it with `filings340b seal` and stops if the committed copy is different, so the committed copy is always one that was checked against the real counts.

After transcribing a new filing with its counts as read, the maintainer runs `uv run filings340b seal`. It moves the small counts into the private file, empties them in the transcription and the image-read file, and writes `claim-sums.csv`. Running it again changes nothing. A test walks every CSV file under `transcriptions/`, `verification/` and `data/` and fails if a claim cell shows a count of 1 to 5.

In this version the rule leaves out 310 counts as `fewer_than_6` and 0 as `beside_small`. All 310 are Rhode Island Schedule G drug rows (of 2,364 such rows). No Schedule C row has a count of 1 to 5. Every filing with small rows has at least two, and the sum of their counts is more than the number of rows and less than five times that number, so no row is left out under the subtraction case.

**Ohio.** The same rule applies to the prescription counts of Ohio's workbooks (total prescriptions and 340B prescriptions, in each payer column, the total and the Indeterminate column), with these differences, because the filers fill in the totals themselves.

- A small count on a total cell is withheld like any other and nothing stops. When the rule's subtraction guard has no neighbouring cell, the printed total is withheld in its place.
- A percentage is 340B prescriptions over all prescriptions. When either count is withheld, the percentage in the same column is withheld (`claims_withheld` is `reveals_small`, and `amount` is empty), because it would give the count away.
- After the rule, `src/filings340b/ohio_recovery.py` plays a reader who has the published figures and the template's sums, and keeps the set of whole numbers each withheld count may still be. If one could be narrowed to a single number, the printed total of its row (or its smallest visible neighbour) is withheld too, until none can. `tests/test_ohio.py` runs the same reader over `data/line_items.csv` and fails if any withheld count can be recovered. A reader can still narrow some counts to a few values; none can be narrowed to one.
- In the earlier layout of the template, which lists each contract pharmacy in its own block (one workbook), the prescription counts and percentages of a block that holds a count of 1 to 5 are withheld in the cells file, and a test checks that no small prescription count is left outside the form's lines.
- The number of contract pharmacies is a count of pharmacies, not of prescriptions, and is published.

In this version 375 Ohio cells are withheld in 59 workbooks: 153 as `fewer_than_6`, 83 as `beside_small` and 139 as `reveals_small`; a sixtieth workbook, the one with the earlier layout, has its small counts withheld in its cells file only. The values are in `private/small-counts.csv`, which is not committed; `filings340b seal` moves them out of the transcription, the file read and the cells file. A workbook has no claim-sums file: no Ohio rule uses a withheld cell.

## 10. State laws

From version 0.6.0 the dataset has a table of enacted state laws that name the 340B program. It is kept by hand in `laws/laws.csv`, one row per enacted act, and published as `data/state-laws.csv`.

**Where a law comes from.** Each law was found by searching, then read on an official page: the legislature's own site, the state's code site, or a state office such as a secretary of state. `laws/hosts.csv` lists every site the table links to, the state it belongs to and who runs it; the build stops at a link to any other site. Lists kept by others were used only to find laws to look for. Nothing in a row is taken from them.

**What is saved.** `tools/save_law_text.py` saves the words of each official page under `sources/laws/<state>/<law_id>.txt`, and a second official page, where one is used, as `<law_id>.more.txt`. A second page is there for what the first does not print: a bill's history page for its dates, or a code section for its number. `source_form` says how the first page was read: `web page`, `pdf`, or `scanned pdf` for a scan read by character recognition (one law, Tennessee's 2025 act). In the saved text, curly quotation marks and long dashes are made plain, runs of spaces become one space, the line numbers in the margin of a numbered bill are taken off, and an e-mail address or a telephone number is replaced by a marker. Nothing else is changed. Each row carries the SHA-256 fingerprint of its saved text.

**What the build checks.** `src/filings340b/laws.py` stops the build unless, for every row:

- the saved text names the program (340B, or 42 U.S.C. 256b);
- `quote` is in the saved text word for word, and itself names the program;
- a filled `signed_date` or `effective_date` is printed in one of the row's saved texts;
- each link is on a site listed for that state, and each saved text matches its fingerprint;
- each kind is one of the seven in `laws/kinds.csv`.

**What is listed.** An act is listed when it sets a rule about the 340B program: for drug makers, for insurers and pharmacy benefit managers, for covered entities, for Medicaid, or for a state office. These are left out and named in `laws/not-listed.csv`, each with its reason: a budget condition whose named years are over; a section since replaced by a listed one; an act that re-enacts a section with the same 340B words as a listed act; an act that names 340B only inside a definition; and a law that came up in the search and whose official text was not read.

**Dates and numbers.** A date is filled only where a saved page prints it as that date. Where an act takes effect a set number of days after a session ends, or on passage, and the page prints no calendar date, `effective_date` is blank, `limits` says how the act takes effect, and `source_note` says that the page prints no date. A bill number or an act number is blank where the official page does not print it. `session_year` is the year of the session that passed the act.

**The words in a row.** `summary`, `binds`, `limits` and `enforcement` are written by hand from the saved text, in plain words. They describe what the text says. They do not say whether a law is in force today, how a court has read it, or what anyone should do about it. `source_note` is kept apart from them: it is about the saved pages, not the law, and says what a page does not print or how it was read.

**What the table does not cover.** Court cases about these laws; bills that did not pass; federal law and guidance; rules made by agencies under these laws. An act amended later is described as enacted, with a note in `limits` where a saved page shows the later change.

**How complete it is.** The search covered the fifty states and the District of Columbia. Nothing was found on official pages for thirteen of them (the README names them). A state with no row is a state where none was found. For comparison, the National Conference of State Legislatures wrote in March 2026 that 19 states enacted 22 bills on 340B in 2025; this table has 18 laws from 2025 sessions, in 17 states. The two were not matched bill for bill.

**Keeping it current.** `retrieved` is the day the official pages were saved. A page that changes later is not picked up until the law is read again.
