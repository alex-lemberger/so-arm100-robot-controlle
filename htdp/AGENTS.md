# AGENTS.md — Human-Task Dataset Pipeline (v0.1)

This project is a **consent-based human-task dataset pipeline for robotics**. The
product unit is a **dataset release**, not an app. v0.1 is a synthetic, filesystem-only
spine.

**Companion repo (control-center dashboard).** The Angular frontend that views this
pipeline's status and runs its jobs from a UI lives at `~/neurofeedback-lang-app`
(separate repo). It consumes `htdp serve` (the FastAPI read + job-runner surface, optional
`serve` extra, localhost-only) via its `/lab` section. Integration doc + contract:
`~/neurofeedback-lang-app/docs/INTEGRATION.md`. The contract source of truth is
`src/htdp/serve/models.py` here, hand-mirrored by the app's `pipeline.models.ts` — change
both together. This repo stays the product (dataset + ML); the app is a consumer — keep
them separate. (`htdp serve` is the one sanctioned exception to the "no servers" rule:
read-only + job-runner, localhost, optional extra — see `docs/ARCHITECTURE.md`.)

## Hard rules
- Do NOT add servers (Postgres/MinIO/FastAPI), Docker, dashboards, real hardware,
  LSL/XDF, video, EEG, or ROS in v0.1.
- Do NOT store raw data in a database.
- Do NOT bypass consent checks. `package` blocks on conflict and writes nothing.
- Do NOT modify raw data during processing. Raw is immutable.
- `htdp ingest-video` re-writes `device_config.json` and `checksums.sha256` of an
  existing raw session as a **raw-construction** step (populating the `video/`
  slot), which is distinct from the prohibited *processing-stage* mutation of raw.
- Keep fixtures tiny and deterministic. Update schemas and docs together.
- Preserve manifests + checksums. Make errors explicit.

## Quality gate (run before every commit)
`uv run ruff format --check . && uv run ruff check . && uv run pytest`
Typecheck: `uv run mypy src/htdp/schemas src/htdp/consent src/htdp/release src/htdp/io src/htdp/ingest src/htdp/export src/htdp/catalog.py`

## Reproducibility
Same code + uv.lock + platform + seed + inputs → identical release-manifest checksum.
Canonical JSON (sorted keys, UTF-8) and CSV (stable columns, 6dp floats, \n). Generated
timestamps seed-derived; tool versions recorded but excluded from the reproducibility hash.

## Skills

Applicable: `superpowers:brainstorming`, `superpowers:writing-plans`,
`superpowers:test-driven-development`, `mujoco-python`.

Ignore: `angular-developer`, `wordpress-divi-admin`, `figma:*`.

## Scope (v0.1 boundary)

v0.1 must remain **offline, deterministic, synthetic, filesystem-only, and testable on a
normal development machine**. Any change introducing real hardware, servers, dashboards,
ROS, EEG, or video is **out of scope** and must be rejected unless this spec is
intentionally revised.

## Architecture summary

```
ingest (xdf → raw/, optional) | synth → raw/ → validate → process → processed/ → qc → package → releases/ → replay
```

Three data tiers on disk:
- **raw/** — immutable once written, checksummed.
- **processed/** — regenerable (Parquet + QC report).
- **releases/** — versioned, packaged. The product unit.

CLI is the only product surface. No server processes, no dashboard.

Usage:
- `uv sync --extra ingest` (install pyxdf optional dependency)
- `htdp ingest <file.xdf> <ingest.json> --out data/raw`
- The `ingest.json` sidecar `ingest_map` supports roles: `motion`, `events`, and `eeg`. An eeg entry shape: `{"role":"eeg","eeg_id":<id>,"channels":{<label>:<index>,...}}`.
- `htdp ingest-video <session_dir> <clip.mp4> <video.json> [--force]`
- `htdp synth --out data/raw`
- `htdp validate data/raw/<session_id>`
- `htdp process data/raw/<session_id>`
- `htdp qc data/processed/<session_id>`
- `htdp package --release <name> --profile <profile> <session_ids...>`
- `htdp replay data/releases/<name>`
- `htdp replay-ik <release_dir> [--max-steps N] [--out PATH] [--force] [--orientation-cost FLOAT]` (drive a vendored 6-DOF arm's EEF along the release's wrist path via mink differential IK; `--orientation-cost` 0.0 = position-only, >0 weights wrist-orientation tracking (full 6-DOF pose on the 6-DOF arm); `--out` writes per-step joint trajectory CSV (`timestamp_s, q0..qN, target_x/y/z, tracking_error_m, target_qw/qx/qy/qz, orientation_error_rad`); `--force` overwrites; requires `uv sync --extra replay` which includes mujoco, mink, and daqp)
- `htdp export-bids <raw_dir> <out_dir> [--force]` (**read-only export**; writes a separate BIDS tree, never mutates raw/processed/releases)
- `htdp export-release-bids <release_dir> <out_dir> [--force]` (**read-only export** of a packaged release to multi-subject BIDS)
- `htdp export-release-rosbag <release_dir> <out_dir> [--force]` (**read-only export** of a packaged release to one rosbag2 mcap bag per session; includes motion, events, and EEG (custom `EegSample` message) when present; requires the `rosbag` extra: `uv sync --extra rosbag`)
- `htdp catalog <sessions_dir> <out.parquet>` — builds a
one-row-per-session Parquet inventory of a raw sessions directory (read-only).
- `htdp catalog-query <catalog.parquet> [--protocol P] [--qc Q] [--participant PID] [--processing-status S] [--modality M] [--start-after SECONDS] [--start-before SECONDS]`
- `htdp catalog-releases <releases_dir> <out.parquet>` — builds a one-row-per-release Parquet inventory (release_name, profile, n_sessions, session_ids, absent_modalities, manifest_sha256) from a directory of packaged releases (read-only).

## Extending the project

- To add a new backend or data source, **do not touch existing pipeline stages**. Add a
  new stage or an adapter before the raw tier.
- Changing a schema model requires updating `docs/DATA_CONTRACT.md` and the JSON schemas
  (`uv run python -c "from pathlib import Path; from htdp.schemas.export import
  export_json_schemas; export_json_schemas(Path('docs/schemas'))"`).
- The `replay` extra (`mujoco`, `mink>=1.1`, `daqp>=0.5`) is optional. Core tests must pass without it.
- New CLI commands go in `src/htdp/cli.py`; business logic goes in a matching submodule.
