# Per-Session Consent Granularity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make modality consent filtering per-session — drop a modality's files only from sessions whose consent forbids it, and record the per-session decisions in the release manifest.

**Architecture:** Add a per-session resolver in `consent/modalities.py`; rewire `release/package.py` to compute present-modalities and apply file drops per session, set release-wide `absent_modalities` to the intersection (fully absent), and write a new `absent_modalities_by_session` manifest field on `DatasetRelease` (schema change → JSON-Schema re-export). The profile consent gate is unchanged.

**Tech Stack:** Python, pydantic (models + JSON schema), polars not involved, pytest.

## Global Constraints

- Profile consent gate (`check_consent`, block-on-conflict) UNCHANGED — only modality filtering becomes per-session.
- `resolve_absent` STAYS (imported by `tests/test_modalities.py`); add `resolve_absent_per_session` alongside it.
- Release-wide `absent_modalities` = sorted **intersection** of per-session absent lists (modalities absent from every session). Homogeneous all-forbid release → intersection == old union → existing tests unchanged.
- `absent_modalities_by_session: dict[str, list[str]]` added to `DatasetRelease` → re-export `docs/schemas/` and update `docs/DATA_CONTRACT.md`.
- Reproducibility hash logic (`_manifest_sha`, hashes `data/` only) UNCHANGED. `dump_json` is `sort_keys=True` so the manifest file stays deterministic.
- No new dependency, no new module. `consent/`, `release/`, `schemas/` are already in the mypy gate.
- Modality rule per session: a modality is *absent* if `not getattr(consent, MODALITY_FLAG[m])` OR it is not present in that session; it contributes *drop globs* only when forbidden AND present. `MODALITIES = ("eeg", "video")`; `MODALITY_FLAG = {"video":"distribute_raw_video","eeg":"distribute_raw_eeg"}`; `MODALITY_GLOBS = {"video":("video/**/*",),"eeg":("streams/eeg_*.csv",)}`.
- Verified: `commercial_dataset` profile gate does NOT require video/eeg distribution, so sessions with `distribute_raw_video` True or False both package under it.

---

### Task 1: `absent_modalities_by_session` manifest field + schema re-export

**Files:**
- Modify: `src/htdp/schemas/models.py` (`DatasetRelease`)
- Modify: `docs/schemas/DatasetRelease.schema.json` (re-export, generated)
- Modify: `docs/DATA_CONTRACT.md` (document the field)
- Create: `tests/test_release_manifest_schema.py`

**Interfaces:**
- Produces: `DatasetRelease.absent_modalities_by_session: dict[str, list[str]]` (default `{}`), placed before `manifest_sha256`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_release_manifest_schema.py`:

```python
import json
from pathlib import Path

from htdp.schemas.models import DatasetRelease


def test_model_has_per_session_field():
    assert "absent_modalities_by_session" in DatasetRelease.model_fields


