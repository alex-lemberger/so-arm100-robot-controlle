# Architecture

Human-Task Dataset Pipeline v0.1 — filesystem-only, offline, deterministic.

## Layers

```
synth ─▶ raw/ ─▶ validate ─▶ process ─▶ processed/ ─▶ qc ─▶ package ─▶ releases/ ─▶ replay
                    │                                    │        │
                 schemas                             defects   consent gate
                (pydantic)                           caught    (block-on-conflict,
                                                     (warn)    atomic staging)
```

### Data tiers

| Tier | Path | Immutable? | Description |
|------|------|-----------|-------------|
| raw | `data/raw/<sid>/` | Yes — checksummed | Written once by `synth` or a future `ingest` step. Never modified by downstream stages. |
| processed | `data/processed/<sid>/` | No — regenerable | Parquet output of `process`; `qc_report.json` and `qc_report.html` added by `qc`. |
| releases | `data/releases/<name>/` | Yes — atomic | Written atomically by `package`; includes consent manifest and checksums. |

### Module layout

```
src/htdp/
  schemas/      # Pydantic models (Session, Consent, DeviceConfig, Manifest, …) + JSON Schema export
  synth/        # Seeded synthetic session generator with deliberate defect injection
  io/           # Raw read/write helpers, checksums, atomic staging
  validate.py   # Schema + structure + checksum validation
  processing/   # extract → Parquet (raw is read-only)
  qc/           # Per-stream and cross-stream checks, HTML/JSON report
  consent/      # Consent model, release profiles, export gate
  release/      # Release packaging, manifest, release manifest
  replay/       # MuJoCo mocap-body player + IK robot-arm replay (optional dep: extra "replay")
  cli.py        # Typer CLI — the only product surface
```

## CLI surface

```
htdp synth      --seed N --out data/raw/<id> [--force]
htdp validate   data/raw/<id>
htdp process    data/raw/<id>
htdp qc         data/processed/<id>
htdp package    <id...> --release <name> --profile <profile>
htdp replay     data/releases/<name>
htdp replay-ik  data/releases/<name> [--max-steps N] [--out PATH] [--force] [--orientation-cost FLOAT]
htdp catalog    <sessions_dir> <out.parquet>
htdp catalog-releases <releases_dir> <out.parquet>
```


## End-to-end integration testing

`tests/test_integration_pipeline.py` threads the whole pipeline end-to-end through the CLI,
covering stages from `synth` through `package`, `catalog`, and export. Three CLI-level
constraints it encodes:

1. **Cwd-anchored `data/` directory** — `process` and `package` use `data/raw`,
   `data/processed`, and `data/releases` relative to the working directory; tests must run
   inside a controlled filesystem root (e.g. `tmp_path`).
2. **Consent edits before re-checksumming** — `ingest-video` rewrites `device_config.json`
   and `checksums.sha256` of an existing raw session. Consent modifications must precede
   this step, otherwise `validate` fails on a checksum mismatch.
3. **Session directory naming** — `process` parses the session number from the directory
   name (e.g. `synth-0001`). Raw session directories must follow this convention.

Optional-extra stages (`replay-ik`, `export-release-rosbag`, XDF `ingest`) are gated
behind `pytest.importorskip` so they run when their extra dependencies are installed and
skip cleanly otherwise.

## IK robot-arm replay

`htdp replay-ik` drives a vendored 6-DOF arm (`src/htdp/replay/assets/arm.xml`) so its
end-effector follows the `right_wrist` Cartesian path of a release via `mink` differential
IK; returns the joint trajectory + max tracking error; headless, deterministic. Default
`--orientation-cost 0.0` is position-only; values > 0 weight wrist-orientation
tracking (full 6-DOF pose on the 6-DOF arm). The summary prints max orientation error in radians.
With `--out PATH`, writes a per-step joint trajectory CSV (`timestamp_s, q0..qN, target_x/y/z, tracking_error_m, target_qw/qx/qy/qz, orientation_error_rad`);
`--force` overwrites an existing file.

## Multi-session catalog

`htdp catalog` scans a raw sessions directory into a deterministic 9-column Parquet index
(session metadata + derived `modalities`); the inventory/query view; build-only (query via
the Parquet file). The catalog is read-only, does not modify any session data, and can be
regenerated at any time.

`htdp catalog-query <catalog.parquet>` filters the catalog by `--protocol/--qc/--participant/--processing-status/--modality`
(AND semantics; `--modality` is set membership on the comma-joined modalities) and supports inclusive range filters
`--start-after SECONDS` / `--start-before SECONDS` (raw Unix seconds, AND-combined with other filters). Prints matching
`session_id`s one per line for piping.

`htdp catalog-releases <releases_dir> <out.parquet>` builds a deterministic 6-column Parquet inventory of packaged
releases (release_name, profile, n_sessions, session_ids, absent_modalities, manifest_sha256) read from each release's
manifest.json — no walk of the `data/` subdirectory. Rows are sorted by release_name; lists are comma-joined in sorted order.

## Design constraints (v0.1)

- **No servers** — Postgres, MinIO, FastAPI, Docker are all deferred to v0.2.

> **v0.2 exception — `htdp serve`.** A read-only + job-runner dashboard server
> (optional extra `serve`, localhost-only, `uv sync --extra serve`) exposes filesystem
> tier status and spawns allowlisted `htdp` subcommands for the control-center dashboard.
> It creates no new data representation and is never part of the dataset product.

- **No real hardware** — no VIVE, LSL, XDF, EEG, video capture.
- **No ROS** — rosbag2 export deferred to v0.2.
- **Deterministic** — seeded generator, canonical serialization (§ Reproducibility).
- **Testable** — all stages have pytest coverage; replay is gated on optional MuJoCo dep.

## Reproducibility

Same code + `uv.lock` + platform + seed + inputs → identical release-manifest checksums.
Tool versions are recorded in the manifest but excluded from the reproducibility hash so
the check is stable across machines with different Python patch versions.

See `docs/DATA_CONTRACT.md` for canonical serialization rules and column specifications.
