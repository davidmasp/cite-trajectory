# Product Requirements Document: OpenAlex Citation Dataset Builder and Plotting App

## 1. Summary

Build a small R-based application or program that creates reusable plotting datasets from OpenAlex Work IDs.

The current repository combines data loading, live OpenAlex API calls, aggregation, plotting, and debugging in one exploratory script. The new product should split this into two independent parts:

1. A long-running dataset builder that accepts one or more OpenAlex source work IDs and a target number of papers, fetches the required citation data from OpenAlex, enriches it, and persists the result.
2. A plotting layer, either a second R script or a Shiny app, that reads the already extracted data and builds citation trajectory plots without calling the OpenAlex API.

This separation is required because OpenAlex API calls can be slow, rate-limited, and failure-prone at larger dataset sizes.

## 2. Background

The current workflow compares citation activity across three Hallmarks corpora:

- `00' HoC`
- `11' HoC - The Next Generation`
- `22' HoC - New Dimensions`

The existing script:

- reads three OpenAlex CSV exports,
- assigns metadata for each source paper,
- combines the data,
- performs one API request per row to retrieve `topics` and `type`,
- aggregates citation counts by month,
- plots monthly and cumulative citation activity.

The major limitation is that live API enrichment is not persisted and is not separated from plotting. A full run requires repeated network calls and cannot resume cleanly after interruption.

## 3. Goals

- Allow a user to create a citation dataset from OpenAlex using source work IDs as input.
- Let the user specify how many citing papers to collect per source work.
- Persist raw and normalized data so extraction only needs to happen once.
- Support slow, resumable API extraction with rate limiting, retries, and progress reporting.
- Produce a plotting-ready table or database that can be consumed by a separate script or Shiny app.
- Recreate the current monthly citation count and cumulative citation plots from persisted data.
- Make it easy to add new source papers or corpora without editing plotting code.

## 4. Non-Goals

- Do not build a general-purpose OpenAlex client.
- Do not require live API calls during plotting.
- Do not require a full production web service or hosted database.
- Do not solve citation disambiguation beyond what OpenAlex provides.
- Do not make claims about citation quality or scholarly impact beyond the plotted OpenAlex data.

## 5. Users

Primary user:

- A researcher or analyst comparing citation trajectories across a small set of important papers or paper groups.

Secondary users:

- Collaborators who need to rerun the plots from a saved dataset.
- Future analysts who want to add another source paper and regenerate the same outputs.

## 6. Key Assumptions

- The primary input OpenAlex ID is a source Work ID, for example `W1234567890` or `https://openalex.org/W1234567890`.
- The dataset for a source work consists of OpenAlex works that cite that source work, fetched with `GET /works?filter=cites:{source_id}`.
- The requested "amount of papers" means the maximum number of citing works to collect per source work.
- Each source work can have user-supplied display metadata, such as edition label, publication date, original journal, and plotting color/group.
- R is the preferred implementation language because the current workflow is already in R.

## 7. Open Questions

- Should the requested paper count be a hard cap per source work or an overall cap across all source works?
- Should non-article OpenAlex work types be included by default, or should the app default to articles only?
- Should January records be excluded, flagged, or left untouched while the current "weird January" issue is investigated?
- Should the final persisted database be SQLite, DuckDB, Parquet, CSV, or a combination?

## 8. Product Shape

### 8.1 Dataset Builder

The dataset builder should be a command-line R script first. A Shiny-based extraction UI can be added later if needed.

Recommended command shape:

```bash
Rscript scripts/build_dataset.R --config config/sources.yml --limit 5000 --out data/openalex_citations.sqlite
```

The builder should:

- read a source configuration file,
- validate OpenAlex IDs,
- create or open a local persistent store,
- fetch source work metadata,
- fetch citing works up to the requested limit,
- enrich citing works with selected fields,
- save raw API responses for auditability,
- save normalized tables for plotting,
- record job progress and failures,
- resume incomplete jobs without duplicating records.

### 8.2 Plotting Script

The plotting script should read only from the persisted dataset.

Recommended command shape:

```bash
Rscript scripts/plot_citations.R --db data/openalex_citations.sqlite --out plots/
```

The script should:

- load normalized citation records,
- filter citations before each source paper publication date,
- aggregate citation counts by month and source group,
- compute cumulative citations,
- save monthly and cumulative plots,
- optionally export the plotting data as CSV.

