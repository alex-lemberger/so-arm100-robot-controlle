# Faster iteration: LoRA adapters and human-in-the-loop corrections

Two mechanisms already in the installed LeRobot that this project was not
using. Both cut the cost of an iteration substantially; neither requires new
hardware or a different base model.

The short version:

- **Stop full-fine-tuning 450M parameters.** `--lora` adapts a low-rank matrix
  instead. Cheaper backward pass, and the artifact is an adapter rather than a
  7.4 GB checkpoint that has to cross a USB stick.
- **Stop recording blind demonstrations to fix failures.** `loop.py dagger`
  runs the policy on the arm and lets you take the leader the moment it is
  about to fail, recording the recovery. Targeted at the failure modes the
  policy actually has.

Both are wired into `robot_learning/loop.py`. Sources:
`lerobot/docs/source/peft_training.mdx` and `hil_data_collection.mdx`.

## Why not a different base model

`lerobot/smolvla_base` is pretrained on SO100/SO101 — the right base for this
arm. There are newer bases in the LeRobot docs (`pi05`, `xvla`, `groot`, `eo1`),
but switching model is not where the speedup is. The two changes below are
about *method*, and they apply whichever base is used.

## LoRA fine-tuning

```bash
python robot_learning/loop.py train \
  --dataset=circle_insert_50ep_trimmed \
  --base=lerobot/smolvla_base \
  --lora
```

Defaults: `r=64`, `alpha=64`, `batch_size=32`, `steps=20000`, `lr=1e-3`.

**The learning rate is the part people get wrong.** The PEFT doc says LoRA
takes roughly **10x** the full-fine-tune rate (1e-4 becomes 1e-3). `loop.py`
applies this automatically with `--lora` and sets `scheduler_decay_lr` to
lr/10. A LoRA run left at the full-fine-tune LR does not fail loudly, it just
underfits.

What LoRA targets by default in SmolVLA: `q_proj` and `v_proj` of the LM
expert, plus the state and action projection matrices — the task-dependent
parts. Override with `--peft.target_modules` on `lerobot-train` directly if a
run needs something else.

Why it helps this project specifically:

- The 30k full fine-tune produced **7.4 GB** across 6 checkpoints, all of which
  had to be hand-copied from the Windows box. Adapters are a small fraction of
  that.
- Multiple task adapters can sit on one frozen base — circle-insert,
  square-insert, shape-selection — instead of a full model per task.
- Frozen weights need no gradients, so steps are cheaper and a larger batch
  fits in the 5070's 12 GB.

Full fine-tuning is still available: omit `--lora`. Keep using it when the
task changes enough that adapting the projections is not sufficient.

## Human-in-the-loop corrections (DAgger)

```bash
python robot_learning/loop.py dagger \
  --checkpoint=outputs/train/<run>/checkpoints/<step>/pretrained_model \
  --tag=v1 --episodes=10
```

Behavioural cloning trains only on successes. At deployment small errors
compound and push the arm into states that appear nowhere in the training set —
which is exactly the failure signature this project has been chasing. DAgger
records the recovery from the *current* policy's real failures instead of
another 50 speculative demonstrations.

Per episode: watch the policy, **space** to pause when failure looks imminent
(the arm holds position), **tab** to start recording your correction, drive the
recovery on the leader, **tab** again and **space** to hand control back. The
episode continues from wherever it is — intervening does not force a reset.
Repeat within the episode as often as needed.

By default only the correction windows are recorded, each as its own episode.
`--record-autonomous` keeps the autonomous frames too.

Then fine-tune on demonstrations plus corrections and repeat against the new
failure modes:

```
Policy v0 (demos) → DAgger → fine-tune → v1 → DAgger → fine-tune → v2 → ...
```

Requirements, both already satisfied here: a teleoperator with active motors
(the `so100_leader` in `CONFIG`, since DAgger mirrors the follower's pose onto
the leader at handover) and `--inference.type=rtc` for SmolVLA, which `loop.py`
passes by default.

## Where this fits

| situation | do this | not this |
|---|---|---|
| Policy fails in specific, repeatable ways | `loop.py dagger`, then fine-tune | record 50 fresh episodes |
| Iterating on the same task | `train --lora` | full fine-tune |
| Task itself changes (new shape, new prompt) | record new demonstrations | DAgger |
| Base model feels wrong | it probably isn't | swapping to pi05/groot |

The recording session is the expensive step — it costs human time, not GPU
time. Reach for it last, after DAgger has been given a chance to fix the
failure and LoRA has made the retrain cheap.

## Still open

The 50 episodes recorded 2026-08-08 use continuous hand-placed scatter for the
piece's start position. The SmolVLA doc recommends discrete repeated variations
(5 positions x 10 episodes). No retrain or correction round fixes that — it is
a recording-session decision. See AGENTS.md, "Follow the LeRobot docs before
inventing a workflow".
