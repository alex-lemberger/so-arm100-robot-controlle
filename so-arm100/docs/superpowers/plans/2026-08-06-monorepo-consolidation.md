# Monorepo Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn this repo into a monorepo containing five top-level, self-contained projects: the existing SO-ARM100 app (moved into `so-arm100/`), and four projects copied in fresh from standalone folders elsewhere on disk (`htdp/`, `htdp-capture/`, `handwerk-robot-sim/`, `neurofeedback-lang-app/`).

**Architecture:** Each project keeps its own build tooling untouched in its own top-level folder — no interleaving of code or dependencies between projects. A single root `.gitignore` is built up incrementally, one project-specific block per task, using anchored (`/project/...`) patterns so one project's ignore rules can't accidentally swallow another's tracked files. Content is copied via `rsync` with explicit `--exclude` flags (not `git subtree`) — per the approved design spec, git history is not preserved for the four incoming projects.

**Tech Stack:** Node/npm + Vite/React/TS (so-arm100, neurofeedback-lang-app), Python/`uv` (htdp, htdp-capture, handwerk-robot-sim), `rsync` and `git mv` for the moves themselves.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-06-monorepo-consolidation-design.md` — read it before starting; this plan implements it exactly.
- Fresh-copy only: do not run `git subtree`, do not attempt to preserve the four incoming projects' commit history.
- Original standalone folders (`/Users/alexanderlemberger/human-task-dataset-pipeline`, `/htdp-capture`, `/handwerk-robot-sim`, `/neurofeedback-lang-app`) are never modified or deleted by this plan. Only `/Users/alexanderlemberger/human-aware-robotic` gets deleted (Task 6).
- Work happens on branch `chore/monorepo-consolidation` (already created off `agent/ollama-and-feetech-control`). Do not switch branches mid-plan.
- One commit per task, focused message, no `--no-verify`.
- Root-level tool config directories (`.claude/`, `.superpowers/`) stay at the repo root and are never copied into or out of any project subfolder.
- All paths below are relative to the repo root (`/Users/alexanderlemberger/so-arm100-robot-controller`) unless given as an absolute source path.

---

### Task 1: Move the current SO-ARM100 app into `so-arm100/`

**Files:**
- Move (git-tracked, via `git mv`): `.env.example`, `AGENTS.md`, `data/`, `docs/`, `index.html`, `metadata.json`, `package-lock.json`, `package.json`, `README.md`, `robot_learning/`, `server.ts`, `src/`, `tsconfig.json`, `vite.config.ts` → same names under `so-arm100/`
- Move (untracked, via plain `mv`): `.cache/`, `.DS_Store`, `.env.local`, `.venv-lerobot/`, `.worktrees/`, `assets/`, `dist/`, `env.example.textClipping`, `node_modules/`, `outputs/` → same names under `so-arm100/`
- Modify: `.gitignore` (stays at repo root, re-anchor so-arm100-specific patterns)

**Interfaces:**
- Produces: a working `so-arm100/` app, runnable via `npm run lint` / `npm run build` with `so-arm100/` as cwd. Later tasks don't depend on this one's internals, only on `so-arm100/` existing as a sibling folder.

- [ ] **Step 1: Create the target directory and move tracked files with `git mv`**

```bash
mkdir -p so-arm100
git mv .env.example so-arm100/.env.example
git mv AGENTS.md so-arm100/AGENTS.md
git mv data so-arm100/data
git mv docs so-arm100/docs
git mv index.html so-arm100/index.html
git mv metadata.json so-arm100/metadata.json
git mv package-lock.json so-arm100/package-lock.json
git mv package.json so-arm100/package.json
git mv README.md so-arm100/README.md
git mv robot_learning so-arm100/robot_learning
git mv server.ts so-arm100/server.ts
git mv src so-arm100/src
git mv tsconfig.json so-arm100/tsconfig.json
git mv vite.config.ts so-arm100/vite.config.ts
```

- [ ] **Step 2: Move the remaining untracked files/dirs with plain `mv`**

```bash
mv .cache so-arm100/.cache
mv .DS_Store so-arm100/.DS_Store
mv .env.local so-arm100/.env.local
mv .venv-lerobot so-arm100/.venv-lerobot
mv .worktrees so-arm100/.worktrees
mv assets so-arm100/assets
mv dist so-arm100/dist
mv env.example.textClipping so-arm100/env.example.textClipping
mv node_modules so-arm100/node_modules
mv outputs so-arm100/outputs
```

- [ ] **Step 3: Verify nothing was left behind at the old root**

```bash
ls -la
```

Expected: only `.claude/`, `.git/`, `.gitignore`, `.superpowers/`, and `so-arm100/` remain at the repo root (plus the new `docs/superpowers/specs/` and `docs/superpowers/plans/` files already inside `so-arm100/docs/` now — confirm with `ls so-arm100/docs/superpowers/specs/ so-arm100/docs/superpowers/plans/`).

- [ ] **Step 4: Re-anchor the so-arm100-specific `.gitignore` patterns**

Replace the full contents of `.gitignore` with:

```
node_modules/
build/
dist/
coverage/
.DS_Store
*.log
.env*
!.env.example

