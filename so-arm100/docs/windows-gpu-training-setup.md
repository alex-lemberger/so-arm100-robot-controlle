# Windows GPU environment setup for SmolVLA fine-tuning

Target machine: Intel i7-14700KF, RTX 5070 (12 GB VRAM), 32 GB DDR5. Goal:
reproduce the Mac's `.venv-lerobot` environment there with CUDA instead of
MPS, so the SmolVLA fine-tune runs at CUDA speed instead of Apple Silicon
MPS speed. See `windows-gpu-training-run.md` for the actual training
command once this setup is done.

## Why move it off the Mac

MPS lacks fused kernels for a lot of transformer ops that CUDA has had for
years, and reliable mixed precision isn't available there — both hold back
a 450M-param fine-tune. A 2000-step smoke run on the M2 Max ran at roughly
2s/step before an unrelated sleep-related slowdown. RTX 5070 + CUDA + AMP
should beat that by a wide margin (rough estimate: 5-10x), making a full
30,000-step run (SmolVLA's own built-in schedule — see
`windows-gpu-training-run.md`) practical in a few hours instead of ~17.

## Pinned versions (match the Mac's `.venv-lerobot` exactly)

| Package | Version |
|---|---|
| Python | 3.12.13 |
| lerobot | 0.6.1 (with `smolvla` extra) |
| torch | 2.11.0 |
| torchvision | 0.26.0 |
| transformers | 5.5.4 |

Matching versions avoids any dataset-schema or checkpoint-format mismatch
between the two machines.

## Steps

1. **Confirm the driver supports the GPU.** RTX 5070 is Blackwell
   (compute capability sm_120), which needs CUDA 12.8+. Run `nvidia-smi`
   and check the reported CUDA version is 12.8 or newer; update the NVIDIA
   driver first if not.

2. **Install Python 3.12** (matches the Mac env) if not already present.

3. **Create a venv and install CUDA-enabled PyTorch pinned to 2.11.0.**
   Use the official selector at pytorch.org to get the right CUDA wheel
   index for your installed CUDA version (12.8 or newer), e.g.:

   ```powershell
   python -m venv .venv-lerobot
   .venv-lerobot\Scripts\activate
   pip install torch==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cu128
   ```

   Adjust the `cu128` tag if the selector points you at a newer CUDA tag
   for Blackwell support.

4. **Verify CUDA is actually visible before installing anything else:**

   ```powershell
   python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
   ```

   Expected: `True RTX 5070`. If `False`, stop and fix the torch/CUDA
   install before proceeding — don't discover this after a long download.

5. **Install lerobot pinned to 0.6.1 with the smolvla and dataset extras:**

   ```powershell
   pip install lerobot==0.6.1
   pip install "lerobot[smolvla]"
   pip install "lerobot[dataset]"
   pip install transformers==5.5.4
   ```

   The `dataset` extra (`datasets`, `pyarrow`, `av`, etc.) is required by `lerobot-train` even
   for local datasets — without it the train script fails at import with a missing-package error.
   `transformers==5.5.4` is pulled in by the `smolvla` extra automatically; the explicit pin is
   kept here as a guard.

6. **Transfer the dataset and strip macOS metadata files.** `so-arm100/data/lerobot_dataset/` is ~300 MB
   (55 episodes, ~100 MB parquet + ~200 MB video) — copy it over via USB
   stick, network share, or a cloud drive, whichever's easiest. Put it
   anywhere on the Windows box; `--dataset.root` in the training command
   points at it directly, so the path doesn't need to match the Mac's
   layout.

   After copying, delete macOS AppleDouble metadata files (`._*`) that
   macOS silently creates alongside every file. They're invisible on Mac
   but land on Windows and cause the `datasets` library to crash with
   "Parquet magic bytes not found":

   ```powershell
   Get-ChildItem -Recurse -Force so-arm100\data\lerobot_dataset `
     | Where-Object { $_.Name -like "._*" } `
     | Remove-Item -Force -Confirm:$false
   ```

7. **Disable sleep for the duration of the run.** The Mac's earlier
   2000-step run took ~5 hours instead of a predicted ~1 hour because the
   machine slept partway through. On Windows, either keep the session
   active manually or run:

   ```powershell
   powercfg /change standby-timeout-ac 0
   powercfg /change monitor-timeout-ac 0
   ```

   (Revert with `powercfg /change standby-timeout-ac <original-minutes>`
   after the run.)

Once steps 1-7 are done, move to `windows-gpu-training-run.md` for the
actual `lerobot-train` command.
