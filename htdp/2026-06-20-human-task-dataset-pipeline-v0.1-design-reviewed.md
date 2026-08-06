# Human-Task Dataset Pipeline — v0.1 (Synthetic Spine) — Design Spec

**Date:** 2026-06-20
**Status:** Draft approved for scaffold, pending implementation review
**Repo:** new greenfield repo `human-task-dataset-pipeline` (sibling to `neurofeedback-lang-app`)
**Source vision:** `docs/human_task_dataset_pipeline_mvp.md` (§1–27)

---

## 0. Context & framing

This is a **greenfield** project, not an extension of `neurofeedback-lang-app`. It is an
*evolution of the idea* (consent-based human-task data for robotics), but a fresh
codebase in a new language and architecture. The existing Angular app and MuJoCo
robot sim become **clients/consumers** of this pipeline later — not part of it.

**Product unit = a dataset release**, not an app. The first milestone proves the
*factory* works before any hardware exists.

### Decisions locked during brainstorming
1. **Greenfield** new repo, Python pipeline spine. Old repo untouched.
2. **v0.1 = synthetic pipeline spine** — zero hardware. Build and trust the factory
   before a single VIVE tracker arrives.
3. **Filesystem-only** — no Postgres / MinIO / FastAPI / Docker in v0.1. Server stack
   deferred to v0.2 when there is a concrete reason (catalog, dashboard, remote access).
4. **Modalities:** motion (6DoF, multi-tracker) + event markers + consent + metadata.
   Video and EEG are **empty schema slots** (contract present, no data).
5. **Defects injected** into the synthetic session so QC has real signal to catch.
6. **MuJoCo replay = minimal mocap-body playback** (spheres at tracker poses).
   IK / robot-arm replay deferred to v0.2.
7. **Consent gate = block-on-conflict** — package refuses and writes nothing on a
   consent violation. Filtering deferred to v0.2.
8. **Sequence:** design → scaffold (this spec first, then repo + rightsized harness).

---

## 1. Goal & success criterion

A filesystem-only Python CLI that turns **one synthetic reach-grasp-place session**
into a **trusted, reproducible dataset release** — with defects the QC actually
catches and a consent gate that actually blocks. Proof of usability is a MuJoCo
mocap-body replay loading *from the release*.

**Done when:**
- `synth → validate → process → qc → package → replay` runs end to end.
- QC flags the injected defects (dropped samples + clock drift).
- `package` refuses on a consent conflict and writes nothing.
- Running the whole pipeline twice yields **identical release checksums**
  (reproducibility = the core trust claim).

---

## 2. Architecture (layers, no servers)

```
synth ─▶ raw/ ─▶ validate ─▶ process ─▶ processed/ ─▶ qc ─▶ package ─▶ releases/ ─▶ replay
                    │                                    │        │
                 schemas                              defects   consent gate
                (pydantic)                            caught   (block-on-conflict)
```