# so-arm100 — downloaded datasets and local experiment outputs
/so-arm100/data/external/
/so-arm100/data/experiments/
/so-arm100/data/local/
/so-arm100/outputs/
/so-arm100/.cache/
/so-arm100/.venv-lerobot/
/so-arm100/.worktrees/
```

- [ ] **Step 5: Verify git sees a clean, correctly-ignored tree**

```bash
git status
```

Expected: shows the renames from Step 1 (as `renamed:`), no untracked entries for `so-arm100/node_modules/`, `so-arm100/dist/`, `so-arm100/data/local/`, `so-arm100/data/external/`, `so-arm100/outputs/`, `so-arm100/.cache/`, `so-arm100/.venv-lerobot/`, `so-arm100/.worktrees/` (all correctly ignored), and untracked entries for `so-arm100/.env.local` (ignored — check it does NOT appear) and `so-arm100/robot_learning/run_policy_prompt.py` / `so-arm100/docs/superpowers/plans/2026-08-05-smolvla-shape-sort-smoke-run.md` (these should appear as untracked — they were untracked before the move too, carried along by `git mv robot_learning ...` / `git mv docs ...`).

- [ ] **Step 6: Verify the app still builds from its new location**

```bash
cd so-arm100 && npm run lint && npm run build && cd ..
```

Expected: `npm run lint` (which runs `tsc --noEmit`) exits 0, `npm run build` completes and writes `so-arm100/dist/`.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "chore: move so-arm100 app into so-arm100/ subfolder"
```

---

### Task 2: Copy `human-task-dataset-pipeline` into `htdp/`

**Files:**
- Create (via `rsync`): `htdp/` — full copy of `/Users/alexanderlemberger/human-task-dataset-pipeline` minus the exclusions below
- Modify: `.gitignore` (append Python-generic + htdp-specific blocks)

**Interfaces:**
- Produces: a working `htdp/` Python project (package `htdp`, CLI entry point `htdp = "htdp.cli:app"`), independently testable via `uv run pytest` from within `htdp/`.

- [ ] **Step 1: Copy with exclusions**

```bash
mkdir -p htdp
rsync -a \
  --exclude='.git/' \
  --exclude='.venv/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.mypy_cache/' \
  --exclude='.pytest_cache/' \
  --exclude='.ruff_cache/' \
  --exclude='.claude/' \
  --exclude='.superpowers/' \
  --exclude='.DS_Store' \
  --exclude='data/' \
  --exclude='demos/' \
  --exclude='outputs/' \
  --exclude='policy.pt' \
  --exclude='IMG_3980.psd' \
  --exclude='toy.ai' \
  --exclude='IMG_3980.jpg' \
  --exclude='IMG_3919.jpg' \
  --exclude='IMG_3981.jpg' \
  --exclude='IMG_3918.jpg' \
  --exclude='IMG_3979.jpg' \
  --exclude='connection.jpg' \
  --exclude='2Boards.jpg' \
  --exclude='looseConnectorWhite.jpg' \
  --exclude='blackArm.jpg' \
  --exclude='boxes.jpg' \
  --exclude='toy2.jpg' \
  --exclude='looseConnectorBlack.jpg' \
  --exclude='webcam.jpg' \
  --exclude='camopening.jpg' \
  --exclude='webcam2.jpg' \
  --exclude='toy.jpg' \
  --exclude='1motorWhite.jpg' \
  --exclude='toy.png' \
  --exclude='613KHZ1vJIL._AC_SL1500_.jpg' \
  --exclude='stash_webcam_test.jpg' \
  --exclude='stash_webcam_test2.jpg' \
  --exclude='Mac-Terminal.txt' \
  --exclude='HW.rtf' \
  /Users/alexanderlemberger/human-task-dataset-pipeline/ ./htdp/
```

