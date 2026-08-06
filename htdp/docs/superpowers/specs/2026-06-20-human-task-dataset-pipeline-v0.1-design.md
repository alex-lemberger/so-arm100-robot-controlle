# Human-Task Dataset Pipeline — v0.1 (Synthetic Spine) — Design Spec

**Date:** 2026-06-20
**Status:** Draft approved for scaffold, pending implementation review
**Repo:** new greenfield repo `human-task-dataset-pipeline` (sibling to `neurofeedback-lang-app`)
**Source vision:** `docs/human_task_dataset_pipeline_mvp.md` (§1–27)
**Review folded in:** `2026-06-20-human-task-dataset-pipeline-v0.1-design-reviewed.md` (15 points, all accepted)

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

### v0.1 implementation boundary (review §1 — hard rule)
v0.1 must remain **offline, deterministic, synthetic, filesystem-only, and testable on
a normal development machine**. Any change introducing real hardware, servers,
dashboards, ROS, EEG, or video is **out of scope** and must be rejected unless this
spec is intentionally revised.

---

## 1. Goal & success criterion

A filesystem-only Python CLI that turns **one synthetic reach-grasp-place session**
into a **trusted, reproducible dataset release** — with defects the QC actually
catches and a consent gate that actually blocks. Proof of usability is a MuJoCo
mocap-body replay loading *from the release*.

**Done when:**
- `synth → validate → process → qc → package → replay` runs end to end.
- QC **flags** the injected defects (dropped samples + clock drift) as `warn` — they do
  not block packaging (defects are present by design; the win is detection).
- `package` refuses on a consent conflict and writes nothing (no partial output).
- Running the whole pipeline twice yields **identical release-manifest checksums**
  (reproducibility = the core trust claim), under the reproducibility definition in §11.

---

## 2. Architecture (layers, no servers)

```
synth ─▶ raw/ ─▶ validate ─▶ process ─▶ processed/ ─▶ qc ─▶ package ─▶ releases/ ─▶ replay
                    │                                    │        │
                 schemas                              defects   consent gate
                (pydantic)                            caught    (block-on-conflict,
                                                      (warn)     atomic staging)
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
    io/             # raw read/write, checksums, manifest, atomic staging
    processing/     # extract → Parquet, timestamp align
    qc/             # checks + HTML/JSON report (pass/warn/fail)
    consent/        # consent model, release profiles, export gate
    release/        # packaging, release manifest
    replay/         # MuJoCo mocap-body player (optional dependency)
    cli.py          # command surface
  protocols/        # reach-grasp-place.md (Task Library seed)
  tests/
  sample-data/      # tiny synthetic fixture (committed, small)
  docs/             # ARCHITECTURE, DATA_CONTRACT, ETHICS_AND_CONSENT, ROADMAP, schemas/
  AGENTS.md  README.md  pyproject.toml  uv.lock
```

---

## 4. Data contract (folder convention)

