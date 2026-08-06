# Design: EEG ingest — XDF adapter extension (v0.2 slice 5)

**Status:** Approved (brainstorm), pending implementation plan.
**Date:** 2026-06-22
**Roadmap:** v0.2, "EEG capture" (EEG-BIDS export deferred to a later slice).

## Goal

Ingest EEG from an LSL `.xdf` recording into the raw session. In a real rig, EEG,
motion, and markers are recorded into one `.xdf`, so EEG is just another stream
role in the existing XDF adapter (slice 1). This lands `streams/eeg_<id>.csv` in
the raw tier and registers a `role="eeg"` stream — closing the loop opened by
slice 2, whose consent filter already reserves `MODALITY_GLOBS["eeg"] =
("streams/eeg_*.csv",)` but had no producer.

## Architecture: extend the XDF adapter

EEG is handled by extending slice 1's `ingest_xdf`, not a separate command,
because EEG is co-recorded with motion in the same `.xdf`. This modifies the
shipped `ingest/mapping.py` and `ingest/session.py` — legitimate extension of the
single adapter that normalizes all XDF streams. Downstream (`validate`, `process`,
`qc`, `package`, `export`) needs **no change**: `validate` already checks declared
streams exist on disk regardless of role; `process` filters `role=="motion"`, so
EEG is ignored downstream with zero edits.

## CSV layout: wide

`streams/eeg_<id>.csv` has columns `timestamp_s` followed by one column per channel
label, in the order declared in the sidecar. One file per EEG stream. This matches
the per-stream raw layout and the conventional wide EEG table.

## Timestamps

EEG samples are rebased to the **same `t0` as motion** (the earliest motion
sample). `compute_t0` is unchanged (motion-only). If an EEG stream starts before
motion, its early `timestamp_s` values are negative — this is faithful (real lead
time), documented, and acceptable. Sample rate is **not** recorded on the EEG
`StreamRef` in this slice (`rate_hz=None`); timestamps are preserved and the rate
is recoverable later if needed.

## Sidecar (`ingest.json`) addition

The existing `ingest_map` gains zero or more `eeg` entries alongside `motion` and
`events`:

```json
"ingest_map": {
  "<motion_stream>": { "role": "motion", "tracker_id": "right_wrist", "channels": { "...": 0 } },
  "<eeg_stream>":    { "role": "eeg", "eeg_id": "eeg", "channels": { "Fp1": 0, "Fp2": 1, "Cz": 2 } },
  "<marker_stream>": { "role": "events" }
}
```

- `eeg_id`: non-empty string → output filename `streams/eeg_<eeg_id>.csv` and the
  `StreamRef.name`.
- `channels`: non-empty ordered map of channel label → XDF channel index. Order
  defines the CSV column order.

Rules unchanged: exactly one `events` stream, at least one `motion` stream. EEG is
optional (zero or more).

## Components

| Unit | Change | File |
|------|--------|------|
| `EegStreamMap` dataclass (`eeg_id: str`, `channels: dict[str, int]`) | new | `ingest/mapping.py` |
| `IngestMap.eeg: dict[str, EegStreamMap]` | new field (keyed by XDF stream name) | `ingest/mapping.py` |
| `parse_ingest_map` handles `role="eeg"` (non-empty channels else `MappingError`) | extend | `ingest/mapping.py` |
| `extract_eeg(stream, m) -> tuple[list[str], list[dict[str, object]]]` | new | `ingest/mapping.py` |
| `build_eeg_rows(eeg_raw, t0) -> dict[str, tuple[list[str], list[dict[str, object]]]]` | new | `ingest/session.py` |
| `write_raw_folder(..., eeg_out=...)` writes `eeg_<id>.csv` + `role="eeg"` StreamRef | extend (default empty) | `ingest/session.py` |
| `ingest_xdf` extracts + wires EEG | extend | `ingest/session.py` |
| EEG-stream emit helper for the round-trip | new (test infra) | `tests/_xdf_writer.py` |

### `extract_eeg`

```python
def extract_eeg(stream: XdfStream, m: EegStreamMap) -> tuple[list[str], list[dict[str, object]]]:
    # reject string-format; for each sample build {"raw_ts": ts, label: value, ...}
    # in channel-label order; raise MappingError on out-of-range channel index.
```