- [ ] **Step 2: Verify the two untracked design docs came along and the excluded binaries did not**

```bash
ls htdp/human_task_dataset_pipeline_mvp.md htdp/2026-06-20-human-task-dataset-pipeline-v0.1-design-reviewed.md
ls htdp/IMG_3980.psd 2>&1 | grep -q "No such file" && echo "OK: excluded"
```

Expected: the first `ls` lists both files; the second prints `OK: excluded`.

- [ ] **Step 3: Append Python-generic and htdp-specific blocks to `.gitignore`**

Append to the end of `.gitignore`:

```

# Python (htdp, htdp-capture, handwerk-robot-sim)
__pycache__/
*.pyc
.venv/
.mypy_cache/
.pytest_cache/
.ruff_cache/
*.rtf

# htdp
/htdp/data/
/htdp/demos/
/htdp/policy.pt
```

- [ ] **Step 4: Run htdp's test suite from its new location**

```bash
cd htdp && uv run pytest && cd ..
```

Expected: passes matching the 30 pass / 1 MuJoCo-gated-skip baseline recorded in `htdp/STATUS.md` (the skip is expected — `mujoco` is not installed by the base `uv sync`).

- [ ] **Step 5: Verify git status is clean of unwanted untracked entries**

```bash
git status --porcelain | grep '^??' | grep -E 'htdp/(\.venv|__pycache__|\.mypy_cache|\.pytest_cache|\.ruff_cache|data|demos|policy\.pt)'
```

Expected: no output (all correctly ignored).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: add human-task-dataset-pipeline as htdp/"
```

---

### Task 3: Copy `htdp-capture` into `htdp-capture/`

**Files:**
- Create (via `rsync`): `htdp-capture/` — full copy of `/Users/alexanderlemberger/htdp-capture` minus the exclusions below
- Modify: `.gitignore` (append htdp-capture's `*.xdf` pattern)

**Interfaces:**
- Consumes: nothing from Task 2 (independent Python package; its own `dev` extra pulls in `htdp` from PyPI-style local resolution only if you run `uv sync --extra dev` inside `htdp-capture/`, which this task does not require).
- Produces: a working `htdp-capture/` Python project, independently testable via `uv run pytest` from within `htdp-capture/`.

- [ ] **Step 1: Copy with exclusions**

```bash
mkdir -p htdp-capture
rsync -a \
  --exclude='.git/' \
  --exclude='.venv/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.mypy_cache/' \
  --exclude='.ruff_cache/' \
  --exclude='.pytest_cache/' \
  --exclude='.DS_Store' \
  /Users/alexanderlemberger/htdp-capture/ ./htdp-capture/
```

- [ ] **Step 2: Append htdp-capture's pattern to `.gitignore`**

Append to the end of `.gitignore`:

```

# htdp-capture
*.xdf
```

- [ ] **Step 3: Run htdp-capture's test suite from its new location**

```bash
cd htdp-capture && uv run pytest && cd ..
```

Expected: all tests pass (the OpenVR hardware tests are hardware-free per its README — they use an injected system handle).

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat: add htdp-capture as htdp-capture/"
```

---

### Task 4: Copy `handwerk-robot-sim` into `handwerk-robot-sim/`

