# Integration — Angular dashboard ↔ `htdp` robot-learning pipeline

Two repos, one system. This document is the shared seam so you can work from either side.

## The two halves

| Repo | Path | Role | Toolchain |
|------|------|------|-----------|
| **neurofeedback-lang-app** | `~/neurofeedback-lang-app` | Control-center **frontend**: `/lab` section views pipeline status + runs jobs; also the neurofeedback/language-learning + Handwerk capture app. | Angular 19, npm |
| **human-task-dataset-pipeline** | `~/human-task-dataset-pipeline` | The **product + ML**: consent-based dataset pipeline (`htdp` CLI) and the robot-arm learning arc (MuJoCo + LeRobot + ACT, visuomotor policy). Serves the dashboard via `htdp serve`. | Python 3.11, uv |

**Boundary (do not erode):** the pipeline is a standalone product — "the dataset release is the product unit, the app is a consumer." Keep them as separate repos. Don't monorepo; don't pull Angular concerns into the pipeline.

## The seam: `htdp serve`

The pipeline exposes a read-only + job-runner FastAPI surface (optional `serve` extra, localhost-only) that the Angular app consumes.

- Server: `cd ~/human-task-dataset-pipeline && uv sync --extra serve && uv run htdp serve` → `http://localhost:8000`.
- Endpoints: `GET /health`, `GET /status`, `GET /jobs`, `GET /jobs/{id}`, `POST /jobs`, `POST /jobs/{id}/cancel`, `WS /jobs/{id}/logs`.
- Job-kind allowlist (sub-project A): `synth`, `gen-demos`, `train-policy`, `eval-policy`. (`sim-task` deferred to sub-project D.)
- App client: `src/app/core/pipeline/pipeline-api.service.ts` + models in `pipeline.models.ts`; state in `src/app/modules/lab/state/lab.state.ts`; UI in `modules/lab/`.

### Contract source of truth

The **Pydantic models in `src/htdp/serve/models.py` (pipeline) are authoritative.** The TS interfaces in `src/app/core/pipeline/pipeline.models.ts` (app) mirror them by hand. Frozen JSON shapes: `PipelineStatus`, `Job`, `JobSummary`, `JobLogMessage` (see the spec below). **Any field change must touch both sides.** (Follow-up: generate TS from the server's OpenAPI to kill drift.)

## Running the whole thing

```bash
# Terminal-free: the local launcher (tools/sim-launcher.js) can start the server for you.
cd ~/neurofeedback-lang-app && npm run dev      # ng (:4200) + launcher (:3001) together
# open http://localhost:4200/lab → "Start server" button boots htdp serve → run jobs from the UI
```

- `npm run dev` (not `npm start`) so the launcher runs; the `/lab` "Start server" button POSTs `:3001/htdp/start`.
- No Supabase needed locally: `useMockData` bypasses the login wall (prod build keeps real auth).
- Launcher env overrides: `HTDP_DIR`, `HTDP_PORT`.

## Task routing — which repo do I open?

- **ML / policy / sim / dataset / `htdp serve` work** → `~/human-task-dataset-pipeline`.
- **Dashboard / UI / `/lab` work** → `~/neurofeedback-lang-app`.
- **Contract change (endpoint or field)** → both: edit `serve/models.py` + `pipeline.models.ts` together, update this doc.

## Where context lives (both repos have their own)

- **Claude memory** is per-repo: app → `~/.claude/projects/-Users-alexanderlemberger-neurofeedback-lang-app/memory/`; pipeline → `…-human-task-dataset-pipeline/memory/`. Each `MEMORY.md` now points at the other. When a task spans both, read both indexes.
- **Specs/plans:** robot-lab spine (this integration) lives in the app repo `docs/superpowers/`. The learning arc (M1→M2.5, R1/R2) lives in the pipeline `docs/` + `docs/superpowers/` and its memory.
- **Roadmap ahead:** sub-projects B (metrics view), C (dataset/QC browser), D (Franka sim viewer + teleop-save) — each extends the seam above.
