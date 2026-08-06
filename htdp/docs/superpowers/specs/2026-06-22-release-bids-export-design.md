# Design: release-level BIDS export (v0.2 slice 7)

**Status:** Approved (brainstorm), pending implementation plan.
**Date:** 2026-06-22
**Roadmap:** v0.2, "release-level BIDS export" (the product-unit form of the
Motion-BIDS + EEG-BIDS exporters).

## Goal

Export a **packaged release** (the product unit) into a single multi-subject BIDS
dataset, reusing the per-session Motion-BIDS (slice 4) and BrainVision EEG-BIDS
(slice 6) writers. Because a release is already consent-filtered, the BIDS dataset
inherits the filtering for free: modalities a participant forbade were dropped from
`data/<sid>/` during packaging, so they never reach the BIDS tree.

## Source: packaged release

Input is a packaged release directory `releases/<name>/`. Each `data/<sid>/` inside
is a full raw-session folder (a consent-filtered copy: dropped eeg/video files are
already gone), directly consumable by the existing per-session export logic. Reading
the release — not raw sessions — is the point: the BIDS output reflects the product
as shipped, including its consent filtering.

## Subject identity

`sub = sanitize(participant_id)`. The synth/contract data is 1:1
(participant `p-0001` ↔ session `synth-0001`), so each session maps to a distinct
`sub-<participant>`. When a release contains more than one session for the **same**
participant, those sessions get a `ses-<sanitize(session_id)>` entity (directory and
filename); otherwise the layout is flat (no `ses-`). Collision is detected by
counting participants across the release before writing.

## Architecture

Refactor `export/bids.py` to extract a reusable per-session writer, then add the
release loop and a CLI command. The single-session `export_motion_bids` keeps its
public signature and produces byte-identical output (slice-4/6 tests stay green).

| Unit | Change | File |
|------|--------|------|
| `_write_session_bids(out_dir, raw_dir, ses)` | new — writes `sub-<sub>[/ses-<ses>]/motion(+eeg)` into an existing tree; returns the participant row | `export/bids.py` |
| `export_motion_bids(raw_dir, out_dir, force)` | rewired to call `_write_session_bids(ses=None)` + write top-level files; behaviour unchanged | `export/bids.py` |
| `export_release_bids(release_dir, out_dir, force)` | new — loop sessions, collision-aware `ses`, aggregate participants, write top-level once | `export/bids.py` |
| `export-release-bids` command | new | `cli.py` |

### `_write_session_bids`

```python
def _write_session_bids(out_dir: Path, raw_dir: Path, ses: str | None) -> dict[str, str]:
    # read session.json + device_config.json from raw_dir
    # sub = sanitize(participant_id); task = sanitize(protocol_id)
    # entity base: f"sub-{sub}" + (f"_ses-{ses}" if ses else "")
    # subject dir: out_dir / f"sub-{sub}" / (f"ses-{ses}" if ses else "")
    # write <ent>_task-<task>_tracksys-<tracksys>_motion.tsv/.json + _channels.tsv
    #       <ent>_task-<task>_events.tsv  under <subject_dir>/motion/
    # for each role=="eeg" stream: BrainVision <ent>_task-<task>_acq-<id>_eeg.* under <subject_dir>/eeg/
    # raise BidsExportError if no motion streams
    # return {"participant_id": f"sub-{sub}", "cohort": "n/a"}
```

This holds the body currently inline in `export_motion_bids` (motion long→wide,
channels, events, BrainVision eeg), generalized over the optional `ses` entity. It
does **not** create `out_dir`, apply the force guard, or write top-level files —
those stay with the callers.

### `export_motion_bids` (single session, unchanged behaviour)

```python
def export_motion_bids(raw_dir: Path, out_dir: Path, force: bool = False) -> Path:
    # existing metadata/force guard + mkdir out_dir
    # row = _write_session_bids(out_dir, raw_dir, ses=None)
    # dump dataset_description(session_id) + README + participants([row])
    # return out_dir
```

With `ses=None`, the directory layout, filenames, and contents are identical to the
slice-4/6 output. No public signature change.

### `export_release_bids`

```python
def export_release_bids(release_dir: Path, out_dir: Path, force: bool = False) -> Path:
    # data = release_dir / "data"; error if missing or empty
    # session_dirs = sorted(p for p in data.iterdir() if p.is_dir())
    # subs = [sanitize(Session(session.json).participant_id) for each]
    # counts = Counter(subs); force guard + mkdir out_dir
    # rows = []; seen = set()
    # for (sd, sub): ses = sanitize(sd.name) if counts[sub] > 1 else None
    #                row = _write_session_bids(out_dir, sd, ses)
    #                add row to rows if sub unseen
    # dump dataset_description(release_dir.name) + README(release_dir.name)
    #      + participants(rows)
    # return out_dir
```

Participants are deduplicated by subject (one row per participant even with multiple
sessions). `dataset_description.Name` is the release name.

## Data flow

```
htdp package ... -> releases/<name>/data/<sid>/...      (consent-filtered)
htdp export-release-bids releases/<name> out/ [--force]
  -> count participants across data/* (collision detection)
  -> for each data/<sid>: _write_session_bids -> sub-<participant>[/ses-<sid>]/motion(+eeg)
  -> dataset_description(Name=<name>) + README + aggregated participants.tsv
-> out/ = multi-subject BIDS; modalities dropped during packaging are absent
```

## Error handling

- `release_dir/data` missing, or no session directories → `BidsExportError`.
- A session missing metadata or motion streams → `BidsExportError` (via
  `_write_session_bids`).
- `out_dir` exists without `force` → `BidsExportError`.
- CLI catches `BidsExportError` → `error: …`, exit 1.
- No partial writes beyond the force-guarded tree.

## Testing (offline, deterministic)

1. **`_write_session_bids` ses branch:** writing with `ses="01"` produces
   `sub-<sub>/ses-01/motion/sub-<sub>_ses-01_task-<task>_tracksys-<tracksys>_motion.tsv`
   (directory + filename carry the `ses` entity); with `ses=None`, the flat layout.
2. **single-session unchanged:** the slice-4/6 `export_motion_bids` tests
   (`test_bids_export.py`, `test_eeg_bids_export.py`) stay green after the refactor.
3. **two-session release:** synth two sessions (seeds 1, 2) → package → 
   `export_release_bids` → BIDS has `sub-p0001/` and `sub-p0002/`; one
   `participants.tsv` with both rows; `dataset_description.json` `Name` equals the
   release name; both motion trees present.
4. **collision:** two session dirs with the same `participant_id` → both gain
   `ses-<session>` directories under one `sub-<participant>`; `participants.tsv` has a
   single row for that subject.
5. **consent inheritance:** a release packaged with `distribute_raw_eeg=False`
   (eeg dropped) → no `eeg/` directory in the BIDS output (the file was never in the
   release). (EEG-present-and-allowed coverage is the slice-6 export test.)
6. **errors:** missing `data/` directory, or empty release → `BidsExportError`.
7. **CLI:** `export-release-bids` happy path exits 0 and writes
   `dataset_description.json`; a non-existent release exits 1 with `error:`.

## Documentation impact

- `docs/DATA_CONTRACT.md`: release→BIDS export — one multi-subject dataset,
  `sub-<participant>` (flat, `ses-<session>` only when a participant repeats),
  inherits the release's consent filtering.
- `docs/ROADMAP.md`: mark release-level BIDS in progress/done.
- `AGENTS.md`: add `export-release-bids` usage (read-only export of a packaged
  release).
- No JSON-Schema re-export (no persisted-schema model change).
```
