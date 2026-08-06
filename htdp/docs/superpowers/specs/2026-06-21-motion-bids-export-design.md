# Design: `htdp export-bids` — Motion-BIDS export (v0.2 slice 4)

**Status:** Approved (brainstorm), pending implementation plan.
**Date:** 2026-06-21
**Roadmap:** v0.2, "Motion-BIDS export."

## Goal

Export a single raw session into a minimal, faithful **Motion-BIDS** (BEP029)
dataset tree, so downstream consumers (analysis tools, the robot sim, other
research pipelines) can read htdp motion data in a standard layout. This is an
**export adapter after the raw tier** — it reads a raw session and writes a
separate BIDS directory; it changes no existing stage or schema.

## Source: raw session (single)

The export reads a **single raw session directory**. Although v0.1 chose
`processed/` (Parquet) for typed motion, the BIDS *labels* (participant, protocol,
tracking system) live only in the raw session's `session.json` / `device_config.json`;
`processed/` does not carry them. The raw session is self-contained (motion CSVs +
metadata JSON), so it is the single input. Motion CSVs are read with the stdlib
`csv` module (canonical 6dp floats, stable columns) — no Parquet/polars dependency
in the export path.

Multi-session / release-level BIDS (multiple `sub-*`, aggregated `participants.tsv`)
is a later thin slice that loops this one. Not in scope here.

## Time representation: irregular-sampling with explicit time column

htdp motion streams may be **misaligned**: synth injects a dropped-sample gap and
clock drift, and `qc` exists to detect them. Strict Motion-BIDS assumes a regular
grid with implicit time (no timestamp column). We **reject resampling** to a fixed
grid because it would fabricate/interpolate samples and hide exactly what `qc`
flags. Instead:

- `_motion.tsv` is the **union of all distinct `timestamp_s`** across trackers, one
  row per timestamp, with a leading explicit `timestamp_s` column. A tracker with
  no sample at a given timestamp gets `n/a` (the BIDS missing-value token) in its
  columns.
- This is faithful (gaps/drift appear as `n/a`, never invented data) and
  deterministic. The explicit `timestamp_s` column is a documented, intentional
  deviation from strict implicit-time Motion-BIDS, required by irregular sampling.

## Architecture

New package `src/htdp/export/`: small pure builders plus a thin orchestrator, and
one CLI command. No new third-party dependency.

| Unit | Responsibility | Pure? | Depends on |
|------|----------------|-------|-----------|
| `export/labels.py` | `sanitize(label)` → BIDS-safe alphanumeric; `entity_stem(sub, task, tracksys)` → `sub-<sub>_task-<task>_tracksys-<tracksys>`. | yes | — |
| `export/tabular.py` | `motion_wide(rows)` long→wide pivot (union timestamps, `n/a` fill); `channels_rows(trackers)`; `events_rows(events)`. | yes | — |
| `export/sidecars.py` | `dataset_description()`, `motion_json(task, tracksys, n_channels, fps)`, `participants_rows(sub, cohort)`, `readme_text(session_id)`. | yes | — |
| `export/bids.py` | `BidsExportError`; `export_motion_bids(raw_dir, out_dir, force)` orchestrator: read metadata + motion CSVs, derive labels, call builders, write the tree. | no (I/O) | the three above, `schemas`, stdlib `csv` |
| `cli.py` (modified) | `export-bids` command, error→`Exit(1)`. | no | `export.bids` |

### Channel typing

`MOTION_COMPONENTS` — the per-tracker data columns and their BIDS metadata:

| column suffix | BIDS `type` | `component` | `units` |
|---------------|-------------|-------------|---------|
| `x_m`, `y_m`, `z_m` | `POS` | `x` / `y` / `z` | `m` |
| `qw`, `qx`, `qy`, `qz` | `ORNT` | `quat_w/x/y/z` | `n/a` |
| `quality` | `MISC` | `n/a` | `n/a` |

`_channels.tsv` columns: `name, type, component, tracked_point, units,
sampling_frequency`. One row per `<tracker>_<suffix>` data column (excludes the
`timestamp_s` column). `tracked_point` = tracker name. `sampling_frequency` = the
motion StreamRef `rate_hz` (100.0).

## Output tree

TSV = tab-separated, `n/a` for missing, floats formatted to 6 decimals (canonical).

```
out_dir/
  dataset_description.json
  README
  participants.tsv
  sub-<sub>/
    motion/
      sub-<sub>_task-<task>_tracksys-<tracksys>_motion.tsv
      sub-<sub>_task-<task>_tracksys-<tracksys>_motion.json
      sub-<sub>_task-<task>_tracksys-<tracksys>_channels.tsv
      sub-<sub>_task-<task>_events.tsv
```

Label mapping (single session, no `ses-`):
- `sub`  = `sanitize(session.participant_id)`  (`p-0001` → `p0001`)
- `task` = `sanitize(session.protocol_id)`     (`reach-grasp-place` → `reachgraspplace`)
- `tracksys` = `sanitize(device_config_id)`    (`vive-synth` → `vivesynth`)

