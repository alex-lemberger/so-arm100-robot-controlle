# htdp-capture EEG stream (design)

**Date:** 2026-06-24
**Status:** Approved (brainstorm complete)
**Repo:** `htdp-capture` (`/Users/alexanderlemberger/htdp-capture`) — additive feature on the shipped motion+events spine.

## Purpose

Add an optional EEG stream to the hardware-free capture app so a recorded `.xdf`
+ `ingest.json` can carry EEG alongside motion + events, consumable by
`htdp ingest` (which already supports EEG, slice 5). Hardware-free: a
`MockEegSource` feeds synthetic samples; a real amplifier/LSL-bridge source is
deferred to a later hardware milestone (same posture as `OpenVRPoseSource`).

## Contract (verified vs htdp `src/htdp/ingest/{mapping,session}.py`)

- EEG is a numeric LSL stream. `ingest_map` entry, keyed by LSL stream name:
  `{"role": "eeg", "eeg_id": <id>, "channels": {<label>: <index>, ...}}`
  (`EegStreamMap`: `eeg_id` non-empty str, `channels` non-empty label→index map).
- htdp `extract_eeg` reads each channel by its mapped index; `build_eeg_rows`
  rebases timestamps to the motion t0 and writes `streams/eeg_<eeg_id>.csv`
  with columns `timestamp_s` + the channel labels (label order = `channels`
  insertion order).
- EEG has **no `quality` channel** (unlike motion) — just the labeled data
  channels.
- EEG is optional: htdp ingest defaults eeg to empty; sessions without eeg are
  unaffected.

## Decisions (locked in brainstorm)

1. **`EegSource` ABC + `MockEegSource`** for the spine, parallel to
   `PoseSource`/`MockPoseSource`. Real source deferred.
2. **One multi-channel eeg stream** (single `eeg_id`, N channels). The
   config/sidecar code keeps a per-stream shape so multiple amps are a trivial
   later extension, but only one is built/tested. YAGNI on multi-amp.
3. **Config = `eeg_id` + `channels` (labels list) + `rate_hz` (default 250).**
   Channel count derived from `len(channels)`. Labels are free strings (htdp
   uses them as eeg CSV column names).
4. **Mock signal = per-channel deterministic sine:** channel `i` =
   `sin(frame*k + i)`. Deterministic given an injected clock/frame, each channel
   distinct (proves channel order/labels survive ingest).
5. **Optional + additive:** `CaptureConfig.eeg: EegConfig | None = None`.
   `None` → today's motion+events behavior, existing tests untouched. EEG reuses
   the numeric `xdf_writer`/`recorder` paths (eeg is numeric like motion).

## Architecture

New files + additive edits in `htdp_capture`:

```
htdp_capture/
  eeg_source.py    # NEW: EegSource ABC + EegConfig dataclass
  mock_eeg.py      # NEW: MockEegSource (per-channel deterministic sine)
  config.py        # EDIT: CaptureConfig += eeg: EegConfig | None = None
  contract.py      # EDIT: eeg_stream_name(eeg_id) -> "eeg_<eeg_id>"
  outlets.py       # EDIT: make_eeg_outlet(eeg_id, labels, rate_hz)
  sidecar.py       # EDIT: add eeg ingest_map entry when config.eeg set
  app.py           # EDIT: wire eeg outlet+recorder when config.eeg set
```

## Interfaces

- `EegConfig(eeg_id: str, channels: list[str], rate_hz: float = 250.0)` —
  channel count = `len(channels)`.
- `EegSource(ABC)`: `poll() -> list[tuple[float, list[float]]]` (timestamped
  N-channel samples since last poll); `close() -> None` (default no-op).
- `MockEegSource(config: EegConfig, clock=time.monotonic)`: each `poll()` emits
  one sample `(t, [sin(frame*k + i) for i in range(N)])`; deterministic per
  frame; `len(sample) == len(config.channels)`.
- `contract.eeg_stream_name(eeg_id: str) -> str` → `f"eeg_{eeg_id}"`.
- `outlets.make_eeg_outlet(eeg_id: str, labels: list[str], rate_hz: float)`:
  `cf_double64`, `channel_count=len(labels)`, type `"eeg"`, name
  `eeg_<eeg_id>`, labels in XML `desc/channels`.
- `sidecar.build_sidecar`: when `config.eeg` set, adds
  `ingest_map[eeg_stream_name(eeg_id)] = {"role":"eeg","eeg_id":eeg_id,
  "channels": {label: i for i, label in enumerate(channels)}}`.

## Data flow

`run_capture` is unchanged for motion/events. When `config.eeg` is set:
- create the eeg outlet and a `StreamRecorder(eeg_stream_name, "double64",
  len(channels), rate_hz)`;
- include the eeg outlet in the `_wait_for_consumers` set (same connection-
  priming requirement as motion — see [[htdp-capture-lsl-delivery]]);
- in the capture loop, `eeg_source.poll()` and push each sample to the eeg
  outlet with its timestamp; drain the eeg recorder alongside the others;
- after events, append the eeg `CapturedStream`.

`xdf_writer` and `recorder` are reused as-is via the numeric path (no change).

## Error handling

- `EegConfig` validation in `config.validate()` when `eeg` is set: `eeg_id`
  non-empty; `channels` non-empty; no duplicate labels; `rate_hz > 0` →
  `ConfigError`.
- Existing guards unchanged: `--force` on output; the "no motion samples" guard
  stays (eeg is supplementary, does not relax the motion requirement).

## Testing (TDD, layered for hardware-free CI)

1. **Unit (no LSL):** `MockEegSource` determinism + channel count == `len(labels)`
   + per-channel distinct; `EegConfig` validation (empty eeg_id / empty channels
   / duplicate labels / bad rate); `contract.eeg_stream_name`; `build_sidecar`
   eeg entry shape **and** htdp `validate_sidecar` accepts a sidecar with eeg
   (contract guard).
2. **Integration (real pylsl, importorskip):** eeg outlet → recorder captures
   the right N-channel samples with values matching what was pushed.
3. **Conformance (pylsl+htdp+pyxdf):** capture **with** eeg → `htdp ingest` →
   assert `streams/eeg_<id>.csv` exists, columns == `timestamp_s` + labels,
   values match the mock; **and** motion/events still land (additive, non-
   disruptive).
4. **Regression:** config **without** eeg → no eeg outlet/stream/file (today's
   behavior preserved).

**False-green guard:** the eeg conformance test is triple-gated
(pylsl+htdp+pyxdf) — it must RUN, not skip. Run with all deps; confirm 0-skip
(LSL-delivery lesson [[htdp-capture-lsl-delivery]]).

## Out of scope (deferred)

- real EEG hardware / amplifier / LSL-bridge source
- EEG `quality` / impedance channels
- filtering, referencing, montage transforms (raw passthrough — htdp handles
  downstream)
- multiple simultaneous eeg amplifiers

## Related

- htdp-capture spine shipped — [[vive-capture-kickoff]]
- LSL connection-priming requirement — [[htdp-capture-lsl-delivery]]
- htdp EEG ingest (slice 5) contract — htdp `src/htdp/ingest/mapping.py`
  (`EegStreamMap`, `extract_eeg`), `session.py` (`build_eeg_rows`)
