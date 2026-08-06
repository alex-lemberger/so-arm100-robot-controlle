# Data Contract

This document is the authoritative reference for the folder layout, file naming, and
CSV/Parquet column specifications used by the Human-Task Dataset Pipeline v0.1.

---

## Folder convention

```
data/raw/<session_id>/
  session.json            # session metadata (Schema: Session)
  consent.json            # participant consent record (Schema: Consent)
  device_config.json      # stream declarations + coordinate frame (Schema: DeviceConfig)
  streams/
    motion_right_wrist.csv
    motion_left_wrist.csv
    motion_torso.csv
    motion_object.csv
    events.csv
  video/                  # empty slot in v0.1 (contract present, no MP4)
  notes.md
  checksums.sha256        # SHA-256 over all raw bytes (immutability proof)

data/processed/<session_id>/
  motion.parquet
  events.parquet
  qc_report.json
  qc_report.html
  manifest.json

data/releases/<release_name>/
  README.md
  LICENSE
  protocol.md
  participants.csv
  sessions.csv
  manifest.json
  checksums.sha256
  data/<session_id>/...   # copied raw streams (motion CSVs)
```

---

## Coordinate frame

Declared in `device_config.json`. All motion data must conform.

- Units: **meters** (position), **seconds** (timestamps).
- World frame: **right-handed**; x = participant right, y = forward, z = up.
- Rotations: **quaternion, order `w, x, y, z`**.

---

## Motion CSV columns

File: `streams/motion_<tracker_id>.csv`

| Column | Type | Description |
|--------|------|-------------|
| `timestamp_s` | float (6dp) | Time since session start, seconds |
| `tracker_id` | str | Tracker name (e.g. `right_wrist`) |
| `x_m` | float (6dp) | Position x, meters |
| `y_m` | float (6dp) | Position y, meters |
| `z_m` | float (6dp) | Position z, meters |
| `qw` | float (6dp) | Quaternion w |
| `qx` | float (6dp) | Quaternion x |
| `qy` | float (6dp) | Quaternion y |
| `qz` | float (6dp) | Quaternion z |
| `quality` | float (6dp) | Tracking quality 0–1 |
| `defect_tag` | str | Empty unless synthetically injected defect |

Canonical rules: stable column order, 6 decimal places, UTF-8, LF line endings.

---

## Event CSV columns

File: `streams/events.csv`

| Column | Type | Description |
|--------|------|-------------|
| `timestamp_s` | float (6dp) | Time since session start, seconds |
| `event_id` | str | Unique event identifier |
| `label` | str | `start`, `grasp`, `release`, `place`, or `stop` |
| `phase` | str | Protocol phase name |
| `source` | str | `synthetic` (generated) or `real` (ingested capture) |
| `confidence` | float (6dp) | Event detection confidence 0–1 |
| `notes` | str | Free text |

Event ordering invariant: `start < grasp < release < place < stop`. All events must
fall within the session time bounds.


---

## EEG CSV columns

File: `streams/eeg_<eeg_id>.csv`

| Column | Type | Description |
|--------|------|-------------|
| `timestamp_s` | float (6dp) | Time relative to motion t0, seconds (may be negative if EEG leads motion) |
| `<label>` | float (6dp) | One column per channel label in declared order from the ingest sidecar |

The file is a wide CSV: one row per sample, `timestamp_s` as the first column followed by
one column per channel label in the order declared in the ingest map. Timestamps are rebased
to the motion `t0`. The EEG sample rate is not recorded in this slice. Each channel's value
is a raw voltage reading from the XDF stream.

The stream is registered in `device_config.json` as a `StreamRef` with `role="eeg"`,
`fmt="csv"`, and `path="streams/eeg_<eeg_id>.csv"`.

EEG data at release time respects consent filtering: if a session's consent form has
`distribute_raw_eeg: false`, the EEG CSV is excluded from the packaged release and `"eeg"`
appears in `manifest.json`'s `absent_modalities` list.

---

## Pre-raw ingest step (`htdp ingest`)

Real LSL recordings (.xdf files) can be ingested into raw session folders using:

    htdp ingest <file.xdf> <ingest.json> --out data/raw/<session_id>

The `ingest.json` sidecar is a JSON file with keys:
- `session` — Session schema fields (participant, protocol, etc.)
- `consent` — Consent record
- `device_config` — DeviceConfig (frame, streams)
- `ingest_map` — stream/channel mapping (motion streams + events stream)
- `frame_transform` (optional) — `{"rotation": [w,x,y,z]}` to rotate data into contract frame; consumed by ingest but **not persisted** into `device_config.json`

The ingest adapter writes canonical raw folder layout with `source="real"` in events and empty `defect_tag=""` in motion CSVs. Install the optional extra first: `uv sync --extra ingest`.

---

## Schemas

Pydantic models in `src/htdp/schemas/models.py`. JSON Schema exported to `docs/schemas/`.

**Changing a schema requires:**
1. Updating the Pydantic model.
2. Re-exporting JSON schemas (`uv run python -c "from pathlib import Path; from htdp.schemas.export import export_json_schemas; export_json_schemas(Path('docs/schemas'))"`).
3. Updating this document.
4. Updating or adding tests.

---

## Absent modalities in release manifests

