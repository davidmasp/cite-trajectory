# OpenAlex Citation Trajectories

Quickstart for the local OpenAlex citation trajectory app in this repository.

## Documentation Map

- [`product-requirements.md`](product-requirements.md): product scope, requirements, and design notes for the consolidated workflow.
- [`openalex_citation_model.md`](openalex_citation_model.md): SQLite schema and OpenAlex API model notes.
- [`archive-exploration-status.md`](archive-exploration-status.md): archived snapshot of the pre-consolidation exploration phase.

## What This Project Does

This project compares citation activity for selected OpenAlex source works. It has two stages:

1. `scripts/fetch_openalex_citations.py` fetches works that cite a source OpenAlex work ID and stores them in SQLite.
2. `app.R` reads the local SQLite database and draws monthly or cumulative citation trajectories.

The Shiny app does not call OpenAlex directly. Fetch or refresh the database first, then open the app.

Run the commands below from the repository root.

## Main Files

- `app.R`: Shiny app for selecting 2 to 5 source papers and plotting citation trajectories.
- `scripts/fetch_openalex_citations.py`: OpenAlex extraction script.
- `scripts/run_fetch_from_config.py`: runs the extraction script for multiple source IDs from a TOML config.
- `scripts/export_plotting_data.py`: exports the monthly plotting table from SQLite to CSV.
- `config/fetch_sources.example.toml`: example batch-fetch config.
- `data/openalex_citations_test.sqlite`: small test database for verifying the app.
- `data/exports/plotting_data_test.csv`: CSV export generated from the test database.
- `docs/openalex_citation_model.md`: schema and API notes for the citation data model.

## Requirements

Python uses only the standard library for the included scripts. The TOML batch runner uses `tomllib`, so it needs Python 3.11+.

The Shiny app needs these R packages:

```r
install.packages(c("shiny", "DBI", "RSQLite", "dplyr", "ggplot2", "lubridate", "scales"))
```

## Run The App

From the repository root:

```bash
Rscript -e "shiny::runApp('app.R')"
```

The app chooses `data/openalex_citations.sqlite` if it exists. Otherwise it falls back to `data/openalex_citations_test.sqlite`.

The checked-in test database currently contains two source works:

- `W2117692326`: Hallmarks of Cancer: The Next Generation
- `W1976149758`: The hallmarks of cancer

Each has a tiny saved citing-work sample, so the test DB is useful for checking that the UI, filters, downloads, and plots work. Build a larger database before using the plots analytically.

## Add A Source Work

Fetch citing works for one OpenAlex source work:

```bash
python3 scripts/fetch_openalex_citations.py \
  --source-id W1976149758 \
  --limit 1000 \
  --db data/openalex_citations.sqlite
```

Run the same command with more `--source-id` values to add papers to the same database. Reruns are safe: source works, citing works, and citation edges use primary keys, so duplicate records are ignored or updated.

Useful options:

- `--limit`: maximum citing works to fetch for that source.
- `--per-page`: OpenAlex page size, up to 100.
- `--delay`: pause between page requests.
- `--email`: contact email passed to OpenAlex as `mailto`.
- `--api-key`: OpenAlex API key, or set `OPENALEX_API_KEY`.

## Add Multiple Source Works From TOML

Create a config file from `config/fetch_sources.example.toml` and list one `[[sources]]` entry per source work.

Example:

```toml
continue_on_error = false

[output]
directory = "../data"
database = "openalex_citations.sqlite"

[fetch]
limit = 1000
per_page = 100
delay = 0.2
retries = 4
timeout = 60

[[sources]]
id = "W2117692326"
label = "Hallmarks of Cancer: The Next Generation"

[[sources]]
id = "W1976149758"
limit = 500
```

Then run:

```bash
python3 scripts/run_fetch_from_config.py --config config/fetch_sources.toml
```

Or with `uv`:

```bash
uv run python scripts/run_fetch_from_config.py --config config/fetch_sources.toml
```

Useful notes:

- `output.directory` and `output.database` control where the SQLite database is written.
- Paths in the TOML file are resolved relative to the TOML file location.
- `[fetch]` sets defaults shared by all sources.
- Each `[[sources]]` entry must define `id`. It can also override `limit` and add a human-readable `label`.
- Use `--dry-run` to validate the config and print the planned jobs without calling OpenAlex.

## Refresh The Test Data

To reproduce the current small test database shape, fetch a few citing works for each source:

```bash
python3 scripts/fetch_openalex_citations.py \
  --source-id W2117692326 \
  --limit 3 \
  --db data/openalex_citations_test.sqlite

python3 scripts/fetch_openalex_citations.py \
  --source-id W1976149758 \
  --limit 3 \
  --db data/openalex_citations_test.sqlite
```

Then refresh the CSV export:

```bash
python3 scripts/export_plotting_data.py \
  --db data/openalex_citations_test.sqlite \
  --out data/exports/plotting_data_test.csv
```

## Export Plotting Data

For a CSV version of the monthly and cumulative plotting table:

```bash
python3 scripts/export_plotting_data.py \
  --db data/openalex_citations.sqlite \
  --out data/exports/plotting_data.csv
```

## How The Data Model Works

The SQLite database has four core tables:

- `source_works`: one row per cited OpenAlex source work.
- `citing_works`: one row per OpenAlex work that cites any selected source.
- `citation_edges`: source-to-citing-work links.
- `extraction_runs`: run metadata and status.

The plotting layer groups `citation_edges` by source work and citing-work publication month. `publication_date` is used as the citation-month proxy because OpenAlex does not provide exact citation-added dates.
