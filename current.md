# Current Status

As of 2026-07-11, this repository is a small exploratory R workspace for comparing citation activity across three related "Hallmarks" corpora exported from OpenAlex.

## Repo Snapshot

- `Untitled-1.R`: the only code file in the repo.
- `hallmarks_og_works-csv-H3e6RcrEAdxdqE7YbYznjr.csv`: 28,176 data rows.
- `hallmarks_nextgen_works-csv-W356rk5THXd9pRNgLYPNZ3.csv`: 63,280 data rows.
- `hallmarks_newdimensions_works-csv-6gXeJ4rmhpsvBSDEw37HFS.csv`: 7,794 data rows.

There is currently no `README`, no `renv` lockfile, no `.Rproj`, no `.gitignore`, and this folder is not initialized as a Git repository.

## What The Script Currently Does

`Untitled-1.R` implements a single end-to-end exploratory workflow:

1. Reads three OpenAlex CSV exports into R.
2. Hardcodes one publication date, journal name, and edition label for each corpus.
3. Combines the three datasets into one table.
4. Extracts OpenAlex work IDs and makes one API request per row to fetch `topics` and `type`.
5. Converts `publication_date` into a date and filters out records published before the relevant source article date.
6. Aggregates counts by month and edition.
7. Builds two plots:
   - monthly citation counts
   - cumulative citation totals
8. Runs a separate January-only debugging section to inspect the "weird January" spike noted in comments.

## Inferred Project Goal

The code appears to be testing whether citation trajectories differ across:

- `00' HoC`
- `11' HoC - The Next Generation`
- `22' HoC - New Dimensions`

The intended output is visual comparison rather than a packaged analysis pipeline.

## Current State Of The Code

The analysis is partially working but still clearly in scratch/exploration mode.

### Working Pieces

- The script is syntactically valid R.
- The CSV inputs required by the script are present in the repo.
- The core aggregation logic for monthly and cumulative citation counts is implemented.
- The plot code is present for both main views.

### Gaps And Risks

- The code is not organized as a reusable project. Everything lives in one script named `Untitled-1.R`.
- The script depends on several packages (`ggplot2`, `readr`, `lubridate`, `dplyr`, `stringr`, `glue`, `progress`, `purrr`, `httr2`) but there is no environment/bootstrap file documenting them.
- The API enrichment block fetches `topics` and `type`, but those results are not merged back into `dat` and are not used in the plotting section.
- The workflow makes one live OpenAlex API call per row, so a full run is network-dependent and likely slow.
- No caching layer exists for API responses.
- The plots are created interactively but are not assigned to objects or saved with `ggsave()`.
- The comment about January overcounting is unresolved; the filtering line is still commented out.
- The final debugging block ends with `table(types_normal)`, but `types_normal` is never defined in the script. That means the script will fail if run all the way to the end.

## Practical Read On Status

At the moment this repo is best described as:

- a valid exploratory analysis draft
- with local input data checked in
- with preliminary plotting logic in place
- but not yet cleaned up into a reproducible or shareable analysis project

## Suggested Next Steps

- Rename `Untitled-1.R` to something descriptive.
- Split the exploratory debugging section from the main analysis path.
- Remove or finish the unused API enrichment logic.
- Save plot outputs to files.
- Add a short `README` describing the datasets, required packages, and how to run the analysis.
- Add dependency management (`renv` or equivalent) if this needs to be rerun reliably.
