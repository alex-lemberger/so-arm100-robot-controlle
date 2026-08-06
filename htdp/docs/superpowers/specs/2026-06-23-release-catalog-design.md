# Release-Level Catalog — Design

**Date:** 2026-06-23
**Slice:** v0.2 — release-level catalog (companion to slices 11–13 session catalog)
**Status:** approved, ready for implementation plan

## Goal

Add `htdp catalog-releases <releases_dir> <out.parquet>`: scan a directory of packaged
releases into a deterministic one-row-per-release Parquet inventory. This is the
release-grain parallel to slice 11's session-grain `htdp catalog`. Manifest-driven — each
release's `manifest.json` is the single source of truth; no walk of `data/` needed.

## Non-Goals

- Query filters on the release catalog (slice 12 added query for the session catalog as its
  own slice; a `catalog-releases-query` is a possible later slice, not this one).
- One-row-per-session output (that is slice 11's grain / the rejected "sessions-within-release"
  alternative).
- Scanning raw sessions (slice 11) or reading session.json/device_config.json (the manifest
  already carries everything this catalog needs).
- New dependency or schema change.

## Background (verified)

A packaged release directory contains `manifest.json` plus `data/<session_id>/...`. The
manifest is the `DatasetRelease` pydantic model (`src/htdp/schemas/models.py`):
`release_name: str`, `profile: str`, `session_ids: list[str]`,
`absent_modalities: list[str]` (default `[]`), `manifest_sha256: str`.
`src/htdp/catalog.py` already has `CatalogError`, `scan_sessions`, `build_catalog`,
`query_catalog` and is in the mypy gate. `polars` is core.

## Architecture

Extend `src/htdp/catalog.py` (no new module), mirroring `scan_sessions`/`build_catalog`:

```python
_RELEASE_COLUMNS = [
    "release_name",
    "profile",
    "n_sessions",
    "session_ids",
    "absent_modalities",
    "manifest_sha256",
]

def scan_releases(releases_dir: Path) -> list[dict[str, str | int]]:
    ...

def build_release_catalog(releases_dir: Path, out_path: Path) -> Path:
    ...
```

- `scan_releases`:
  - `releases_dir` not a directory → `CatalogError`.
  - release dirs = sorted subdirs `p` where `(p / "manifest.json").exists()`.
  - none found → `CatalogError`.
  - per release: `DatasetRelease.model_validate_json((p / "manifest.json").read_text(...))`;
    on `pydantic.ValidationError` → `CatalogError` (fail-fast, like `scan_sessions`).
  - row:
    - `release_name` = `release.release_name`
    - `profile` = `release.profile`
    - `n_sessions` = `len(release.session_ids)` (int)
    - `session_ids` = `",".join(sorted(release.session_ids))`
    - `absent_modalities` = `",".join(sorted(release.absent_modalities))` (empty → `""`)
    - `manifest_sha256` = `release.manifest_sha256`
  - return rows sorted by `release_name`.
- `build_release_catalog`: `pl.DataFrame(rows).select(_RELEASE_COLUMNS).write_parquet(out_path)`;
  returns `out_path`. (Same shape as `build_catalog`.)

`CatalogError` is reused (already in the module).

## CLI

`src/htdp/cli.py`, new command mirroring `catalog`:

```
htdp catalog-releases <releases_dir> <out_path>
```

- Calls `build_release_catalog`; on success prints `wrote <out> (<n> releases)` where `n` =
  `pl.read_parquet(out).height`.
- `CatalogError` → `error: <msg>` to stderr, exit 1.

## Error Handling

- `releases_dir` missing / not a directory → `CatalogError`.
- A subdir without `manifest.json` is simply skipped (not a release); a dir with no release
  subdirs at all → `CatalogError` (`no releases found`).
- Malformed `manifest.json` → `CatalogError`.

## Determinism

Rows sorted by `release_name`; `session_ids`/`absent_modalities` are sorted before joining;
`polars.write_parquet` is byte-identical for identical input (verified in slice 11). Same
releases dir → byte-identical Parquet.

## Testing

Append to `tests/test_catalog.py` (no optional-dep gate — polars + synth + package are base):

Build two releases from synth sessions via `package_release` (reuse the slice-10/11 release
fixture pattern: `generate_session` seed 1 & 2, then `package_release([...], name, profile,
raw_root, releases_root)`), giving releases under one `releases_root`. Then:

- **Columns:** built Parquet `.columns == _RELEASE_COLUMNS`.
- **One row per release:** `.height == 2`; `release_name` column sorted.
- **n_sessions:** matches the session count packaged into each release (e.g. a single-session
  release → `1`).
- **session_ids:** comma-joined sorted ids of that release (e.g. `"synth-0001"`).
- **profile:** equals the profile value the release was packaged with.
- **absent_modalities:** for a `commercial_dataset` release of synth sessions this is
  `"eeg,video"` (that profile's consent forbids eeg+video; comma-joined sorted) — assert the
  exact string read back from the manifest, or `"eeg,video"` directly.
- **manifest_sha256:** equals the value in that release's `manifest.json` (read back, not
  hardcoded).
- **Determinism:** two builds of the same releases dir → byte-identical Parquet.
- **Errors:** `scan_releases(<missing dir>)` and `scan_releases(<empty dir>)` raise
  `CatalogError`; a dir whose only subdir lacks `manifest.json` → `CatalogError`.
- **CLI:** `catalog-releases <releases_root> <out>` exit 0, output contains `releases`, file
  exists; `catalog-releases <missing> <out>` exit 1 + `error:`.

## Files Touched

- Modify: `src/htdp/catalog.py` (add `_RELEASE_COLUMNS`, `scan_releases`, `build_release_catalog`)
- Modify: `src/htdp/cli.py` (add `catalog-releases` command)
- Modify: `tests/test_catalog.py` (append release-catalog tests)
- Modify: docs — `docs/ARCHITECTURE.md`, `AGENTS.md`, `docs/ROADMAP.md`

No new module, no new dependency, no persisted-schema change → no JSON-Schema re-export.
`catalog.py` is already in the mypy gate.

## Self-Review

- **Placeholders:** none — every column, its source manifest field, the join rules, and the
  test expectations are concrete.
- **Consistency:** mirrors `scan_sessions`/`build_catalog` (same fail-fast, same sorted
  determinism, same `pl.DataFrame(...).select(...).write_parquet` shape); reuses
  `CatalogError`; manifest field names match `DatasetRelease`.
- **Scope:** single plan — two functions, one CLI command, appended tests, docs. Build-only,
  no query (query is a separate potential slice).
- **Ambiguity:** release grain (one row per release) explicit; manifest-driven (no data/
  walk); subdir without `manifest.json` skipped, empty result is an error; `n_sessions` is an
  int column, `session_ids`/`absent_modalities` comma-joined sorted strings.
