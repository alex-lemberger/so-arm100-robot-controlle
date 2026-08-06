# Monorepo consolidation design

**Date:** 2026-08-06
**Status:** approved by user, pending implementation plan

## Context

Five related but independently-started projects exist as standalone folders on
this machine, in different states of completeness and staleness:

1. **so-arm100-robot-controller** (this repo) — React/Vite/TS teleoperation UI
   + Python `robot_learning/` training scripts for the physical SO-ARM100 arm.
   Most recent (2026-08-06), hardware-verified, has a real 29-episode dataset
   and SmolVLA checkpoints. **This is the base.**
2. **human-aware-robotic** — a single `agent.md` prompt spec for a 2D Pygame
   human-safety-zone demo. No code was ever written, no git repo. Dead stub.
3. **human-task-dataset-pipeline** — a substantial, separately-pushed GitHub
   project (`htdp` CLI). Deliberately spun off 2026-06-20 from an Angular app
   to be pipeline-first. Targets a Franka Panda in MuJoCo with VIVE
   tracker/EEG capture — unrelated hardware/domain to the SO-ARM100 work.
   Last commit 2026-07-12.
4. **htdp-capture** — a capture companion specifically for
   human-task-dataset-pipeline (VIVE → LSL → XDF). Own GitHub repo, explicitly
   coupled to #3.
5. **handwerk-robot-sim** — a MuJoCo UR5e "troweling" demo, deployed
   standalone to a HuggingFace Space. Its own README calls it a stand-in for
   a future cobot consuming captured Handwerk skill data — a downstream
   consumer of #3, not of this repo. Stale since 2026-06-12. Has one
   uncommitted local edit (`sim/trowel_h1.py`).
6. **neurofeedback-lang-app** — not originally named by the user, discovered
   via cross-references. The original Angular app that #3 was spun off from;
   still cross-linked as of 2026-07-12.

Projects 3, 4, 5, 6 form one coherent, already-separated "human task capture /
imitation learning" family. Project 1 is a wholly separate "SO-ARM100 hardware
control" product. The user's explicit decision, after this was surfaced, is to
merge all of it into a single monorepo anyway, with each project kept
self-contained in its own top-level folder (not interleaved).

### Branch-base correction

The repo's `master` branch is a stale single-commit scaffold
(`chore: initialize project`) — none of the real SO-ARM100 work described in
`AGENTS.md` (hardware verification, dataset pipeline, SmolVLA fine-tuning)
has been merged there. All of that work lives only on
`agent/ollama-and-feetech-control` (itself 7 commits ahead of its own remote).
Branching the consolidation off `master` would consolidate the wrong,
near-empty snapshot. The consolidation branch is therefore created off
`agent/ollama-and-feetech-control` instead, not `master`.

## Decisions (confirmed with user)

- **Scope:** merge all five real projects (not #2, which is deleted outright)
  into this repo as a monorepo.
- **Structure:** monorepo with top-level sibling folders, one per project.
  Each keeps its own build tooling untouched (npm/vite for the TS apps,
  `uv`/pyproject for the Python projects).
- **Git history:** fresh copy of each project's current working-tree state.
  No `git subtree`/history graft. Original standalone folders and their
  GitHub/HF remotes are left untouched on disk — nothing is deleted or
  overwritten there.
- **Current app placement:** moved from repo root into `so-arm100/`, so all
  five projects are structurally symmetric.
- **human-aware-robotic:** deleted from disk. Nothing is lost — it was one
  unimplemented prompt file with no git history.
- **neurofeedback-lang-app:** included, alongside htdp/htdp-capture/handwerk.
- **Branch:** `chore/monorepo-consolidation`, based on
  `agent/ollama-and-feetech-control` (see correction above), not `master`.
- **htdp raw assets:** ~192MB of untracked photos/PSD/AI files in
  human-task-dataset-pipeline's root are left behind (never version-controlled
  there either). The two untracked design-doc `.md` files in the same root
  are copied in.

