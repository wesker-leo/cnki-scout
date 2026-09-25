# CNKI Scout: Literature Screening Metadata Collector

[中文](README.md) · [English](README.en.md)

CNKI Scout uses a visible browser session to search China National Knowledge Infrastructure (CNKI), read result lists and article detail pages sequentially, and export metadata for human review or AI-assisted literature screening. It collects **fields visible on the page**, including title, authors, affiliations, source, publication date, database, citation and download counts, abstract, keywords, collection, topic, DOI, and discipline. It does not download full-text papers and is not affiliated with CNKI.

## Features

- Search by keywords and use CNKI's relevance, publication time, citation, or download sorting.
- Filter publication years and minimum citations locally; paginate with explicit limits on saved records and scanned pages.
- Read detail pages and retain every scanned result row with its inclusion or exclusion reason, so counts can be audited.
- Export JSONL, CSV, and Markdown; retain partial results if a run stops.
- Use one browser session and sequential, paced visits; stop when access is restricted or human verification appears.

## Installation

You need Python 3.10+ and access through a campus network, university VPN, or institutional account. On macOS/Linux:

```bash
git clone https://github.com/wesker-leo/cnki-scout.git
cd cnki-scout
python3.12 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m playwright install chromium
```

If Chrome is already installed, you may skip the last step and add `--browser-channel chrome` immediately after `cnki-scout` in the commands below. On Windows, replace `.venv/bin/` with `.venv\Scripts\` and create the environment with `py -3.12 -m venv .venv`.

## Login and collection

First, complete your institutional login **manually** in the opened browser, then press Enter in the terminal:

```bash
.venv/bin/cnki-scout login
```

Replace `your search terms` with your own query. This example keeps papers in the specified year range with at least three citations and sorts by citations:

```bash
.venv/bin/cnki-scout collect "your search terms" \
  --start-year 2022 --end-year 2026 \
  --min-citations 3 --sort citations \
  --max-results 30 --max-pages 8
```

Other examples:

```bash
# Filter by year only; sort by relevance
.venv/bin/cnki-scout collect "your search terms" --start-year 2022 --end-year 2026 --sort relevance --max-results 30

# No year or citation filter; sort by downloads
.venv/bin/cnki-scout collect "your search terms" --sort downloads --max-results 50 --max-pages 8

# Set the search and sort options in CNKI manually, then collect
.venv/bin/cnki-scout collect "your search terms" --manual-search --max-results 30
```

`--sort` accepts `relevance`, `time`, `citations`, or `downloads`. Sorting happens on CNKI's site; year and minimum-citation filters are applied locally after reading the result list. **The number displayed on CNKI may therefore exceed the number of saved papers.** When a year filter is set, rows without a year are excluded. When `--min-citations` is set, rows with no displayed citation count are excluded **even if the threshold is `0`**. Omit the option to apply no citation filter.

## Output files

Each run creates `output/<timestamp>-<query>/`:

| File | Purpose |
| --- | --- |
| `records.md` | Read each paper's metadata and abstract |
| `records.csv` | Spreadsheet with Chinese column headings |
| `records.jsonl` | One paper per line for AI tools and scripts; unknown numbers are `null` |
| `search_results.csv` | Every scanned result row and its screening decision |
| `candidate_rows.jsonl` | Machine-readable version of scanned result rows |
| `manifest.json` | Query, site result count, scanned and saved counts, options, and stop reason |
| `errors.jsonl` | Detail-page errors, if any |

When the site shows more hits than the collector saves, inspect `search_results.csv` to see which rows were excluded by year, missing citation counts, or deduplication. Title and abstract should drive initial relevance screening; citation counts and affiliations are supporting context, not standalone quality scores.

## Access pacing and limitations

Visits are separated by a randomized 8–15 second delay by default, with a minimum allowed delay of 5 seconds. A run can save at most 200 papers and scan at most 50 pages. The tool does not solve CAPTCHAs, rotate proxies, or send concurrent requests. It stops and preserves partial results on verification pages, HTTP 403/429/503, or pagination failures. Browser session data stays in `.browser_profile/`, and collected data stays in `output/`; both are excluded by `.gitignore`. **Do not upload or share the browser profile.** Follow the [CNKI membership service agreement](https://wap.oversea.cnki.net/cn/member/agreement.html) and your institution's access rules.

CNKI may change its page structure. `--manual-search` can help when the search controls change; field extraction may still require selector updates. Browser search, sorting, and detail extraction were checked on 2026-09-25, but future site compatibility cannot be guaranteed.

## Tests, license, and attribution

```bash
.venv/bin/python -m unittest discover -s tests -v
```

This project is released under the [MIT License](LICENSE). Search entry points, result fields, and sorting selectors were informed by the MIT-licensed [wuruiqi/cnki-mcp](https://github.com/wuruiqi/cnki-mcp). The paced collection, filtering, pagination, detail parsing, and exports are implemented in this repository. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for upstream attribution and license text.