Three data tiers on disk (vision §14):
- **raw/** — immutable once written, checksummed.
- **processed/** — regenerable (Parquet + QC).
- **releases/** — versioned, packaged. The product unit.

Pure CLI + library. Python package + `typer` (or `click`) CLI. No server processes.

---

## 3. Repo layout

```
human-task-dataset-pipeline/
  src/htdp/
    schemas/        # pydantic models + exported JSON Schema
    synth/          # synthetic session generator (seeded, defect injection)
    io/             # raw read/write, checksums, manifest
    processing/     # extract → Parquet, timestamp align
    qc/             # checks + HTML/JSON report
    consent/        # consent model + export gate
    release/        # packaging, release manifest
    replay/         # MuJoCo mocap-body player
    cli.py          # command surface
  protocols/        # reach-grasp-place.md (Task Library seed)
  tests/
  sample-data/      # tiny synthetic fixture (committed, small)
  docs/             # ARCHITECTURE, DATA_CONTRACT, ETHICS_AND_CONSENT, ROADMAP
  AGENTS.md  README.md  pyproject.toml
```

---

## 4. Data contract (folder convention)

```
data/raw/<session_id>/
  session.json            # metadata
  consent.json            # consent record (the gate input)
  device_config.json      # stream/device declaration
  streams/
    motion_right_wrist.csv  motion_left_wrist.csv
    motion_torso.csv        motion_object.csv
    events.csv
  video/                  # empty slot in v0.1 (contract present, no MP4)
  notes.md
  checksums.sha256        # over all raw bytes → immutability proof

data/processed/<session_id>/
  motion.parquet  events.parquet
  qc_report.json  qc_report.html
  manifest.json

data/releases/human-reach-grasp-place-v0.1/
  README.md LICENSE protocol.md
  participants.csv sessions.csv
  manifest.json checksums.sha256
  data/<session_id>/...
```

**Deliberate v0.1 simplification:** raw motion stored as **CSV** (timestamped rows,
human-inspectable), *not* XDF. Real LSL capture produces XDF later; a v0.2 `ingest`
step converts XDF → this same raw representation. Keeps the contract coherent without
XDF-writing pain now. This is the one place the design intentionally bends vision §14.1.

---

## 5. Schemas

Pydantic models, with JSON Schema exported into `docs/` so external users can validate
releases independently.

- `Session` — participant_id, session_id, protocol_id, consent ref, device_config ref,
  start_time, file list, qc_status, processing_status, checksums.
- `Consent` — flags per vision §17: `commercial_use`, `distribute_raw_video`,
  `distribute_raw_eeg`, `derived_features_only`, `model_training`, `public_release`,
  `internal_only`, `third_party_access`, plus `delete_after` (date) and
  `consent_form_version`.
- `DeviceConfig` — declared streams, rates, units, coordinate frame.
- `StreamRef` / `FileRef` — path, format, checksum, role.
- `EventMarker` — timestamp, label (start/grasp/release/place/stop).
- `Manifest` — processed-session manifest (inputs, outputs, checksums, tool versions).
- `Participant`, `TaskProtocol`, `DatasetRelease`.

Schemas ARE the contract. Changing a schema requires updating `DATA_CONTRACT.md` and tests.

---

## 6. Synthetic generator (seeded + defects)

Deterministic from a seed. Generates a plausible reach-grasp-place session:
- wrist trajectories moving toward the object, returning, placing;
- `start / grasp / release / place / stop` events at phase boundaries;
- ~100 Hz motion sampling.

**Injects two defects deliberately:**
1. a **dropped-sample gap** in one motion stream;
2. a **clock-drift offset** between two streams.

A QC report that always says "perfect" proves nothing — these defects give QC real
signal. Defect parameters are seed-controlled and documented in the report.

---

## 7. QC checks (the heart of trust)

**Per-stream:** sample count; actual-vs-expected rate; **gaps / dropped samples**
(catches defect 1); monotonic timestamps; NaN check.

**Cross-stream:** pairwise offset / **drift estimate** (catches defect 2);
common-time coverage across streams.

**Events:** valid ordering (start < … < stop; grasp < release); all events within
session time bounds.

**Output:** `qc_report.json` (machine-readable, pass/warn/fail per check) +
`qc_report.html` (human-readable). Failing checks are loud and explicit, not buried.

---

## 8. Consent gate (block-on-conflict)

`package` reads `consent.json`. If a required permission for the requested release type
is missing or false, it **refuses, packages nothing, and errors explicitly**.

Tested both directions:
- synthetic session's consent allows packaging → release built;
- flip one required flag → command refuses, no partial output.

Filtering (strip-disallowed-modalities) is explicitly deferred to v0.2.

---

## 9. Replay (usability proof)

Standalone `mjpython` script reads the **packaged release's** motion Parquet, places
**mocap spheres** at the 6DoF tracker poses (right wrist, left wrist, torso, object),
plays them back in time, and flashes/logs on events. No robot, no IK. Smoke-tested
headless. Uses the `mujoco-python` skill. Fully decoupled from the old
`handwerk-robot-sim`. Proves the *release format round-trips into a sim* — i.e. the
data is usable by a downstream robotics consumer.

---

## 10. CLI surface

```
htdp synth      --seed N --out data/raw/<id>     # generate synthetic session
htdp validate   data/raw/<id>                    # schema + structure + checksums
htdp process    data/raw/<id>                    # → processed/ Parquet
htdp qc         data/processed/<id>              # → qc report (json + html)
htdp package    <id...> --release <name>         # consent gate → releases/
htdp replay     data/releases/<name>             # MuJoCo mocap playback
```

The CLI is the product surface for v0.1. No dashboard.

---

## 11. Testing (TDD, pytest)

Deterministic synth via seed enables exact assertions.

- Schema validation rejects malformed sessions/consent/manifests.
- **QC detects each injected defect** (dropped samples, clock drift) — asserted explicitly.
- Consent gate: allow → release built; deny → refused with no output.
- Checksum / immutability integrity (tampering detected).
- **Reproducibility:** run pipeline twice → identical release checksums. Generation
  timestamps are fixed (seed-derived) or excluded from hashed content so the hash is
  deterministic.
- Replay smoke test: loads a release, steps the sim headless without error.

---

## 12. Out of scope for v0.1 (named, not forgotten → v0.2+)

Postgres / MinIO / FastAPI / Docker Compose; Angular ops dashboard; real hardware
(VIVE / LSL / XDF ingest); video + EEG data capture; ROS 2 / rosbag2 export;
EEG-BIDS / Motion-BIDS; IK / robot-arm replay; agent-orchestration layer (Hermes /
OpenClaw); multi-session queryable catalog; consent *filtering* (vs blocking).

---

## 13. Risks & judgment calls

- **Raw-as-CSV (not XDF)** for v0.1 — see §4. Mitigated by a planned v0.2 `ingest`
  step that normalizes XDF into the same raw representation.
- **Reproducibility hinges on deterministic hashing** — generation timestamps must be
  fixed or excluded from hashed bytes (§11). This is the single most important
  implementation detail for the core trust claim.
- **Sync QC is where the project lives or dies** (per assessment). Even in synthetic
  form, the drift/gap detection must be rigorous; it is the seed of the real moat.

---

## 14. Harness rightsizing (companion task, post-scaffold)

The new repo gets its own rightsized agent harness (separate from this Angular repo's):
- `AGENTS.md` from vision §22 — data-platform-first; never store raw signals in a DB;
  raw data immutable; never bypass consent checks; Python-first; local-first; small
  fixtures; explicit errors; preserve manifests + checksums.
- project `settings.json` — permissions for the Python toolchain (pytest, ruff, the CLI).
- skills note — applicable: superpowers planning/TDD, mujoco-python. Ignore:
  angular-developer, wordpress-divi, figma.
- Memory auto-scopes by project path → fresh namespace, no bleed from this project.


---

# Review — Human-Task Dataset Pipeline v0.1 Design Spec

Reviewer notes date: 2026-06-20

## Executive assessment

This is a strong v0.1 spec. The most important decision is correct: v0.1 should be a synthetic, filesystem-only pipeline spine, not a premature hardware/backend/dashboard project.

The spec correctly protects the main product thesis: the product unit is a dataset release, not an app. It also correctly moves Postgres, MinIO, FastAPI, Angular, LSL/XDF, EEG, video, ROS, and BIDS into later milestones. That keeps v0.1 small enough to implement and test.

The strongest parts are the synthetic-first approach, the explicit defect injection, the consent gate, the reproducibility requirement, and the MuJoCo replay from the packaged release. These are exactly the kinds of constraints that turn the project from a loose prototype into a trustworthy dataset factory.

## Recommended changes before implementation

### 1. Add a strict v0.1 implementation boundary

The coding agent should not expand v0.1 into real hardware, servers, dashboards, ROS, EEG, or video. Any pull request that introduces those should be rejected unless the spec is intentionally changed.

Suggested rule: v0.1 must remain offline, deterministic, synthetic, filesystem-only, and testable on a normal development machine.

### 2. Clarify what “raw immutable” means for synthetic CSV

The spec says raw data is immutable once written. For v0.1, this should mean:

- `htdp synth` may create a new raw session folder.
- `htdp synth` must refuse to overwrite an existing raw session unless an explicit `--force` flag is used.
- `htdp validate` must detect any modification after checksums are generated.
- `htdp process` must never modify files under `data/raw/<session_id>/`.
- checksums should be calculated over canonical file bytes and stable manifest content.

This should become a testable invariant.

### 3. Reproducibility needs canonical packaging rules

The spec correctly identifies reproducibility as critical, but the implementation needs precise rules.

Recommended rules:

- File ordering inside release packages must be deterministic.
- JSON should be serialized with sorted keys and stable indentation.
- CSV should use stable column order, stable float precision, stable line endings, and UTF-8.
- Parquet can be tricky because metadata can vary. Either test reproducibility at the logical manifest/checksum level or write Parquet with controlled engine/version settings.
- Generated timestamps should be seed-derived or excluded from release checksums.
- Tool versions should be recorded, but if they are included in the checksum, reproducibility may break across machines. Decide explicitly whether reproducibility means same machine/same environment or cross-machine.

I recommend defining v0.1 reproducibility as: same code version, same dependency lockfile, same platform class, same seed, same inputs → identical release manifest checksums.

### 4. Split QC into “warnings” and “blocking failures”

QC should not only report defects; it should classify severity.

Recommended statuses:

- pass: acceptable
- warn: detected but dataset can still be packaged
- fail: invalid session or unsafe release

Dropped samples and clock drift should probably be `warn` in synthetic v0.1 unless they exceed configured thresholds. Missing mandatory streams, invalid timestamps, checksum mismatch, or malformed consent should be `fail`.

This matters because the synthetic dataset intentionally contains defects. The pipeline should prove that it can detect them, not necessarily block packaging because of them.

### 5. Define a small synthetic coordinate frame

The synthetic motion should declare a coordinate frame from day one.

Recommended v0.1 coordinate frame:

- units: meters
- world frame: right-handed
- x: participant right
- y: forward from participant
- z: up
- timestamp unit: seconds
- rotations: quaternion, order `w, x, y, z`

Even if the data is synthetic, this prevents ambiguity when MuJoCo replay is added.

### 6. Define motion CSV columns explicitly

The spec says 6DoF motion CSV, but the exact columns should be locked.

Recommended columns:

- `timestamp_s`
- `tracker_id`
- `x_m`
- `y_m`
- `z_m`
- `qw`
- `qx`
- `qy`
- `qz`
- `quality`
- `defect_tag`

For separate stream files like `motion_right_wrist.csv`, `tracker_id` can still be present for consistency.

### 7. Define event CSV columns explicitly

Recommended event columns:

- `timestamp_s`
- `event_id`
- `label`
- `phase`
- `source`
- `confidence`
- `notes`

For v0.1, `source` can be `synthetic`.

### 8. Consent gate should define release profiles

The spec says package checks required permissions for the requested release type. This is good, but release types should be explicit.

Recommended v0.1 release profile:

- `internal_research`
- `public_sample`
- `commercial_dataset`

Each profile maps to required consent flags.

For example, `commercial_dataset` requires `commercial_use`, `model_training`, and `third_party_access`. If video and EEG are absent, their flags should not block v0.1 packaging, but their absence should be recorded.

### 9. Add a “no partial output” atomicity rule

The consent gate says package writes nothing on conflict. This should be implemented with a staging directory.

Recommended rule:

`htdp package` writes to a temporary staging directory first. Only after all validations, consent checks, manifest generation, and checksums pass should it atomically rename or move the staging directory into `data/releases/<release_name>`.

Tests should assert that a failed package command leaves no release directory.

### 10. Add dependency locking

The spec mentions `pyproject.toml` but should also require a lockfile.

Suggested tools: `uv` with `uv.lock`, or Poetry with `poetry.lock`.

For a reproducibility-focused project, dependency locking is not optional.

### 11. Add `ruff`, `mypy`, and `pytest` as the default quality gate

Recommended v0.1 quality commands:

- `ruff check`
- `ruff format --check`
- `mypy` or `pyright`
- `pytest`

If `mypy` feels too heavy, use it only for `schemas`, `consent`, `release`, and `io` first.

### 12. Add a small AGENTS.md instruction block

The spec already references a future harness. For implementation, AGENTS.md should exist immediately. It should tell the coding agent:

- do not add servers in v0.1
- do not add real hardware dependencies in v0.1
- do not store raw data in a database
- do not bypass consent checks
- do not modify raw data during processing
- keep fixtures tiny and deterministic
- update schemas and docs together

### 13. Add an implementation sequence

The spec is excellent as design, but the coding agent needs a build order.

Recommended sequence:

1. Create Python package, CLI shell, tests, and project tooling.
2. Implement schemas and JSON Schema export.
3. Implement synthetic session generator.
4. Implement checksums and raw validation.
5. Implement processing to Parquet.
6. Implement QC JSON and HTML report.
7. Implement consent release profiles and package gate.
8. Implement deterministic release packaging.
9. Implement MuJoCo replay smoke test.
10. Add docs and AGENTS.md.

### 14. Keep MuJoCo optional in CI

MuJoCo replay is valuable, but it may complicate local or CI setup. The replay test should be marked as optional or smoke-only.

Recommended approach:

- core tests run without MuJoCo
- replay test runs when MuJoCo is installed
- CLI should give a clear error if replay dependencies are missing

### 15. Rename “Approved” status

The spec status says “Approved (design), pending implementation plan.” Since this is still being reviewed, I would change this to:

Status: Draft approved for scaffold, pending implementation review.

This avoids over-committing before the first code milestone.

## Final judgment

This spec is good enough to start a greenfield repo. I would not broaden it. The biggest risk is not missing features; the biggest risk is scope creep.

The best implementation principle is:

Build the smallest deterministic dataset factory that proves trust.

If v0.1 can generate a synthetic session, detect defects, enforce consent, package a reproducible release, and replay it in MuJoCo, it will be a strong foundation.
