# End-to-End Integration Test — Design

**Date:** 2026-06-23
**Slice:** v0.2 — pipeline integration test (hardening / v0.2-cut readiness)
**Status:** approved, ready for implementation plan

## Goal

Add a single CLI-level end-to-end test that threads the whole pipeline —
`synth → ingest-video → validate → process → qc → package (per-session consent) → catalog /
catalog-releases / catalog-query → export-release-bids` — and asserts the cross-slice
properties no unit test covers. Plus gated segments for the optional-extra consumers
(`replay-ik`, `export-release-rosbag`) and the alternate ingest entry (`htdp ingest` XDF).
This proves the 18 slices *compose*, the thing a v0.2 cut needs.

## Non-Goals

- New production code or behavior change — this is a test-only slice (plus one small docs note).
- v0.2 housekeeping (CHANGELOG, version bump, README) — a separate later slice.
- Re-testing logic already covered by unit tests at the function level — the value here is
  the *wiring* across stages via the real CLI entry points.
- Exhaustive matrix coverage — one representative thread + the key cross-slice assertions.

## Background (verified live)

The full core thread runs green via `typer.testing.CliRunner` in an isolated filesystem.
Two real integration constraints were discovered and must shape the test:

1. **The CLI is cwd-anchored at `data/`.** `process` writes to `Path("data/processed")` and
   `package` reads `Path("data/raw")` / writes `Path("data/releases")` (hardcoded, cli.py).
   So the test runs inside `runner.isolated_filesystem()` and uses `synth --out data/raw`.
2. **Consent edits must precede a re-checksum step.** `synth` writes `checksums.sha256` over
   the session; editing `consent.json` afterward makes `validate` fail
   (`checksum mismatch: consent.json`). `ingest-video` re-checksums the folder, so the order
   must be: synth → edit consent → ingest-video → validate.
3. **The raw session dir name must encode the session number.** `process` parses an int from
   the directory name (a non-conforming name like `ingested` fails with
   `invalid literal for int()`), so the `ingest --out` target must use the session-id
   convention `data/raw/synth-0001`, not an arbitrary name.

Command surface (cli.py): base-env = `synth, ingest-video, validate, process, qc, package,
catalog, catalog-releases, catalog-query, export-bids, export-release-bids`; extra-gated =
`ingest` (pyxdf), `export-release-rosbag` (rosbags), `replay`/`replay-ik` (mink). The XDF test
writer `tests/_xdf_writer.py` exposes `write_xdf` and `build_sidecar`.

## Architecture

One new file: `tests/test_integration_pipeline.py`. No production change.

### Shared helpers

```python
def _run(runner, *args) -> Result   # invoke app, assert exit_code == 0, return result
def _build_core_release(runner) -> None
    # within the current isolated cwd: synth seed 1 & 2 → edit consent
    # (synth-0001 distribute_raw_video=True, synth-0002=False) → ingest-video a dummy
    # mp4 ("cam0", fps 30) into both → package synth-0001 synth-0002
    #   --release rel --profile commercial_dataset.
    # Leaves data/raw, data/releases/rel populated.
```

`ingest-video` sidecar is `{"name": "cam0", "fps": 30.0}`; the mp4 is a 3-byte dummy
(`b"\x00\x01\x02"`) — `ingest-video` copies opaque bytes, no decode.

### Core test — `test_full_pipeline_cli` (base env, NOT gated)

Inside `runner.isolated_filesystem()`:
1. `synth --out data/raw --seed 1`, `--seed 2`.
2. For each session: edit `data/raw/<sid>/consent.json` `distribute_raw_video`
   (synth-0001 True, synth-0002 False), then `ingest-video data/raw/<sid> clip.mp4 vid.json`.
3. Per session: `validate data/raw/<sid>` (exit 0 / "OK"), `process data/raw/<sid>`,
   `qc data/processed/<sid>`.
4. `package synth-0001 synth-0002 --release rel --profile commercial_dataset`.
5. **Cross-slice assertions:**
   - `data/releases/rel/data/synth-0001/video/cam0.mp4` exists (A allowed → kept).
   - `data/releases/rel/data/synth-0002/video/cam0.mp4` does NOT exist (B forbade → dropped).
   - manifest `absent_modalities_by_session == {"synth-0001": ["eeg"], "synth-0002": ["eeg","video"]}`.
   - manifest `absent_modalities == ["eeg"]`.
6. `catalog data/raw sess.parquet`, `catalog-releases data/releases rel.parquet`,
   `catalog-query sess.parquet --modality video`.
   - **Grain assertion:** the query returns BOTH session ids (both raw device_configs carry the
     video StreamRef), even though the release dropped video for synth-0002 — catalog reflects
     raw, release reflects consent.
7. `export-release-bids data/releases/rel bids_out`; assert `bids_out/dataset_description.json`
   exists and both `sub-p0001`, `sub-p0002` directories are present.

### Gated segments (each its own test)

Each runs `_build_core_release` in its own isolated fs, then the extra command:

- `test_pipeline_replay_ik` — `pytest.importorskip("mink")`; `replay-ik data/releases/rel
  --out traj.csv` exit 0; `traj.csv` exists with a header row.
- `test_pipeline_rosbag` — `pytest.importorskip("rosbags")`; `export-release-rosbag
  data/releases/rel rosbag_out` exit 0; a per-session bag dir exists under `rosbag_out`.
- `test_pipeline_xdf_ingest` — `pytest.importorskip("pyxdf")`; use
  `tests._xdf_writer.write_xdf` + `build_sidecar` (from a throwaway `synth` session) to produce
  an `.xdf` + sidecar, then `ingest s.xdf ingest.json --out data/raw/synth-0001` exit 0
  (the out-dir must be the session dir and follow the `synth-0001` naming so `process` accepts
  it — constraint 3), then `validate`/`process data/raw/synth-0001` exit 0. Proves the
  real-hardware entry path threads. (Reuses the exact fixture the XDF round-trip unit tests
  use.)

## Error Handling

The test only exercises the happy path end-to-end. `_run` asserts `exit_code == 0` with the
command output included in the assertion message for debuggability.

## Determinism / Offline

Core is base-env with fixed synth seeds (1, 2) → reproducible. All segments are offline (no
network). Gated segments RUN when their extra is installed and SKIP (cleanly) otherwise — they
are NOT part of the always-on core, so a missing extra never hides a core regression.

## Docs

Small addition to `docs/ARCHITECTURE.md`: note the end-to-end integration test and the two
real constraints it encodes — the CLI pipeline is cwd-anchored at `data/`, and consent edits
must precede a re-checksumming step (`ingest-video`) to keep a raw session valid.

## Files Touched

- Create: `tests/test_integration_pipeline.py`
- Modify: `docs/ARCHITECTURE.md` (integration-test + cwd/checksum constraint note)

No production code change, no new dependency, no schema change.

## Self-Review

- **Placeholders:** none — the exact CLI thread, sidecar/mp4 fixtures, gated `importorskip`
  targets, and every assertion are concrete and live-verified.
- **Consistency:** the core thread matches the verified prototype (consent-before-ingest
  ordering, isolated-fs cwd); gated segments reuse real fixtures (`tests._xdf_writer`).
- **Scope:** one test module + a docs note; no production change; housekeeping deferred.
- **Ambiguity:** core is base-env and never gated (no false-green); each optional consumer is
  its own gated test; the grain assertion (catalog=raw vs release=consent) is stated explicitly
  so it is not mistaken for a bug.
