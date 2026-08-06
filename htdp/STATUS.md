# STATUS — session handoff

> Read this first in a fresh session, then `AGENTS.md` (rules) and `docs/ROADMAP.md`
> (what's next). Last updated: **2026-06-20**.

## What this repo is

Consent-based **human-task dataset pipeline for robotics**. The product unit is a
**dataset release**, not an app. Pipeline-first, filesystem-first. The moat is a
reproducible capture protocol + sync QC + consent governance + a Task Library — not the
code.

Spun off **2026-06-20** from the neurofeedback / Handwerk capture project (separate
Angular repo). That old app and the MuJoCo H1 robot sim are future **consumers** of this
pipeline's releases, not part of it.

- **Package / CLI:** `htdp`
- **Remote:** https://github.com/alex-lemberger/human-task-dataset-pipeline (branch `master`)
- **Stack:** `uv` + `uv.lock`, pydantic schemas, polars/parquet, jinja QC report,
  ruff / mypy-strict / pytest, optional `mujoco` extra for replay.

## Current state — v0.1 synthetic spine, COMPLETE

Zero hardware. Full CLI loop works:

```
synth → validate → process → qc → package → replay
```

Built via subagent-driven TDD (10 tasks). **30 tests pass / 1 MuJoCo-gated skip.** Opus
final review = ready-to-merge. Pushed; tree clean.

Three data tiers on disk: `raw/` (immutable, checksummed) · `processed/` (regenerable
Parquet + QC report) · `releases/` (versioned, packaged — the product unit).

### Four trust guarantees (all verified)
1. **Raw is immutable** — checksums enforced, processing never writes to `raw/`.
2. **Consent gate blocks atomically** — `package` blocks on conflict and writes *nothing*
   (no partial output).
3. **Reproducible** — same code + `uv.lock` + platform + seed + inputs → identical
   `manifest_sha256`. Hash covers `data/` only; excludes timestamps + tool_versions.
4. **QC has real signal** — synth injects defects on purpose (dropped-sample gap +
   cross-stream clock drift); QC flags them `warn`, overall `warn`.

## Key v0.1 design calls (don't re-litigate without reason)
- Raw stored as **CSV, not XDF** (v0.2 `ingest` will convert XDF → same shape).
- Consent = **block-on-conflict**; modality *filtering* deferred to v0.2.
- Replay = **mocap spheres, no IK**; arm kinematics is v0.2.
- Defects injected deliberately so QC isn't testing against clean data.

## Known wording nit
Spec §9 says replay reads Parquet, but the release ships raw CSV. Reconcile in v0.2.

## Where things live
- `AGENTS.md` — hard rules + scope boundary + quality gate. **Obey it.**
- `docs/ROADMAP.md` — v0.1 done list, v0.2 plan, explicit out-of-scope.
- `docs/ARCHITECTURE.md`, `docs/DATA_CONTRACT.md`, `docs/ETHICS_AND_CONSENT.md`
- `docs/schemas/*.json` — exported JSON Schemas (regen from pydantic, see AGENTS.md).
- `docs/superpowers/specs/` — v0.1 reviewed design + **v0.2 XDF ingest adapter spec**
  (`2026-06-20-xdf-ingest-adapter-design.md`, written this session — first v0.2 piece).
- `docs/superpowers/plans/` — v0.1 implementation plan.
- `protocols/reach-grasp-place.md` — first capture protocol.
- `HW.rtf` — hardware shopping notes.

## Quality gate (run before every commit)
```
uv run ruff format --check . && uv run ruff check . && uv run pytest
uv run mypy src/htdp/schemas src/htdp/consent src/htdp/release src/htdp/io src/htdp/ingest src/htdp/export
```

## Next session — start here
v0.2 = real hardware ingest, **one modality at a time**. Each modality adds an `ingest`
adapter that normalizes to the existing raw representation; downstream
(validate → process → qc → package) must **not** change.

First concrete v0.2 task: implement the **XDF ingest adapter** per
`docs/superpowers/specs/2026-06-20-xdf-ingest-adapter-design.md` (XDF → raw CSV shape).

Hardware plan: VIVE Ultimate trackers + webcam + ESP32 markers, < 3000 EUR,
motion-first, EEG-later.