```
data/raw/<session_id>/
  session.json            # metadata
  consent.json            # consent record (the gate input)
  device_config.json      # stream/device declaration + coordinate frame
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

### 4.1 Coordinate frame (review §5 — declared from day one)
- units: **meters**; timestamp unit: **seconds**
- world frame: **right-handed**; x = participant right, y = forward, z = up
- rotations: **quaternion, order `w, x, y, z`**

Declared in `device_config.json`. Even synthetic data commits to this so MuJoCo replay
is unambiguous.

### 4.2 Motion CSV columns (review §6 — locked)
`timestamp_s, tracker_id, x_m, y_m, z_m, qw, qx, qy, qz, quality, defect_tag`
Per-stream files still carry `tracker_id` for consistency. `defect_tag` marks
synthetically injected defect samples (empty otherwise).

### 4.3 Event CSV columns (review §7 — locked)
`timestamp_s, event_id, label, phase, source, confidence, notes`
`label` ∈ {start, grasp, release, place, stop}. `source = synthetic` in v0.1.

---

## 5. Schemas

Pydantic models, with JSON Schema exported into `docs/schemas/` so external users can
validate releases independently.

- `Session` — participant_id, session_id, protocol_id, consent ref, device_config ref,
  start_time, file list, qc_status, processing_status, checksums.
- `Consent` — flags per vision §17: `commercial_use`, `distribute_raw_video`,
  `distribute_raw_eeg`, `derived_features_only`, `model_training`, `public_release`,
  `internal_only`, `third_party_access`, plus `delete_after` (date) and
  `consent_form_version`.
- `DeviceConfig` — declared streams, rates, units, coordinate frame (§4.1).
- `StreamRef` / `FileRef` — path, format, checksum, role.
- `EventMarker` — fields per §4.3.
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
signal. Defect parameters are seed-controlled, tagged via `defect_tag`, and documented
in the report.

### 6.1 Immutability semantics (review §2 — testable invariant)
- `synth` creates a new raw session folder; **refuses to overwrite** an existing one
  unless `--force`.
- `validate` detects any modification after `checksums.sha256` is written.
- `process` must **never** modify files under `data/raw/<session_id>/`.
- Checksums computed over canonical file bytes (§11) and stable manifest content.

---

## 7. QC checks (the heart of trust)

**Per-stream:** sample count; actual-vs-expected rate; **gaps / dropped samples**
(catches defect 1); monotonic timestamps; NaN check.

**Cross-stream:** pairwise offset / **drift estimate** (catches defect 2);
common-time coverage across streams.

**Events:** valid ordering (start < … < stop; grasp < release); all events within
session time bounds.

### 7.1 Severity (review §4)
- `pass` — acceptable.
- `warn` — detected, dataset can still be packaged. **Dropped samples and clock drift
  are `warn`** unless they exceed configured thresholds.
- `fail` — invalid/unsafe: missing mandatory streams, non-monotonic/invalid timestamps,
  checksum mismatch, malformed consent.

**Output:** `qc_report.json` (machine-readable, per-check status) + `qc_report.html`
(human-readable). Failing checks are loud and explicit.

---

## 8. Consent gate (block-on-conflict)

`package` reads `consent.json` and the requested **release profile**, then enforces
required permissions. On any missing/false required flag → **refuse, write nothing,
error explicitly**.

### 8.1 Release profiles (review §8)
- `internal_research`
- `public_sample`
- `commercial_dataset` — requires `commercial_use`, `model_training`, `third_party_access`.

Absent modalities (video/EEG) do **not** block v0.1 packaging, but their absence is
recorded in the release manifest.

### 8.2 Atomicity — no partial output (review §9)
`package` writes to a **staging directory** first. Only after all validations, consent
checks, manifest generation, and checksums pass does it atomically move staging into
`data/releases/<name>`. A failed `package` leaves **no** release directory. Tested.

Tested both directions: allow → release built; flip a required flag → refused, no output.
Filtering (strip-disallowed-modalities) is deferred to v0.2.

---

## 9. Replay (usability proof)

Standalone `mjpython` script reads the **packaged release's** motion Parquet, places
**mocap spheres** at the 6DoF tracker poses (right wrist, left wrist, torso, object),
plays them back in time, and flashes/logs on events. No robot, no IK. Smoke-tested
headless. Uses the `mujoco-python` skill. Fully decoupled from the old
`handwerk-robot-sim`. Proves the *release format round-trips into a sim*.

**MuJoCo is an optional dependency (review §14):** core tests run without it; the replay
test runs only when MuJoCo is installed; the CLI gives a clear error if replay deps are
missing.

---

## 10. CLI surface

```
htdp synth      --seed N --out data/raw/<id> [--force]   # generate synthetic session
htdp validate   data/raw/<id>                            # schema + structure + checksums
htdp process    data/raw/<id>                            # → processed/ Parquet (raw read-only)
htdp qc         data/processed/<id>                      # → qc report (json + html)
htdp package    <id...> --release <name> --profile <p>   # consent gate → releases/ (atomic)
htdp replay     data/releases/<name>                     # MuJoCo mocap playback (optional dep)
```

The CLI is the product surface for v0.1. No dashboard.

---

## 11. Reproducibility & canonical serialization (review §3)

**Definition (v0.1):** same code version + same dependency lockfile + same platform
class + same seed + same inputs → **identical release-manifest checksums**.

Canonical rules:
- Deterministic file ordering inside release packages.
- JSON: sorted keys, stable indentation, UTF-8.
- CSV: stable column order, fixed float precision, stable line endings, UTF-8.
- Parquet: write with controlled engine/version settings; assert reproducibility at the
  logical manifest/checksum level (not raw Parquet bytes, which vary).
- Generated timestamps: seed-derived or **excluded** from hashed content.
- Tool versions: recorded in the manifest but **excluded** from the reproducibility
  checksum (cross-machine stability).

This is the single most important implementation detail for the trust claim.

---

## 12. Tooling & quality gate (review §10, §11)

- **Dependency lock required** — `uv` + `uv.lock` (reproducibility-focused; not optional).
- Quality commands: `ruff check`, `ruff format --check`, `mypy` (start with `schemas`,
  `consent`, `release`, `io`), `pytest`.

---

## 13. Testing (TDD, pytest)

Deterministic synth via seed enables exact assertions.

- Schema validation rejects malformed sessions/consent/manifests.
- **QC detects each injected defect** (dropped samples, clock drift) — asserted as `warn`.
- QC `fail` cases: missing stream, bad timestamps, checksum mismatch, malformed consent.
- Immutability invariants (§6.1): no overwrite without `--force`; `process` never writes
  raw; post-write tampering detected by `validate`.
- Consent gate: allow → release built; deny → refused with **no** release directory (§8.2).
- **Reproducibility:** run pipeline twice → identical release-manifest checksums (§11).
- Replay smoke test (MuJoCo-gated): loads a release, steps the sim headless without error.

---

## 14. Implementation sequence (review §13 — build order)

1. Python package, CLI shell, tests, project tooling (`uv`, `ruff`, `mypy`, `pytest`).
2. Schemas + JSON Schema export.
3. Synthetic session generator (seeded, defect injection, immutability).
4. Checksums + raw validation.
5. Processing → Parquet (raw read-only).
6. QC JSON + HTML report (pass/warn/fail).
7. Consent release profiles + package gate.
8. Deterministic release packaging (atomic staging).
9. MuJoCo replay smoke test (optional dep).
10. Docs + `AGENTS.md`.

---

## 15. Harness rightsizing & AGENTS.md (review §12; companion task)

`AGENTS.md` must exist **immediately** (not deferred). It instructs the coding agent:
- do not add servers, real hardware, dashboards, ROS, EEG, or video in v0.1;
- do not store raw data in a database;
- do not bypass consent checks;
- do not modify raw data during processing;
- keep fixtures tiny and deterministic;
- update schemas and docs together;
- preserve manifests + checksums; make errors explicit.

Plus project `settings.json` with Python-toolchain permissions (pytest, ruff, mypy, uv,
the CLI). Applicable skills: superpowers planning/TDD, mujoco-python. Ignore:
angular-developer, wordpress-divi, figma. Memory auto-scopes by project path → fresh
namespace, no bleed from this project.

---

## 16. Out of scope for v0.1 (named, not forgotten → v0.2+)

Postgres / MinIO / FastAPI / Docker Compose; Angular ops dashboard; real hardware
(VIVE / LSL / XDF ingest); video + EEG data capture; ROS 2 / rosbag2 export;
EEG-BIDS / Motion-BIDS; IK / robot-arm replay; agent-orchestration layer (Hermes /
OpenClaw); multi-session queryable catalog; consent *filtering* (vs blocking).

---

## 17. Risks & judgment calls

- **Raw-as-CSV (not XDF)** for v0.1 — §4. Mitigated by a planned v0.2 `ingest` step that
  normalizes XDF into the same raw representation.
- **Reproducibility hinges on deterministic hashing/serialization** — §11. Most important
  implementation detail for the core trust claim.
- **Sync QC is where the project lives or dies** — even synthetic, drift/gap detection
  must be rigorous; it is the seed of the real moat.
- **Biggest project risk is scope creep, not missing features** (reviewer's verdict).
  Guiding principle: *build the smallest deterministic dataset factory that proves trust.*
