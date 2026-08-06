# M2.5 C1 — Domain Randomization (scoped milestone)

**Goal:** harden the B3 visuomotor policy against appearance shift, and report a robustness
number. Answers the #1 interview question about a sim policy ("what about sim-to-real?"). Still
0 €. Builds directly on B3; no teacher/physics changes.

**Depends on E1** (docs/m2/e1-eval-n-scope.md): all C1 robustness numbers are reported at n≥30
with Wilson 95% CI via E1's eval machinery — a DR claim on n=6 is the same anecdote problem E1
exists to fix. Run E1 first.

## Approach — runtime model-field edits, no XML rewrite

A single `randomize_scene(model, rng, cfg)` perturbs `mjModel` fields after
`MjModel.from_xml_path(...)`, before stepping/rendering. Applied **per episode** at demo-gen and
(optionally) per episode at rollout. Keeps `task_scene_physics.xml` as the canonical scene.

### Knobs (grounded in the scene)

| field | mjModel handle | randomize |
|-------|----------------|-----------|
| light direction/intensity | `model.light_dir`, `model.light_diffuse` | dir jitter ±~15°, diffuse 0.4–0.9 |
| headlight | `model.vis.headlight.diffuse/ambient` | mild |
| table color | `model.geom_rgba[table_gid]` | full hue range |
| floor texture color | groundplane `rgb1/rgb2` (tex regen or swap material rgba) | mild — or just table |
| camera pose | `model.cam_pos[front]`, `model.cam_mat0`/xyaxes | small jitter (±2 cm, ±2°) |
| cube friction/mass | `model.geom_friction`, `model.body_mass` | mild (keep grasp feasible) |

### The cube-color decision (the crux)

The B2/B3 cube is red; the image gate asserts **red pixels present**, and the CNN can lean on
"find red". Two options:

- **A — keep cube red (mild shade jitter only), randomize background/lighting/camera.** Policy
  still localises by color but must survive lighting/background/viewpoint shift. Lower risk, the
  red-pixel gate still holds. **Recommended first.**
- **B — randomize cube color too.** Forces shape/context localisation — much stronger
  generalisation claim, but harder to learn and **breaks the red-pixel gate** (need a
  geometry-based cube-visibility check instead). Defer to a C2.

## Evaluation — the robustness number

Train visuomotor **with** DR (A), then eval three ways and tabulate (each cell = n≥30 fresh
positions via E1's `--n-positions`, reported with Wilson 95% CI):
1. canonical fixed scene (the B3 setting) — should stay near the E1 baseline number,
2. **novel** DR seeds (unseen lighting/background/camera) — the headline robustness number,
3. (optional) the no-DR B3 policy on novel DR seeds — to show DR *helped* (expected: it tanks).

Gate test: DR-trained policy beats zero on held-out **under novel randomization** (gate itself
stays small-n for suite time; the n≥30 table is the offline CLI run, as in E1).

## Build order (TDD, ~1 session)

1. `randomize_scene(model, rng, cfg)` + unit test (fields actually change; cube still graspable —
   a teacher episode under DR still lifts+places).
2. Wire DR into `generate_demos` (per-episode, seeded, `cfg` toggle; default off so existing
   gates/datasets are unchanged).
3. Wire optional DR into `rollout_visuomotor_policy` / a `randomize` flag for eval.
4. End-to-end gate: train-with-DR → rollout-under-novel-DR → success > 0.
5. Update `docs/SIM_LOOP.md` with the robustness table + a DR rollout clip.

## Risks / watch-items

- **Red-pixel gate** (`test_front_camera_frames_the_cube`, B2 sidecar test) assumes a red cube —
  option A keeps it valid; option B requires replacing it. Grep for the red-pixel check before
  touching cube color.
- **Keep DR default-off** so the B1/B2/B3 gates and committed numbers stay reproducible; DR is an
  opt-in path, not a silent change to the existing loop.
- Camera jitter must not push the cube/target out of frame — bound it and reuse the cube-visible
  assertion as a guard.
- Suite time: DR adds another train+rollout gate (~3 min). Keep it as one focused gate.

**Then (after C1):** generalization stress test (OOD cube positions / distractors), then portfolio
packaging. Real SO-ARM100 still optional.
