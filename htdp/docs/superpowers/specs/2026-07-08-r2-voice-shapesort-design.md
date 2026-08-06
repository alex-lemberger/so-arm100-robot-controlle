# R2 — Voice-Commanded Shape-Sort Mile (SmolVLA + classical insertion)

**Status:** design approved, not yet started. Sequenced **after R1** (real-arm cube pick-place,
hardware in transit) closes.

## Goal

Say "put the green triangle in the box" → SO-ARM101 finds that piece among distractors on the
table (Montessori shape-sorter toy: coin-stacker discs, triangle, cube, cylinder, trapezoid,
etc.), picks it up, rotates it to match its color-coded cutout in the toy's lid, and inserts it.
Headline claim: the robot understands spoken color + shape, not just "grasp the one object in
frame."

## Relationship to R1

R1 ships first, unchanged (single cube, scripted target zone, 50 teleop demos, upstream ACT,
n≥20 Wilson CI). This mile reuses R1's rig, teleop pipeline, and eval discipline — it does not
replace or block R1. Rationale: R1 alone already carries several unknowns (dual-arm calibration,
macOS serial, demo quality). Stacking multi-object perception + voice + insertion on top of an
unproven rig would make failures undiagnosable. R2 starts only once R1c (trained policy + n≥20
real eval) is done.

## Architecture

Three modules, each independently testable:

1. **ASR** — Whisper (local, small/base model) converts push-to-talk mic audio → text. No
   wake-word/VAD for v1 — keypress trigger is simplest and sufficient for a demo.
2. **SmolVLA (fine-tuned)** — HuggingFace's 450M-param VLA (ships in upstream `lerobot`). Takes
   camera frames + proprio + the raw text string directly as its `--task` prompt and drives the
   pick phase (find the matching piece among distractors, grasp, lift). Chosen over hand-rolled
   HSV/contour detection because its pretrained VLM backbone already fuses vision+language —
   more robust to lighting/pose variation than threshold-based color/shape classifiers, and is
   lerobot's own flagship use case (`--task="Put lego brick into the transparent box"` is a doc
   example). Fine-tuned on our own teleop demos of this task (see Data below).
3. **Insertion (classical, not learned)** — after SmolVLA lifts the piece, a scripted
   closed-loop controller: detect the target hole's colored outline ring, estimate the held
   piece's rotation from its contour, rotate the wrist, visual-servo-correct alignment every
   frame (not open-loop), then lower and insert. Peg-in-hole needs tighter tolerances than a
   learned policy reliably hits from a demo-sized dataset; classical geometric alignment is more
   robust and debuggable here. This is the one part of the pipeline that stays classical
   regardless of how well SmolVLA performs.

A small deterministic **text → target_hole_id lookup** (color+shape phrase → known hole on the
toy) runs alongside SmolVLA — it is NOT removed by the VLA swap, because the insertion module
needs an explicit target hole identity independent of whatever SmolVLA grasped. This same lookup
also gates the **classical fallback**: if SmolVLA fails to produce a successful pick after N
retries (gripper never closes on target, or no height gain), fall back to an HSV/contour
detector that locates the piece matching `target_hole_id`'s known color+shape and runs a
scripted servo-grasp. The classical detector is kept in the design purely as this fallback/
comparison path, not as the primary grounding mechanism.

## Control loop

```
mic (push-to-talk)
  → Whisper → text
  → lookup: text → target_hole_id
  → SmolVLA.rollout(task=text, cams, proprio)     [pick phase, step-budget timeout]
       success check: gripper closed + height-gain heuristic
       fail after N retries → classical fallback (HSV/contour detect target_hole_id's
       known color+shape → scripted servo-grasp)
  → handoff: target_hole_id + gripper pose → insertion module
  → insertion: detect hole outline ring → estimate held-piece rotation from contour →
       rotate wrist → closed-loop visual servo (recheck each frame) → lower + insert
  → log outcome per phase: ASR-miss / wrong-pick / grasp-fail / insert-fail / success
```

## Data / fine-tuning

lerobot docs recommend ~10 demo episodes per task variation for SmolVLA generalization. Scope
the toy's vocabulary to its actual distinguishable color+shape holes (expect ~4: circle, square,
triangle, rectangle, each color-keyed) → ~40-60 teleop demos total, in range of R1's already-
planned demo count. Each demo recorded with its own free-text instruction (matches SmolVLA's
per-episode task-string format). Fine-tuning needs a single decent GPU (docs use A100 as
reference) — resource dependency to solve at execution time (rented cloud GPU or reduced step
count), not a blocker to this design.

## Error handling / safety

- ASR text not in known vocab → no-op, log "not understood," wait for next command. Never guess
  a target.
- Named piece not on table, or both SmolVLA and classical fallback exhaust retries → arm returns
  home, reports failure. No blind action taken.
- Low-confidence orientation estimate before insertion (occluded contour) → re-grasp/re-orient,
  do not force the insert.
- **Safety guard:** stall/current-limit + timeout on the insertion push. A misaligned peg-in-hole
  attempt grinding into real wood + servos can damage hardware — abort on stall, never
  retry-into-force.
- Single command at a time, no queueing — avoids interrupt/race handling for v1.

## Evaluation

Matches this project's existing discipline (R1c/E1/C1/OOD1 pattern):

- n≥20 real trials, random target + full distractor scene each trial, Wilson 95% CI on success.
- Success criterion fixed **before** the first trial: piece fully seated flush in the matching
  hole (not merely released above it) — no post-hoc rubric bending (R1 lesson repeats).
- Failure taxonomy logged per phase: ASR-miss / wrong-pick / grasp-fail / insert-fail.
- Report the SmolVLA→classical-fallback trigger rate separately — isolates VLA reliability from
  overall system success.
- v1 scope: aggregate n≥20 across mixed targets. Per-shape/color breakdown is a stretch goal, not
  required for the first pass — avoids a combinatorial explosion of trials up front.

## Open risks

- SmolVLA fine-tune GPU access not yet solved (see Data section).
- SO-ARM101 wrist DOF sufficiency for orientation-aware insertion unverified — check during R1a
  bring-up before this mile's build order locks in.
- Toy's actual hole count/colors need a real-world check against this doc's assumed ~4 once the
  toy is in hand (confirm against the shape-sorter lid, not just the product photo).
