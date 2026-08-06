# EEG → rosbag2 Export — Design

**Date:** 2026-06-22
**Slice:** v0.2 — EEG in the rosbag2 export (follow-up to slice 8)
**Status:** approved, ready for implementation plan

## Goal

Extend the existing `htdp export-release-rosbag` so each per-session bag also carries the
session's EEG streams. There is **no new CLI command** — the same command gains EEG
output, which appears whenever the (consent-filtered) session carries an EEG stream.
This mirrors how slice 6 (EEG-BIDS) extended slice 4 (Motion-BIDS) without changing the
motion path or adding a command.

EEG has no standard ROS message type, so this slice introduces a small custom message,
`htdp_msgs/msg/EegSample`, registered inline via `rosbags`. The custom definition is
embedded in the mcap file (mcap is self-describing), so a consumer can deserialize
without an external `.msg` file.

## Non-Goals

- New CLI command (EEG folds into `export-release-rosbag`).
- Changing the motion or events output of slice 8 (byte-for-byte unaffected aside from
  added topics in EEG-bearing bags).
- `sensor_msgs/*` types or any ROS-standard EEG representation (none exists).
- Sampling-frequency / filter metadata (per-sample timestamps carry timing; no fs sidecar).
- Per-channel topics (one multi-channel `EegSample` per sample).
- A single-raw-session command (release source only, as in slice 8).

## Background (verified)

- EEG never comes from `synth`; it enters only via `htdp ingest` (slice 5, XDF). EEG raw
  is a wide CSV `streams/eeg_<id>.csv`: header `timestamp_s,<label1>,<label2>,…`, one row
  per sample. `role == "eeg"` stream, `rate_hz = None`.
- EEG-BIDS (`eeg_bids.py`) reads it as `(labels, timestamps, samples)`. This slice copies
  that read logic into `rosbag.py` (the no-touch rule forbids editing `eeg_bids.py`).
- Releases keep or drop EEG per consent (slice 2). A kept EEG stream is present in
  `data/<sid>/`; a dropped one is absent. EEG topics therefore appear only when the
  release kept EEG — automatic consent inheritance, no special handling.

## Verified `rosbags` custom-msgdef API (probed live)

```python
from rosbags.typesys import Stores, get_typestore, get_types_from_msg

_EEG_SAMPLE_MSGDEF = "float64 stamp\nfloat32[] data\n"
_EEG_SAMPLE_TYPE = "htdp_msgs/msg/EegSample"
ts.register(get_types_from_msg(_EEG_SAMPLE_MSGDEF, _EEG_SAMPLE_TYPE))
EegSample = ts.types[_EEG_SAMPLE_TYPE]
# float32[] field requires a numpy float32 array:
import numpy as np
msg = EegSample(stamp=1.5, data=np.array([1.0, 2.0, 3.0], dtype=np.float32))
```

Write/read round-trip confirmed (write via `ts.serialize_cdr`, read via a typestore that
re-registers the same def). `numpy` ships with `rosbags`, so no new dependency.

## Architecture

Extend `src/htdp/export/rosbag.py` only. New pieces:

- Module-level constants `_EEG_SAMPLE_MSGDEF`, `_EEG_SAMPLE_TYPE`, and registration of the
  custom type on the module's existing `_TYPESTORE` (the same typestore already built for
  motion/events). After registration, fetch `_EEG_SAMPLE = _TYPESTORE.types[_EEG_SAMPLE_TYPE]`.
- `_read_eeg_csv(path) -> tuple[list[str], list[float], list[list[float]]]` — returns
  `(labels, timestamps, samples)`; copied from the slice-6 implementation.
- An EEG loop inside `_write_session_bag`, after the events loop.

No change to `export_release_rosbag`, the CLI, or `pyproject.toml`.

## Message Mapping

For each `role == "eeg"` stream (read via `_read_eeg_csv`):

**Samples** — topic `/eeg/<sanitize(stream.name)>`, type `htdp_msgs/msg/EegSample`:
- One message per sample row.
- `stamp` ← `timestamp_s` (float seconds).
- `data` ← `np.array(<that row's channel values>, dtype=np.float32)`.
- rosbag2 log time ← `int(round(timestamp_s * 1e9))` ns.

