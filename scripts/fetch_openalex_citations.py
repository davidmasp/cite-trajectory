#!/usr/bin/env python3
"""Fetch works that cite a given OpenAlex work into a local SQLite database."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


BASE_URL = "https://api.openalex.org"

SOURCE_SELECT = ",".join(
    [
        "id",
        "display_name",
        "publication_date",
        "publication_year",
        "type",
        "cited_by_count",
        "primary_location",
        "open_access",
        "primary_topic",
    ]
)

CITING_WORK_SELECT = ",".join(
    [
        "id",
        "doi",
        "display_name",
        "publication_date",
        "publication_year",
        "type",
        "language",
        "cited_by_count",
        "is_retracted",
        "is_paratext",
        "primary_location",
        "open_access",
        "primary_topic",
        "fwci",
    ]
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def normalize_work_id(value: str) -> str:
    match = re.search(r"W\d+", value or "", flags=re.IGNORECASE)
    if not match:
        raise ValueError(f"Could not find an OpenAlex work ID in: {value!r}")
    return match.group(0).upper()


def as_bool_int(value: Any) -> int | None:
    if value is None:
        return None
    return 1 if bool(value) else 0


def nested(data: dict[str, Any] | None, *keys: str) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def request_json(
    path: str,
    params: dict[str, Any],
    retries: int,
    timeout: int,
) -> dict[str, Any]:
    clean_params = {k: v for k, v in params.items() if v not in (None, "")}
    url = f"{BASE_URL}{path}?{urllib.parse.urlencode(clean_params)}"

    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers={"User-Agent": "openalex-citation-fetcher/0.1"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = resp.read().decode("utf-8")
                return json.loads(payload)
        except urllib.error.HTTPError as exc:
            retry_after = exc.headers.get("Retry-After")
            wait = int(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
            if exc.code in {429, 500, 502, 503, 504} and attempt < retries:
                print(f"HTTP {exc.code}; retrying in {wait}s: {url}", file=sys.stderr)
                time.sleep(wait)
                continue
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code} for {url}: {body}") from exc
        except urllib.error.URLError as exc:
            if attempt < retries:
                wait = 2**attempt
                print(f"Network error; retrying in {wait}s: {exc}", file=sys.stderr)
                time.sleep(wait)
                continue
            raise RuntimeError(f"Network error for {url}: {exc}") from exc

    raise RuntimeError(f"Request failed after retries: {url}")


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        create table if not exists source_works (
          source_id text primary key,
          source_openalex_url text not null,
          display_name text,
          publication_date text,
          publication_year integer,
          type text,
          source_name text,
          source_openalex_id text,
          cited_by_count integer,
          api_list_count integer,
          fetched_at text not null,
          raw_json text not null
        );

        create table if not exists citing_works (
          work_id text primary key,
          openalex_url text not null,
          display_name text,
          doi text,
          publication_date text,
          publication_year integer,
          type text,
          cited_by_count integer,
          is_retracted integer,
          is_paratext integer,
          language text,
          source_name text,
          source_openalex_id text,
          source_type text,
          is_oa integer,
          oa_status text,
          primary_topic_name text,
          primary_topic_id text,
          primary_topic_domain_name text,
          primary_topic_field_name text,
          primary_topic_subfield_name text,
          fwci real,
          fetched_at text not null,
          raw_json text not null
        );

        create table if not exists citation_edges (
          source_id text not null,
          citing_work_id text not null,
          fetched_at text not null,
          primary key (source_id, citing_work_id)
        );

        create table if not exists extraction_runs (
          run_id text primary key,
          source_id text not null,
          requested_limit integer not null,
          records_seen integer not null default 0,
          records_saved integer not null default 0,
          next_cursor text,
          status text not null,
          started_at text not null,
          finished_at text,
          error_message text
        );

        create index if not exists idx_citation_edges_source_id
          on citation_edges(source_id);
        create index if not exists idx_citing_works_publication_date
          on citing_works(publication_date);
        """
    )
    conn.commit()


def flatten_source(source_id: str, raw: dict[str, Any], fetched_at: str) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "source_openalex_url": raw.get("id"),
        "display_name": raw.get("display_name"),
        "publication_date": raw.get("publication_date"),
        "publication_year": raw.get("publication_year"),
        "type": raw.get("type"),
        "source_name": nested(raw, "primary_location", "source", "display_name"),
        "source_openalex_id": nested(raw, "primary_location", "source", "id"),
        "cited_by_count": raw.get("cited_by_count"),
        "api_list_count": None,
        "fetched_at": fetched_at,
        "raw_json": json.dumps(raw, sort_keys=True),
    }