def test_exported_schema_includes_field():
    schema = json.loads(
        Path("docs/schemas/DatasetRelease.schema.json").read_text(encoding="utf-8")
    )
    assert "absent_modalities_by_session" in schema["properties"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_release_manifest_schema.py -v`
Expected: FAIL — both assertions false (field not on the model, not in the exported schema).

- [ ] **Step 3: Add the field to `DatasetRelease`**

In `src/htdp/schemas/models.py`, in `class DatasetRelease(_Base)`, add the field between `absent_modalities` and `manifest_sha256`:

```python
    absent_modalities_by_session: dict[str, list[str]] = Field(default_factory=dict)
```

- [ ] **Step 4: Re-export the JSON schemas**

Run: `uv run python -c "from pathlib import Path; from htdp.schemas.export import export_json_schemas; export_json_schemas(Path('docs/schemas'))"`
Then confirm the field landed: `grep -n absent_modalities_by_session docs/schemas/DatasetRelease.schema.json`
Expected: a match (the property is now in the exported schema).

- [ ] **Step 5: Document the field in the data contract**

In `docs/DATA_CONTRACT.md`, find the `DatasetRelease` / release-manifest description and add a line describing `absent_modalities_by_session`: a map from `session_id` to the list of modalities absent from that session (forbidden by consent or not present), complementing the release-wide `absent_modalities` (modalities absent from every session). Match the surrounding wording style.

- [ ] **Step 6: Run to verify tests pass + gate**

Run: `uv run pytest tests/test_release_manifest_schema.py -v && uv run ruff format --check . && uv run ruff check . && uv run mypy src/htdp/schemas`
Expected: PASS, no findings.

- [ ] **Step 7: Commit**

```bash
git add src/htdp/schemas/models.py docs/schemas/DatasetRelease.schema.json docs/DATA_CONTRACT.md tests/test_release_manifest_schema.py
git commit -m "feat(schema): add absent_modalities_by_session to DatasetRelease"
```

---

### Task 2: Per-session resolver + package rewire

**Files:**
- Modify: `src/htdp/consent/modalities.py` (add `resolve_absent_per_session`)
- Modify: `src/htdp/release/package.py` (`_present_by_session`, per-session apply, intersection, manifest field)
- Create: `tests/test_per_session_consent.py`

**Interfaces:**
- Consumes: `MODALITIES`, `MODALITY_FLAG`, `MODALITY_GLOBS` (modalities.py); `DatasetRelease.absent_modalities_by_session` (Task 1).
- Produces:
  - `resolve_absent_per_session(consents: dict[str, Consent], present: dict[str, set[str]]) -> tuple[dict[str, list[str]], dict[str, list[str]]]` — `(absent_by_session, drop_globs_by_session)`, sorted lists.
  - `_present_by_session(session_ids: list[str], raw_root: Path) -> dict[str, set[str]]`.

- [ ] **Step 1: Write the failing mixed-consent test**

Create `tests/test_per_session_consent.py`:

```python
import json
from pathlib import Path

from htdp.release.package import package_release
from htdp.schemas.enums import ReleaseProfile
from htdp.synth.generate import generate_session


def test_per_session_video_consent(tmp_path: Path):
    generate_session(tmp_path / "raw", seed=1)
    generate_session(tmp_path / "raw", seed=2)
    raw = tmp_path / "raw"
    for sid, allow in [("synth-0001", True), ("synth-0002", False)]:
        (raw / sid / "video").mkdir(exist_ok=True)
        (raw / sid / "video" / "clip.mp4").write_bytes(b"\x00\x01")
        cpath = raw / sid / "consent.json"
        c = json.loads(cpath.read_text(encoding="utf-8"))
        c["distribute_raw_video"] = allow
        cpath.write_text(json.dumps(c), encoding="utf-8")

    out = package_release(
        ["synth-0001", "synth-0002"],
        "rel-mixed",
        ReleaseProfile.COMMERCIAL_DATASET,
        raw,
        tmp_path / "releases",
    )

    assert (out / "data/synth-0001/video/clip.mp4").exists()  # A allowed → kept
    assert not (out / "data/synth-0002/video/clip.mp4").exists()  # B forbidden → dropped
    m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert m["absent_modalities_by_session"] == {
        "synth-0001": ["eeg"],
        "synth-0002": ["eeg", "video"],
    }
    assert m["absent_modalities"] == ["eeg"]  # video kept by A → not fully absent
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_per_session_consent.py -v`
Expected: FAIL — currently video is dropped from BOTH sessions (release-wide union), so `data/synth-0001/video/clip.mp4` is gone (first assertion fails); and the manifest has no `absent_modalities_by_session`.

- [ ] **Step 3: Add `resolve_absent_per_session`**

In `src/htdp/consent/modalities.py`, add after `resolve_absent` (keep `resolve_absent` and the `MODALITY_FLAG`/`MODALITY_GLOBS`/`MODALITIES` constants):

```python
def resolve_absent_per_session(
    consents: dict[str, "Consent"],
    present: dict[str, set[str]],
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Per session, decide absent modalities and file globs to drop.

    A modality is absent for a session if its consent forbids it OR it is not present in that
    session. It contributes drop globs only when both forbidden AND present. Returns
    (absent_by_session, drop_globs_by_session), each keyed by session_id with sorted lists.
    """
    absent_by_session: dict[str, list[str]] = {}
    drop_globs_by_session: dict[str, list[str]] = {}
    for sid, consent in consents.items():
        absent: list[str] = []
        drop_globs: list[str] = []
        present_set = present.get(sid, set())
        for m in MODALITIES:
            flag = MODALITY_FLAG[m]
            forbidden = not getattr(consent, flag)
            is_present = m in present_set
            if forbidden or not is_present:
                absent.append(m)
            if forbidden and is_present:
                drop_globs.extend(MODALITY_GLOBS[m])
        absent_by_session[sid] = sorted(absent)
        drop_globs_by_session[sid] = sorted(drop_globs)
    return absent_by_session, drop_globs_by_session
```

(`Consent` is already imported at the top of `modalities.py` as `from htdp.schemas.models import Consent`; the string annotation avoids any ordering concern.)

- [ ] **Step 4: Rewire `package.py` to per-session**

In `src/htdp/release/package.py`:

(a) Change the import on line 9 to:

```python
from htdp.consent.modalities import MODALITY_GLOBS, resolve_absent_per_session
```

(b) Replace `_present_modalities` (lines 17-25) with:

```python
def _present_by_session(session_ids: list[str], raw_root: Path) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for sid in session_ids:
        session_dir = raw_root / sid
        present: set[str] = set()
        for modality, globs in MODALITY_GLOBS.items():
            if any(p.is_file() for pattern in globs for p in session_dir.glob(pattern)):
                present.add(modality)
        out[sid] = present
    return out
```

(c) Replace the consent-gate loop (the block that builds `consents: list[Consent]`) with a dict:

```python
    # Consent gate FIRST — fail before any output.
    consents: dict[str, Consent] = {}
    for sid in session_ids:
        consent = Consent.model_validate_json(
            (raw_root / sid / "consent.json").read_text(encoding="utf-8")
        )
        missing = check_consent(consent, profile)
        if missing:
            raise ConsentError(f"{sid}: profile {profile.value} requires {missing}")
        consents[sid] = consent
```

(d) Replace the present/resolve block (the two lines computing `present` and `absent, drop_globs`):

```python
    present = _present_by_session(session_ids, raw_root)
    absent_by_session, drop_globs_by_session = resolve_absent_per_session(consents, present)
```

(e) In the per-session copy loop, change the drop application to use that session's globs:

```python
        for sid in session_ids:
            dest = data_dir / sid
            shutil.copytree(raw_root / sid, dest)
            for pattern in drop_globs_by_session[sid]:
                for p in sorted(dest.glob(pattern)):
                    if p.is_file():
                        p.unlink()
```

(keep the rest of the loop body — `session = Session.model_validate_json(...)`, `participants.append(...)`, `sessions.append(...)` — unchanged).

(f) Before building the manifest, compute the release-wide intersection, and add the new field to `DatasetRelease(...)`:

```python
        manifest_sha = _manifest_sha(data_dir)
        absent = sorted(
            set.intersection(*(set(v) for v in absent_by_session.values()))
            if absent_by_session
            else set()
        )
        release = DatasetRelease(
            release_name=release_name,
            profile=profile.value,
            session_ids=session_ids,
            absent_modalities=absent,
            absent_modalities_by_session=absent_by_session,
            manifest_sha256=manifest_sha,
        )
```

- [ ] **Step 5: Run the new test + the existing consent tests**

Run: `uv run pytest tests/test_per_session_consent.py tests/test_video_consent_filtering.py tests/test_eeg_consent_filtering.py tests/test_consent.py tests/test_modalities.py tests/test_catalog.py -v`
Expected: ALL pass. The new test passes; existing consent tests pass (homogeneous releases give intersection == old union, so `absent_modalities` is unchanged, e.g. a single video-forbidding session still lists `video`); `test_modalities.py` still passes (`resolve_absent` kept); slice-17 release-catalog tests still pass (`absent_modalities` for an all-forbid release is still `["eeg","video"]`).

- [ ] **Step 6: Full gate**

Run: `uv run ruff format --check . && uv run ruff check . && uv run pytest && uv run mypy src/htdp/schemas src/htdp/consent src/htdp/release src/htdp/io src/htdp/ingest src/htdp/export src/htdp/catalog.py`
Expected: all pass. (If `mypy` reports only a numpy stub error on `export/rosbag.py`, run `uv sync --extra dev --extra rosbag` and re-run — env artifact, not this slice.)

- [ ] **Step 7: Commit**

```bash
git add src/htdp/consent/modalities.py src/htdp/release/package.py tests/test_per_session_consent.py
git commit -m "feat(consent): per-session modality filtering in package_release"
```

---

### Task 3: Docs

**Files:**
- Modify: `docs/ETHICS_AND_CONSENT.md` (per-session filtering behavior)
- Modify: `docs/ROADMAP.md` (consent-filtering line)

**Interfaces:** none (docs only).

- [ ] **Step 1: Locate the consent-filtering text**

Run: `grep -rn "consent\|absent_modalities\|modality" docs/ETHICS_AND_CONSENT.md docs/ROADMAP.md`
Expected: existing consent-filtering descriptions.

- [ ] **Step 2: Update the wording**

In `docs/ETHICS_AND_CONSENT.md`, describe that modality filtering is now per-session: a modality's raw files are removed only from the sessions whose consent forbids it; the manifest's `absent_modalities_by_session` records each session's absent modalities and the release-wide `absent_modalities` lists modalities absent from every session. In `docs/ROADMAP.md`, update the consent-filtering line from "in progress" to note per-session granularity landed. Keep each file's style.

- [ ] **Step 3: Commit**

```bash
git add docs/ETHICS_AND_CONSENT.md docs/ROADMAP.md
git commit -m "docs: document per-session consent modality filtering"
```

---

## Self-Review

**1. Spec coverage:**
- `resolve_absent_per_session` (per-session absent + drop globs) → Task 2 Step 3. ✅
- `_present_by_session` (per-session present) → Task 2 Step 4b. ✅
- Per-session file drops (not uniform) → Task 2 Step 4e; asserted by the mixed test (A kept, B dropped). ✅
- Release-wide `absent_modalities` = intersection → Task 2 Step 4f; asserted `["eeg"]`. ✅
- `absent_modalities_by_session` manifest field + schema re-export + DATA_CONTRACT → Task 1. ✅
- Profile gate unchanged → consent-gate loop only changes list→dict, `check_consent` untouched. ✅
- Reproducibility unchanged → `_manifest_sha` not touched. ✅
- `resolve_absent` kept (test_modalities importer) → constraint + Task 2 Step 3 keeps it. ✅
- Regression (homogeneous behavior) → Task 2 Step 5 runs existing consent + catalog tests. ✅
- Docs (ETHICS_AND_CONSENT, ROADMAP) → Task 3. ✅
- No new dep/module → none added. ✅

**2. Placeholder scan:** No TBD/TODO; full code in every code step; commands have expected output. ✅

**3. Type consistency:** `resolve_absent_per_session(consents: dict[str, Consent], present: dict[str, set[str]]) -> tuple[dict[str, list[str]], dict[str, list[str]]]` identical in modalities.py and package.py's call (`absent_by_session, drop_globs_by_session = ...`). `_present_by_session -> dict[str, set[str]]` feeds `present`. `DatasetRelease.absent_modalities_by_session: dict[str, list[str]]` (Task 1) matches the `absent_by_session` passed in Task 2. `consents` is `dict[str, Consent]` consistently after the gate-loop change. ✅
