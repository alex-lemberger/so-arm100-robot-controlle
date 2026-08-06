# Catalog Range Filters — Design

**Date:** 2026-06-22
**Slice:** v0.2 — catalog range filters (follow-up to slice 12)
**Status:** approved, ready for implementation plan

## Goal

Add numeric range filtering on `start_time_s` to `htdp catalog-query`. Extend the
slice-12 `query_catalog` function and CLI command with `--start-after` / `--start-before`
options that keep sessions whose `start_time_s` falls within the given (inclusive) window.
Pure read/filter — no catalog rebuild, no new file, no new dependency, no schema change.

This is the explicit non-goal deferred in slice 12 ("Range / comparison filters").

## Non-Goals

- Range filters on any column other than `start_time_s` (the only numeric catalog column).
- OR semantics (range bounds combine with each other and all existing filters via AND only).
- Output formats beyond plain `session_id` lines (unchanged from slice 12).
- Date/time string parsing — bounds are raw `float` Unix seconds, matching the catalog column.
- Re-scanning raw sessions or rebuilding the catalog.

## Background (verified, slices 11–12)

`src/htdp/catalog.py` has `CatalogError`, `scan_sessions`, `build_catalog`, and
`query_catalog`. The catalog Parquet has 9 columns; `start_time_s` is a `float` (Unix
seconds, copied from `Session.start_time_s`). `query_catalog` already reads the Parquet via
`polars.read_parquet`, applies each provided (non-`None`) filter with AND semantics, and
returns sorted `session_id`s. `polars` is core; `src/htdp/catalog.py` is in the mypy gate.

## Architecture

Extend `query_catalog` in `src/htdp/catalog.py` with two new keyword-only params:

```
query_catalog(
    catalog_path: Path,
    *,
    protocol: str | None = None,
    qc_status: str | None = None,
    participant: str | None = None,
    processing_status: str | None = None,
    modality: str | None = None,
    start_after: float | None = None,
    start_before: float | None = None,
) -> list[str]
```

- `start_after` → `pl.col("start_time_s") >= start_after` (inclusive lower bound).
- `start_before` → `pl.col("start_time_s") <= start_before` (inclusive upper bound).
- Both new filters AND with each other and with all existing equality/modality filters.
- Inverted range (`start_after > start_before`) is not an error — it simply matches no rows
  (empty output, exit 0), consistent with slice 12's data-driven "unknown value matches
  nothing" rule.
- Returns matching `session_id`s sorted ascending, unchanged.

No new module, no change to `scan_sessions` / `build_catalog`. `CatalogError` reused.

## CLI

`src/htdp/cli.py`, extend the existing `catalog_query` command:

```
htdp catalog-query <catalog_path> [...existing filters...]
                                  [--start-after SECONDS] [--start-before SECONDS]
```

- New options: `start_after: float | None = typer.Option(None, "--start-after")` and
  `start_before: float | None = typer.Option(None, "--start-before")`, passed through to
  `query_catalog` by name.
- Output, exit codes, and `CatalogError` handling unchanged (one id per line; empty match
  exit 0; `CatalogError` → `error: <msg>` stderr, exit 1).

## Error Handling

- Missing / unreadable catalog → `CatalogError` (unchanged).
- Inverted or out-of-data-range bounds are not errors — they match no rows (exit 0).
- Bound type is enforced by typer (`float`); a non-numeric value fails at CLI parse time
  with typer's standard usage error (no `query_catalog` change needed).

## Testing

Append to `tests/test_catalog.py` (no optional-dep gate — polars + synth are base env).

**Why not synth:** the synth generator hardcodes `start_time_s=0.0`
(`src/htdp/synth/generate.py:155`), so two synth sessions share the same time — useless for
range tests. `query_catalog` only *reads* the Parquet, so build a controlled 2-row catalog
Parquet directly via `pl.DataFrame` (all 9 catalog columns, distinct `start_time_s` values
e.g. `100.0` and `200.0`) and query it. This isolates the range logic and stays deterministic.

A small test helper writes such a Parquet. With `lo=100.0`, `hi=200.0`, `mid=150.0` and ids
`session-a` (lo) / `session-b` (hi):

- `start_after=mid` → `["session-b"]` (only the later session).
- `start_before=mid` → `["session-a"]` (only the earlier session).
- `start_after=lo, start_before=hi` → both (inclusive bounds keep both endpoints).
- Inclusive boundary: `start_after=hi` → `["session-b"]` (>= includes the exact value).
- Inverted range `start_after=hi, start_before=lo` → `[]`.
- Range AND an existing filter (`start_after=lo, protocol="p"`) → both (both rows protocol `p`).
- **CLI:** `catalog-query <parquet> --start-after 150` exit 0, output = `session-b` only;
  `--start-before 150` → `session-a` only.

## Determinism

Results sorted by `session_id`. Same catalog + same bounds → identical output.

## Files Touched

- Modify: `src/htdp/catalog.py` (two params + two filter branches in `query_catalog`)
- Modify: `src/htdp/cli.py` (two options on `catalog_query`)
- Modify: `tests/test_catalog.py` (append range tests)
- Modify: docs — `docs/ARCHITECTURE.md`, `AGENTS.md`, `docs/ROADMAP.md`

No new module, no new dependency, no persisted-schema change → no JSON-Schema re-export.
`catalog.py` already in the mypy gate.

## Self-Review

- **Placeholders:** none — params, filter exprs, inclusive semantics, and the read-back
  test strategy are concrete.
- **Consistency:** `start_time_s` is the slice-11 column; bounds reuse the AND-merge pattern
  and the data-driven "no error on empty match" rule from slice 12; `CatalogError` reused.
- **Scope:** single plan — two function params, two CLI options, appended tests, docs.
- **Ambiguity:** inclusive bounds (`>=` / `<=`) explicit; inverted range is empty not error;
  bounds are raw float seconds (no date parsing); test reads `start_time_s` back rather than
  assuming hardcoded values.