**Channel labels** — topic `/eeg/<sanitize(stream.name)>/labels`, type `std_msgs/String`:
- Exactly **one** message, `data` = `",".join(labels)` (channel order).
- Log time ← first sample's ns (or `0` if the stream has no samples — see below).

If an EEG stream has zero sample rows: write the `/labels` message (with whatever labels
the header declared) at log time `0` and no sample messages. No error is raised.

## Error Handling

No new error type and no new raise. EEG is additive: a session with no EEG stream simply
produces no EEG topics (the existing motion/events behaviour is unchanged). Missing
metadata / no-motion errors remain governed by the existing slice-8 checks.

## Testing

New `tests/test_eeg_rosbag_export.py`, gated on **both** `pytest.importorskip("pyxdf")`
and `pytest.importorskip("rosbags")` (both installed in the dev env):

Build an EEG-bearing session with the established fixture pattern
(`tests._xdf_writer.write_xdf` / `build_sidecar` + `htdp.ingest.session.ingest_xdf`),
set consent to **keep** EEG (`distribute_raw_eeg=True` plus the commercial flags, as in
the slice-7 consent test), `write_checksums`, then `package_release` with
`ReleaseProfile.COMMERCIAL_DATASET`, then `export_release_rosbag`. Read the bag back with
`rosbags.rosbag2.Reader` (registering `_EEG_SAMPLE_MSGDEF` on the reader typestore):

- `/eeg/eeg` topic exists; message count == number of EEG sample rows.
- First `EegSample.data` equals the ingested first-sample channel values (float32 approx).
- `/eeg/eeg/labels` topic exists with exactly one `std_msgs/String`; `data` ==
  `"Fp1,Fp2,Cz"` (the ingested channel order).
- Motion topics still present (EEG is additive, not replacing).

A second test asserts a **consent-dropped** EEG release produces **no** `/eeg/*` topics
(reuse the slice-7 forbidden-eeg consent setup: `distribute_raw_eeg=False`), confirming
inheritance.

**Critical (false-green guard):** these tests need both `pyxdf` and `rosbags`. The
executor MUST `uv sync --extra rosbag --extra ingest --extra dev` and confirm the new
tests **RUN, not SKIP** before claiming green. A SKIPPED EEG-rosbag test is a failure.

## Files Touched

- Modify: `src/htdp/export/rosbag.py` (custom type registration + `_read_eeg_csv` + EEG loop)
- New: `tests/test_eeg_rosbag_export.py`
- Modify: docs — `docs/DATA_CONTRACT.md`, `AGENTS.md`, `docs/ROADMAP.md`

No other files change. No `pyproject.toml` change (no new dependency; `numpy` ships with
`rosbags`). No CLI change. No persisted-schema change → no JSON-Schema re-export.

## mypy Note

The custom message class is fetched dynamically (`_TYPESTORE.types[_EEG_SAMPLE_TYPE]`), so
mypy types it as `type` and will likely flag `EegSample(stamp=…, data=…)` construction
(`call-arg` / "too many arguments"). Resolve with a narrow `# type: ignore[call-arg]` (or
assign the fetched class to a variable annotated as needed) — decided against actual mypy
output in the plan, not guessed. The `rosbags.*` import override from slice 8 (if present)
stays.

## Determinism

Logical-level determinism (topics, counts, values), not byte-identical — unchanged from
slice 8 (mcap embeds a library-version string). Tests read the bag back; they never hash
bytes.

## Self-Review

- **Placeholders:** none — msgdef, topics, field mapping, fixture pattern, and consent
  flags are all concrete.
- **Consistency:** EEG loop sits after events in `_write_session_bag`, same per-stream
  shape as motion; custom type registered on the existing `_TYPESTORE`; topic naming
  `/eeg/<sanitize(name)>` matches the `/motion/<sanitize(name)>` convention; `_read_eeg_csv`
  return shape matches the slice-6 original it is copied from.
- **Scope:** single implementation plan — one module extension, one new test file, docs.
  No new command, no dependency, no schema change.
- **Ambiguity:** zero-sample EEG behaviour pinned (labels at log time 0, no samples, no
  raise); labels delivered once on a `/labels` String topic; `data` is float32 numpy.
