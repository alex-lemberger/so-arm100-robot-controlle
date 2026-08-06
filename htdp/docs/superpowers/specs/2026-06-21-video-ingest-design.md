# Design: `htdp ingest-video` — video augment adapter (v0.2 slice 3)

**Status:** Approved (brainstorm), pending implementation plan.
**Date:** 2026-06-21
**Roadmap:** v0.2, "Video capture (MP4 population in the `video/` slot)."

## Goal

Populate the raw session `video/` slot. A raw session is finalized by `synth` or
`ingest_xdf` with an empty `video/` directory. `htdp ingest-video` augments an
**existing** raw session: it copies an `.mp4` into `video/`, registers a video
`StreamRef` in `device_config.json`, and re-writes `checksums.sha256`.

This closes a loop opened by slice 2 (consent modality filtering): `resolve_absent`
already drops `video/**` when a session's consent forbids raw-video distribution,
but nothing previously put a file in that slot. After this slice the filter
operates on real data.

## Attachment model (decision: standalone augment)

Video attaches via a **standalone command** that augments an already-finalized raw
session, rather than extending `ingest_xdf`. Chosen for flexibility: it works for
any existing raw session (synth, XDF-ingested, or otherwise), and leaves the
shipped `ingest_xdf` untouched. The re-checksum of an existing session is an
explicit **raw-construction** step, distinct from the forbidden *processing-stage*
mutation of raw — the session is not sealed/consumed until it is validated for a
release. This is documented in `AGENTS.md`.

## Video is opaque

The `.mp4` is treated as an opaque file: **no decoding, transcoding, thumbnailing,
or codec/resolution introspection.** Frame rate cannot be read from the bytes
without a decoder, so it is declared in a sidecar. This keeps the slice offline,
deterministic, and dependency-free (stdlib `shutil` only; tests use a few dummy
bytes).

## Non-goals

Named, not forgotten:

- No decode/transcode/thumbnail/codec/resolution introspection.
- No frame-level time synchronization to the session `t0` (we record `fps`, not
  per-frame alignment). Deferred.
- No multi-camera in a single call — multiple cameras = repeated calls, each
  appending one `StreamRef`.
- No new persisted schema model (the sidecar model is local to the ingest module;
  the registration reuses the existing `StreamRef`).
- No change to `ingest_xdf`, `synth`, or any downstream stage.

## Sidecar input

A small `video.json` sidecar declares what the bytes cannot:

```json
{ "name": "frontal", "fps": 30.0 }
```

- `name`: non-empty string. Determines the deterministic output filename
  (`video/<name>.mp4`) and the `StreamRef.name`. The source filename is ignored.
- `fps`: float > 0. Recorded as `StreamRef.rate_hz`.

Validated by a local pydantic model `VideoSidecar` before any write.

## Architecture

New module `src/htdp/ingest/video.py` + one CLI command. No new package.

| Unit | Responsibility | Depends on |
|------|----------------|-----------|
| `ingest/video.py` | `VideoSidecar` model; `VideoIngestError`; `ingest_video()` orchestrator — validate sidecar, guard duplicates, copy mp4, append video `StreamRef`, re-checksum. | `io.canonical`, `io.checksums`, `schemas` |
| `cli.py` (modified) | `ingest-video` command following the existing optional-error → `Exit(1)` pattern. | `ingest.video` |

### `ingest/video.py`

```python
class VideoIngestError(RuntimeError): ...

class VideoSidecar(BaseModel):           # local, NOT persisted
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    fps: float = Field(gt=0)

def ingest_video(
    session_dir: Path, mp4_path: Path, sidecar_path: Path, force: bool = False
) -> Path: ...
```

`ingest_video` behavior:
1. Validate `mp4_path` exists and `session_dir/device_config.json` exists →
   `VideoIngestError` otherwise.
2. Load + validate the sidecar into `VideoSidecar` (`ValidationError` on bad input).
3. Load `device_config.json` into `DeviceConfig`. If a `role="video"` stream with
   the same `name` (or path `video/<name>.mp4`) already exists → `VideoIngestError`
   unless `force` (with `force`, drop the existing matching StreamRef first).
4. Copy `mp4_path` → `session_dir/video/<name>.mp4` (the `video/` dir already
   exists from session creation; create if absent).
5. Append `StreamRef(name=name, path=f"video/{name}.mp4", fmt="mp4", role="video",
   rate_hz=fps)`; `dump_json` the device config.
6. `write_checksums(session_dir)` — re-seal raw including the new mp4 and updated
   device config. Return `session_dir`.

Steps 1–3 (all validation/guards) run before any write (step 4): no partial state.

## Data flow

```
htdp ingest-video raw/synth-0001 frontal.mp4 video.json [--force]
  → validate mp4 + device_config exist
  → load+validate sidecar {name, fps}
  → load device_config; guard duplicate video name (unless --force)
  → copy mp4 -> raw/synth-0001/video/<name>.mp4
  → append StreamRef(role=video, fmt=mp4, rate_hz=fps) -> device_config.json
  → write_checksums (re-seal)
→ htdp validate raw/synth-0001  passes unchanged
→ htdp package ... with distribute_raw_video=False  drops video/<name>.mp4,
   records "video" in absent_modalities
```

## Error handling

- Missing mp4 or missing `device_config.json` → `VideoIngestError`.
- Invalid sidecar → `pydantic.ValidationError`.
- Duplicate video `name` without `--force` → `VideoIngestError`.
- CLI catches `(VideoIngestError, ValidationError, FileNotFoundError)` → prints
  `error: ...` to stderr, exits 1.
- No partial writes: all checks precede the copy.

## Testing (offline, deterministic)

Tests use a few dummy bytes as the `.mp4` (opaque — never decoded).

1. **happy path:** synth session → `ingest_video` → `video/frontal.mp4` exists;
   `device_config.json` has a `role="video"` StreamRef named `frontal` with
   `rate_hz=30.0`; `validate_session` returns `[]` (checksums re-sealed).
2. **duplicate guard:** second `ingest_video` with the same `name` → raises
   `VideoIngestError`; with `force=True` → overwrites file + replaces the StreamRef
   (no duplicate stream).
3. **invalid sidecar:** missing `fps` or `fps <= 0` or empty `name` → error, nothing
   written.
4. **loop closure (consent filtering):** synth session → `ingest_video` →
   `package_release`:
   - consent `distribute_raw_video=True` → `video/frontal.mp4` present in the
     release, `"video"` not in `absent_modalities`.
   - consent `distribute_raw_video=False` → `video/frontal.mp4` dropped, `"video"`
     in `absent_modalities`, session + motion intact.
5. **CLI:** `ingest-video` happy path exits 0 and writes the file; a missing mp4
   exits 1 with `error:`.

## Documentation impact

- `docs/DATA_CONTRACT.md`: document the video `StreamRef` (role `video`, fmt `mp4`,
  `rate_hz` = fps) and the opaque-file policy (no decode).
- `AGENTS.md`: add `ingest-video` usage; note the re-checksum is a raw-construction
  step, not a processing-stage mutation of raw.
- `docs/ROADMAP.md`: mark "Video capture" in progress.
- No JSON-Schema re-export (no persisted-schema model change).
```
