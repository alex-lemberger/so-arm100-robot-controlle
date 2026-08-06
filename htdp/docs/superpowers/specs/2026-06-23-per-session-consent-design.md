# Per-Session Consent Granularity — Design

**Date:** 2026-06-23
**Slice:** v0.2 — per-session consent modality filtering (follow-up to slice 2)
**Status:** approved, ready for implementation plan

## Goal

Make modality consent filtering **per-session** instead of release-wide. Today (slice 2) a
modality is dropped from the *entire* release if *any* session forbids it. After this slice,
a modality's files are dropped only from the sessions whose consent forbids it; sessions that
permit it keep their data. The manifest records, per session, which modalities were absent, so
a mixed-consent release is self-describing.

## Non-Goals

- Changing the **profile consent gate** (`check_consent`, block-on-conflict for permission
  flags like `model_training`/`commercial_use`). Only *modality filtering* becomes per-session.
- New modalities (still `eeg`, `video` from `MODALITIES`).
- Changing the reproducibility hash algorithm (`_manifest_sha` still hashes `data/` only).
- Per-session profiles (one profile per release, unchanged).
- Surfacing per-session absent info in the release catalog (slice 17 keeps reading the
  release-wide `absent_modalities`; a per-session catalog column is a possible later slice).

## Background (verified)

- `src/htdp/consent/modalities.py`: `MODALITY_FLAG` (`video→distribute_raw_video`,
  `eeg→distribute_raw_eeg`), `MODALITY_GLOBS`, `MODALITIES=("eeg","video")`, and
  `resolve_absent(consents, present) -> (absent, drop_globs)` (release-wide union).
- `src/htdp/release/package.py`: `_present_modalities` (union across sessions),
  `package_release` applies `drop_globs` uniformly to **every** session (lines 80-83) and
  writes `DatasetRelease(absent_modalities=sorted(absent), ...)`.
- `Consent` flags default `False`; `commercial_dataset` profile gate does **not** require
  video/eeg distribution (verified: an existing test packages a `distribute_raw_video=False`
  session under that profile without `ConsentError`).
- `DatasetRelease` is in the JSON-Schema export list (`schemas/export.py`); adding a field
  requires re-exporting `docs/schemas/` and updating `docs/DATA_CONTRACT.md` (per AGENTS.md).
- `resolve_absent` is imported only by `package.py` (no test imports it directly — tests
  exercise behavior through `package_release`).

## Architecture

### 1. `consent/modalities.py` — per-session resolver

Add:

```python
def resolve_absent_per_session(
    consents: dict[str, Consent],
    present: dict[str, set[str]],
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Per session, decide absent modalities and file globs to drop.

    For each session, a modality is absent if its consent forbids it OR it is not present in
    that session. A modality contributes drop globs only when it is both forbidden AND present.
    Returns (absent_by_session, drop_globs_by_session), each keyed by session_id with sorted
    lists.
    """
```

Logic mirrors the current single-modality rule, keyed by session. `resolve_absent` is
removed (its only caller is rewired); if a direct importer is found, keep it instead.

### 2. `release/package.py` — apply per session

- Replace `_present_modalities` with `_present_by_session(session_ids, raw_root) -> dict[str, set[str]]`.
- Build `consents` as `dict[sid, Consent]` (already loaded in the gate loop — collect into a dict).
- `absent_by_session, drop_globs_by_session = resolve_absent_per_session(consents, present)`.
- In the copy loop, apply **that session's** `drop_globs_by_session[sid]` to its `dest` only.
- Release-wide `absent_modalities` = sorted **intersection** of all `absent_by_session.values()`
  (modalities absent from every session).
- `DatasetRelease(..., absent_modalities=<intersection>, absent_modalities_by_session=<absent_by_session>)`.

### 3. `schemas/models.py` — manifest field

