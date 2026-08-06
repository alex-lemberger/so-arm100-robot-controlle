# SmolVLA Shape-Sort Smoke Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run a 10-step SmolVLA fine-tuning smoke test against `data/local/lerobot_dataset/` and report whether the loop actually works (weights download, dataset schema compatibility, loss decrease, checkpoint written) and its real per-step timing.

**Architecture:** This is not new code — it's running one already-fully-specified `lerobot-train` command via `.venv-lerobot` and verifying its output. There is nothing to build; the deliverable is a verified run plus a clear report of what happened, including timing data needed for a later (separate, not-this-plan) decision about a longer real training run.

**Tech Stack:** `lerobot-train` CLI (from `.venv-lerobot`, already has `lerobot==0.6.1` installed), `lerobot/smolvla_base` pretrained weights (downloaded from the Hugging Face Hub on first use — not currently cached on this machine).

## Global Constraints

- No test framework in this repo — verification is running the actual command and reading its printed output, the same way the earlier ACT smoke run this session was verified (loss 86.6→21.8 over 10 steps, checkpoint at `outputs/train/act_shape_sort_smoke/checkpoints/000010/`).
- Environment is `.venv-lerobot` (`/Users/alexanderlemberger/so-arm100-robot-controller/.venv-lerobot/bin/lerobot-train`), not `~/lerobot/.venv`.
- Exact command, verbatim from the spec — do not modify any flag or value:
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
- **This command has not been tried against this dataset before.** Do not treat "it will just work" as an assumption — the spec's own Risks table flags that SmolVLA's expected input schema might not match this dataset's feature dict (different camera-key conventions, different expected image resolution, etc.). If it fails with a schema/shape/API error, that is a valid, reportable outcome of this task — do not attempt to guess-fix it into working (e.g. by changing dataset feature names, adding image resizing, or modifying `robot_learning/build_lerobot_dataset.py`). This plan's job is to run the command and report what actually happens, not to make it pass at any cost. A schema mismatch found here likely needs a follow-up spec revision, not a code patch made under this plan.
- Report whether the first-time `lerobot/smolvla_base` download from the Hugging Face Hub succeeded, and roughly how large/how long it took — this machine's network reliability for this kind of download hasn't been explicitly verified this session.
- Do not proceed to any longer training run. This plan stops after the 10-step smoke run and its verification, regardless of outcome.

---

### Task 1: Run and verify the SmolVLA smoke run

**Files:** None created or modified — this task runs an existing CLI tool and inspects its output and the checkpoint directory it produces.

**Interfaces:**
- Consumes: `data/local/lerobot_dataset/` (built and verified in an earlier session plan — 29 episodes, 20,001 frames, LeRobot v3 format).
- Produces: `outputs/train/smolvla_shape_sort/checkpoints/000010/pretrained_model/` (if successful) — not consumed by any other task in this plan; this is the plan's final deliverable, to be picked up by a future, separately-brainstormed project once a real training run happens.

- [ ] **Step 1: Confirm network reachability to the Hugging Face Hub before starting**

Run: `curl -s -o /dev/null -w "%{http_code}\n" https://huggingface.co`

Expected: `200`. If this fails (timeout, non-200, DNS error), STOP and report this immediately as the blocker — don't attempt the training command, since it will just fail the same way after a potentially long hang.

- [ ] **Step 2: Run the smoke-run command**

From the repo root (`/Users/alexanderlemberger/so-arm100-robot-controller`), run the exact command from Global Constraints. Let it run to completion — the first run includes a one-time download of `lerobot/smolvla_base`'s weights (~450M parameters), which may take a while depending on connection speed; this is expected, not a hang.

Capture the full output (stdout+stderr) to a file so you can review it and quote from it in your report, e.g.:

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
  --log_freq=1 2>&1 | tee /tmp/smolvla-smoke-run.log
```

- [ ] **Step 3: Handle the outcome**

**If the command fails** (any traceback, `ValueError`, shape mismatch, or non-zero exit before completing all 10 steps): stop here. Do not modify any code to try to fix it. Read `/tmp/smolvla-smoke-run.log` and identify the exact error message and which line/feature/shape it concerns — this goes directly into your report as-is. This is a valid, complete outcome of this task.

**If the command succeeds** (all 10 steps complete, a checkpoint is written): continue to Step 4.

- [ ] **Step 4: Verify loss actually decreased (not just "ran without crashing")**

Run: `grep -E "step:[0-9]+ " /tmp/smolvla-smoke-run.log`

Expected: 10 lines, one per step, each containing a `loss:` value. Compare the `loss:` value on the `step:1` line against the `step:10` line — confirm the value decreased. (This is exactly how the earlier ACT smoke run's success was judged: loss 86.6 → 21.8 over 10 steps was treated as evidence the model is actually learning, not just that the loop executes.)

- [ ] **Step 5: Verify the checkpoint directory**

Run: `find outputs/train/smolvla_shape_sort/checkpoints/000010/pretrained_model -maxdepth 1`

Expected: at minimum `config.json`, `model.safetensors`, `train_config.json` present (matching the structure of the existing `outputs/train/act_shape_sort_smoke/checkpoints/000010/pretrained_model/` from the earlier ACT run).

- [ ] **Step 6: Extract per-step timing from the log**

Run: `grep -E "step/s\]|s/step\]" /tmp/smolvla-smoke-run.log | tail -3`

Expected: the training progress bar's per-step rate (e.g. `X.XXs/step`). Record this exact figure — it's the key output this plan exists to produce, needed for the later decision about whether a longer real training run is feasible locally on MPS or should be run on a rented GPU instead (per the spec's Risks table).

- [ ] **Step 7: Clean up the log file**

```bash
rm -f /tmp/smolvla-smoke-run.log
```

(The checkpoint itself stays at `outputs/train/smolvla_shape_sort/` — `outputs/` is already gitignored, nothing here gets committed.)

- [ ] **Step 8: Report**

No commit for this task — nothing was created or modified in the repo (the checkpoint lives under the already-gitignored `outputs/`). Instead, produce a clear final report covering:
- Did the command succeed or fail? If it failed, the exact error and what it concerns.
- If it succeeded: the loss value at step 1 vs step 10 (confirming real decrease), confirmation the checkpoint directory has the expected contents, and the per-step timing figure from Step 6.
- Whether the `lerobot/smolvla_base` download happened, and roughly how large/long it took (or whether it was somehow already cached).
- Whether Step 1's network check passed.
