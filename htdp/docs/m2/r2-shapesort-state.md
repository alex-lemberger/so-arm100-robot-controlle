# R2 — Voice Shape-Sort: software-foundation state

**Done (this plan, all unit-tested offline, no hardware/model dependency):**
- `htdp.shapesort.vocab.parse_target` — command → target-hole lookup.
- `htdp.shapesort.classical_detect.detect_piece`/`detect_hole` — HSV+contour color/shape/
  orientation detector, tested against synthetic PIL fixtures (single shape, distractor
  scene, absent target, relative-rotation tracking).
- `htdp.shapesort.orchestrator.run_trial` — retry + classical-fallback + insert control
  loop, tested with injected fakes covering the ASR-miss/retry/fallback/grasp-fail/insert-fail
  branches specifically.
- `htdp.shapesort.eval.aggregate` — Wilson-CI + failure-taxonomy + fallback-rate report,
  reusing `htdp.learn.eval.wilson_ci`.
- CLI: `htdp shapesort-eval-report --trials trials.jsonl --out report.json`.

**Explicitly NOT done — hardware/model-gated, deferred until R1 closes and hardware/GPU
are available (per the design doc's sequencing decision):**
- Live ASR wiring: `openai-whisper`'s `model.transcribe(audio_path)` call itself is
  untested by this plan — only the vocab parser downstream of it is. Wire + smoke-test
  once a mic is on the rig.
- SmolVLA fine-tuning and the real `smolvla_pick` callable — needs ~40-60 real teleop
  demos and single-GPU (A100-class) access; both unresolved resource dependencies noted
  in the design doc.
- Live camera integration of `detect_piece`/`detect_hole` — the HSV ranges in
  `classical_detect.py` are tuned against synthetic fixtures, NOT real camera footage;
  expect to retune `_HSV_RANGES` once real images exist.
- Confidence-gated re-grasp/re-orient branch — low-confidence orientation estimate before
  insertion (occluded contour scenario) should trigger re-grasp instead of forcing the insert.
  `Detection.confidence` is computed by `classical_detect.py` but nothing currently reads it
  to make this decision in `orchestrator.run_trial`. Not implemented or tested yet.
- The real insertion servo loop (wrist rotation + closed-loop visual servo + stall/
  current-limit abort) — `InsertResult.aborted_stall` exists as a field for this to
  report into, but no hardware-side implementation exists yet.
- `COLOR_SHAPE_TO_HOLE` in `vocab.py` is a 4-entry placeholder from the product photo —
  confirm against the physical toy and edit if wrong.
- The real n>=20 trial eval run itself (the `shapesort-eval-report` CLI is ready to
  consume its output once trials exist).
- The `Outcome` type in `orchestrator.py` (success/asr_miss/grasp_fail/insert_fail) does
  not include a `wrong-pick` category, even though the original design doc's failure
  taxonomy lists one — there is currently no way to detect a wrong-pick at this layer
  since `PickResult` carries no object-identity-verification signal. This is a real
  scope gap for a future task, not a bug in what was built.

**Next session, once R1 closes and hardware is available:** R1a-style bring-up for this
mile — confirm toy hole colors, wire live ASR, record SmolVLA fine-tune demos, retune HSV
ranges against real footage, then build the live insertion servo loop.