```python
class DatasetRelease(_Base):
    release_name: str
    profile: str
    session_ids: list[str]
    absent_modalities: list[str] = Field(default_factory=list)
    absent_modalities_by_session: dict[str, list[str]] = Field(default_factory=dict)
    manifest_sha256: str
```

Re-export JSON schemas to `docs/schemas/` and update `docs/DATA_CONTRACT.md`.

## Data Flow

`session_ids` → per-session `Consent` + per-session present-set → `resolve_absent_per_session`
→ per-session file drops in staging + per-session absent map → manifest
(`absent_modalities` intersection + `absent_modalities_by_session`).

## Error Handling

Unchanged. The profile gate still raises `ConsentError` before any output. Modality filtering
never raises — it drops files.

## Determinism / Reproducibility

`_manifest_sha` hashes `data/` files only, so per-session drops are reflected and the digest
stays reproducible; manifest dict ordering is excluded from the hash. `absent_modalities_by_session`
is serialized via canonical `dump_json` (sorted keys) so the manifest file itself is stable.

## Testing

`tests/` (base env — no optional dep):

**New mixed-consent test (the slice's point):**
- Two synth sessions (seed 1 & 2). Write `video/clip.mp4` into **both**. Set
  `distribute_raw_video=True` for session A (`synth-0001`) and `False` for session B
  (`synth-0002`); leave other flags as synth defaults (so the `commercial_dataset` gate passes).
- `package_release(["synth-0001","synth-0002"], "rel-mixed", COMMERCIAL_DATASET, raw, releases)`.
- Assert A keeps `data/synth-0001/video/clip.mp4`; B's `data/synth-0002/video/clip.mp4` is gone.
- Manifest `absent_modalities_by_session == {"synth-0001": ["eeg"], "synth-0002": ["eeg","video"]}`.
- Manifest `absent_modalities == ["eeg"]` (video kept by A → not fully absent; eeg absent in both).

**Regression (homogeneous behavior preserved):** existing slice-2 tests
(`test_video_consent_filtering`, `test_eeg_consent_filtering`, `test_consent`) and the slice-17
release-catalog test still pass — an all-forbid synth release yields intersection == old union
(`absent_modalities` unchanged, e.g. `["eeg","video"]`), and single-session releases are
unaffected.

**Schema:** a test (or the existing schema-export test, if present) confirms
`DatasetRelease` JSON schema includes `absent_modalities_by_session`; `docs/schemas/` is
re-exported and committed.

## Files Touched

- Modify: `src/htdp/consent/modalities.py` (add `resolve_absent_per_session`, remove unused `resolve_absent`)
- Modify: `src/htdp/release/package.py` (`_present_by_session`, per-session apply, intersection, manifest field)
- Modify: `src/htdp/schemas/models.py` (`DatasetRelease.absent_modalities_by_session`)
- Modify: `docs/schemas/` (re-export), `docs/DATA_CONTRACT.md`
- Modify: `tests/` (new mixed-consent test; existing consent tests stay green)
- Modify: docs — `docs/ETHICS_AND_CONSENT.md`, `docs/ROADMAP.md`

No new dependency, no new module. Schema change → JSON-Schema re-export. `consent/`,
`release/`, `schemas/` are already in the mypy gate.

## Self-Review

- **Placeholders:** none — function signatures, manifest field, the exact mixed-consent
  assertions, and the intersection rule are concrete.
- **Consistency:** per-session rule reuses the slice-2 modality logic keyed by session;
  intersection collapses to the old union for homogeneous releases (regression-safe);
  `absent_modalities_by_session` is the honest per-session record the release-wide field can't
  express.
- **Scope:** single plan — one resolver fn, package rewire, one manifest field + re-export,
  new test, docs. Profile gate untouched.
- **Ambiguity:** modality filtering per-session, profile gate unchanged; release-wide
  `absent_modalities` = intersection ("fully absent"); per-session record in a new dict field;
  reproducibility hash logic unchanged.