### 8.3 Optional Shiny App

A Shiny app can be built once the extraction schema is stable.

The Shiny app should:

- load an existing extracted dataset,
- allow users to select source works or editions,
- toggle monthly versus cumulative views,
- filter by work type, source journal, topic domain, publication date range, or open access status,
- download plots and plotting data.

The Shiny app should not perform large OpenAlex extraction jobs in the first version.

## 9. Source Configuration

Use a structured config file so source papers are not hardcoded in scripts.

Example:

```yaml
sources:
  - source_id: W0000000001
    label: "00' HoC"
    source_publication_date: "2000-01-07"
    source_journal: "Cell"
    requested_citing_works: 5000

  - source_id: W0000000002
    label: "11' HoC - The Next Generation"
    source_publication_date: "2011-04-03"
    source_journal: "Cell"
    requested_citing_works: 5000

  - source_id: W0000000003
    label: "22' HoC - New Dimensions"
    source_publication_date: "2022-01-12"
    source_journal: "Cancer Discovery"
    requested_citing_works: 5000
```

## 10. Data Requirements

### 10.1 Minimum Source Work Fields

- `source_id`
- `source_openalex_url`
- `source_display_name`
- `source_publication_date`
- `source_publication_year`
- `source_journal`
- `label`
- `requested_citing_works`
- `created_at`
- `updated_at`

### 10.2 Minimum Citing Work Fields

- `source_id`
- `citing_work_id`
- `citing_work_openalex_url`
- `display_name`
- `doi`
- `publication_date`
- `publication_year`
- `type`
- `cited_by_count`
- `primary_source_display_name`
- `primary_source_id`
- `primary_source_type`
- `is_retracted`
- `language`
- `is_open_access`
- `oa_status`
- `primary_topic_display_name`
- `topic_domain_display_name`
- `fwci`
- `raw_json_path` or `raw_json_id`
- `fetched_at`

### 10.3 Plotting Table Fields

- `source_id`
- `label`
- `source_publication_date`
- `source_journal`
- `month_start_date`
- `publication_year`
- `publication_month`
- `work_type`
- `topic_domain_display_name`
- `n_citations`
- `cumulative_citations`

The plotting table can be materialized during extraction or generated on demand by the plotting script.

## 11. Storage Requirements

The first version should use a local file-based store. Recommended option:

- SQLite database for normalized tables and job state.
- Optional raw JSON files under `data/raw_openalex/` for API audit/debugging.
- CSV exports under `data/exports/` for easy inspection.
- Plot files under `plots/`.

Suggested structure:

```text
config/
  sources.yml
data/
  openalex_citations.sqlite
  raw_openalex/
  exports/
plots/
scripts/
  build_dataset.R
  plot_citations.R
R/
  openalex_client.R
  storage.R
  plotting_data.R
```

## 12. Extraction Requirements

### 12.1 Input Validation

The builder must:

- accept `W123`, `openalex.org/W123`, and `https://openalex.org/W123` forms,
- normalize all IDs to `W...`,
- reject empty or malformed IDs,
- reject missing source labels,
- reject missing or invalid publication dates,
- warn if requested paper count is larger than the source work's current cited-by count.

### 12.2 API Behavior

The builder must:

- use paginated OpenAlex API requests where possible,
- fetch citing works with `filter=cites:{source_id}` or its OpenAlex-normalized equivalent, `filter=referenced_works:{source_id}`,
- select only required fields when possible,
- use a configurable delay between requests,
- support a configured mailto/contact parameter if available,
- retry transient HTTP failures,
- stop gracefully after repeated failures,
- persist progress after each successful page or record batch.

### 12.3 Resume Behavior

The builder must:

- detect existing completed citing work records,
- avoid duplicate inserts,
- continue from the last saved cursor or page where possible,
- mark failed records or pages for retry,
- produce a final job summary.

### 12.4 Progress Reporting

The builder should display:

- source currently being processed,
- number of citing works fetched,
- requested limit,
- elapsed time,
- estimated remaining time when practical,
- retry/failure count.

## 13. Plotting Requirements

The plotting layer must:

- never call OpenAlex,
- read from the local persisted dataset,
- filter out citing works with `publication_date < source_publication_date`,
- aggregate by month and source label,
- compute cumulative counts in chronological order,
- save a monthly citation plot,
- save a cumulative citation plot,
- save the final plotting table as CSV.

