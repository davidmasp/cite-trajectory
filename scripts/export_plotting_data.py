#!/usr/bin/env python3
"""Export monthly citation plotting data from the local OpenAlex SQLite database."""

from __future__ import annotations

import argparse
import csv
import os
import sqlite3
import sys


QUERY = """
with monthly as (
  select
    ce.source_id,
    sw.display_name as source_display_name,
    sw.publication_date as source_publication_date,
    sw.source_name as source_journal,
    sw.cited_by_count as source_cited_by_count,
    sw.api_list_count as source_api_list_count,
    substr(cw.publication_date, 1, 7) || '-01' as month_start_date,
    count(*) as n_citations
  from citation_edges ce
  join source_works sw
    on sw.source_id = ce.source_id
  join citing_works cw
    on cw.work_id = ce.citing_work_id
  where cw.publication_date is not null
    and sw.publication_date is not null
    and date(cw.publication_date) >= date(sw.publication_date)
  group by
    ce.source_id,
    sw.display_name,
    sw.publication_date,
    sw.source_name,
    sw.cited_by_count,
    sw.api_list_count,
    month_start_date
)
select
  source_id,
  source_display_name,
  source_publication_date,
  source_journal,
  source_cited_by_count,
  source_api_list_count,
  month_start_date,
  n_citations,
  sum(n_citations) over (
    partition by source_id
    order by month_start_date
    rows between unbounded preceding and current row
  ) as cumulative_citations
from monthly
order by source_id, month_start_date;
"""


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export monthly and cumulative citation counts for plotting."
    )
    parser.add_argument(
        "--db",
        default="data/openalex_citations.sqlite",
        help="SQLite database created by fetch_openalex_citations.py.",
    )
    parser.add_argument(
        "--out",
        default="data/exports/plotting_data.csv",
        help="Output CSV path.",
    )
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> int:
    if not os.path.exists(args.db):
        print(f"Database does not exist: {args.db}", file=sys.stderr)
        return 1

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(QUERY).fetchall()
    finally:
        conn.close()

    if not rows:
        print("No plotting rows found after date filtering.", file=sys.stderr)
        return 1

    with open(args.out, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(dict(row) for row in rows)

    print(f"Wrote {len(rows)} plotting rows to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run(parse_args(sys.argv[1:])))
