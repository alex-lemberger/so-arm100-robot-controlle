# Design: EEG-BIDS export — BrainVision (v0.2 slice 6)

**Status:** Approved (brainstorm), pending implementation plan.
**Date:** 2026-06-22
**Roadmap:** v0.2, "EEG-BIDS export" (the export half of EEG capture).

## Goal

Export ingested EEG into a **BIDS-valid** EEG dataset using the **BrainVision**
format, extending the slice-4 `export-bids` command so a session with EEG streams
emits `sub-/eeg/` alongside `sub-/motion/` in one coherent BIDS dataset.

BIDS forbids `.tsv` for continuous EEG data — it must be a supported binary format.
We use BrainVision (text `.vhdr`/`.vmrk` + binary `.eeg`) because it is the simplest
BIDS-valid continuous-EEG format to write by hand, needs no third-party dependency
(stdlib `struct`), and is read by the standard EEG-BIDS toolchain (MNE-BIDS, etc.).

## Architecture: extend `export-bids`

A session with `role="eeg"` streams emits `sub-/eeg/` next to `sub-/motion/`, reusing
the existing labels, `dataset_description.json`, and `participants.tsv`. A
motion-only session produces no `eeg/` directory — slice-4 behaviour is unchanged.
This adds a new pure module `export/eeg_bids.py` and extends the orchestrator in
`export/bids.py`. No CLI change (`export_motion_bids` keeps its name and now also
emits EEG when present), no schema change, no new dependency.

## Regular-grid assumption

EEG-BIDS / BrainVision model continuous EEG as a regular grid at a single
`SamplingFrequency`; there is no per-sample timestamp column. Our ingested EEG CSV
carries an explicit `timestamp_s` column (possibly irregular / rebased, even
negative). On export we **drop `timestamp_s`** and write the samples in order at an
estimated nominal `SamplingFrequency`. This is a documented deviation: the export
approximates the recording as regularly sampled. `EEGReference`,
`PowerLineFrequency`, and `SoftwareFilters` are unknown to the pipeline and recorded
as `"n/a"`.

`SamplingFrequency` is estimated from the CSV timestamps as `(n-1)/(t_last - t_first)`
(average rate). A stream with fewer than two samples, or zero time span, cannot be
exported → `BidsExportError`.

## Output layout

Per EEG stream (the `StreamRef.name` = `eeg_id` becomes the BIDS `acq-<id>` entity,
which keeps multiple EEG streams distinct):

```
sub-<sub>/eeg/
  sub-<sub>_task-<task>_acq-<id>_eeg.vhdr     (BrainVision header, text)
  sub-<sub>_task-<task>_acq-<id>_eeg.vmrk     (BrainVision markers, text)
  sub-<sub>_task-<task>_acq-<id>_eeg.eeg      (binary, multiplexed IEEE float32 LE)
  sub-<sub>_task-<task>_acq-<id>_eeg.json     (sidecar)
  sub-<sub>_task-<task>_acq-<id>_channels.tsv
```

`sub`, `task` come from the existing `labels.sanitize` of `participant_id` /
`protocol_id` (same as motion). `acq = sanitize(eeg_id)`.

### File contents

- **`.eeg`** — multiplexed: for each sample (time point), the channel values in
  channel order, each as little-endian IEEE `float32`. No header in this file.
- **`.vhdr`** (text, UTF-8, `\n`):
  ```
  Brain Vision Data Exchange Header File Version 1.0

  [Common Infos]
  Codepage=UTF-8
  DataFile=<acq-stem>_eeg.eeg
  MarkerFile=<acq-stem>_eeg.vmrk
  DataFormat=BINARY
  DataOrientation=MULTIPLEXED
  NumberOfChannels=<N>
  SamplingInterval=<1e6 / fs, microseconds>

  [Binary Infos]
  BinaryFormat=IEEE_FLOAT_32

  [Channel Infos]
  Ch1=<label1>,,1,µV
  Ch2=<label2>,,1,µV
  ...
  ```
  (`DataFile`/`MarkerFile` are bare filenames; channel line is
  `<name>,<ref=empty>,<resolution=1>,<unit=µV>`.)
- **`.vmrk`** (text):
  ```
  Brain Vision Data Exchange Marker File, Version 1.0

  [Common Infos]
  Codepage=UTF-8
  DataFile=<acq-stem>_eeg.eeg

  [Marker Infos]
  Mk1=New Segment,,1,1,0
  ```
- **`.json`** sidecar: `{"TaskName": task, "SamplingFrequency": fs,
  "EEGReference": "n/a", "PowerLineFrequency": "n/a", "SoftwareFilters": "n/a",
  "EEGChannelCount": N, "RecordingType": "continuous"}`.
