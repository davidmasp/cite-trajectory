#!/usr/bin/env python3
"""Run OpenAlex citation fetch jobs from a TOML config file."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
import tomllib
from typing import Any

import fetch_openalex_citations as fetcher


@dataclass
class FetchJob:
    index: int
    total: int
    label: str
    normalized_source_id: str
    args: argparse.Namespace


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run fetch_openalex_citations.py for multiple source IDs from TOML."
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to a TOML config file describing output settings and source IDs.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the config and print the planned fetch jobs without calling OpenAlex.",
    )
    return parser


def load_config(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise ValueError(f"Config file does not exist: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Could not parse TOML config {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Config root must be a TOML table: {path}")
    return data


def expect_table(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"{key!r} must be a TOML table")
    return value


def expect_bool(data: dict[str, Any], key: str, default: bool) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key!r} must be true or false")
    return value


def expect_int(data: dict[str, Any], key: str, default: int) -> int:
    value = data.get(key, default)
    if not isinstance(value, int):
        raise ValueError(f"{key!r} must be an integer")
    return value


def expect_float(data: dict[str, Any], key: str, default: float) -> float:
    value = data.get(key, default)
    if not isinstance(value, (int, float)):
        raise ValueError(f"{key!r} must be numeric")
    return float(value)


def expect_str(data: dict[str, Any], key: str, default: str) -> str:
    value = data.get(key, default)
    if not isinstance(value, str):
        raise ValueError(f"{key!r} must be a string")
    return value


def resolve_path(base_dir: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def build_db_path(config_dir: Path, config: dict[str, Any]) -> Path:
    output = expect_table(config, "output")
    output_dir = resolve_path(config_dir, expect_str(output, "directory", "data"))
    database = Path(expect_str(output, "database", "openalex_citations.sqlite"))
    if database.is_absolute():
        return database
    return output_dir / database


def build_jobs(config_path: Path, config: dict[str, Any]) -> tuple[list[FetchJob], bool]:
    sources = config.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("'sources' must be a non-empty TOML array of tables")

    config_dir = config_path.parent.resolve()
    db_path = build_db_path(config_dir, config)
    continue_on_error = expect_bool(config, "continue_on_error", False)
    fetch = expect_table(config, "fetch")

    default_limit = expect_int(fetch, "limit", 100)
    per_page = expect_int(fetch, "per_page", 100)
    delay = expect_float(fetch, "delay", 0.2)
    retries = expect_int(fetch, "retries", 4)
    timeout = expect_int(fetch, "timeout", 60)
    sort = expect_str(fetch, "sort", "")
    api_key = expect_str(fetch, "api_key", "")
    email = expect_str(fetch, "email", "")

    jobs: list[FetchJob] = []
    total = len(sources)

    for index, source in enumerate(sources, start=1):
        if not isinstance(source, dict):
            raise ValueError("Each source entry must be a TOML table")

        raw_source_id = source.get("id", source.get("source_id"))
        if not isinstance(raw_source_id, str) or not raw_source_id.strip():
            raise ValueError(f"Source #{index} must define a non-empty 'id'")

        label = source.get("label", "")
        if not isinstance(label, str):
            raise ValueError(f"Source #{index} field 'label' must be a string")

        limit = source.get("limit", default_limit)
        if not isinstance(limit, int):
            raise ValueError(f"Source #{index} field 'limit' must be an integer")

        args = argparse.Namespace(
            source_id=raw_source_id,
            limit=limit,
            db=str(db_path),
            per_page=per_page,
            sort=sort,
            delay=delay,
            retries=retries,
            timeout=timeout,
            api_key=api_key,
            email=email,
        )
        try:
            fetcher.validate_args(args)
            normalized_source_id = fetcher.normalize_work_id(raw_source_id)
        except ValueError as exc:
            raise ValueError(f"Invalid source #{index} ({raw_source_id!r}): {exc}") from exc

        jobs.append(
            FetchJob(
                index=index,
                total=total,
                label=label.strip(),
                normalized_source_id=normalized_source_id,
                args=args,
            )
        )

    return jobs, continue_on_error


def planned_command(job: FetchJob) -> str:
    return " ".join(
        [
            "python3",
            "scripts/fetch_openalex_citations.py",
            f"--source-id {job.args.source_id}",
            f"--limit {job.args.limit}",
            f"--db {job.args.db}",
            f"--per-page {job.args.per_page}",
            f"--delay {job.args.delay}",
            f"--retries {job.args.retries}",
            f"--timeout {job.args.timeout}",
        ]
        + ([f"--sort {job.args.sort}"] if job.args.sort else [])
        + ([f"--email {job.args.email}"] if job.args.email else [])
        + (["--api-key ***"] if job.args.api_key else [])
    )


def run(args: argparse.Namespace) -> int:
    config_path = Path(args.config).expanduser().resolve()

    try:
        jobs, continue_on_error = build_jobs(config_path, load_config(config_path))
    except ValueError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 1

    print(f"Loaded {len(jobs)} source job(s) from {config_path}")

    failures = 0
    for job in jobs:
        label_suffix = f" [{job.label}]" if job.label else ""
        print(f"[{job.index}/{job.total}] {job.normalized_source_id}{label_suffix}")
        print(f"DB: {job.args.db}")

        if args.dry_run:
            print(f"Dry run: {planned_command(job)}")
            continue

        exit_code = fetcher.run(job.args)
        if exit_code != 0:
            failures += 1
            if not continue_on_error:
                print("Stopping after first failed job.", file=sys.stderr)
                return 1

    if args.dry_run:
        print("Dry run complete.")
        return 0

    if failures:
        print(f"Completed with {failures} failed job(s).", file=sys.stderr)
        return 1

    print("All jobs completed successfully.")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    return build_parser().parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(run(parse_args(sys.argv[1:])))