Returns `(labels, rows)` where `labels = list(m.channels)` (declared order) and each
row carries `raw_ts` plus one entry per label.

### `build_eeg_rows`

```python
def build_eeg_rows(
    eeg_raw: dict[str, tuple[list[str], list[dict[str, object]]]],
    t0: float,
) -> dict[str, tuple[list[str], list[dict[str, object]]]]:
    # per eeg_id: copy labels; for each row emit {"timestamp_s": raw_ts - t0, **channel values}
```

### `write_raw_folder`

Adds a keyword-only `eeg_out: dict[str, tuple[list[str], list[dict[str, object]]]]`
defaulting to `{}` (existing callers/tests unaffected). For each `eeg_id`:
- write `streams/eeg_<eeg_id>.csv` with columns `["timestamp_s"] + labels` via
  `io.canonical.write_csv`;
- append `StreamRef(name=eeg_id, path=f"streams/eeg_{eeg_id}.csv", fmt="csv",
  role="eeg", rate_hz=None)`.

## Data flow

```
htdp ingest <file.xdf> <ingest.json> --out data/raw
  → parse motion + events (unchanged)
  → parse eeg entries → EegStreamMap
  → for each eeg stream: extract_eeg → rows (raw_ts + channels)
  → t0 = earliest motion sample (unchanged)
  → build_eeg_rows: rebase timestamp_s = raw_ts - t0
  → write_raw_folder: streams/eeg_<id>.csv + role=eeg StreamRef
→ validate passes; process/qc ignore eeg (role!=motion)
→ package with distribute_raw_eeg=False drops streams/eeg_*.csv, records "eeg" absent
```

## Error handling

- `role="eeg"` with missing/empty `channels` or missing `eeg_id` → `MappingError`.
- EEG stream string-format, or a channel index out of range → `MappingError`.
- A mapped EEG stream absent from the `.xdf` → `KeyError` naming it (mirrors motion).
- No partial writes: extract + build all rows in memory before `write_raw_folder`.

## Testing (offline, deterministic, no hardware)

1. **mapping:** `parse_ingest_map` resolves an `eeg` entry into `IngestMap.eeg`;
   empty/missing channels or missing `eeg_id` → `MappingError`. `extract_eeg`
   builds labelled rows in declared order; string-format and out-of-range index →
   `MappingError`.
2. **session:** `build_eeg_rows` rebases (`timestamp_s = raw_ts - t0`), including a
   negative result when an EEG sample precedes `t0`. `write_raw_folder` with a
   populated `eeg_out` writes `streams/eeg_<id>.csv` with the right header/columns
   and a `role="eeg"` StreamRef; output passes `validate_session`.
3. **writer:** the `_xdf_writer` EEG helper produces a stream that `load_xdf_streams`
   reads back with the expected channel count.
4. **round-trip:** build a motion+eeg `.xdf` + matching sidecar → `ingest_xdf` →
   `streams/eeg_eeg.csv` exists with `timestamp_s` + declared channel columns and
   the expected values; the EEG `StreamRef` is registered; `validate_session == []`.
   Skipped without `pyxdf` (mirrors existing round-trip tests).
5. **loop closure (consent):** ingest an EEG session →
   - `distribute_raw_eeg=True` → `streams/eeg_eeg.csv` present in the release,
     `"eeg"` not in `absent_modalities`;
   - `distribute_raw_eeg=False` → dropped, `"eeg"` in `absent_modalities`, motion
     intact.
6. **regression:** existing slice-1 ingest tests stay green (default `eeg_out={}`,
   no eeg entries → behaviour identical).

## Documentation impact

- `docs/DATA_CONTRACT.md`: document the EEG stream — wide CSV `streams/eeg_<id>.csv`
  (`timestamp_s` + channel columns), `role="eeg"`, timestamps rebased to motion
  `t0` (may be negative), sample rate deferred.
- `docs/ROADMAP.md`: mark "EEG capture" in progress (EEG-BIDS still deferred).
- `AGENTS.md`: note the `ingest_map` now supports an `eeg` role.
- No JSON-Schema re-export (no persisted-schema model change; `role` is a free
  string on `StreamRef`).
```