- **`_channels.tsv`**: header `name\ttype\tunits`; one row per channel
  (`type=EEG`, `units=µV`).

## Components

| Unit | Responsibility | Pure? | File |
|------|----------------|-------|------|
| `estimate_fs(timestamps) -> float` | average sample rate `(n-1)/span`; raise `ValueError` if `<2` samples or zero span | yes | `export/eeg_bids.py` |
| `eeg_binary(samples) -> bytes` | multiplexed float32 LE packing | yes | `export/eeg_bids.py` |
| `vhdr_text(stem, labels, fs) -> str` | BrainVision header | yes | `export/eeg_bids.py` |
| `vmrk_text(stem) -> str` | BrainVision markers | yes | `export/eeg_bids.py` |
| `eeg_channels_rows(labels) -> list[dict[str,str]]` + `EEG_CHANNELS_HEADER` | channels.tsv rows | yes | `export/eeg_bids.py` |
| `eeg_json(task, n_channels, fs) -> dict[str,object]` | sidecar | yes | `export/eeg_bids.py` |
| `_read_eeg_csv(path) -> tuple[list[str], list[float], list[list[float]]]` | parse eeg CSV → labels, timestamps, samples | no (I/O) | `export/bids.py` |
| orchestrator extension | when eeg streams present, write `sub-/eeg/` files | no | `export/bids.py` |

`stem` passed to `vhdr_text`/`vmrk_text` is the full `acq` stem
`sub-<sub>_task-<task>_acq-<id>` so the embedded `DataFile`/`MarkerFile` names match.

## Data flow

```
export-bids raw/<session> out/
  → (existing) write sub-/motion/ + dataset_description + participants + README
  → eeg_streams = device.streams where role == "eeg"
  → if eeg_streams: mkdir sub-/eeg/
      for each eeg stream:
        labels, timestamps, samples = _read_eeg_csv(streams/eeg_<id>.csv)
        fs  = estimate_fs(timestamps)
        acq = sanitize(stream.name)
        write .eeg (eeg_binary), .vhdr (vhdr_text), .vmrk (vmrk_text),
              .json (eeg_json), _channels.tsv (eeg_channels_rows)
→ out/ is a BIDS dataset with motion + (BrainVision) eeg
```

## Error handling

- EEG stream with `<2` samples or zero time span → `estimate_fs` raises; the
  orchestrator surfaces it as `BidsExportError`.
- Existing `BidsExportError` cases (missing metadata, no motion streams, existing
  out_dir without force) unchanged.
- No partial writes: the motion tree is created under the existing force guard; eeg
  files are built in memory and written into the same out tree.

## Testing (offline, deterministic; no external validator)

1. **`estimate_fs`**: `[0.0, 0.004]` (2 samples) → `250.0`; `[0,0.004,0.008]` →
   `250.0`; single sample or zero span → `ValueError`.
2. **`eeg_binary`**: pack `[[1.0, 2.0], [3.0, 4.0]]` → 16 bytes; `struct.unpack`
   round-trips to the same floats in multiplexed order.
3. **`vhdr_text`**: contains `BinaryFormat=IEEE_FLOAT_32`, `NumberOfChannels=<N>`,
   `SamplingInterval=4000.0` for fs 250, and one `Ch<i>=<label>,,1,µV` per channel;
   `DataFile` names the `.eeg`. **`vmrk_text`**: has the `New Segment` marker and the
   matching `DataFile`.
4. **`eeg_channels_rows`/`eeg_json`**: one row per channel, `type=EEG`, `units=µV`;
   sidecar `SamplingFrequency`, `EEGChannelCount`, `RecordingType="continuous"`.
5. **integration** (pyxdf-gated, via the eeg-ingest `_xdf_writer` path): ingest a
   session with an EEG stream → `export_motion_bids` →
   - `sub-<sub>/eeg/` contains all five files at the `acq` stem;
   - `.vhdr` `NumberOfChannels` equals the channel count and `SamplingInterval`
     matches the estimated fs;
   - reading the `.eeg` bytes with `struct.unpack` reproduces the ingested channel
     values (float32 tolerance);
   - `_channels.tsv` row count equals the channel count;
   - `.json` `SamplingFrequency` > 0.
6. **regression**: a motion-only session export produces **no** `eeg/` directory;
   existing slice-4 motion-BIDS tests stay green.

## Documentation impact

- `docs/DATA_CONTRACT.md`: EEG-BIDS export uses BrainVision (`.vhdr`/`.vmrk`/`.eeg`),
  regular-grid assumption with `SamplingFrequency` estimated from timestamps, units
  µV, reference/line-frequency/filters recorded as `n/a`.
- `docs/ROADMAP.md`: mark "EEG-BIDS export" in progress / done.
- No JSON-Schema re-export (no persisted-schema model change).
```