The plotting layer should support optional filters:

- source label,
- date range,
- work type,
- topic domain,
- source journal,
- open access status,
- retracted status.

## 14. Shiny Requirements

If implemented as a Shiny app, the app should use the extracted dataset as read-only input.

Minimum views:

- Dataset overview: source works, total citing works, date coverage, last extraction date.
- Monthly citations plot.
- Cumulative citations plot.
- Filter controls.
- Data table preview of plotted rows.
- Download buttons for plots and CSV.

The app should clearly show when data was last extracted and which database file is loaded.

## 15. Error Handling

The builder should handle:

- invalid OpenAlex IDs,
- source works with zero citations,
- API timeouts,
- rate limit responses,
- partial extraction failures,
- duplicate citing works,
- missing publication dates,
- malformed API responses,
- interrupted runs.

The plotting script should handle:

- missing database file,
- empty plotting table,
- missing required columns,
- all records filtered out,
- invalid output directory.

## 16. Acceptance Criteria

### Dataset Builder

- Given a config with one valid OpenAlex Work ID and a limit of 100, the builder creates a local database with up to 100 citing works.
- Running the same builder command twice does not duplicate records.
- If the builder is interrupted and rerun, it resumes or safely skips already saved records.
- The builder records source metadata, citing work metadata, and extraction job metadata.
- The builder writes enough data for plotting without another API call.

### Plotting Script

- Given a completed database, the plotting script creates monthly and cumulative citation plots.
- The script writes a plotting CSV with monthly counts and cumulative counts.
- The script reproduces the current analysis pattern without running API requests.
- The script can plot all sources together and a selected subset of sources.

### Shiny App

- Given a completed database, the app loads without making API calls.
- Users can select sources, apply filters, and view updated plots.
- Users can download the current plotting table and plot images.

## 17. Implementation Plan

### Phase 1: Project Cleanup

- Rename `Untitled-1.R` into a descriptive legacy or exploratory script.
- Add `README.md` with setup and run instructions.
- Add dependency management, preferably `renv`.
- Add `.gitignore` for generated data, raw API responses, plots, and local R artifacts.

### Phase 2: Dataset Builder MVP

- Add `config/sources.yml`.
- Add OpenAlex ID normalization and validation.
- Add an API client wrapper with retries and rate limiting.
- Add SQLite schema and insert/upsert helpers.
- Fetch citing works for one source ID.
- Save normalized records and job state.
- Support rerun without duplicates.

### Phase 3: Multi-Source Extraction

- Support multiple source IDs from config.
- Add per-source requested limits.
- Add source metadata fetch.
- Add extraction summary output.
- Add raw response persistence if needed.

### Phase 4: Plotting Script

- Build plotting table from SQLite.
- Recreate monthly citation and cumulative citation plots.
- Save plots and CSV exports.
- Add basic CLI filters.

### Phase 5: Shiny App

- Build read-only app over existing extracted database.
- Add filters and downloads.
- Add dataset overview page.
- Add visual validation against static plots.

## 18. Suggested Technical Choices

- Language: R.
- CLI parsing: `optparse` or `argparse`.
- API requests: `httr2`.
- Data manipulation: `dplyr`, `tidyr`, `lubridate`, `stringr`, `purrr`.
- Storage: `DBI` plus `RSQLite`.
- Config: `yaml`.
- Plotting: `ggplot2`.
- Progress: `progress` or `cli`.
- Shiny app: `shiny`, `DT`, `bslib`.

## 19. Risks

- OpenAlex API response shapes may differ from the current CSV export columns.
- Large citation sets may take a long time to fetch and store.
- Some citing works may have incomplete or missing publication dates.
- The meaning of "citation count by month" depends on citing work publication date, not the actual date the citation was added.
- Existing January spike behavior may reflect source data, export behavior, missing dates, or work types and needs separate investigation.

## 20. Future Enhancements

- Add support for DuckDB or Parquet for larger datasets.
- Add scheduled refresh for existing source works.
- Compare snapshots over time.
- Add topic/domain breakdown plots.
- Add work-type filters to inspect article versus non-article behavior.
- Add automated data quality checks.
- Add a report export with methods and caveats.