`sanitize` keeps `[A-Za-z0-9]`, drops everything else (BIDS entity rule).

### File contents

- **`_motion.tsv`**: header `timestamp_s\t<tracker>_x_m\t…`; union-timestamp rows
  with `n/a` fill. Column order: `timestamp_s`, then per tracker (in the device's
  motion-stream order) the eight suffixes `x_m,y_m,z_m,qw,qx,qy,qz,quality`. The
  `defect_tag` column is **not** exported (it is htdp QC metadata, not motion).
- **`_channels.tsv`**: one row per data column (see Channel typing).
- **`_motion.json`**: `{"TaskName": task, "SamplingFrequency": fps,
  "TrackingSystemName": tracksys, "MotionChannelCount": n_channels,
  "SpatialAxes": "RFU", "ACCELChannelCount": 0, "ANGACCChannelCount": 0,
  "GYROChannelCount": 0, "MAGNChannelCount": 0, "ORNTChannelCount": <#quat>,
  "POSChannelCount": <#pos>}`.
- **`_events.tsv`**: header `onset\tduration\ttrial_type\tvalue`; one row per event
  (`onset=timestamp_s`, `duration=n/a`, `trial_type=label`, `value=event_id`).
- **`dataset_description.json`**: `{"Name": session_id, "BIDSVersion": "1.10.0",
  "DatasetType": "raw", "GeneratedBy": [{"Name": "htdp"}]}`.
- **`participants.tsv`**: header `participant_id\tcohort`; one row `sub-<sub>\t<cohort>`.
- **`README`**: short text naming the session and the irregular-sampling caveat.

## Data flow

```
htdp export-bids raw/synth-0001 out/ [--force]
  → load session.json (participant_id, protocol_id), device_config.json (id, motion streams)
  → read each motion CSV (role=motion) into rows
  → labels: sub/task/tracksys via sanitize
  → motion_wide(rows)        -> header + union-timestamp wide rows (n/a fill)
  → channels_rows(trackers)  -> channel metadata
  → events_rows(events)      -> BIDS events
  → sidecars: dataset_description / motion_json / participants / README
  → write the tree under out/
→ out/ is a minimal Motion-BIDS dataset
```

## Error handling

- Missing `session.json` or `device_config.json`, or no `role="motion"` streams →
  `BidsExportError`.
- `out_dir` exists and not `force` → `BidsExportError`. With `force`, replace it.
- No partial writes: parse + build everything in memory, then write the tree
  (write to a temp dir and `os.replace`, mirroring `package`'s atomic pattern, OR
  build fully then write — the implementation must not leave a half-written tree on
  error).
- CLI catches `BidsExportError` → `error: …` on stderr, exit 1.

## Testing (offline, deterministic; no external bids-validator)

1. **`test_bids_labels.py`** (pure): `sanitize("p-0001") == "p0001"`,
   `sanitize("reach-grasp-place") == "reachgraspplace"`; `entity_stem` format.
2. **`test_bids_tabular.py`** (pure):
   - `motion_wide`: union timestamps sorted; a tracker missing at a timestamp →
     `"n/a"` in its columns; a known dropped-gap timestamp yields `n/a` for the
     gapped tracker; column order matches spec.
   - `channels_rows`: one row per `<tracker>_<suffix>`; position→`POS`/`m`,
     quaternion→`ORNT`, quality→`MISC`.
   - `events_rows`: onset/duration/trial_type/value mapping.
3. **`test_bids_sidecars.py`** (pure): `dataset_description` has `BIDSVersion`;
   `motion_json` channel counts (`POSChannelCount`, `ORNTChannelCount`) match the
   tracker count; `participants_rows` shape.
4. **`test_bids_export.py`** (orchestrator): synth session → `export_motion_bids` →
   - tree exists with all six files at the right paths;
   - `_motion.tsv` first column is `timestamp_s`, header lists every
     `<tracker>_<suffix>` column, and the left-wrist dropped-gap rows contain `n/a`;
   - `_channels.tsv` row count == number of data columns;
   - `dataset_description.json` parses and has `BIDSVersion`;
   - `_events.tsv` onsets equal the session's event timestamps;
   - existing `out_dir` without `force` → `BidsExportError`; with `force` → replaced.
5. **CLI** (`test_cli_shell.py`): `export-bids` happy path exits 0 and writes the
   tree; a non-existent raw dir exits 1 with `error:`.

## Documentation impact

- `docs/DATA_CONTRACT.md`: add a "Motion-BIDS export" note — single-session,
  irregular-sampling with explicit `timestamp_s` column, `defect_tag` not exported,
  BIDS version, label sanitization.
- `docs/ROADMAP.md`: mark "Motion-BIDS export" in progress.
- `AGENTS.md`: add `export-bids` usage; note it is a read-only export (writes a
  separate tree, never mutates raw/processed/releases).
- No JSON-Schema re-export (no persisted-schema model change).
```
