# Handover: Windows GPU training run → Mac (2026-08-07)

## What was done on Windows

Full 30,000-step SmolVLA fine-tune completed on the RTX 5070 box.

| | |
|---|---|
| Final loss | 0.031 (from 0.469 at step 1) |
| Wall time | ~2 hours |
| Speed | ~5.3 steps/sec (vs ~2s/step on Mac MPS — ~10× faster) |
| GPU memory | 3.06 GB / 12 GB |
| Checkpoints saved | 005000, 010000, 015000, 020000, 025000, 030000 |

## What to copy to Mac

Copy the entire folder from the Windows box:

```
C:\projects\so-arm100-robot-controlle\so-arm100\outputs\train\smolvla_shape_sort_30000\
```

Place it at:

```
/Users/alexanderlemberger/so-arm100-robot-controller/so-arm100/outputs/train/smolvla_shape_sort_30000/
```

## What to do next (per the finetune design spec)

1. **Run held-out-split MAE evaluation** before any hardware test — the spec
   (`docs/superpowers/specs/2026-08-05-smolvla-shape-sort-finetune-design.md`)
   requires this. Use the 5 eval episodes that were held out (`eval_split=0.15`).

2. **Test on the physical arm** via `robot_learning/run_policy_prompt.py`,
   pointing at `outputs/train/smolvla_shape_sort_30000/checkpoints/030000/pretrained_model/`.
   Same workflow as the 500/2000-step ACT checkpoint tests.

## Windows-specific patches applied to .venv-lerobot

These are in the venv on the Windows box only — the Mac venv is unaffected:

- `lerobot/policies/pretrained.py`: `str(path)` → `path.as_posix()` to fix
  Windows backslash in HuggingFace repo ID
- `lerobot/processor/pipeline.py`: same fix in `DataProcessorPipeline.from_pretrained`
- `lerobot/common/train_utils.py`: `symlink_to` wrapped in try/except (Windows
  requires Developer Mode for symlinks; non-fatal, checkpoint saves fine without it)

None of these affect the checkpoint format — the saved weights are identical to
what the Mac would have produced.