def flatten_citing_work(raw: dict[str, Any], fetched_at: str) -> dict[str, Any]:
    work_id = normalize_work_id(raw.get("id", ""))
    return {
        "work_id": work_id,
        "openalex_url": raw.get("id"),
        "display_name": raw.get("display_name"),
        "doi": raw.get("doi"),
        "publication_date": raw.get("publication_date"),
        "publication_year": raw.get("publication_year"),
        "type": raw.get("type"),
        "cited_by_count": raw.get("cited_by_count"),
        "is_retracted": as_bool_int(raw.get("is_retracted")),
        "is_paratext": as_bool_int(raw.get("is_paratext")),
        "language": raw.get("language"),
        "source_name": nested(raw, "primary_location", "source", "display_name"),
        "source_openalex_id": nested(raw, "primary_location", "source", "id"),
        "source_type": nested(raw, "primary_location", "source", "type"),
        "is_oa": as_bool_int(nested(raw, "open_access", "is_oa")),
        "oa_status": nested(raw, "open_access", "oa_status"),
        "primary_topic_name": nested(raw, "primary_topic", "display_name"),
        "primary_topic_id": nested(raw, "primary_topic", "id"),
        "primary_topic_domain_name": nested(raw, "primary_topic", "domain", "display_name"),
        "primary_topic_field_name": nested(raw, "primary_topic", "field", "display_name"),
        "primary_topic_subfield_name": nested(raw, "primary_topic", "subfield", "display_name"),
        "fwci": raw.get("fwci"),
        "fetched_at": fetched_at,
        "raw_json": json.dumps(raw, sort_keys=True),
    }


