# Design: `htdp ingest` — XDF ingest adapter (v0.2 slice 1)

**Status:** Approved (brainstorm), pending implementation plan.
**Date:** 2026-06-20
**Roadmap:** v0.2, "Real hardware ingest" — first incremental slice.

## Goal

Add `htdp ingest`: convert an LSL `.xdf` recording plus an operator metadata
sidecar into the **existing v0.1 raw session folder**. The downstream pipeline
(`validate → process → qc → package → replay`) must not change. `ingest` is the
structural inverse of `synth`: where `synth` fabricates a raw folder from a seed,
`ingest` derives one from a real recording.

This realizes the v0.2 guiding principle: *add one real modality at a time; each
modality adds an `ingest` adapter that normalizes to the existing raw
representation.*

## Non-goals

Explicitly out of scope for this slice (named, not forgotten):

- Live LSL capture / streaming. Input is a recorded `.xdf` file only.
- Video, EEG, ROS, IK. Motion + events only.
- A real VIVE driver. The frame transform is data-declared, not device-specific.
- Multi-session catalog. One file → one raw session.

## Architecture

New package `src/htdp/ingest/`. Small, single-purpose units with explicit
interfaces:

| Unit | Responsibility | Depends on |
|------|----------------|-----------|
| `ingest/reader.py` | Parse `.xdf` via `pyxdf` into in-memory streams: name, type, channel labels, timeseries, timestamps. Optional-dependency guard raising `IngestUnavailable` when `pyxdf` is missing (mirrors `replay`'s `ReplayUnavailable`). | `pyxdf` (optional) |
| `ingest/mapping.py` | Resolve which XDF stream maps to which tracker / events, and which channel index maps to which contract column, using the sidecar `ingest_map`. Raises a clear error on unmapped or missing streams/channels. | `schemas` |
| `ingest/frame.py` | Apply a declared coordinate transform (position + quaternion remap) into the contract frame (`x=right, y=forward, z=up`, quat `w,x,y,z`, meters). **Default = identity.** Pure function, unit-tested in isolation with no XDF involved. | — |
| `ingest/session.py` | Orchestrator: rebase timestamps to `t0`, build motion + event rows, write the raw folder via `io.canonical` / `io.checksums`. Sets `source="real"`, `defect_tag=""`. | `io`, `schemas`, the three units above |

CLI: add an `ingest` command to `src/htdp/cli.py`, following the existing
optional-dep pattern (`try/except IngestUnavailable → Exit(1)`).

Test scaffold (NOT shipped in the CLI or package public surface):

| Unit | Responsibility |
|------|----------------|
| `tests/_xdf_writer.py` | Convert an existing synth raw session into a `.xdf` file, for the round-trip test. Throwaway test infrastructure; lives under `tests/`. |

## Sidecar input

XDF carries signal data, not consent/protocol/identity. The operator supplies a
single `ingest.json` sidecar (one file = reproducible, versionable, diffable):

```json
{
  "session":       { "...": "Session schema fields (session_id, participant_id, protocol_id, consent_form_version, device_config_id, start_time_s)" },
  "consent":       { "...": "Consent schema fields" },
  "device_config": { "...": "DeviceConfig fields, including frame and the transform declaration" },
  "ingest_map": {
    "<xdf_stream_name>": { "role": "motion", "tracker_id": "right_wrist", "channels": { "x_m": 0, "y_m": 1, "z_m": 2, "qw": 3, "qx": 4, "qy": 5, "qz": 6, "quality": 7 } },
    "<xdf_marker_stream>": { "role": "events" }
  }
}
```

The sidecar is validated against the existing Pydantic schemas (`Session`,
`Consent`, `DeviceConfig`) before any writing, so a malformed sidecar fails fast.

## Data flow

```
htdp ingest <file.xdf> <ingest.json> --out data/raw
  → reader: pyxdf.load_xdf(file) → streams
  → mapping: streams + ingest_map → typed motion/event records
  → frame: apply declared transform → contract frame
  → session: rebase timestamps to t0 (earliest sample across motion streams),
             write motion_<tracker>.csv, events.csv, session.json,
             consent.json, device_config.json, notes.md
  → write_checksums()
→ raw folder identical in structure to a synth session
→ existing `htdp validate <raw_dir>` passes unchanged
```

Timestamp rebasing: XDF timestamps are an absolute LSL clock. `t0` is the
earliest motion sample timestamp; all `timestamp_s` become `raw - t0`, matching
the contract's "time since session start". `Session.start_time_s` records the
absolute `t0` for provenance.

Provenance: motion rows carry `defect_tag=""` (real data — defects are detected
downstream by `qc`, never injected). Event `source="real"`. `notes.md` records
the source `.xdf` filename and ingest tool version.

## Error handling

- `pyxdf` missing → `IngestUnavailable`, CLI exits 1 with an install hint.
- Sidecar fails schema validation → fail before writing anything.
- An `ingest_map` stream/channel absent from the XDF → explicit error naming the
  missing stream/channel.
- A declared `tracker_id` not in the contract tracker set → error.
- No partial writes: build all rows in memory, then write the folder.

## Testing (round-trip, no hardware)

1. **`test_ingest_roundtrip`**: `synth(seed) → tests/_xdf_writer → ingest →`
   assert the ingested raw session equals the original geometry/timestamps.
   Fields legitimately differing (`source`: `synthetic` vs `real`; `notes.md`
   provenance line) are asserted explicitly, not byte-compared. Skipped when
   `pyxdf` is unavailable (mirrors the replay smoke test).
2. **`test_frame.py`**: unit tests for `frame.py` with no XDF — identity
   (input == output) and a 90° axis remap with a known expected result.
3. **`test_mapping_errors`**: missing stream, missing channel, unknown tracker
   each raise the expected error.
4. **`test_validate_passes`**: the ingested raw folder passes `validate_session`
   unchanged.

## Dependencies

Add `pyxdf` as an optional extra (e.g. `[project.optional-dependencies] ingest`),
parallel to the existing MuJoCo optional handling. Core install stays slim.

## Documentation impact

- `docs/DATA_CONTRACT.md`: note `source` may be `real`; no schema column change.
- `docs/ROADMAP.md`: mark the XDF `ingest` item in progress / done.
- `README` / `AGENTS.md`: add the `ingest` command usage.
- Re-export JSON schemas only if a schema model changes (not expected — sidecar
  reuses existing schemas).
