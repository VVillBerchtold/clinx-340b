# Data dictionary

Every file in `data/` is UTF-8 with a header row and `\n` line ends. `340b-state-filings.json` holds the filings tables in one document, with `dataset_version` and `license`; `340b-state-laws.json` does the same for the state laws. Columns ending `_as_filed` are copied from the filing without correction.

Five states are in the dataset, and each record names the form it was made on (`filings.csv`, column `form`). Rhode Island's form prints schedule letters and line numbers. Vermont's page, Minnesota's tables and Idaho's report print none, so for those states `schedule` and `line` in `line_items.csv` hold short keys assigned by this dataset (listed under `line_items.csv` below). A column that does not apply to a form is blank for that form's records; a blank is never a zero.

Rhode Island and Vermont records are an entity's own filing. Minnesota's are not: they are the figures the Minnesota Department of Health printed about the covered entities it names, in its report to the legislature, one figure each (the report is titled 2025 and covers 2024 data). For Minnesota, "as filed" in a column name means as printed in the State's report, and a "filing" is one printed row of the report's Appendix Table 6.1, or the statewide record. `filings.csv` column `record_kind` tells the three kinds apart.

Ohio's records are each covered entity's own report, posted by the Department of Health as an Excel workbook. For Ohio, "as filed" means as the workbook stores it, and a "page" is the template sheet (page 1).

Idaho's one record is the State Controller's report of statewide totals; the entities' own filings are confidential and the report names none of them. For Idaho, "as filed" means as printed in that report.

## filings.csv

One row per filing.

