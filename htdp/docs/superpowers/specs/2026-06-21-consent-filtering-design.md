# Design: consent modality filtering (v0.2 slice 2)

**Status:** Approved (brainstorm), pending implementation plan.
**Date:** 2026-06-21
**Roadmap:** v0.2, "Consent filtering — strip disallowed modalities from a release
while still including the session."

## Goal

Today `htdp package` is **block-on-conflict**: if a session's consent does not
permit the requested release profile, packaging aborts and writes nothing. That
is correct for *profile-permission* consent (commercial use, model training,
etc.) but too blunt for *per-modality* consent: a participant who allows their
motion data to be shared but forbids raw video distribution should still appear
in the release — with the video omitted, not the whole session dropped.

This slice adds **modality filtering** to the release stage: include the session,
omit the data types its consent forbids, and record the omission in the manifest.

## Scope: filter vs. block

Two distinct kinds of consent flag, handled differently:

- **Permission flags** — `commercial_use`, `model_training`, `third_party_access`,
  `public_release`. These gate whether a session may appear in a profile **at
  all**. They remain **block-on-conflict** (existing `check_consent` behavior,
  unchanged). Filtering them would silently ship data for a use the participant
  forbade — unacceptable.
- **Modality flags** — `distribute_raw_video`, `distribute_raw_eeg`. These gate a
  **data type within** an otherwise-permitted session. These are **filtered**:
  the modality's files are dropped from the release, the session is still
  included, and the modality is listed in `manifest.absent_modalities`.

Motion (the core product) has no modality flag and is always included.

## Non-goals

Named, not forgotten:

- **Per-session modality granularity.** v0.2 uses a **release-level union**: if
  *any* session in the release forbids a modality, that modality is dropped for
  the *whole* release. Mixed releases (video present for some sessions, absent
  for others) are deferred. This keeps `absent_modalities: list[str]`
  release-level (no schema change).
- New consent flags or new modalities beyond video/eeg. The map is extensible but
  this slice ships only the two existing modality flags.
- Changing the permission gate, the CLI surface, or any schema model.
- Re-validating the release after filtering (release is not a raw session).

## Architecture

Extends the **release stage only**. One new pure module + a localized change to
`package.py`. No CLI change, no schema change (`DatasetRelease.absent_modalities`
already exists).

| Unit | Responsibility | Depends on |
|------|----------------|-----------|
| `consent/modalities.py` (new) | Declare the modality↔flag and modality↔file-glob maps. Pure function `resolve_absent` deciding which modalities are absent and which file globs to drop. No I/O. | `schemas` |
| `consent/profiles.py` (unchanged) | Permission gate `check_consent`. Stays block-on-conflict. | `schemas` |
| `release/package.py` (modified) | Call `resolve_absent`; exclude dropped files when copying each session into staging; record computed `absent_modalities` in the manifest. | `consent.modalities`, `io`, `schemas` |

### `consent/modalities.py`

```python
MODALITY_FLAG: dict[str, str] = {
    "video": "distribute_raw_video",
    "eeg": "distribute_raw_eeg",
}
MODALITY_GLOBS: dict[str, tuple[str, ...]] = {
    "video": ("video/**",),
    "eeg": ("streams/eeg_*.csv",),
}
```

`resolve_absent(consents, present) -> tuple[list[str], list[str]]`:
- Inputs: `consents: list[Consent]` (one per session in the release);
  `present: set[str]` (modalities that have ≥1 file in ≥1 session).
- A modality `m` (key of `MODALITY_FLAG`) is **absent** when:
  - it is **forbidden** — `any(not getattr(c, MODALITY_FLAG[m]) for c in consents)`, OR
  - it is **not present** — `m not in present`.
- Returns `(absent, drop_globs)`:
  - `absent` = sorted list of absent modality names.
  - `drop_globs` = the globs (from `MODALITY_GLOBS`) of modalities that are
    **forbidden AND present** — i.e. files that exist and must be excluded. (A
    not-present modality contributes to `absent` but has no files to drop.)
- Pure, deterministic, unit-testable with no filesystem.

### `release/package.py` changes

1. Keep the permission gate exactly as is (loop over sessions, `check_consent`,
   raise `ConsentError` on missing permission flags — runs first, before any
   output).
2. After the gate, before copying: scan each session's raw folder to compute
   `present` (which modalities have matching files), load each `Consent`, then
   call `resolve_absent`.
3. When copying a session into staging, exclude files matching any `drop_glob`.
   Implement via `shutil.copytree(..., ignore=...)` or copy selectively; the
   excluded files must not appear in staging (so they are absent from the
   manifest hash and the shipped release).
4. Replace the hardcoded `absent = ["eeg", "video"]` with the computed `absent`
   from `resolve_absent`. The manifest's `absent_modalities` is this sorted list.

The consent objects are already loaded in the gate loop; reuse them (load once).

## Data flow

```
htdp package <sids> --release R --profile P
  → permission gate: check_consent per session → ConsentError if any missing  (BLOCK, unchanged)
  → scan session folders → present: set[str]
  → resolve_absent(consents, present) → (absent, drop_globs)                  (FILTER)
  → copytree each session into staging, excluding drop_globs                  (omit forbidden files)
  → manifest.absent_modalities = absent
  → write checksums, atomic os.replace into releases/                         (unchanged)
```

## Reproducibility

Dropping files changes the set of `data/` files and therefore `manifest_sha256` —
expected and still deterministic: same sessions + same consents + same code →
identical release, identical hash. The hash scope (data/ only, excluding
timestamps/tool_versions) is unchanged.

## Error handling

- Permission conflict → `ConsentError`, nothing written (unchanged, atomic).
- Filtering itself never raises — it omits files. A fully-forbidden,
  no-data-left session still produces a valid release entry (session row +
  metadata; its motion remains, since motion is unfilterable).
- No partial writes: staging in a temp dir, atomic `os.replace` (unchanged).

## Testing (offline, deterministic)

Fixtures add a dummy `video/clip.mp4` (a few bytes) into a synth raw session so
filtering has something to drop. **`synth` is not modified.**

1. **`test_modalities.py`** (pure, no fs):
   - forbidden flag → modality in `absent`, its glob in `drop_globs`.
   - allowed flag + present → not absent, no glob dropped.
   - not present (no files) → absent, but **no** glob in `drop_globs`.
   - release-level union: one forbidding consent among several → absent.
2. **`test_release_filtering.py`** (package-level):
   - video present + `distribute_raw_video=True` → `video/clip.mp4` in release,
     `"video"` **not** in `absent_modalities`.
   - video present + `distribute_raw_video=False` → `video/clip.mp4` **absent**
     from release, `"video"` in `absent_modalities`, session row still present,
     motion CSVs intact.
   - mixed: session A allows video, session B forbids → release-level union drops
     video for both; `"video"` in `absent_modalities`.
3. **Existing tests stay green:** permission block-on-conflict
   (`test_release.py`/`test_consent.py`) and reproducible-manifest tests must not
   regress.

## Documentation impact

- `docs/ETHICS_AND_CONSENT.md`: document filter-vs-block — permission flags block,
  modality flags filter; release-level union semantics.
- `docs/DATA_CONTRACT.md`: `absent_modalities` is now **computed** (consent +
  presence), not a fixed `["eeg","video"]`.
- `docs/ROADMAP.md`: mark "Consent filtering" in progress.
- No schema re-export (no model change).
```