**Files:**
- Create (via `rsync`): `handwerk-robot-sim/` — full copy of `/Users/alexanderlemberger/handwerk-robot-sim` minus the exclusions below (note: `models/h1_hand/` IS git-tracked in the source repo and must be included; only `models/ur5e/` is excluded — it's fetched separately by `setup_model.sh`)
- Modify: `.gitignore` (append handwerk-specific anchored pattern)

**Interfaces:**
- Produces: `handwerk-robot-sim/` containing `sim/*.py` (including the carried-over uncommitted edit to `sim/trowel_h1.py`), `models/h1_hand/`, `docs/`, `Dockerfile`, `setup_model.sh`, `requirements*.txt`.

- [ ] **Step 1: Copy with exclusions**

```bash
mkdir -p handwerk-robot-sim
rsync -a \
  --exclude='.git/' \
  --exclude='.venv/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.DS_Store' \
  --exclude='models/ur5e/' \
  --exclude='MUJOCO_LOG.TXT' \
  /Users/alexanderlemberger/handwerk-robot-sim/ ./handwerk-robot-sim/
```

- [ ] **Step 2: Verify `models/h1_hand/` came along and `models/ur5e/` did not**

```bash
ls handwerk-robot-sim/models/h1_hand/h1_hand.xml handwerk-robot-sim/models/h1_hand/scene.xml
ls handwerk-robot-sim/models/ur5e 2>&1 | grep -q "No such file" && echo "OK: excluded"
```

Expected: first `ls` lists both files; second prints `OK: excluded`.

- [ ] **Step 3: Verify the uncommitted `trowel_h1.py` edit came through**

```bash
diff /Users/alexanderlemberger/handwerk-robot-sim/sim/trowel_h1.py handwerk-robot-sim/sim/trowel_h1.py
```

Expected: no diff output (both are the current, edited working-tree version — the source repo's edit was never committed there either, so this just confirms the copy captured the live file, not a stale committed one).

- [ ] **Step 4: Append handwerk's pattern to `.gitignore`**

Append to the end of `.gitignore`:

```

# handwerk-robot-sim
/handwerk-robot-sim/models/ur5e/
```

- [ ] **Step 5: Syntax-check the sim modules (no MuJoCo install / GUI required)**

```bash
python3 -m py_compile handwerk-robot-sim/sim/__init__.py handwerk-robot-sim/sim/ik.py handwerk-robot-sim/sim/trowel_h1.py handwerk-robot-sim/sim/trowel_h1_hand.py handwerk-robot-sim/sim/ws_server.py
echo "exit: $?"
```

Expected: `exit: 0`, no `SyntaxError` output. (A full `mjpython sim/zigzag_demo.py`/`trowel_h1.py` run is out of scope for this task per the design spec — it needs MuJoCo installed and a GUI.)

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: add handwerk-robot-sim as handwerk-robot-sim/"
```

---

### Task 5: Copy `neurofeedback-lang-app` into `neurofeedback-lang-app/`

**Files:**
- Create (via `rsync`): `neurofeedback-lang-app/` — full copy of `/Users/alexanderlemberger/neurofeedback-lang-app` minus the exclusions below
- Modify: `.gitignore` (append neurofeedback-specific blocks)

**Interfaces:**
- Produces: a working `neurofeedback-lang-app/` Angular project, independently testable via `npm run build` from within `neurofeedback-lang-app/` (after `npm install`, since `node_modules/` is excluded from the copy).

- [ ] **Step 1: Copy with exclusions**

```bash
mkdir -p neurofeedback-lang-app
rsync -a \
  --exclude='.git/' \
  --exclude='node_modules/' \
  --exclude='.angular/' \
  --exclude='dist/' \
  --exclude='.DS_Store' \
  --exclude='.claude/' \
  --exclude='.superpowers/' \
  --exclude='.agents/' \
  --exclude='.aider*' \
  /Users/alexanderlemberger/neurofeedback-lang-app/ ./neurofeedback-lang-app/
```

- [ ] **Step 2: Verify size is sane (should be well under 100MB, not the original 4.3GB)**

```bash
du -sh neurofeedback-lang-app
```

Expected: a few tens of MB at most (the 3.7GB `.angular/` build cache and 590MB `node_modules/` were excluded).

- [ ] **Step 3: Append neurofeedback-lang-app's blocks to `.gitignore`**

Append to the end of `.gitignore`:

```

# neurofeedback-lang-app
/neurofeedback-lang-app/tmp/
/neurofeedback-lang-app/out-tsc/
/neurofeedback-lang-app/bazel-out/
/neurofeedback-lang-app/.angular/
/neurofeedback-lang-app/connect.lock
/neurofeedback-lang-app/typings/
/neurofeedback-lang-app/docs/local-model/BUNDLE.md
npm-debug.log
yarn-error.log
libpeerconnection.log
testem.log
Thumbs.db
.idea/
.project
.classpath
.c9/
*.launch
.settings/
*.sublime-workspace
.vscode/*
!.vscode/settings.json
!.vscode/tasks.json
!.vscode/launch.json
!.vscode/extensions.json
.history/*
.sass-cache/
.aider*
```

- [ ] **Step 4: Install dependencies and build from the new location**

```bash
cd neurofeedback-lang-app && npm install && npm run build && cd ..
```

Expected: `npm install` completes, `npm run build` (`ng build`) completes without errors.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: add neurofeedback-lang-app as neurofeedback-lang-app/"
```

Note: this task does not commit `neurofeedback-lang-app/node_modules/` (excluded from copy and covered by the generic `node_modules/` rule already at the top of `.gitignore`).

---

### Task 6: Root README, drop the dead stub, final cross-project verification

**Files:**
- Create: `README.md` (repo root — does not exist yet; the old one moved to `so-arm100/README.md` in Task 1)
- Delete: `/Users/alexanderlemberger/human-aware-robotic/` (standalone folder, outside this repo)

**Interfaces:**
- Consumes: the final state of all five project folders from Tasks 1–5.
- Produces: nothing further consumes this task — it's the last one in the plan.

- [ ] **Step 1: Write the root README**

Create `README.md` at the repo root with this content:

```markdown
# Robotics monorepo

Five self-contained projects, each in its own top-level folder with its own
build tooling. None of them share code or dependencies with each other.

## SO-ARM100 hardware control

- **`so-arm100/`** — React/Vite/TS teleoperation UI and Python training
  scripts for the physical SO-ARM100 arm: joint control, kinematics, dataset
  recording, and SmolVLA/ACT policy fine-tuning. See `so-arm100/AGENTS.md`
  for setup, hardware state, and current dataset/checkpoint status.

## Human-task capture / imitation learning

These four form one family: a consent-based pipeline for capturing human
task demonstrations and training imitation-learning policies from them,
independent of the SO-ARM100 hardware above.

- **`htdp/`** — `human-task-dataset-pipeline`: the core `htdp` CLI (ingest,
  validate, process, QC, package, export, replay) plus a from-scratch
  MuJoCo + LeRobot + ACT visuomotor imitation-learning research loop on a
  Franka Panda. See `htdp/STATUS.md` and `htdp/README.md`.
- **`htdp-capture/`** — hardware capture companion to `htdp`: VIVE tracker
  poses (OpenVR) and EEG streams over LSL, written out as `.xdf` for
  `htdp ingest`. See `htdp-capture/README.md`.
- **`handwerk-robot-sim/`** — a MuJoCo cobot simulation (UR5e troweling
  demo), a stand-in for the future cobot that would consume `htdp` releases
  of captured Handwerk (craft) skill data. See `handwerk-robot-sim/README.md`.
- **`neurofeedback-lang-app/`** — the original Angular control-center app
  that `htdp` was spun off from on 2026-06-20; still cross-linked as a
  companion dashboard.

## Working in this repo

Each project folder is independently installable and runnable — `cd` into
it and follow that project's own README. There is no root-level build step
that spans all five.
```

- [ ] **Step 2: Delete the dead stub folder**

```bash
rm -rf /Users/alexanderlemberger/human-aware-robotic
```

- [ ] **Step 3: Verify it's gone**

```bash
ls /Users/alexanderlemberger/human-aware-robotic 2>&1 | grep -q "No such file" && echo "OK: deleted"
```

Expected: `OK: deleted`.

- [ ] **Step 4: Final cross-project verification pass**

```bash
echo "--- so-arm100 ---" && (cd so-arm100 && npm run lint)
echo "--- htdp ---" && (cd htdp && uv run pytest -q)
echo "--- htdp-capture ---" && (cd htdp-capture && uv run pytest -q)
echo "--- handwerk-robot-sim ---" && python3 -m py_compile handwerk-robot-sim/sim/*.py && echo "syntax OK"
echo "--- neurofeedback-lang-app ---" && (cd neurofeedback-lang-app && npm run build)
```

Expected: every section reports success (same pass/fail bar as each task's own verification step — this is a regression check that nothing in a later task's `.gitignore` edits or file placement broke an earlier one).

- [ ] **Step 5: Confirm final top-level layout**

```bash
ls -la
git status
```

Expected root entries: `.claude/`, `.git/`, `.gitignore`, `.superpowers/`, `README.md`, `handwerk-robot-sim/`, `htdp/`, `htdp-capture/`, `neurofeedback-lang-app/`, `so-arm100/`. `git status` shows a clean tree (everything from this task committed in Step 6).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "docs: add root README tying the five projects together"
```

---

## Post-plan (not part of this plan, for the user to decide separately)

- Whether/when to merge `chore/monorepo-consolidation` into `agent/ollama-and-feetech-control` or `master`.
- Whether to eventually delete the four now-superseded standalone folders (`human-task-dataset-pipeline`, `htdp-capture`, `handwerk-robot-sim`, `neurofeedback-lang-app`) and their remotes, or keep them as backups.
- Rotating the HuggingFace token found in `handwerk-robot-sim`'s local `.git/config` (unrelated to this merge, flagged separately).