## Target structure

```
so-arm100-robot-controller/
├── so-arm100/              current app content, moved from root
│   (src/, server.ts, robot_learning/, package.json, AGENTS.md, docs/,
│    assets/, index.html, vite.config.ts, tsconfig.json, metadata.json, ...;
│    data/, outputs/, .venv-lerobot/, .cache/, node_modules/, dist/ stay
│    gitignored exactly as today, paths re-anchored to so-arm100/)
├── htdp/                   from human-task-dataset-pipeline
│   (src/, docs/, protocols/, ontology/, tests/, pyproject.toml, uv.lock,
│    AGENTS.md, README.md, STATUS.md, CHANGELOG.md, plus the 2 untracked
│    design docs; excludes .venv, caches, data/, demos/, policy.pt, and the
│    ~192MB of raw photo/PSD/AI files)
├── htdp-capture/           from htdp-capture
│   (src/, tests/, pyproject.toml, uv.lock, README.md; excludes .venv, caches)
├── handwerk-robot-sim/     from handwerk-robot-sim
│   (sim/ — including the current uncommitted trowel_h1.py edit — docs/,
│    Dockerfile, setup_model.sh, requirements*.txt, README.md; excludes
│    .venv, models/ [gitignored, fetched by setup_model.sh], MUJOCO_LOG.TXT,
│    .DS_Store)
├── neurofeedback-lang-app/ from neurofeedback-lang-app
│   (src/, docs/, public/, config files, AGENTS.md, CLAUDE.md, specs/,
│    plans/, tools/, supabase/, form_outside/, package.json, angular.json,
│    firebase.json, firestore.rules; excludes node_modules/, .angular/,
│    dist/, caches, .DS_Store)
└── README.md               new root README explaining the five projects and
                             how they relate (SO-ARM100 arm control vs. the
                             human-task-capture family)
```

## Mechanics

1. Branch `chore/monorepo-consolidation` off `agent/ollama-and-feetech-control`
   (done).
2. `git mv` current root content into `so-arm100/`; update internal path
   references (`.gitignore` anchors, any relative paths in configs/docs) so
   everything still works from the new location. Commit.
3. For each of htdp, htdp-capture, handwerk-robot-sim,
   neurofeedback-lang-app: copy the working tree (respecting the exclusions
   above) into its subfolder, one commit per project with a clear message.
4. Write a merged root `.gitignore`: per-project patterns, most unchanged
   (unanchored patterns like `node_modules/`, `.venv/`, `__pycache__/`,
   `dist/`, `.DS_Store` already match anywhere in the tree; anchored patterns
   like so-arm100's `/data/local/` need re-prefixing to `/so-arm100/data/local/`
   etc.).
5. Write the new root `README.md`.
6. Verify each subproject still works from its new location:
   - `so-arm100/`: `npm run lint` and `npm run build`
   - `htdp/`: `uv run pytest` (from within `htdp/`)
   - `htdp-capture/`: `uv run pytest` (from within `htdp-capture/`)
   - `handwerk-robot-sim/`: import/syntax check (no MuJoCo run required)
   - `neurofeedback-lang-app/`: `npm run build` or equivalent
7. Delete the standalone `human-aware-robotic` folder.
8. Leave the four other standalone folders (human-task-dataset-pipeline,
   htdp-capture, handwerk-robot-sim, neurofeedback-lang-app) on disk as-is —
   still valid standalone repos/HF Space, just superseded as the working copy.

## Explicitly out of scope

- Preserving per-project git history (fresh copy only).
- Interleaving code across projects, or building shared modules between the
  SO-ARM100 work and the human-task-capture family.
- Deleting or altering the four standalone source folders that get copied
  from, or their remotes.
- Rotating/removing the HuggingFace token found in handwerk-robot-sim's local
  `.git/config` — flagged to the user separately, not part of this change.
- Any code changes beyond what's needed to make each project run correctly
  from its new subfolder path.
