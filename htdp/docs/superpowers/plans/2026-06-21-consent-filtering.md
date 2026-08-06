# Consent Modality Filtering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-modality consent filtering to `htdp package`: include a session in a release but omit the raw data types its consent forbids (video/eeg), recording the omission in `manifest.absent_modalities` — while permission flags stay block-on-conflict.

**Architecture:** One new pure module `consent/modalities.py` (modality↔flag and modality↔glob maps + a pure `resolve_absent` decision function) plus a localized change to `release/package.py` (scan present modalities → compute absent → drop forbidden files when copying). No CLI change, no schema change.

**Tech Stack:** Python ≥3.11, pydantic v2, pytest. Pure stdlib.

## Global Constraints

Copied verbatim from `AGENTS.md`:

- Python `>=3.11`. mypy `strict` must pass on the gate targets (this slice adds no new package to the mypy target list; `consent` is already covered).
- ruff: `line-length = 100`, `line-ending = lf`. `uv run ruff format --check . && uv run ruff check .` clean.
- Canonical output only (`io.canonical`, `io.checksums`). Do not change canonical formats.
- **Consent gate must run FIRST and block atomically** — permission conflict raises `ConsentError` and writes nothing. Do not weaken this.
- **No partial writes:** packaging stages in a temp dir and atomically `os.replace`s into `releases/`. Preserve this.
- **No schema model change** (`DatasetRelease.absent_modalities: list[str]` already exists) → no JSON-Schema re-export.
- Reuse existing schemas/modules; do not touch other pipeline stages (`synth`, `validate`, `processing`, `qc`, `replay`, `ingest`).
- Deterministic: same sessions + same consents + same code → identical release + identical `manifest_sha256`.

**Reference — current consent model fields** (`src/htdp/schemas/models.py` `Consent`): includes `distribute_raw_video: bool = False`, `distribute_raw_eeg: bool = False` (the two modality flags this slice filters on) plus the permission flags (`commercial_use`, `model_training`, `third_party_access`, `public_release`, `internal_only`).

**Reference — synth defaults that keep existing tests green:** a synth session's `consent.json` leaves `distribute_raw_video=False`/`distribute_raw_eeg=False`, and its `video/` dir is empty (no files). So with no modality files present, video/eeg are *not present* → recorded absent with **no files to drop** → byte-identical to today's hardcoded `["eeg","video"]`. Existing `test_release.py` must not regress.

---

### Task 1: `consent/modalities.py` — maps + `resolve_absent` (pure)

**Files:**
- Create: `src/htdp/consent/modalities.py`
- Test: `tests/test_modalities.py`

**Interfaces:**
- Consumes: `Consent` from `htdp.schemas.models`.
- Produces:
  - `MODALITY_FLAG: dict[str, str] = {"video": "distribute_raw_video", "eeg": "distribute_raw_eeg"}`
  - `MODALITY_GLOBS: dict[str, tuple[str, ...]] = {"video": ("video/**/*",), "eeg": ("streams/eeg_*.csv",)}`
    (globs enumerate **files** under a staged session dir via `Path.glob` + `is_file` filter)
  - `MODALITIES: tuple[str, ...] = ("eeg", "video")` (sorted modality names)
  - `resolve_absent(consents: list[Consent], present: set[str]) -> tuple[list[str], list[str]]`
    - A modality `m` is **absent** when forbidden (`any(not getattr(c, MODALITY_FLAG[m]) for c in consents)`) OR not present (`m not in present`).
    - Returns `(absent, drop_globs)`: `absent` = sorted absent modality names; `drop_globs` = globs of modalities that are **forbidden AND present** (the only ones with files to remove). Sorted, deterministic.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_modalities.py
from htdp.consent.modalities import resolve_absent
from htdp.schemas.models import Consent


def _c(**over) -> Consent:
    base = dict(consent_form_version="v1", distribute_raw_video=True, distribute_raw_eeg=True)
    base.update(over)
    return Consent(**base)


def test_allowed_and_present_is_not_absent():
    absent, drop = resolve_absent([_c()], {"video", "eeg"})
    assert absent == []
    assert drop == []


