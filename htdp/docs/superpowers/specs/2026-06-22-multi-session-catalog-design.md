# Multi-Session Catalog — Design

**Date:** 2026-06-22
**Slice:** v0.2 — multi-session queryable catalog
**Status:** approved, ready for implementation plan

## Goal

Add `htdp catalog <sessions_dir> <out.parquet>`: scan a directory of raw session folders
and emit a one-row-per-session Parquet index — the inventory view of "what sessions do I
have", queryable by any Parquet-aware tool (polars, DuckDB, pandas). This slots in after
ingest as the factory-floor catalog; releases are curated subsets and are out of scope.

## Non-Goals

- Indexing packaged releases (raw sessions dir only; releases already ship `sessions.csv`).
- A bespoke query language or CLI filters (`--protocol`, `--qc`, …) — query the Parquet
  directly. Build-only this slice.
- Duration / sample-count columns (would require reading stream CSVs; deferred).
- Incremental / append updates (full rebuild each run).
- Cross-session analytics or joins.

## Background (verified)

A raw session folder contains `session.json` and `device_config.json`. Field locations
(verified against `src/htdp/schemas/models.py` and the actual written JSON):

- **`session.json`** (`Session` model): `session_id`, `participant_id`, `protocol_id`,
  `consent_form_version`, `device_config_id`, `start_time_s` (float), `qc_status`
  (enum, default `pass`), `processing_status` (enum, default `raw`).
- **`device_config.json`** (`DeviceConfig` model): `device_config_id`, `frame`, and
  `streams` — each with a `role` (`motion` / `eeg` / `video` / `events`).

There is **no session-level `source`/provenance field**: `source` exists only as a
per-row field inside the events-stream CSV (`"synthetic"` / `"real"`), which is marker
provenance, not session provenance. The catalog therefore does NOT include a `source`
column — `device_config_id` (e.g. `"vive-synth"`) already proxies provenance, and
fabricating a session `source` from marker rows would be misleading. `polars` is already a
core dependency (used by `replay`/`processing`); no new dependency. `validate.py` already
parses these files via the `Session` / `DeviceConfig` pydantic models.

## Architecture

New single module `src/htdp/catalog.py` (mirrors `validate.py`'s single-file shape):

```
CatalogError(RuntimeError)
scan_sessions(sessions_dir: Path) -> list[dict[str, str | float]]
build_catalog(sessions_dir: Path, out_path: Path) -> Path
```

### `scan_sessions(sessions_dir) -> list[dict]`

- `sessions_dir` not a directory → `CatalogError`.
- Iterate immediate subdirectories that contain a `session.json`, sorted by directory name.
- Zero such subdirectories → `CatalogError` (empty inventory is an error, fail-fast).
- For each: parse `session.json` via `Session.model_validate_json` and
  `device_config.json` via `DeviceConfig.model_validate_json`. A missing or invalid file
  raises `CatalogError` (no partial catalog).
- Build one row dict (schema below). Return rows sorted by `session_id`.

### `build_catalog(sessions_dir, out_path) -> Path`

- `rows = scan_sessions(sessions_dir)`.
- Construct a polars DataFrame with the explicit column order (below) and write
  `out_path` via `write_parquet`. Return `out_path`.

## Row Schema

Stable column order:

| Column | Source | Notes |
|---|---|---|
| `session_id` | session.json | sort key |
| `participant_id` | session.json | |
| `protocol_id` | session.json | |
| `device_config_id` | session.json | also proxies provenance (e.g. `vive-synth`) |
| `consent_form_version` | session.json | |
| `qc_status` | session.json | enum value as string (e.g. `"pass"`) |
| `processing_status` | session.json | enum value as string (e.g. `"raw"`) |
| `start_time_s` | session.json | float |
| `modalities` | device_config.json | comma-joined **sorted unique** stream roles, e.g. `"events,motion"` |

Nine columns. Enum fields are written as their string values (`qc_status.value`,
`processing_status.value`). `modalities` for the synth session is `"events,motion"`
(roles `{motion, events}` sorted).

## CLI

`src/htdp/cli.py`, new command:

```
htdp catalog <sessions_dir> <out_path>
```

Lazy-imports `build_catalog` / `CatalogError`; on `CatalogError` prints `error: <msg>` to
stderr and exits 1; on success prints `wrote <out_path> (<n> sessions)`.

## Error Handling

All raise `CatalogError`:
- `sessions_dir` missing / not a directory.
- No session subfolders found.
- A session folder missing `session.json` or `device_config.json`, or failing pydantic
  validation.

Fail-fast: no Parquet is written if any session is malformed.

## Testing

New `tests/test_catalog.py` (no optional-dep gate — polars + synth are in the base env):

- **Build:** a synth dir with two sessions (`generate_session` seed 1 & 2) →
  `build_catalog` writes Parquet; read back via `polars.read_parquet`: 2 rows, exact
  column list/order (9 columns), `modalities == "events,motion"`, rows sorted by
  `session_id`, `qc_status == "pass"`.
- **Determinism:** two builds of the same dir produce byte-identical Parquet files
  (Parquet write is deterministic for identical input/schema).
- **Missing dir** → `CatalogError`.
- **Empty dir** (exists, no session folders) → `CatalogError`.
- **Malformed session** (a subfolder with `session.json` but no `device_config.json`) →
  `CatalogError`.
- **CLI:** happy path exit 0 + output contains `2 sessions`; bad dir exit 1 + `error:`.

## Files Touched

- New: `src/htdp/catalog.py`
- New: `tests/test_catalog.py`
- Modify: `src/htdp/cli.py` (add `catalog` command)
- Modify: docs — `docs/ARCHITECTURE.md` (or `docs/DATA_CONTRACT.md`), `AGENTS.md`,
  `docs/ROADMAP.md`
- Modify: the mypy gate command (add `src/htdp/catalog.py` — it is core, no optional dep)

No other files change. No new dependency. No persisted-schema change → no JSON-Schema
re-export.

## mypy

`src/htdp/catalog.py` joins the mypy gate target. polars is typed; if a specific call
trips strict mypy, resolve with a narrow annotation (not a blanket ignore), decided
against real mypy output in the plan.

## Determinism

Sessions sorted by id; modalities sorted; explicit stable column order → reproducible
Parquet. Tests assert byte-identical rebuilds.

## Self-Review

- **Placeholders:** none — every column, its source file, the error conditions, and the
  synth expected values (`source="synthetic"`, `modalities="events,motion"`) are concrete.
- **Consistency:** no `source` column (no session-level source field exists — verified);
  `device_config.json` is still read for `modalities`; parsing reuses the same pydantic
  models as `validate.py`; column order (9) is fixed once and referenced by the test.
- **Scope:** single implementation plan — one module, one CLI command, one test file, docs.
  Build-only; raw-dir only; no query DSL.
- **Ambiguity:** `modalities` defined as comma-joined sorted unique roles; enums written as
  string values; empty dir is an error (not an empty catalog); full rebuild (no append).