The `absent_modalities` field in the release manifest (`manifest.json`) is now
**computed** from consent flags and on-disk file presence — no longer a fixed
`["eeg", "video"]`. It lists modalities that are absent from **every** session (the
intersection of per-session absent lists). For per-session detail, the manifest includes
`absent_modalities_by_session`: a map from `session_id` to the list of modalities absent
from that session (forbidden by consent or not present). This complements the release-wide
`absent_modalities` which covers only modalities absent from all sessions. Motion data is
never filtered and never appears in either field.

---

## Canonical serialization rules (reproducibility)

- JSON: sorted keys, 2-space indent, UTF-8, LF.
- CSV: stable column order (as above), 6dp floats, UTF-8, LF.
- Parquet: reproducibility asserted at the logical manifest/checksum level, not raw bytes.
- Generated timestamps: seed-derived or excluded from hashed content.
- Tool versions: recorded in the manifest but excluded from the reproducibility checksum.

These rules ensure: same code + `uv.lock` + platform + seed + inputs → identical release-manifest checksums.

---

## Video stream (opaque MP4)

A raw session may contain a `video/` directory with one or more `.mp4` files.
Each video file is registered in `device_config.json` as a `StreamRef` with:

- `role`: `"video"`
- `fmt`: `"mp4"`
- `path`: `"video/<name>.mp4"` (relative to session root)
- `rate_hz`: the declared frame rate (fps) from the ingest sidecar

The `.mp4` file is stored **opaque**: it is copied as-is into the raw session
and never decoded, transcoded, or introspected by any pipeline stage. Frame
extraction and synchronization are deferred to v0.2+.

Video files are populated via `htdp ingest-video`, which registers a video
`StreamRef`, copies the file into the `video/` slot, and re-seals
`checksums.sha256`. At release time, consent filtering respects the
`distribute_raw_video` flag: sessions that disallow video distribution have
their video files excluded from the packaged release.

---

## Motion-BIDS export

The `htdp export-bids <raw_dir> <out_dir> [--force]` command reads a single raw session
and writes a minimal Motion-BIDS (BEP029) dataset tree. Key characteristics:

- Single raw session → separate BIDS directory; the raw session is never mutated.
- Irregular sampling is preserved via an explicit `timestamp_s` column and `n/a` fill
  (no resampling).
- The internal QC metadata column `defect_tag` is **not exported** — it is pipeline-internal,
  not motion data.
- BIDS version: **1.10.0**.
- Labels (`participant_id`, `protocol_id`, `device_config_id`) are sanitized to
  alphanumerics for BIDS entity compliance.

---

## EEG-BIDS export

The `htdp export-bids` command can also export EEG data from raw sessions that contain
`role="eeg"` streams. EEG is exported as BrainVision format (`.vhdr` header, `.vmrk`
markers, `.eeg` binary multiplexed IEEE float32) under `sub-<subject>/eeg/`, alongside
the `sub-<subject>/motion/` directory. Each EEG stream produces:

- `<stem>_eeg.vhdr` — BrainVision header with channel info (resolution 1, unit µV).
- `<stem>_eeg.vmrk` — Marker file with a single `New Segment` marker.
- `<stem>_eeg.eeg` — Binary data (multiplexed little-endian IEEE float32).
- `<stem>_channels.tsv` — Per-channel metadata (type `EEG`, units µV).
- `<stem>_eeg.json` — BIDS EEG sidecar with sampling frequency and channel count.

The export assumes a **regular grid**: the `timestamp_s` column from the raw CSV is
dropped and `SamplingFrequency` is estimated from the timestamps as `(n-1)/span`. The
reference, power-line frequency, and software filters are recorded as `n/a` in the
sidecar.

The `acq` entity in the BIDS filename is derived from the EEG stream's `name` field via
the same sanitization applied to other BIDS entities. Motion-only sessions export no
`eeg/` directory (regression-safe).


---

## Release-level BIDS export

The `htdp export-release-bids <release_dir> <out_dir> [--force]` command reads a
packaged release directory and writes one multi-subject BIDS dataset. Key characteristics:

- One packaged release → one BIDS directory; the release is never mutated (read-only export).
- Participant IDs are flattened: `sub-<participant>` with no `ses-` entity unless the same
  participant appears in more than one session within the release, in which case each
  session gets a `ses-<session_id>` subdirectory.
- `dataset_description.json.Name` is set to the release name.
- The dataset inherits the release's consent filtering: modalities that were dropped during
  packaging (e.g., EEG when `distribute_raw_eeg` was false) are absent from the BIDS output.
- `participants.tsv` is aggregated across all sessions, with duplicate participant IDs
  deduplicated.

---

---

## Release-level rosbag2 export

The `htdp export-release-rosbag <release_dir> <out_dir> [--force]` command exports a
packaged release into one rosbag2 (mcap) bag **per session** under `out_dir/<session_id>/`.

- Motion data: per-tracker topic `/motion/<tracker>` carrying `geometry_msgs/PoseStamped`
  messages (one per CSV row; quality and defect_tag columns are dropped).
- Events: topic `/events` carrying `std_msgs/String` messages (one per row, `data=label`).
- The dataset inherits the release's consent filtering: sessions whose consent forbids
  the requested profile are excluded during packaging and thus absent from the export.
- EEG-bearing sessions also emit, per EEG stream, a sample topic `/eeg/<stream>` (custom message `htdp_msgs/msg/EegSample` = `float64 stamp` + `float32[] data`, one message per sample) and a one-shot `/eeg/<stream>/labels` (`std_msgs/String`, comma-joined channel names). The custom message definition is embedded in the mcap file. EEG topics appear only when the release kept EEG (consent inheritance).
- Install the optional extra first: `uv sync --extra rosbag`.

