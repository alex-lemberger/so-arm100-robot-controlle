# Fine-tune SmolVLA on the shape-sort dataset

## Context

This adapts the training portion of the already-approved
[`2026-08-03-policy-hardware-control-design.md`](2026-08-03-policy-hardware-control-design.md)
to the dataset actually built today, rather than the cube-into-bin dataset that
spec originally targeted. That spec's own findings still hold: the trained ACT
checkpoint (`outputs/train/act_so100_pickplace_500/` and today's
`outputs/train/act_shape_sort_smoke/`) has no language input and cannot accept
a prompt — the leverage for prompt-driven control has to come from a real
vision-language-action model, `lerobot/smolvla_base`, fine-tuned on real
demonstrations.

Today's session built `data/local/lerobot_dataset/` (29 episodes, 20,001
frames, LeRobot v3 format, task string `"Pick up a shape piece and insert it
into its matching hole on the puzzle board."`, camera keys
`observation.images.overview`/`observation.images.wrist`) and confirmed the
LeRobot training pipeline works end-to-end with a 10-step ACT smoke run (loss
86.6 → 21.8, checkpoint saved). This spec covers fine-tuning SmolVLA on that
same dataset instead.

**This spec covers fine-tuning only.** Running the resulting checkpoint on the
physical arm — action-frame mapping, the policy server, the dead-man switch
and other safety gating — is a separate follow-up project (the rest of the
2026-08-03 spec, sections 3 and 5–7), not started here.

## Goal

Produce a SmolVLA checkpoint fine-tuned on `data/local/lerobot_dataset/`, with
an offline held-out-split evaluation metric, proving the fine-tuning loop
works on this exact dataset before any hardware execution work begins.

## Non-goals

- No running the checkpoint on the physical arm. No `policyFrame.ts`, no
  policy server, no dead-man switch. That is deliberately a separate,
  separately-brainstormed project once a checkpoint exists worth running.
- No co-training against the borrowed `svla_so100_pickplace` dataset (old
  spec §4) in this pass — different task, different physical arm, and the old
  spec's own risk assessment expected it not to help. Revisit only if the
  smoke run or offline eval results suggest scarce data is the binding
  constraint.
- No prompting between multiple tasks. `data/local/lerobot_dataset/` has one
  task string; the model is language-conditioned architecturally but this
  fine-tune teaches it one task, matching the old spec's own non-goal.
- No decision here about renting a cloud GPU for a longer real run. MPS
  (confirmed available on this machine: `torch.backends.mps.is_available()`
  returns `True` on an M2 Max, contradicting `AGENTS.md`'s stale "no
  accelerator" claim — same finding the old spec already made) is what the
  smoke run below uses. Whether a longer real run happens locally on MPS or
  on a rented GPU is a decision to make *after* the smoke run reports real
  per-step timing, not before.

## Training command

```bash
.venv-lerobot/bin/lerobot-train \
  --dataset.repo_id=local/shape_sort_teleop \
  --dataset.root=data/local/lerobot_dataset \
  --dataset.video_backend=pyav \
  --dataset.eval_split=0.15 \
  --policy.path=lerobot/smolvla_base \
  --policy.push_to_hub=false \
  --policy.device=mps \
  --output_dir=outputs/train/smolvla_shape_sort \
  --job_name=smolvla_shape_sort \
  --wandb.enable=false \
  --steps=10 \
  --save_freq=10 \
  --log_freq=1
```

`--dataset.repo_id`/`--dataset.root` point at today's dataset instead of
`local/cube_bin`. `--policy.path=lerobot/smolvla_base` (not
`--policy.type=act`) loads SmolVLA's pretrained weights for fine-tuning,
matching the old spec's §2 exactly. `--dataset.eval_split=0.15` reserves
~4 of the 29 episodes for offline evaluation, also matching the old spec.

**First-run network dependency:** `lerobot/smolvla_base`'s weights are not
currently cached anywhere on this machine (checked: nothing under
`~/.cache/huggingface` matches `smolvla`) — the first invocation downloads
them from the Hugging Face Hub. No account/auth needed for this public model,
but it does need network access and will take some time depending on
connection speed (SmolVLA is roughly 450M parameters).

## Smoke run first

Same pattern as today's ACT run: a short run (10 steps, matching both the
existing `act_so100_pickplace_smoke` precedent and today's own ACT smoke run
— `--save_freq` matches `--steps` so exactly one checkpoint gets written) to
confirm:

1. The SmolVLA weights download and load without error.
2. The dataset's features (camera keys, 6-dim state/action, task string) are
   accepted by SmolVLA's expected input schema without a shape/schema
   mismatch.
3. Loss decreases across the smoke steps (not just "doesn't crash").
4. A checkpoint is written to `outputs/train/smolvla_shape_sort/checkpoints/`.

**Do not proceed to a longer real training run automatically.** Report the
smoke run's actual per-step timing back before committing to anything longer
— SmolVLA is roughly 9x ACT's parameter count, so its real per-step cost on
MPS is unknown until measured, and that measurement is what informs the
local-MPS-vs-rented-GPU decision the old spec already flagged as a risk
("MPS training too slow to iterate → Rent a GPU").

## Verification

No test framework in this repo (matches project convention). Verification is:
the smoke run's printed loss values (must show a real decrease, not just
"ran without a traceback" — this is exactly how the ACT smoke run's success
was judged earlier today), confirmation a checkpoint directory with the
expected `pretrained_model/` contents gets written, and (if a longer real run
is later approved) the held-out-split MAE the old spec's §2 already asks for,
reported before any physical execution work begins.

## Risks

| Risk | Mitigation |
|---|---|
| SmolVLA's input schema doesn't match this dataset's feature dict (different camera-key conventions, different expected image resolution, etc.) | Smoke run surfaces this immediately as a loud error before any time is spent on a real run. |
| MPS training too slow to iterate on, even for the smoke run | Smoke run is short (10-20 steps) specifically to bound this cost before deciding on a longer run. |
| Only 29 episodes (fewer than the old spec's cube-into-bin target of "minimum 30, revised up from 10") | Same mitigation the old spec already gives: pipeline makes recording more episodes cheap; that's the expected fix if offline eval looks weak, not a blocker for attempting the smoke run now. |
| First-run Hugging Face download fails or is slow (no network, rate limiting, etc.) | Surfaces immediately as a loud error on the first smoke-run attempt; not silently retried or worked around. |
