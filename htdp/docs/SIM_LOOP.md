# Pixels to a Friction Grasp — a Visuomotor Sim Loop

A Franka Panda picks a cube and places it on a target in MuJoCo — **from a single camera
image, under true contact physics**, with a policy that was never told where the cube or the
target are. It reads them from pixels.

This is a from-scratch robot-learning loop: scripted physics teacher → imitation demos →
action-chunking transformer policy → closed-loop rollout, built and debugged end-to-end. The
interesting part is not that it works — it's the specific ways it *looked* like it worked while
being broken, and how each was caught.

| policy | observation | held-out success (n=40) | 95% CI | mean place error |
|--------|-------------|-------------------------|--------|------------------|
| baseline (scripted physics teacher) | privileged state | 40/40 (100%) | [91%, 100%] | 0.008 m |
| state ACT | joints + eef + **cube xyz + target xyz** + finger width | 33/40 (82.5%) | [68%, 91%] | 0.058 m |
| **visuomotor ACT** | **96×96 camera image + proprioception only** | **35/40 (87.5%)** | [74%, 95%] | 0.050 m |

> *n=40 freshly sampled held-out positions (seeded, disjoint from the train and test splits),
> Wilson 95% intervals. An earlier n=6 eval read 4/6 (67%) for both policies — inside these
> intervals, and a lesson in why six episodes is an anecdote, not a measurement. Mean place error
> is averaged over all positions, so it is dominated by the grasp-slip failures (~0.25 m each);
> successful placements land within a few centimetres. Read the success column for "did it
> work," the error column for "how clean when it did."*

The visuomotor policy **matches** the state-based policy (overlapping CIs) while seeing none of
the privileged coordinates.

- **Visuomotor policy rollout** (the headline — pixels in, friction grasp out):
  [`docs/demo/m25_visuomotor_rollout.mp4`](demo/m25_visuomotor_rollout.mp4)
  ([GIF](demo/m25_visuomotor_rollout.gif),
  [narrated/captioned version](demo/m25_visuomotor_rollout_narrated.mp4))
- Eval reports (n=40): [`docs/m2/e1-eval-n40-visuomotor.json`](m2/e1-eval-n40-visuomotor.json),
  [`docs/m2/e1-eval-n40-state.json`](m2/e1-eval-n40-state.json)
  (legacy n=6: [`docs/demo/m25_visuomotor_eval.json`](demo/m25_visuomotor_eval.json))
- Scripted physics teacher rollout: [`docs/demo/m25_physics_pick_place.mp4`](demo/m25_physics_pick_place.mp4)

## Domain randomization robustness (C1)

"What about sim-to-real?" — the #1 question a sim-only policy gets. A `randomize_scene(model,
rng, cfg)` perturbs light direction/intensity, headlight, table color (full hue range), camera
pose (±2 cm, ±2°), and cube friction/mass **at runtime**, per episode, after loading the
canonical XML — no scene rewrite. The cube itself only gets a mild hue jitter and stays
red-dominant (option A): it must still trip the same red-pixel visibility gate the B2/B3 pipeline
already relies on. A visuomotor policy was retrained **with** this randomization on, then
evaluated two ways at n=40 with Wilson 95% CI:

| eval scene | held-out success (n=40) | 95% CI | mean place error |
|------------|--------------------------|--------|-------------------|
| canonical fixed scene (same setting as the B3/E1 table above) | 39/40 (97.5%) | [87%, 100%] | 0.020 m |
| **novel** DR seeds (unseen light/table-color/camera/friction draws) | **40/40 (100%)** | **[91%, 100%]** | 0.015 m |

> Reports: [`docs/m2/c1-eval-n40-canonical.json`](m2/c1-eval-n40-canonical.json),
> [`docs/m2/c1-eval-n40-novel-dr.json`](m2/c1-eval-n40-novel-dr.json). Same physics baseline
> (100%) both rows — DR doesn't touch the teacher or the grasp mechanics, only what the camera
> sees.

The DR-trained policy holds up under scene draws it never trained on — no measurable drop
against its own canonical-scene number, and both cells sit on top of the no-DR E1 visuomotor
number (87.5% [74%, 95%]). Two readings, both defensible: the extra visual variety in training
acted as a regularizer: the CNN can no longer key off one fixed lighting/table/camera
configuration, so it's forced to actually localize the (still-red) cube by color+shape rather
than memorize a scene. Read this as "robust to the randomized nuisance factors it trained under,"
not as a sim-to-real guarantee — the gap to a real camera/lighting/lens is untested (see Honest
limitations).

## The loop

```
sample cube pose (in the friction-grasp success zone)
        │
        ▼
scripted physics teacher  ──►  position-servo actuators + mj_step + friction grasp
        │                      (no kinematic attach — the cube is held by finger contact)
        ▼
LeRobot-format demos       ──►  per-step state, action chunk, AND a 96×96 front-camera frame
        │
        ▼
ACT policy (transformer)   ──►  state ACT  |  visuomotor ACT (CNN over the image + proprio)
        │
        ▼
closed-loop rollout        ──►  same physics, same friction grasp, same camera path
                               policy localises the cube from pixels and places it
