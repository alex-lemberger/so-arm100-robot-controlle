# Catalog Query Filters — Design

**Date:** 2026-06-22
**Slice:** v0.2 — catalog query filters (follow-up to slice 11)
**Status:** approved, ready for implementation plan

## Goal

Add `htdp catalog-query <catalog.parquet> [filters]`: read the slice-11 catalog Parquet,
apply field filters, and print the matching `session_id`s (one per line, sorted) so the
result pipes into other commands. Pure read/filter — no catalog rebuild, no new file.

## Non-Goals

- Range / comparison filters (e.g. `start_time_s` windows).
- OR semantics across filters (filters combine with AND only).
- Output formats beyond plain `session_id` lines (no table, no JSON, no filtered Parquet —
  pipe the ids into the next command instead).
- Re-scanning the raw sessions directory (query operates on the built Parquet).
- Building the catalog (that is slice 11's `build_catalog`).

## Background (verified, slice 11)

`src/htdp/catalog.py` exists with `CatalogError`, `scan_sessions`, `build_catalog`. The
catalog Parquet has 9 string/float columns:
`session_id, participant_id, protocol_id, device_config_id, consent_form_version,
qc_status, processing_status, start_time_s, modalities`. `modalities` is a comma-joined
sorted set of stream roles, e.g. `"events,motion"`. `polars` is core. The mypy gate already
includes `src/htdp/catalog.py`.

## Architecture

Extend `src/htdp/catalog.py` (no new module):

```
query_catalog(
    catalog_path: Path,
    *,
    protocol: str | None = None,
    qc_status: str | None = None,
    participant: str | None = None,
    processing_status: str | None = None,
    modality: str | None = None,
) -> list[str]
```

- Reads the Parquet via `polars.read_parquet`. A missing file (or unreadable Parquet)
  raises `CatalogError`.
- Applies each **provided** (non-`None`) filter with **AND** semantics:
  - `protocol` → `protocol_id == protocol`
  - `qc_status` → `qc_status == qc_status`
  - `participant` → `participant_id == participant`
  - `processing_status` → `processing_status == processing_status`
  - `modality` → set membership: a row matches if `modality` is in
    `row.modalities.split(",")` (so `--modality eeg` matches sessions whose modality set
    contains `eeg`, not a raw substring match).
- Returns the matching `session_id`s, sorted ascending. No filters → all session_ids.

`CatalogError` is reused (already defined in the module).

## CLI

`src/htdp/cli.py`, new command:

```
htdp catalog-query <catalog_path> [--protocol P] [--qc Q] [--participant PID]
                                  [--processing-status S] [--modality M]
```

- Maps `--qc` → `qc_status`, `--processing-status` → `processing_status`; other options map
  by name.
- Calls `query_catalog`; prints each matching `session_id` on its own line to stdout.
- Empty match → no output, exit 0.
- `CatalogError` → `error: <msg>` to stderr, exit 1.

## Error Handling

- `catalog_path` missing / not a readable Parquet → `CatalogError`.
- Unknown filter values (e.g. `--qc bogus`) are not errors — they simply match no rows
  (empty output, exit 0). This keeps the filter purely data-driven.

## Testing

Append to `tests/test_catalog.py` (no optional-dep gate — polars + synth are base env):

Build a catalog from two synth sessions (`generate_session` seed 1 & 2 → both
`protocol_id="reach-grasp-place"`, `modalities="events,motion"`, `qc_status="pass"`), then:

- **No filters** → both session_ids, sorted (`["synth-0001", "synth-0002"]`).
- **Matching protocol** (`protocol="reach-grasp-place"`) → both.
- **Non-matching protocol** (`protocol="nope"`) → `[]`.
- **Modality membership:** `modality="motion"` → both; `modality="eeg"` → `[]` (synth has
  no eeg).
- **AND combination:** `protocol="reach-grasp-place", qc_status="pass"` → both;
  `protocol="reach-grasp-place", qc_status="fail"` → `[]`.
- **Missing catalog file** → `CatalogError`.
- **CLI:** `catalog-query <parquet> --modality motion` exit 0, output contains both ids,
  one per line; `catalog-query <missing> ...` exit 1 + `error:`.

## Determinism

Results sorted by `session_id`. Same catalog + same filters → identical output.

## Files Touched

- Modify: `src/htdp/catalog.py` (add `query_catalog`)
- Modify: `src/htdp/cli.py` (add `catalog-query` command)
- Modify: `tests/test_catalog.py` (append query tests)
- Modify: docs — `docs/ARCHITECTURE.md`, `AGENTS.md`, `docs/ROADMAP.md`

No new module, no new dependency, no persisted-schema change → no JSON-Schema re-export.
`catalog.py` is already in the mypy gate.

## Self-Review

- **Placeholders:** none — every filter, its column, the membership rule, and the synth
  expected values are concrete.
- **Consistency:** filters map to the slice-11 column names; `modality` uses set membership
  on the comma-joined `modalities` field (matching how `build_catalog` writes it); `CatalogError`
  reused from the same module.
- **Scope:** single implementation plan — one function, one CLI command, appended tests,
  docs. AND-only, equality + modality-membership, session_id output.
- **Ambiguity:** AND semantics explicit; unknown filter values match nothing (not an error);
  empty result is valid (exit 0); output is one session_id per line.
