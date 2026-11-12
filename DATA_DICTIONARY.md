# Data dictionary

Every file in `data/` is UTF-8 with a header row and `\n` line ends. `340b-state-filings.json` holds the same tables in one document, with `dataset_version` and `license`. Columns ending `_as_filed` are copied from the filing without correction.

Three states are in the dataset, and each record names the form it was made on (`filings.csv`, column `form`). Rhode Island's form prints schedule letters and line numbers. Vermont's page and Minnesota's tables print none, so for those states `schedule` and `line` in `line_items.csv` hold short keys assigned by this dataset (listed under `line_items.csv` below). A column that does not apply to a form is blank for that form's records; a blank is never a zero.

Rhode Island and Vermont records are an entity's own filing. Minnesota's are not: they are the figures the Minnesota Department of Health printed about the covered entities it names, in its report to the legislature, one figure each (the report is titled 2025 and covers 2024 data). For Minnesota, "as filed" in a column name means as printed in the State's report, and a "filing" is one printed row of the report's Appendix Table 6.1, or the statewide record. `filings.csv` column `record_kind` tells the three kinds apart.

## filings.csv

One row per filing.

| Column | Meaning |
|---|---|
| `filing_id` | State, reporting year and a short name, for example `ri-2025-east-bay-cap`. Minnesota: `mn-2024-<key>`, with a key assigned by this dataset from the printed name, and `mn-2024-statewide` |
| `entity_id` | The filer, constant across years |
| `state` | Two-letter state code |
| `reporting_year` | The year the filing covers. Rhode Island: the calendar year. Vermont: the year of the period the page prints as `FY2025` (see `period_as_filed`). Minnesota: the data year, 2024; the report's title says 2025 |
| `form_revision` | The form and revision, or the document's title, as printed on the pages. Minnesota: `340B Covered Entity Report, 2025` |
| `reporting_basis_as_filed` | Cash or accrual, as printed on the cover page. Blank for Vermont: its page prints none |
| `recertification_date_as_filed` | As printed on the cover page. Blank for Vermont: its page prints none |
| `corporate_address_as_filed` | As printed on the cover page. Blank for Vermont: its page prints none |
| `source_url` | Where the PDF was retrieved from |
| `source_file` | The PDF's file name in `sources/` |
| `retrieved_at` | When it was retrieved (UTC) |
| `pdf_sha256` | SHA-256 of the archived PDF |
| `pdf_bytes` | Size of the PDF |
| `page_count` | Pages in the PDF |
| `scanned` | `true` when the PDF has no text layer |
| `form` | The form the filing was made on: `ri-oag-340b` (Rhode Island's Form RIOAG-340B), `vt-gmcb-340b-financial` (Vermont's 340B Program Financial Reporting Detail) or `mn-mdh-340b-report` (Minnesota's report to the legislature, Appendix Tables 6.1 and 6.2). It decides the rows, units, sums and measures that apply |
| `status_as_filed` | The status the page prints. Vermont: `draft`. Blank for Rhode Island: its form prints none |
| `status_notice_as_filed` | The notice that carries the status, quoted exactly as printed (its line break written as a space). Blank for Rhode Island |
| `period_as_filed` | The period the page prints. Vermont: `FY2025`. Blank for Rhode Island |
| `submission_as_filed` | The line the page prints about its submission. Vermont: `As Submitted to the Green Mountain Care Board in 2026`. Blank for Rhode Island |
| `cover_page_url` | The state web page that lists the document, when the manifest records one (Vermont). Blank for Rhode Island and Minnesota |
| `record_kind` | `filing`: an entity's own filing (Rhode Island, Vermont). `state_report_row`: one printed row of Minnesota's Table 6.1, a figure the State published about one entity. `state_report_totals`: the one record (`mn-2024-statewide`) that holds Minnesota's Table 6.2 and the report's running text around the tables; it is not an entity |

## entities.csv

One row per filer.

| Column | Meaning |
|---|---|
| `entity_id` | The filer |
| `state` | Two-letter state code |
| `entity_type` | `health_center` or `hospital` (Rhode Island); `hospital` (Vermont). Minnesota: `hospital` when the printed type (`entity_type_as_filed`) contains the word Hospital, `other` for any other printed type, and `state_total` for the statewide record. Nothing is read into an abbreviation |
| `name_as_filed` | The covered entity name on the cover page (Vermont: the name printed as the page's heading; Minnesota: the name in the Covered Entity Name column, with a wrapped name joined by single spaces). Blank for `mn-statewide`: the report prints no name for it |
| `opais_ids_as_filed` | The 340B ID numbers on the cover page. Blank for Vermont and Minnesota: they print none |
| `entity_type_as_filed` | Minnesota: the 340B Covered Entity Type column, as printed (for example `Disproportionate Share Hospital`, `CHD Treatment Center`). Blank for Rhode Island, Vermont and `mn-statewide` |
| `city_as_filed` | Minnesota: the City column, as printed. Blank for Rhode Island, Vermont and `mn-statewide` |

## line_items.csv

One row per printed row of a schedule. This is the dataset.

| Column | Meaning |
|---|---|
| `filing_id` | The filing |
| `schedule` | Rhode Island: `A` to `I`. Vermont: a key assigned by this dataset, because the page prints no schedule letters: `payments`, `acquisition`, `expenses`, `result`, or `page_note` for text the page prints below the figures. Minnesota: `table_6_1` (an entity's two figures), `table_6_2` (the totals table), or `page_note` (the report's running text around the tables) |
| `line` | Rhode Island: the printed line number. `under_5000` is the form's one row for items each below $5,000. `total` is the printed total row. `12@p9` is a line number the filing prints a second time, with the page. `u1`, `u2` are rows printed without a number. Vermont: a key assigned by this dataset, because the page prints no line numbers (see the table below). Minnesota: a key assigned by this dataset (see below). The printed label is in `label_as_filed` |
| `row_kind` | `detail`, `below_threshold` or `total` |
| `label_as_filed` | The row's printed description (Schedules A, C, F, H, I and total rows). Vermont: the label the page prints on every row; for a `page_note` row, the text the page prints. Minnesota: the entity name as printed (`table_6_1` rows) or the Dimension as printed (`table_6_2` rows); for a `page_note` row, the text exactly as printed, a wrapped line joined with a space |
| `name_as_filed` | The vendor, pharmacy, category or drug named on the row (Schedules B, D, E, G) |
| `normalized_vendor` | One spelling for the company named (Schedules B, D, E); blank when the row names several companies or none |
| `category` | Schedule E only: `third_party_administrator`, `referral_capture`, `consulting_audit` or `other` |
| `description_as_filed` | Schedule E's description cell; Schedule I's explanation cell. Minnesota: the column heading the figure is printed under (`Net 340B Revenue ($)`, `% of Statewide Net 340B Revenue`, `% of Total`) |
| `ndc_as_filed` | Schedule G's National Drug Code cell, punctuation kept |
| `amount_as_filed` | The amount as printed, without the `$` sign. `-` is a printed dash. Blank is an empty cell. Parentheses, a minus sign and a `%` sign are kept as printed. `N/R` and `N/A` are kept as printed |
| `amount` | The amount as a number, at the scale filed. A dash is `0`. Blank when the cell is empty or prints words (`N/A`, `N/R`). A percentage is the number without its `%` sign (`-33.30%` is `-33.30`); its `unit` says it is a percentage |
| `unit` | What the `amount` is: `usd` (dollars), `percent` (a percentage, as printed: Minnesota's `26.1%` is `26.1`), `count` (a number of items; no `amount` is in this unit today, claim counts are in `claims`; the unit appears in `discrepancies.csv`), or `none` (the row carries no figure: a Schedule I answer, or text printed on the page). The unit is fixed by the form and the row's schedule and line |
| `claims_as_filed` | The claim count as printed (Schedules C and G). Empty when `claims_withheld` is not empty |
| `claims` | The claim count as a whole number. Empty when `claims_withheld` is not empty |
| `claims_withheld` | Empty when the claim count is published. `fewer_than_6`: the count on this row is 1 to 5 and is not republished; the filing's PDF prints it on the page in `page`. `beside_small`: the count is 6 or more and is not republished, because it would let a reader work out a `fewer_than_6` count from the printed total. See METHODS.md section 9 |
| `answer_as_filed` | Schedule I: `YES`, `NO`, `YES and NO`, or blank |
| `page` | The PDF page the row is printed on; the first page is 1. Minnesota: 42 to 45 |
| `verification` | `text_and_image`, `two_image_reads`, `adjudicated` or `unreadable`. See METHODS.md section 3 |
| `note` | A note the filer printed beside the row (`Printed note: …`), or what was seen when a row was adjudicated |

### Vermont's keys

Vermont's page prints these 12 figure rows, in this order. The keys are assigned by this dataset; the labels are as printed.

| `schedule` | `line` | `label_as_filed` | `unit` |
|---|---|---|---|
| `payments` | `in_house_pharmacy` | In-House Pharmacy Dispensed | `usd` |
| `payments` | `contract_pharmacy` | Contract Pharmacy Dispensed | `usd` |
| `payments` | `administered_paid_separately` | Administered Drugs Paid Separately | `usd` |
| `payments` | `administered_bundled` | Administered Drugs Bundled Payments | `usd` |
| `payments` | `total` | Total 340B Payments Received | `usd` |
| `acquisition` | `cost` | 340B Prescription Drug Acquisition Costs | `usd` |
| `expenses` | `contract_pharmacies` | Payments Made to Contract Pharmacies | `usd` |
| `expenses` | `internal` | Internal 340B Program Expenses | `usd` |
| `expenses` | `outside_vendors` | Payments Made to Outside Vendors | `usd` |
| `expenses` | `total` | Total 340B Expenses | `usd` |
| `result` | `net_revenue` | 340B Net Revenue | `usd` |
| `result` | `operating_margin` | 340B Operating Margin | `percent` |

The page prints "(payments received minus acquisition costs minus expenses)" under 340B Net Revenue; it is kept in that row's `note`. Text printed below the figures is a `page_note` row, `note_1`, `note_2` and so on, with the text in `label_as_filed`. Every Vermont row is on page 1. Rhode Island's rows have unit `usd`, except Schedule I rows, which are `none`.

### Minnesota's keys

Every entity record (`state_report_row`) has these two rows, on the page the entity's row is printed on. Neither key is printed by the report; `label_as_filed` is the entity's name and `description_as_filed` the column heading.

| `schedule` | `line` | Column printed | `unit` |
|---|---|---|---|
| `table_6_1` | `net_revenue` | Net 340B Revenue ($) | `usd` |
| `table_6_1` | `pct_of_statewide` | % of Statewide Net 340B Revenue | `percent` |

The statewide record (`state_report_totals`) has, for each of the six rows of Table 6.2, a `net_revenue` row and a `pct_of_total` row. The line is the dimension key and the column key joined by an underscore, for example `top_unadjusted_net_revenue` and `total_adjusted_pct_of_total`. Unadjusted rows are on page 44 and adjusted rows on page 45.

| Dimension key | `label_as_filed` | `row_kind` |
|---|---|---|
| `top_unadjusted` | Top 25, unadjusted | `detail` |
| `remaining_unadjusted` | Remaining 156, unadjusted | `detail` |
| `total_unadjusted` | Total, unadjusted | `total` |
| `top_adjusted` | Top 25, adjusted | `detail` |
| `remaining_adjusted` | Remaining 156, adjusted | `detail` |
| `total_adjusted` | Total, adjusted | `total` |

The statewide record also has six `page_note` rows, `note_1` to `note_6`, in the order the text is printed: the paragraph above Table 6.1 (page 42), the title of Table 6.1 (42), the "Source:" line under Table 6.1 (44), the paragraph above Table 6.2 (44), the title of Table 6.2 (44) and the "Source:" line under Table 6.2 (45). The text is in `label_as_filed`. The table's printed order is not a column: nothing in the data is a rank or a place in an order.

## discrepancies.csv

One row per place where two figures in one filing differ.

| Column | Meaning |
|---|---|
| `filing_id` | The filing |
| `rule` | The rule's short name, for example `B.total=A1`. Minnesota's rules compare figures across the report's records and sit on the record they describe (METHODS.md section 4) |
| `basis` | `form` when the form itself says the two figures agree; `comparison` when it does not and the figures are only shown together |
| `description` | The rule in words |
| `expected` | The figure the rule is measured against |
| `filed` | The figure it is compared with |
| `difference` | `filed` minus `expected` |
| `unit` | The unit of `expected`, `filed` and `difference`: `usd`, `percent` (percentage points) or `count` |
| `note` | What the filing prints. Never a reason |

## measures.csv

One row per filing and measure.

| Column | Meaning |
|---|---|
| `filing_id` | The filing |
| `measure` | `gross_margin`, `external_cost`, `external_share_of_margin`, or `schedule_e_<category>` (Rhode Island only: Vermont's page has no Schedule E). Minnesota has no measures: its tables print no acquisition cost and no payments to pharmacies or vendors, so this file has no Minnesota rows |
| `formula` | The calculation in words, naming the rows of the filing's own form |
| `value` | The result; blank when it cannot be calculated |

## vendors.csv

One row per name as filed that has a normalized name.

| Column | Meaning |
|---|---|
| `normalized_name` | The one spelling used in `line_items.normalized_vendor` |
| `vendor_type` | `wholesaler`, `distributor`, `manufacturer`, `pharmacy`, `program_vendor` or `unclassified` |
| `alias_as_filed` | A name exactly as a filing prints it |
| `note` | The reason for a mapping that is more than a spelling difference |

## attachments.csv

One row per run of pages a filer added to the form. These pages are archived in the PDF and are not transcribed.

| Column | Meaning |
|---|---|
| `filing_id` | The filing |
| `first_page`, `last_page` | The page range |
| `kind` | `cover_letter`, `notes`, `appendix`, `supplemental_detail`, `blank_page`, `narrative` or `other`. `narrative` is a separate PDF the state lists beside the filing (Vermont's 340B Narrative Reporting) |
| `title_as_filed` | The first heading on the pages, if any. Blank for Vermont's narratives |
| `note` | One sentence saying what the pages are |
| `document_file` | When the attachment is a separate PDF: its file name in `sources/`. Blank when the pages are inside the filing's own PDF (Rhode Island) |
| `document_url` | The address that separate PDF was retrieved from |
| `document_cover_page_url` | The state web page that lists it |
| `document_sha256` | SHA-256 of the archived PDF |
| `document_bytes` | Size of the PDF. Its page count is `last_page` (`first_page` is 1) |

## Working files

These are not part of the published data, but they are in the repository.

- `transcriptions/<state>/<year>/<filing_id>.csv`: the columns are those of the transcription, in the order the file has them. A file that leaves out any claim count has a last column, `claims_withheld`, with the same values as in `line_items.csv`. On such a row `claims_as_filed` is empty. A file with no left-out count has no such column.
- `verification/<state>/<year>/<filing_id>.image-read.csv`: `page`, `schedule`, `line`, `amount`, `claims`, `answer`, and the same last column `claims_withheld` when a row is left out. On such a row `claims` is empty.
- `verification/<state>/<year>/claim-sums.csv`: `filing_id`, `schedule`, and `claim_sum`, the sum of the claim counts of the schedule's rows, not counting the printed total. It has a row for each filing and schedule that has a left-out count.
- `private/small-counts.csv` (never committed): `filing_id`, `schedule`, `line`, `claims_as_filed` (the count as transcribed) and `image_read_claims` (the count the second reader wrote).

## external-share-light.svg, external-share-dark.svg

The chart in the README, drawn from `measures.csv` by the same build. It shows the Rhode Island filings only; its title and its groups (health centers, hospitals) are Rhode Island's. Minnesota is not in the chart.
