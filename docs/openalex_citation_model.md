# OpenAlex Citation Dataset Model

## API Finding

For this project, the dataset for a source work should be the set of OpenAlex works that cite that source work.

The direct API query is:

```text
GET https://api.openalex.org/works?filter=cites:W2117692326
```

OpenAlex currently normalizes that filter internally to:

```text
filter=referenced_works:W2117692326
```

That means each returned work has the source work in its `referenced_works` list. In plain language: returned works are citing works, and the input work is the cited work.

For large result sets, use cursor paging:

```text
GET https://api.openalex.org/works?filter=cites:W2117692326&per_page=100&cursor=*
GET https://api.openalex.org/works?filter=cites:W2117692326&per_page=100&cursor={next_cursor}
```

Use `select` to keep responses smaller, but only for top-level fields. Nested selections such as `open_access.is_oa` are not supported by the OpenAlex API.

## Example Source Work

Example:

```text
https://api.openalex.org/works/W2117692326
```

As checked on 2026-07-11, this resolves to:

- `display_name`: `Hallmarks of Cancer: The Next Generation`
- `publication_date`: `2011-03-01`
- `type`: `review`
- `primary_location.source.display_name`: `Cell`
- `cited_by_count`: `66655`

The citing-works list query returned `64832` matching works at the same check time. Store both values because they may not match exactly.

## Recommended Storage Model

Use SQLite first. It is local, resumable, easy to inspect, and enough for tens or hundreds of thousands of works.

### `source_works`

One row per input OpenAlex source work.

| Column | Type | Meaning |
| --- | --- | --- |
| `source_id` | text primary key | Normalized OpenAlex ID, for example `W2117692326` |
| `source_openalex_url` | text | Full OpenAlex URL |
| `display_name` | text | Source work title |
| `publication_date` | text | Source publication date |
| `publication_year` | integer | Source publication year |
| `type` | text | Source work type |
| `source_name` | text | Source/journal name |
| `source_openalex_id` | text | Source/journal OpenAlex ID |
| `cited_by_count` | integer | Count from the singleton work record |
| `api_list_count` | integer | Count reported by the citing-works list query |
| `fetched_at` | text | UTC timestamp |
| `raw_json` | text | Raw source work JSON |

### `citing_works`

One row per unique citing work.

| Column | Type | Meaning |
| --- | --- | --- |
| `work_id` | text primary key | Normalized citing work ID |
| `openalex_url` | text | Full OpenAlex URL |
| `display_name` | text | Citing work title |
| `doi` | text | DOI URL, if present |
| `publication_date` | text | Citing work publication date |
| `publication_year` | integer | Citing work publication year |
| `type` | text | Citing work type |
| `cited_by_count` | integer | Citing work's own citation count |
| `is_retracted` | integer | Boolean as 0/1 |
| `is_paratext` | integer | Boolean as 0/1 |
| `language` | text | OpenAlex language |
| `source_name` | text | Primary source/journal name |
| `source_openalex_id` | text | Primary source/journal ID |
| `source_type` | text | Primary source type |
| `is_oa` | integer | Boolean as 0/1 |
| `oa_status` | text | Open access status |
| `primary_topic_name` | text | Primary topic display name |
| `primary_topic_id` | text | Primary topic ID |
| `primary_topic_domain_name` | text | Domain display name |
| `primary_topic_field_name` | text | Field display name |
| `primary_topic_subfield_name` | text | Subfield display name |
| `fwci` | real | Field-weighted citation impact, if present |
| `fetched_at` | text | UTC timestamp |
| `raw_json` | text | Raw citing work JSON |

### `citation_edges`

One row per source-work-to-citing-work relationship.

| Column | Type | Meaning |
| --- | --- | --- |
| `source_id` | text | Cited source work ID |
| `citing_work_id` | text | Citing work ID |
| `fetched_at` | text | UTC timestamp |

Primary key:

```text
(source_id, citing_work_id)
```

This table matters because the same citing work may cite more than one source work in a multi-source comparison.

### `extraction_runs`

One row per run or per source/run pair.

| Column | Type | Meaning |
| --- | --- | --- |
| `run_id` | text primary key | Timestamp-derived run ID |
| `source_id` | text | Source being extracted |
| `requested_limit` | integer | Requested max citing works |
| `records_saved` | integer | Citing works saved in this run |
| `next_cursor` | text | Last cursor returned by OpenAlex |
| `status` | text | `running`, `complete`, or `failed` |
| `started_at` | text | UTC timestamp |
| `finished_at` | text | UTC timestamp |
| `error_message` | text | Failure details |

## Plotting Model

The plotting layer should read only from SQLite and build a derived table:

```sql
select
  ce.source_id,
  sw.display_name as source_display_name,
  sw.publication_date as source_publication_date,
  sw.source_name as source_journal,
  cw.publication_date as citing_publication_date,
  substr(cw.publication_date, 1, 7) || '-01' as month_start_date,
  cw.publication_year,
  cw.type as work_type,
  cw.primary_topic_domain_name,
  count(*) as n_citations
from citation_edges ce
join source_works sw on sw.source_id = ce.source_id
join citing_works cw on cw.work_id = ce.citing_work_id
where cw.publication_date >= sw.publication_date
group by
  ce.source_id,
  month_start_date,
  cw.type,
  cw.primary_topic_domain_name;
```

Then compute cumulative counts in R or SQL, grouped by `source_id`.

## Important Design Notes

- Treat `publication_date` on the citing work as the citation month proxy. OpenAlex does not provide the exact date the citation was added.
- Do not use the source work's `counts_by_year` for monthly plots. It is source-level yearly citation history, not the list of individual citing works.
- Do not assume `cited_by_count` equals the current count of list-query results. Store both.
- Keep raw JSON while prototyping. It makes schema changes and debugging much easier.
- Prefer extraction as a batch job, not inside Shiny. Shiny should consume the completed database.

## OpenAlex Docs Used

- API overview and access model: https://developers.openalex.org/
- Filtering: https://developers.openalex.org/guides/filtering
- Cursor paging: https://developers.openalex.org/guides/page-through-results
- Selecting fields: https://developers.openalex.org/guides/selecting-fields
- Works API reference: https://developers.openalex.org/api-reference/works