| Column | Meaning |
|---|---|
| `filing_id` | State, reporting year and a short name, for example `ri-2025-east-bay-cap`. Minnesota: `mn-2024-<key>`, with a key assigned by this dataset from the printed name, and `mn-2024-statewide`. Idaho: `id-2025-statewide` |
| `entity_id` | The filer, constant across years |
| `state` | Two-letter state code |
| `reporting_year` | The year the filing covers. Rhode Island: the calendar year. Vermont: the year of the period the page prints as `FY2025` (see `period_as_filed`). Minnesota: the data year, 2024; the report's title says 2025. Idaho: the calendar year the report covers |
| `form_revision` | The form and revision, or the document's title, as printed on the pages. Minnesota: `340B Covered Entity Report, 2025`. Idaho: `Idaho 340B Drug Pricing Program, Inaugural Report, Calendar Year 2025` |
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
| `form` | The form the filing was made on: `ri-oag-340b` (Rhode Island's Form RIOAG-340B), `vt-gmcb-340b-financial` (Vermont's 340B Program Financial Reporting Detail) `mn-mdh-340b-report` (Minnesota's report to the legislature, Appendix Tables 6.1 and 6.2) `id-sco-340b-report` (the Idaho State Controller's statewide report) or `oh-odh-340b-report` (the Ohio Department of Health's covered entity reporting template, an Excel workbook). It decides the rows, units, sums and measures that apply |
| `status_as_filed` | The status the page prints. Vermont: `draft`. Blank for Rhode Island: its form prints none |
| `status_notice_as_filed` | The notice that carries the status, quoted exactly as printed (its line break written as a space). Blank for Rhode Island |
| `period_as_filed` | The period the page prints. Vermont: `FY2025`. Blank for Rhode Island |
| `submission_as_filed` | The line the page prints about its submission. Vermont: `As Submitted to the Green Mountain Care Board in 2026`. Blank for Rhode Island |
| `cover_page_url` | The state web page that lists the document, when the manifest records one (Vermont). Blank for Rhode Island, Minnesota and Idaho |
| `record_kind` | `filing`: an entity's own filing (Rhode Island, Vermont). `state_report_row`: one printed row of Minnesota's Table 6.1, a figure the State published about one entity. `state_report_totals`: the one record (`mn-2024-statewide`) that holds Minnesota's Table 6.2 and the report's running text around the tables; it is not an entity. Idaho's only record (`id-2025-statewide`) is of this kind: the whole statewide report |
| `other_entity_ids` | Ohio: when a workbook names more than one 340B ID, it is one filing for all of them. `entity_id` is the first ID (the one in the file name) and this column lists the others, separated by `; `. Blank everywhere else |

## entities.csv

One row per filer.

| Column | Meaning |
|---|---|
| `entity_id` | The filer |
| `state` | Two-letter state code |
| `entity_type` | `health_center` or `hospital` (Rhode Island); `hospital` (Vermont). Minnesota: `hospital` when the printed type (`entity_type_as_filed`) contains the word Hospital, `other` for any other printed type, and `state_total` for the statewide record. Idaho: `state_total`. Nothing is read into an abbreviation |
| `name_as_filed` | The covered entity name on the cover page (Vermont: the name printed as the page's heading; Minnesota: the name in the Covered Entity Name column, with a wrapped name joined by single spaces). Blank for `mn-statewide` and `id-statewide`: the reports print no name for them |
| `opais_ids_as_filed` | The 340B ID numbers on the cover page. Blank for Vermont and Minnesota: they print none |
| `entity_type_as_filed` | Minnesota: the 340B Covered Entity Type column, as printed (for example `Disproportionate Share Hospital`, `CHD Treatment Center`). Blank for Rhode Island, Vermont and `mn-statewide` |
| `city_as_filed` | Minnesota: the City column, as printed. Blank for Rhode Island, Vermont and `mn-statewide` |
| `hrsa_name` | Ohio only: the name HRSA's public list of covered entities holds for the ID, with the site's subdivision name in brackets when it has one. It is HRSA's name, read on the day in `hrsa_list_date`; Ohio's workbooks print no entity name, so `name_as_filed` is blank for Ohio. Blank when HRSA's list does not hold the ID, and blank for every other state |
| `hrsa_id_spelling` | Ohio only: the ID as HRSA writes it (`CAH361300-00`), where the workbook's file name writes `CAH36130000`. Blank when `hrsa_match` says the ID is not in the list, and for every other state |
| `hrsa_list_date` | Ohio only: the day HRSA's list was saved (`2026-11-11`). Blank for every other state |
| `hrsa_match` | Ohio only: how the ID was found. `exact`; `with or without the 00 ending` (HRSA's spelling ends in `-00` and the file name's does not, or the other way round); `found by the ID typed in the workbook` (the file name's ID is not in the list and the ID typed in the workbook is); `not in HRSA's list` (neither is, and the name is blank). Blank for every other state |
| `opais_ids_as_filed` (Ohio) | The 340B ID typed in the workbook, as typed. The ID in the file name is in `entity_id` and in `filings.csv` `source_file`; the two differ in 37 workbooks and both are kept |

## line_items.csv

One row per printed row of a schedule. This is the dataset.

| Column | Meaning |
|---|---|
| `filing_id` | The filing |
| `schedule` | Rhode Island: `A` to `I`. Vermont: a key assigned by this dataset, because the page prints no schedule letters: `payments`, `acquisition`, `expenses`, `result`, or `page_note` for text the page prints below the figures. Minnesota: `table_6_1` (an entity's two figures), `table_6_2` (the totals table), or `page_note` (the report's running text around the tables). Idaho: `key_highlights`, `key_financial_metrics`, `submissions`, `acquisition_cost`, `payments_received`, `contract_pharmacy_payments`, `claims`, `savings_use`, or `page_note` (see below) |
| `line` | Rhode Island: the printed line number. `under_5000` is the form's one row for items each below $5,000. `total` is the printed total row. `12@p9` is a line number the filing prints a second time, with the page. `u1`, `u2` are rows printed without a number. Vermont: a key assigned by this dataset, because the page prints no line numbers (see the table below). Minnesota and Idaho: a key assigned by this dataset (see below). The printed label is in `label_as_filed` |
| `row_kind` | `detail`, `below_threshold` or `total` |
| `label_as_filed` | The row's printed description (Schedules A, C, F, H, I and total rows). Vermont: the label the page prints on every row; for a `page_note` row, the text the page prints. Minnesota: the entity name as printed (`table_6_1` rows) or the Dimension as printed (`table_6_2` rows); for a `page_note` row, the text exactly as printed, a wrapped line joined with a space. Idaho: the row's printed label (a payer type, a savings use, a tile's caption, a bar's label), the same way for a `page_note` row |
| `name_as_filed` | The vendor, pharmacy, category or drug named on the row (Schedules B, D, E, G) |
| `normalized_vendor` | One spelling for the company named (Schedules B, D, E); blank when the row names several companies or none |
| `category` | Schedule E only: `third_party_administrator`, `referral_capture`, `consulting_audit` or `other` |
| `description_as_filed` | Schedule E's description cell; Schedule I's explanation cell. Minnesota: the column heading the figure is printed under (`Net 340B Revenue ($)`, `% of Statewide Net 340B Revenue`, `% of Total`). Idaho: the column heading too (for example `Aggregate Payments Received`, `% of Total Payments`); blank for a tile or a chart label, which have none |
| `ndc_as_filed` | Schedule G's National Drug Code cell, punctuation kept |
| `amount_as_filed` | The amount as printed, without the `$` sign. `-` is a printed dash. Blank is an empty cell. Parentheses, a minus sign and a `%` sign are kept as printed. `N/R` and `N/A` are kept as printed |
| `amount` | The amount as a number, at the scale filed. A dash is `0`. Blank when the cell is empty or prints words (`N/A`, `N/R`). A percentage is the number without its `%` sign (`-33.30%` is `-33.30`); its `unit` says it is a percentage |
| `unit` | What the `amount` is: `usd` (dollars), `percent` (a percentage, as printed: Minnesota's `26.1%` is `26.1`), `count` (a number of items: Idaho's claim totals, submissions, child sites and covered entities. Rhode Island's claim counts are in `claims`, beside the amount on the same row), or `none` (the row carries no figure: a Schedule I answer, or text printed on the page, which for Idaho includes a rounded tile such as `$812.9M`, kept in `answer_as_filed`). The unit is fixed by the form and the row's schedule and line |
| `claims_as_filed` | The claim count as printed (Schedules C and G). Empty when `claims_withheld` is not empty |
| `claims` | The claim count as a whole number. Empty when `claims_withheld` is not empty |
| `claims_withheld` | Empty when the figure is published. `reveals_small` is used by Ohio only (see Ohio's keys). `fewer_than_6`: the count on this row is 1 to 5 and is not republished; the filing's PDF prints it on the page in `page`. `beside_small`: the figure is 6 or more (or a printed total) and is not republished, because it would let a reader work out a `fewer_than_6` count from the printed total or the other counts. See METHODS.md section 9 |
| `answer_as_filed` | Schedule I: `YES`, `NO`, `YES and NO`, or blank |

| `page` | The PDF page the row is printed on; the first page is 1. Minnesota: 42 to 45. Idaho: 2 to 7 |
| `verification` | `text_and_image`, `two_image_reads`, `two_file_reads` (a workbook cell read by two different programs that agree), `adjudicated` or `unreadable`. See METHODS.md section 3 |
| `note` | A note the filer printed beside the row (`Printed note: …`), or what was seen when a row was adjudicated |
| `source_cell` | Ohio only: the address of the workbook cell the row was read from (`I19`). Rows are found by the label printed beside them, so a workbook whose filer inserted rows names the cell it actually used. Blank for every other state |

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

### Idaho's keys

The one record (`id-2025-statewide`) has a row for every cell the report prints. None of these keys is printed by the report; `label_as_filed` is the row's printed label and `description_as_filed` the column heading.

| `schedule` | What it is | `line` | `unit` |
|---|---|---|---|
| `key_highlights` | The four tiles under KEY HIGHLIGHTS | `total_claims`, `covered_entities` | `count` |
| `key_highlights` | | `payments_received`, `savings_to_community`: rounded figures such as `$812.9M`, kept as text in `answer_as_filed` | `none` |
| `key_financial_metrics` | The four labels of the chart | `contract_pharmacy_payments`, `acquisition_cost`, `savings_utilized`, `payments_received` | `usd` |
| `submissions` | The submissions table | `received_count`, `child_sites_count`, `complete_count` | `count` |
| `submissions` | | `complete_pct`: the percentage printed in the same cell as `complete_count` (`62 (100%)`) | `percent` |
| `submissions` | | `received_notes`, `complete_notes`: the words in the Notes column, in `answer_as_filed` | `none` |
| `acquisition_cost`, `payments_received`, `contract_pharmacy_payments` | The three tables of dollars by payer type | `<payer>_amount` | `usd` |
| `claims` | Number of Claims by Payer Type | `<payer>_claims` | `count` |
| the four tables above | Their percentage columns | `<payer>_pct` | `percent` |
| `savings_use` | 340B Savings Utilization | `<use>_amount` | `usd` |
| `savings_use` | | `<use>_pct` | `percent` |
| `page_note` | A sentence that states a figure, the chart's title, or the labels of its value axis, in `label_as_filed` | `note_1`, `note_2`, ... | `none` |

`<payer>` is `commercial`, `medicare`, `medicaid`, `self_pay`, `other`, `uninsured` or `total` (the TOTAL row, `row_kind` `total`). `<use>` is `under_reimbursement`, `uncompensated_care`, `patient_financial_assistance`, `prescription_assistance`, `community_health`, `subsidized_services`, `health_professional_education`, `access_barriers`, `other_uses` or `total`; the printed wording of each is in `label_as_filed`.

### Ohio's keys

Each of the 241 workbooks is one filing on the form `oh-odh-340b-report` (the Ohio Department of Health's ORC 3701.88 covered entity reporting template). The workbook has no pages: the template sheet is page 1 and every row says `page` 1. Every key is assigned by this dataset. `label_as_filed` is the label the workbook prints beside the row and `description_as_filed` is the heading of the column; `source_cell` is the cell. A prescription count is kept in the claim columns (`claims_as_filed`, `claims`) so that the small-number rule can apply to it; every other figure is in `amount_as_filed` and `amount`, exactly as the workbook stores it (`602.56000000000006` is kept as stored). A cell that holds words or an error where a figure belongs (`N/A`, `#DIV/0!`) keeps the words and has no amount. A formula cell is read as its stored result; when the file stores none, the row's `note` says so. A percentage row whose cell is formatted as a percentage stores a fraction of one, and its `note` says so.

| `schedule` | What it is | `line` | `unit` |
|---|---|---|---|
| `in_house_acquisition_cost`, `in_house_payments_received` | Drugs dispensed in house: aggregate acquisition cost and payments received | `<payer>` | `usd` |
| `in_house_rx_all`, `in_house_rx_340b` | Total prescriptions, and 340B prescriptions | `<payer>` | `count` |
| `in_house_rx_pct` | Percentage of prescriptions that were 340B | `<payer>` | `percent` |
| `contract_acquisition_cost`, `contract_payments_received` | Contract pharmacies: the same, in dollars | `<payer>`, `indeterminate` | `usd` |
| `contract_rx_all`, `contract_rx_340b`, `contract_rx_pct` | Contract pharmacies: counts and the percentage | `<payer>`, `indeterminate` | `count`, `percent` |
| `administered_acquisition_cost`, `administered_payments_actual`, `administered_payments_estimated`, `administered_payments_total` | Administered drugs: dollars | `<payer>` | `usd` |
| `administered_rx_all`, `administered_rx_340b`, `administered_rx_pct` | Administered drugs: counts and the percentage | `<payer>` | `count`, `percent` |
| `costs` | Payments to outside parties and the entity's own 340B costs | `contract_pharmacies`, `third_party_administrators`, `consultants`, `software_it`, `other_external`, `staffing`, `internal_it`, `other_internal` | `usd` |
| `contract_pharmacies` | The entity's number of contract pharmacies | `count`: a number of pharmacies, not of prescriptions, so it is in `amount` | `count` |
| `contract_pharmacy_notes` | The explanation asked for when "Indeterminate" is used | `indeterminate_explanation` | `none` |
| `identity` | The reporting period, the HRSA ID as typed (`hrsa_id`, or `id_prefix` and `id_number` when the workbook splits it) and the NPIs | `reporting_period`, `hrsa_id`, `id_prefix`, `id_number`, `npi_1`, `npi_2`, ... | `none` |
| `uses` | How the entity used 340B income | `program_1_description`, `program_1_amount`, ..., `equipment_1_description`, `equipment_1_amount`, ..., `other_uses_description`, `other_uses_amount`, `narrative`, `alternative_narrative` | `usd` for amounts, otherwise `none` |
| `other_cells` | A cell a filer typed outside the template's cells, kept as text in `answer_as_filed` | `cell_<address>` | `none` |

`<payer>` is `commercial`, `medicare`, `medicaid`, `other_third_party`, `uninsured` or `total` (the TOTAL cell, `row_kind` `total`). In the contract pharmacy tables the template's total leaves out `indeterminate`. A cell a filer typed beside the template's columns in one of these rows is the line `cell_<column letter>` of the row's schedule.

The three contact cells (name, e-mail address, telephone number) are never copied into any file; the cells files show `[contact detail withheld]` in their place, and any e-mail address or telephone number anywhere is replaced by a marker.

A withheld Ohio cell has an empty `amount_as_filed`, `amount`, `claims_as_filed` and `claims` and a `claims_withheld` reason: `fewer_than_6` (the count is 1 to 5), `beside_small` (a count or total withheld so that a small count cannot be worked out from the printed sums) or `reveals_small` (a percentage that would give a withheld count away; its figure is the percentage, in `amount`, and is empty). Rows that print words keep them.

## discrepancies.csv

One row per place where two figures in one filing differ.

| Column | Meaning |
|---|---|
| `filing_id` | The filing |
| `rule` | The rule's short name, for example `B.total=A1`. Minnesota's rules compare figures across the report's records and sit on the record they describe (METHODS.md section 4). Idaho's are all on its one record |
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
| `measure` | `gross_margin`, `external_cost`, `external_share_of_margin`, or `schedule_e_<category>` (Rhode Island only: Vermont's page has no Schedule E). Minnesota has no measures: its tables print no acquisition cost and no payments to pharmacies or vendors, so this file has no Minnesota rows. Idaho has none either: its record is a statewide total |
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

## state-laws.csv

One row per enacted state law that names the 340B program. Kept by hand in `laws/laws.csv`; METHODS.md section 10 says how. Rows are in order of state, session year and `law_id`.

| Column | Meaning |
|---|---|
| `law_id` | The row's name: state, session year, then the bill number or, where the official page prints no bill number, the chapter or code section. Example: `co-2025-sb25-071`, `mt-2019-ch215` |
| `state` | Two-letter state code |
| `kinds` | One or more of the seven kinds in `laws/kinds.csv`, joined by `\|`, in that file's order. In the JSON file this is a list |
| `title` | The act's short title, where the act gives itself one. Otherwise blank |
| `citation` | Where the law sits in the state's code, or in the act where the page prints no code number |
| `bill` | The bill as the official page prints it. Blank where the page does not print it |
| `session_year` | The year of the session that passed the act |
| `act` | The act, chapter or public law number as printed. Blank where the page does not print it |
| `signed_date` | The day the act was signed or approved, `YYYY-MM-DD`. Blank unless a saved page prints it |
| `effective_date` | The day the act, or its 340B part, took effect. Blank unless a saved page prints it as that |
| `binds` | Who the law puts a duty on |
| `summary` | What the law does, in plain words |
| `limits` | What it leaves out, and when it starts or ends |
| `enforcement` | Penalties, and who enforces. Blank where the text gives none |
| `quote` | One passage from the law that names the program, word for word as in the saved text |
| `source_url` | The official page the law was read on |
| `source_form` | How that page was read: `web page`, `pdf` or `scanned pdf` |
| `source_text`, `source_sha256` | The saved text of that page in this repository, and its SHA-256 fingerprint |
| `more_url`, `more_text`, `more_sha256` | A second official page (a bill's history, or a code section), its saved text and fingerprint. All three blank where there is none |
| `source_note` | A note about the saved pages themselves, for anyone checking a row: for example that a page prints no effective date, or prints an act's chapter and not its bill number. Blank where there is nothing to note |
| `retrieved` | The day the pages were saved |

## state-laws-not-listed.csv

Laws that came up and are not in the table. Kept by hand in `laws/not-listed.csv`.

| Column | Meaning |
|---|---|
| `state` | Two-letter state code |
| `name` | The law, as it is usually cited |
| `reason` | The reason it is not listed, in a sentence |
| `source_url` | Its official page, where one was read. Otherwise blank |

## 340b-state-laws.json

`dataset_version`, `license`, then `kinds` (the seven kinds, each with a label and a description), `laws` (the rows of `state-laws.csv`, with `kinds` as a list) and `not_listed`, then `sites`: each official site a law links to, with its `host`, its `state` and `owner`, the office that publishes it.

## Working files

These are not part of the published data, but they are in the repository.

- `transcriptions/<state>/<year>/<filing_id>.csv`: the columns are those of the transcription, in the order the file has them. A file that leaves out any claim count has a last column, `claims_withheld`, with the same values as in `line_items.csv`. On such a row `claims_as_filed` is empty. A file with no left-out count has no such column.
- `verification/oh/2025/<filing_id>.file-read.csv`: for an Ohio workbook, the second read (made by a different program) in the layout of an image read: `page`, `schedule`, `line`, `amount`, `claims`, `answer`, and the same last column when a cell is withheld.
- `sources/oh/2025/manifest.csv`, `cells/<name>.csv` (`sheet`, `cell`, `value`: every filled cell of the template sheet, contact cells masked and withheld cells marked), `workbook-contents.csv` (every sheet of every workbook by name, state and number of filled cells) and `workbook-objects.csv` (every picture, drawing, embedded object, macro or link found inside a workbook). The workbooks themselves are not committed.
- `reference/hrsa-oh-extract.csv` and `.source.toml`: what HRSA's list holds for each Ohio ID, with the day of the list and the size and SHA-256 of the export it was made from.
- `verification/<state>/<year>/<filing_id>.image-read.csv`: `page`, `schedule`, `line`, `amount`, `claims`, `answer`, and the same last column `claims_withheld` when a row is left out. On such a row `claims` is empty.
- `verification/<state>/<year>/claim-sums.csv`: `filing_id`, `schedule`, and `claim_sum`, the sum of the claim counts of the schedule's rows, not counting the printed total. It has a row for each filing and schedule that has a left-out count.
- `laws/laws.csv`, `laws/not-listed.csv`: the two published laws tables, as kept by hand. `laws/kinds.csv`: `kind`, `label`, `description`. `laws/hosts.csv`: `host`, `state`, `owner`, one row for each official site a law links to.
- `sources/laws/<state>/<law_id>.txt` and `<law_id>.more.txt`: the saved text of a law's official page and of its second page.
- `private/small-counts.csv` (never committed): `filing_id`, `schedule`, `line`, `claims_as_filed` (the count as transcribed) and `image_read_claims` (the count the second reader wrote).

## external-share-light.svg, external-share-dark.svg

The chart in the README, drawn from `measures.csv` by the same build. It shows the Rhode Island filings only; its title and its groups (health centers, hospitals) are Rhode Island's. Minnesota is not in the chart.