def upsert_source(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    conn.execute(
        """
        insert into source_works (
          source_id, source_openalex_url, display_name, publication_date,
          publication_year, type, source_name, source_openalex_id,
          cited_by_count, api_list_count, fetched_at, raw_json
        )
        values (
          :source_id, :source_openalex_url, :display_name, :publication_date,
          :publication_year, :type, :source_name, :source_openalex_id,
          :cited_by_count, :api_list_count, :fetched_at, :raw_json
        )
        on conflict(source_id) do update set
          source_openalex_url = excluded.source_openalex_url,
          display_name = excluded.display_name,
          publication_date = excluded.publication_date,
          publication_year = excluded.publication_year,
          type = excluded.type,
          source_name = excluded.source_name,
          source_openalex_id = excluded.source_openalex_id,
          cited_by_count = excluded.cited_by_count,
          fetched_at = excluded.fetched_at,
          raw_json = excluded.raw_json
        """,
        row,
    )


def update_source_list_count(conn: sqlite3.Connection, source_id: str, count: int | None) -> None:
    conn.execute(
        "update source_works set api_list_count = ? where source_id = ?",
        (count, source_id),
    )


def upsert_citing_work(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    conn.execute(
        """
        insert into citing_works (
          work_id, openalex_url, display_name, doi, publication_date,
          publication_year, type, cited_by_count, is_retracted, is_paratext,
          language, source_name, source_openalex_id, source_type, is_oa,
          oa_status, primary_topic_name, primary_topic_id,
          primary_topic_domain_name, primary_topic_field_name,
          primary_topic_subfield_name, fwci, fetched_at, raw_json
        )
        values (
          :work_id, :openalex_url, :display_name, :doi, :publication_date,
          :publication_year, :type, :cited_by_count, :is_retracted, :is_paratext,
          :language, :source_name, :source_openalex_id, :source_type, :is_oa,
          :oa_status, :primary_topic_name, :primary_topic_id,
          :primary_topic_domain_name, :primary_topic_field_name,
          :primary_topic_subfield_name, :fwci, :fetched_at, :raw_json
        )
        on conflict(work_id) do update set
          openalex_url = excluded.openalex_url,
          display_name = excluded.display_name,
          doi = excluded.doi,
          publication_date = excluded.publication_date,
          publication_year = excluded.publication_year,
          type = excluded.type,
          cited_by_count = excluded.cited_by_count,
          is_retracted = excluded.is_retracted,
          is_paratext = excluded.is_paratext,
          language = excluded.language,
          source_name = excluded.source_name,
          source_openalex_id = excluded.source_openalex_id,
          source_type = excluded.source_type,
          is_oa = excluded.is_oa,
          oa_status = excluded.oa_status,
          primary_topic_name = excluded.primary_topic_name,
          primary_topic_id = excluded.primary_topic_id,
          primary_topic_domain_name = excluded.primary_topic_domain_name,
          primary_topic_field_name = excluded.primary_topic_field_name,
          primary_topic_subfield_name = excluded.primary_topic_subfield_name,
          fwci = excluded.fwci,
          fetched_at = excluded.fetched_at,
          raw_json = excluded.raw_json
        """,
        row,
    )


def insert_edge(conn: sqlite3.Connection, source_id: str, citing_work_id: str, fetched_at: str) -> int:
    cur = conn.execute(
        """
        insert or ignore into citation_edges (source_id, citing_work_id, fetched_at)
        values (?, ?, ?)
        """,
        (source_id, citing_work_id, fetched_at),
    )
    return cur.rowcount


def create_run(conn: sqlite3.Connection, source_id: str, limit: int) -> str:
    run_id = f"{source_id}-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    conn.execute(
        """
        insert into extraction_runs (
          run_id, source_id, requested_limit, status, started_at
        )
        values (?, ?, ?, 'running', ?)
        """,
        (run_id, source_id, limit, utc_now()),
    )
    conn.commit()
    return run_id


def update_run(
    conn: sqlite3.Connection,
    run_id: str,
    records_seen: int,
    records_saved: int,
    next_cursor: str | None,
    status: str,
    error_message: str | None = None,
) -> None:
    finished_at = utc_now() if status in {"complete", "failed"} else None
    conn.execute(
        """
        update extraction_runs
        set records_seen = ?,
            records_saved = ?,
            next_cursor = ?,
            status = ?,
            finished_at = coalesce(?, finished_at),
            error_message = ?
        where run_id = ?
        """,
        (records_seen, records_saved, next_cursor, status, finished_at, error_message, run_id),
    )
    conn.commit()


def fetch_source_work(args: argparse.Namespace, source_id: str) -> dict[str, Any]:
    params = {
        "select": SOURCE_SELECT,
        "api_key": args.api_key,
        "mailto": args.email,
    }
    return request_json(f"/works/{source_id}", params, args.retries, args.timeout)


def fetch_citing_page(
    args: argparse.Namespace,
    source_id: str,
    cursor: str,
) -> dict[str, Any]:
    params = {
        "filter": f"cites:{source_id}",
        "per_page": args.per_page,
        "cursor": cursor,
        "select": CITING_WORK_SELECT,
        "sort": args.sort,
        "api_key": args.api_key,
        "mailto": args.email,
    }
    return request_json("/works", params, args.retries, args.timeout)


def run(args: argparse.Namespace) -> int:
    source_id = normalize_work_id(args.source_id)
    os.makedirs(os.path.dirname(os.path.abspath(args.db)), exist_ok=True)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    init_db(conn)

    run_id = create_run(conn, source_id, args.limit)
    records_seen = 0
    records_saved = 0
    next_cursor = "*"

    try:
        fetched_at = utc_now()
        source_raw = fetch_source_work(args, source_id)
        upsert_source(conn, flatten_source(source_id, source_raw, fetched_at))
        conn.commit()

        print(
            f"Source {source_id}: {source_raw.get('display_name')} "
            f"({source_raw.get('cited_by_count')} cited_by_count)"
        )

        while records_seen < args.limit and next_cursor:
            page = fetch_citing_page(args, source_id, next_cursor)
            meta = page.get("meta", {})
            results = page.get("results", [])
            update_source_list_count(conn, source_id, meta.get("count"))

            if not results:
                next_cursor = None
                break

            for raw_work in results:
                if records_seen >= args.limit:
                    break
                fetched_at = utc_now()
                work_row = flatten_citing_work(raw_work, fetched_at)
                upsert_citing_work(conn, work_row)
                records_saved += insert_edge(conn, source_id, work_row["work_id"], fetched_at)
                records_seen += 1

            next_cursor = meta.get("next_cursor")
            conn.commit()
            update_run(conn, run_id, records_seen, records_saved, next_cursor, "running")
            print(
                f"Fetched {records_seen}/{args.limit}; "
                f"new edges this run: {records_saved}; API count: {meta.get('count')}"
            )

            if records_seen < args.limit and next_cursor and args.delay > 0:
                time.sleep(args.delay)

        update_run(conn, run_id, records_seen, records_saved, next_cursor, "complete")
        print(f"Complete. Database: {args.db}")
        print(f"Run ID: {run_id}")
        return 0
    except Exception as exc:
        update_run(conn, run_id, records_seen, records_saved, next_cursor, "failed", str(exc))
        print(f"Failed: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch OpenAlex works that cite a source work into SQLite."
    )
    parser.add_argument(
        "--source-id",
        default="W2117692326",
        help="OpenAlex work ID or URL for the cited source work.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of citing works to fetch.",
    )
    parser.add_argument(
        "--db",
        default="data/openalex_citations.sqlite",
        help="SQLite database path.",
    )
    parser.add_argument(
        "--per-page",
        type=int,
        default=100,
        help="OpenAlex page size. Max 100.",
    )
    parser.add_argument(
        "--sort",
        default="",
        help="Optional OpenAlex sort expression, for example cited_by_count:desc.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.2,
        help="Delay between page requests, in seconds.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=4,
        help="Retries for transient HTTP/network failures.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("OPENALEX_API_KEY", ""),
        help="OpenAlex API key. Defaults to OPENALEX_API_KEY.",
    )
    parser.add_argument(
        "--email",
        default=os.environ.get("OPENALEX_EMAIL", ""),
        help="Contact email passed as mailto. Defaults to OPENALEX_EMAIL.",
    )
    return parser


def validate_args(args: argparse.Namespace) -> argparse.Namespace:
    if args.limit < 1:
        raise ValueError("--limit must be >= 1")
    if args.per_page < 1 or args.per_page > 100:
        raise ValueError("--per-page must be between 1 and 100")
    return args


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return validate_args(args)
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(run(parse_args(sys.argv[1:])))