def test_forbidden_and_present_is_absent_and_dropped():
    absent, drop = resolve_absent([_c(distribute_raw_video=False)], {"video", "eeg"})
    assert absent == ["video"]
    assert drop == ["video/**/*"]


def test_not_present_is_absent_but_not_dropped():
    absent, drop = resolve_absent([_c()], set())  # nothing present
    assert absent == ["eeg", "video"]
    assert drop == []  # nothing on disk to remove


def test_release_level_union_one_forbidding_consent_drops_for_all():
    consents = [_c(), _c(distribute_raw_video=False)]  # one allows, one forbids
    absent, drop = resolve_absent(consents, {"video", "eeg"})  # both present
    assert absent == ["video"]  # eeg allowed+present -> kept; video forbidden by one -> absent
    assert drop == ["video/**/*"]


def test_absent_list_is_sorted():
    absent, _ = resolve_absent([_c(distribute_raw_video=False, distribute_raw_eeg=False)],
                               {"video", "eeg"})
    assert absent == ["eeg", "video"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_modalities.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'htdp.consent.modalities'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/htdp/consent/modalities.py
from __future__ import annotations

from htdp.schemas.models import Consent

MODALITY_FLAG: dict[str, str] = {
    "video": "distribute_raw_video",
    "eeg": "distribute_raw_eeg",
}
MODALITY_GLOBS: dict[str, tuple[str, ...]] = {
    "video": ("video/**/*",),
    "eeg": ("streams/eeg_*.csv",),
}
MODALITIES: tuple[str, ...] = ("eeg", "video")


def resolve_absent(
    consents: list[Consent],
    present: set[str],
) -> tuple[list[str], list[str]]:
    """Decide which modalities are absent from a release and which file globs to drop.

    A modality is absent if any session forbids it (consent flag False) or it is not
    present in any session. Only modalities that are both forbidden AND present
    contribute file globs to drop (a not-present modality has no files to remove).
    """
    absent: list[str] = []
    drop_globs: list[str] = []
    for m in MODALITIES:
        flag = MODALITY_FLAG[m]
        forbidden = any(not getattr(c, flag) for c in consents)
        is_present = m in present
        if forbidden or not is_present:
            absent.append(m)
        if forbidden and is_present:
            drop_globs.extend(MODALITY_GLOBS[m])
    return sorted(absent), sorted(drop_globs)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_modalities.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/htdp/consent/modalities.py tests/test_modalities.py
git commit -m "feat(consent): modality maps + resolve_absent decision (pure)"
```

---

### Task 2: `package.py` — `_present_modalities` scan helper

**Files:**
- Modify: `src/htdp/release/package.py` (add helper near top, after imports)
- Test: `tests/test_release_present.py`

**Interfaces:**
- Consumes: `MODALITY_GLOBS` (Task 1).
- Produces: `_present_modalities(session_ids: list[str], raw_root: Path) -> set[str]` — returns the set of modality names that have ≥1 file matching their globs in ≥1 session's raw folder. Uses `Path.glob` + `is_file`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_release_present.py
from pathlib import Path

from htdp.release.package import _present_modalities
from htdp.synth.generate import generate_session


def test_synth_session_has_no_video_or_eeg_present(tmp_path: Path):
    generate_session(tmp_path / "raw", seed=1)
    assert _present_modalities(["synth-0001"], tmp_path / "raw") == set()


def test_video_file_marks_video_present(tmp_path: Path):
    generate_session(tmp_path / "raw", seed=1)
    (tmp_path / "raw" / "synth-0001" / "video" / "clip.mp4").write_bytes(b"\x00\x01")
    assert _present_modalities(["synth-0001"], tmp_path / "raw") == {"video"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_release_present.py -v`
Expected: FAIL — `ImportError: cannot import name '_present_modalities'`

- [ ] **Step 3: Write minimal implementation**

Add the import to `src/htdp/release/package.py` (with the other `from htdp...` imports):

```python
from htdp.consent.modalities import MODALITY_GLOBS, resolve_absent
```

Add this helper after the imports (e.g. just before `class ConsentError`):

```python
def _present_modalities(session_ids: list[str], raw_root: Path) -> set[str]:
    present: set[str] = set()
    for modality, globs in MODALITY_GLOBS.items():
        for sid in session_ids:
            session_dir = raw_root / sid
            if any(
                p.is_file() for pattern in globs for p in session_dir.glob(pattern)
            ):
                present.add(modality)
                break
    return present
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_release_present.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/htdp/release/package.py tests/test_release_present.py
git commit -m "feat(release): _present_modalities raw-folder scan"
```

---

### Task 3: `package.py` — computed `absent_modalities` (gather consents, no file drop yet)

**Files:**
- Modify: `src/htdp/release/package.py` (gate loop + absent computation)
- Test: `tests/test_release.py` (append one test; existing tests must stay green)

**Interfaces:**
- Consumes: `resolve_absent` (Task 1), `_present_modalities` (Task 2).
- Produces: `package_release` now records a **computed** `absent_modalities` (consent + presence) instead of the hardcoded `["eeg", "video"]`. File dropping comes in Task 4 — here, behavior is byte-identical for synth sessions (nothing present), proving no regression.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_release.py`:

```python
def test_absent_modalities_recorded_when_video_present_but_forbidden(tmp_path: Path):
    raw = _raw(tmp_path)
    # video present on disk, but consent forbids distributing raw video
    (raw / "synth-0001" / "video" / "clip.mp4").write_bytes(b"\x00\x01")
    consent = raw / "synth-0001/consent.json"
    data = json.loads(consent.read_text(encoding="utf-8"))
    data["distribute_raw_video"] = False
    consent.write_text(json.dumps(data), encoding="utf-8")
    out = package_release(
        ["synth-0001"], "rel-vid", ReleaseProfile.COMMERCIAL_DATASET, raw, tmp_path / "releases"
    )
    manifest = json.loads((out / "manifest.json").read_text())
    assert "video" in manifest["absent_modalities"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_release.py::test_absent_modalities_recorded_when_video_present_but_forbidden -v`
Expected: PASS *or* FAIL depending on starting state — with the hardcoded `["eeg","video"]` it may already pass. To make the test meaningful, FIRST confirm the wiring is needed: run the full file `uv run pytest tests/test_release.py -v` and proceed to Step 3 to replace the hardcoded value with the computed one regardless. (The decisive proof is Task 4; this task wires the computation.)

- [ ] **Step 3: Write minimal implementation**

In `src/htdp/release/package.py`, change the gate loop to **collect** consents, then compute absent. Replace this block:

```python
    # Consent gate FIRST — fail before any output.
    for sid in session_ids:
        consent = Consent.model_validate_json(
            (raw_root / sid / "consent.json").read_text(encoding="utf-8")
        )
        missing = check_consent(consent, profile)
        if missing:
            raise ConsentError(f"{sid}: profile {profile.value} requires {missing}")

    # v0.1: video + EEG are never captured -> always recorded absent (spec §8.1).
    absent = ["eeg", "video"]
```

with:

```python
    # Consent gate FIRST — fail before any output.
    consents: list[Consent] = []
    for sid in session_ids:
        consent = Consent.model_validate_json(
            (raw_root / sid / "consent.json").read_text(encoding="utf-8")
        )
        missing = check_consent(consent, profile)
        if missing:
            raise ConsentError(f"{sid}: profile {profile.value} requires {missing}")
        consents.append(consent)

    # Modality filtering: a modality is absent if any session forbids it (consent)
    # or it is not present on disk. drop_globs lists files to omit from staging.
    present = _present_modalities(session_ids, raw_root)
    absent, drop_globs = resolve_absent(consents, present)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_release.py -v`
Expected: PASS (all tests in the file, including the new one and the existing reproducibility/block tests).

- [ ] **Step 5: Commit**

```bash
git add src/htdp/release/package.py tests/test_release.py
git commit -m "feat(release): compute absent_modalities from consent + presence"
```

---

### Task 4: `package.py` — drop forbidden-present files from staging

**Files:**
- Modify: `src/htdp/release/package.py` (the `copytree` loop)
- Test: `tests/test_release_filtering.py`

**Interfaces:**
- Consumes: `drop_globs` computed in Task 3.
- Produces: forbidden modality files are excluded from the staged (and shipped) release. Session row, metadata, and motion CSVs remain.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_release_filtering.py
import json
from pathlib import Path

from htdp.release.package import package_release
from htdp.schemas.enums import ReleaseProfile
from htdp.synth.generate import generate_session


def _raw_with_video(tmp_path: Path, seed: int, allow_video: bool) -> Path:
    generate_session(tmp_path / "raw", seed=seed)
    sid = f"synth-{seed:04d}"
    (tmp_path / "raw" / sid / "video" / "clip.mp4").write_bytes(b"\x00\x01\x02")
    consent = tmp_path / "raw" / sid / "consent.json"
    data = json.loads(consent.read_text(encoding="utf-8"))
    data["distribute_raw_video"] = allow_video
    consent.write_text(json.dumps(data), encoding="utf-8")
    return tmp_path / "raw"


def test_allowed_video_is_included(tmp_path: Path):
    raw = _raw_with_video(tmp_path, 1, allow_video=True)
    out = package_release(
        ["synth-0001"], "rel", ReleaseProfile.COMMERCIAL_DATASET, raw, tmp_path / "releases"
    )
    assert (out / "data/synth-0001/video/clip.mp4").exists()
    manifest = json.loads((out / "manifest.json").read_text())
    assert "video" not in manifest["absent_modalities"]


def test_forbidden_video_is_dropped_session_kept(tmp_path: Path):
    raw = _raw_with_video(tmp_path, 1, allow_video=False)
    out = package_release(
        ["synth-0001"], "rel", ReleaseProfile.COMMERCIAL_DATASET, raw, tmp_path / "releases"
    )
    assert not (out / "data/synth-0001/video/clip.mp4").exists()  # dropped
    assert (out / "data/synth-0001/session.json").exists()  # session kept
    assert (out / "data/synth-0001/streams/motion_right_wrist.csv").exists()  # motion intact
    manifest = json.loads((out / "manifest.json").read_text())
    assert "video" in manifest["absent_modalities"]


def test_release_level_union_drops_for_all_sessions(tmp_path: Path):
    generate_session(tmp_path / "raw", seed=1)
    generate_session(tmp_path / "raw", seed=2)
    for seed in (1, 2):
        sid = f"synth-{seed:04d}"
        (tmp_path / "raw" / sid / "video" / "clip.mp4").write_bytes(b"\x00")
    # session 1 allows video, session 2 forbids it
    for seed, allow in ((1, True), (2, False)):
        sid = f"synth-{seed:04d}"
        c = tmp_path / "raw" / sid / "consent.json"
        d = json.loads(c.read_text(encoding="utf-8"))
        d["distribute_raw_video"] = allow
        c.write_text(json.dumps(d), encoding="utf-8")
    out = package_release(
        ["synth-0001", "synth-0002"], "rel", ReleaseProfile.COMMERCIAL_DATASET,
        tmp_path / "raw", tmp_path / "releases",
    )
    assert not (out / "data/synth-0001/video/clip.mp4").exists()  # dropped for allowing session too
    assert not (out / "data/synth-0002/video/clip.mp4").exists()
    manifest = json.loads((out / "manifest.json").read_text())
    assert "video" in manifest["absent_modalities"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_release_filtering.py -v`
Expected: FAIL — `test_forbidden_video_is_dropped_session_kept` and `test_release_level_union_drops_for_all_sessions` fail (files still copied; `clip.mp4` exists in the release).

- [ ] **Step 3: Write minimal implementation**

In `src/htdp/release/package.py`, find the per-session copy line inside the staging loop:

```python
            shutil.copytree(raw_root / sid, data_dir / sid)
```

Replace it with a copy that then removes dropped-modality files:

```python
            dest = data_dir / sid
            shutil.copytree(raw_root / sid, dest)
            for pattern in drop_globs:
                for p in sorted(dest.glob(pattern)):
                    if p.is_file():
                        p.unlink()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_release_filtering.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/htdp/release/package.py tests/test_release_filtering.py
git commit -m "feat(release): drop consent-forbidden modality files from release"
```

---

### Task 5: Docs + full gate

**Files:**
- Modify: `docs/ETHICS_AND_CONSENT.md` (filter-vs-block + union semantics)
- Modify: `docs/DATA_CONTRACT.md` (`absent_modalities` is computed, not fixed)
- Modify: `docs/ROADMAP.md` (mark consent filtering in progress)

**Interfaces:** none.

- [ ] **Step 1: Update docs**

`docs/ETHICS_AND_CONSENT.md` — add a "Modality filtering" note: permission flags (`commercial_use`, `model_training`, `third_party_access`, `public_release`) **block** the session from a profile; modality flags (`distribute_raw_video`, `distribute_raw_eeg`) **filter** — the session is included but those files are omitted and listed in `manifest.absent_modalities`. v0.2 uses a **release-level union**: if any session in a release forbids a modality, it is dropped for the whole release.

`docs/DATA_CONTRACT.md` — note that `absent_modalities` is now **computed** from consent + on-disk presence (no longer a fixed `["eeg","video"]`); motion is never filtered.

`docs/ROADMAP.md` — change the "Consent filtering" bullet to mark progress, e.g. append `— **in progress (modality filtering landed)**`.

- [ ] **Step 2: Run the full gate**

Run:
```
uv run ruff format --check . && uv run ruff check . && uv run pytest
uv run mypy src/htdp/schemas src/htdp/consent src/htdp/release src/htdp/io src/htdp/ingest
```
Expected: ruff clean; pytest all pass (no skips beyond the pre-existing mujoco/pyxdf-gated ones); mypy `Success`.

- [ ] **Step 3: Commit**

```bash
git add docs/ETHICS_AND_CONSENT.md docs/DATA_CONTRACT.md docs/ROADMAP.md
git commit -m "docs(consent): document modality filtering vs block-on-conflict"
```

---

## Self-Review

**Spec coverage** (`2026-06-21-consent-filtering-design.md`):
- `consent/modalities.py` maps + pure `resolve_absent` → Task 1. ✓
- Permission gate stays block-on-conflict (unchanged) → preserved in Task 3 edit. ✓
- Present-modality scan → Task 2. ✓
- Computed `absent_modalities` replaces hardcoded → Task 3. ✓
- Drop forbidden-present files when copying → Task 4. ✓
- Release-level union (any session forbids → dropped for all) → `resolve_absent` (Task 1) + Task 4 test. ✓
- Reproducibility / no-partial-writes / atomic replace preserved (no change to staging/replace logic) → Tasks 3–4. ✓
- Tests: modalities unit, present scan, computed absent, filtering incl. mixed union, existing green → Tasks 1–4. ✓
- Docs (ETHICS, DATA_CONTRACT, ROADMAP), no schema re-export → Task 5. ✓

**No-regression check:** synth sessions have no video/eeg files and forbid both by default → `present=∅` → `absent=["eeg","video"]`, `drop_globs=[]` → byte-identical to the old hardcoded behavior. Existing `test_release.py` (build, block, reproducibility) stays green (verified by running the whole file in Task 3 Step 4).

**Placeholder scan:** none — every code/test step is concrete. (Task 3 Step 2 intentionally explains why its standalone failure is ambiguous and defers the decisive proof to Task 4; the implementation step is unconditional.)

**Type consistency:** `resolve_absent(consents: list[Consent], present: set[str]) -> tuple[list[str], list[str]]` (Task 1) matches the call in Task 3; `_present_modalities(session_ids, raw_root) -> set[str]` (Task 2) feeds `resolve_absent`'s `present` arg; `drop_globs` (list[str]) from Task 3 consumed by Task 4's glob loop; `MODALITY_GLOBS` values are file-enumerating patterns (`video/**/*`, `streams/eeg_*.csv`) used identically in Tasks 1/2/4.
```