```

The teacher, the demos, and the rollout all run the *same* physics and render through the *same*
camera function — so nothing the policy trains on differs from what it sees at test time.

## What made it credible (and what didn't)

Every milestone shipped a metric that was green before the system was right. The work was mostly
in distrusting the metric.

- **The 5-DOF wall.** Started on an SO-ARM100 (5-DOF). The pick-place metrics passed, but the
  rendered video showed the gripper pointing *up*, missing the cube, links clipping through the
  table. A position-only `place_error` read 0.0 because the cube was being teleported by a weld
  regardless of where the fingers were. Three separate false-greens, all from checking position
  and not contact. Then the real wall: a 5-DOF arm *physically cannot* orient a gripper top-down
  at a tabletop target — proven by a mount-height sweep (15–27 cm error everywhere). Swapped to a
  7-DOF Franka Panda, which is also the imitation-learning standard.

- **The normalization landmine.** The first imitation policy scored 0% closed-loop while
  predicting *perfectly* on demo observations open-loop. The cause: a constant observation
  feature (finger width — the kinematic teacher never moved the fingers, so its std was ~0). A
  tiny mismatch at rollout, divided by ~0 during normalization, produced an astronomically large
  input that destroyed the policy. Fix: drop constant features. (When the physics teacher *did*
  actuate the fingers, the feature carried real signal and came back.)

- **Kinematic vs. physics action mismatch.** A kinematic teacher (joint angles forced into
  `qpos`) produces actions that position-servo actuators cannot track (1.76 rad error). Teacher
  and executor must agree. This drove the whole M2.5 rewrite: replace the kinematic shortcut with
  a true friction grasp on *both* sides — teacher and rollout — so the same actions mean the same
  thing.

- **Friction compounds error.** Under a true friction grasp, held-out success is ~80–90%, not
  the 100% the kinematic attach reported. A slightly-off approach slips the grasp; the attach
  used to paper over exactly that. The lower number is the honest one.

- **A blank camera still renders something.** The image gate doesn't assert "frame is non-blank"
  — a camera pointed at a wall passes that. It asserts the red cube's pixels are present, so a
  misaimed camera can't silently train a blind policy.

## How it's built

- **Physics & control** — MuJoCo (vendored Menagerie Franka), differential IK via `mink` to turn
  Cartesian waypoints into joint targets, position-servo actuators stepped with `mj_step`. The
  grasp is finger friction on a high-friction cube, not a weld.
- **Data** — demos in LeRobot dataset layout (Parquet for low-dim state/action; 96×96 RGB image
  stacks as aligned `.npy` sidecars, the way LeRobot sidecars video).
- **Policy** — a compact action-chunking transformer (ACT): observation → memory token → decoder
  with learned queries → a chunk of actions, executed receding-horizon. The visuomotor variant
  adds a small 3-stride CNN over the image, fused with proprioception. PyTorch, MPS.
- **Robustness** — observation-noise / image-jitter augmentation (DART-style) against the
  covariate shift that compounds in closed loop.
- **Tests** — TDD throughout, including two end-to-end guards that train a policy and assert
  nonzero held-out success under physics (the state loop and the visuomotor loop). Each milestone
  has a short result doc under [`docs/m2/`](m2/).

```bash
uv sync --extra replay --extra dev
htdp gen-demos       --out demos --n-train 40            # physics teacher + 96×96 images
htdp gen-demos       --out demos_dr --n-train 40 --domain-randomize   # + per-episode scene DR (C1)
htdp train-visuomotor --demos demos --out vm.pt --steps 6000
htdp eval-visuomotor  --demos demos --policy vm.pt --n-positions 40   # success + 95% CI vs physics baseline
htdp eval-visuomotor  --demos demos --policy vm.pt --n-positions 40 --domain-randomize   # eval under novel DR seeds
htdp render-physics   --video out.mp4                    # teacher rollout from the front camera
```

## Position generalization (OOD1)

The headline 87.5% is measured **in-distribution** — freshly sampled but from the same region
the policy trained on. To find the actual generalization edge, a plain (no-DR) visuomotor policy
was evaluated on cube positions from a never-trained-on band immediately adjacent to the training
region (same friction-feasible x-range; y shifted outside the trained y-band):

| eval positions | held-out success (n=40) | 95% CI | mean place error |
|---|---|---|---|
| in-distribution (repro of the headline number) | 35/40 (87.5%) | [74%, 95%] | 0.050 m |
| **out-of-distribution** (never-trained y-band) | **24/40 (60.0%)** | **[45%, 74%]** | 0.180 m |

> Reports: [`docs/m2/ood1-eval-n40-indist.json`](m2/ood1-eval-n40-indist.json),
> [`docs/m2/ood1-eval-n40-ood.json`](m2/ood1-eval-n40-ood.json). The physics teacher (baseline)
> stays 100% on **both** position sets — the physics and IK generalize fine; the drop is
> entirely the CNN policy failing to localize/act correctly on positions it never saw. This is
> the honest number for "does it generalize beyond the training region": roughly half.

## Honest limitations

- Success rates above are **for the trained cube region and the region tested in OOD1** — a
  ~7×10 cm training band and an adjacent ~7×9 cm OOD band, both still on the table and within IK
  reach. Positions far outside either band, or distractor objects, are untested.
- One object, one fixed third-person camera. Domain randomization (C1) covers light, table
  color, camera pose, and cube friction/mass — but the cube color itself stays red (mild jitter
  only), so this is not yet a shape/context-generalization or sim-to-real claim.
- 87.5% [74%, 95%] is a real friction-grasp number, not a polished demo number; the failures are
  grasp slips on off-center approaches, and the CI is reported because n=40 still leaves a
  ±10 pp band.

## Where it could go

Wrist camera; randomizing the cube's own color (forces shape/context localization, breaks the
red-pixel gate — needs a geometry-based cube-visibility check instead); or driving a real
SO-ARM100 now that the loop is validated in sim. The point of stopping here:
the loop is closed and honest end-to-end — pixels to a friction grasp, no kinematic shortcut and
no privileged state.

---
*Origin: this began as a consent-based human-task capture pipeline (see the
[README](../README.md)); the manipulation sim loop is the part re-scoped toward robot-learning
engineering.*
