---
sdk: docker
app_port: 7860
---

# Handwerk Robot Sim — v1

Standalone **MuJoCo** demo: a **Universal Robots UR5e** arm performing a scripted
"troweling" zigzag. A stand-in for the future cobot that would consume captured
Handwerk skill data — so we can test/demo the concept before real cobots ship.

Runs **native on Apple Silicon (M-series)** — no Rosetta, no black viewport
(the reason we chose MuJoCo over Webots for a Mac).

## Status
- **v1 = kinematic fake**: joints are driven by a scripted pattern that *looks*
  like a troweling pass. Not yet driven by IK or by captured data.
- **Scaffolded, NOT yet run.** This was written without MuJoCo installed —
  first run is on your machine. Expect to tweak the HOME pose / pattern.

## Setup (macOS, Apple Silicon)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
chmod +x setup_model.sh && ./setup_model.sh   # fetches UR5e from mujoco_menagerie
```

## Run
```bash
source .venv/bin/activate
mjpython sim/zigzag_demo.py      # macOS: use mjpython, NOT python (GUI must run on the main thread)
```
A window opens; the arm sweeps in a troweling zigzag. Close the window to stop.

> Env already built with **Python 3.12** (`.venv/`). macOS system Python 3.9 has no
> mujoco wheel; 3.14 is too new — 3.12 has arm64 wheels. The UR5e model is fetched
> by `setup_model.sh` into `models/ur5e/`.

## Layout
```
README.md
requirements.txt
setup_model.sh        # clones mujoco_menagerie, copies the UR5e model
models/ur5e/          # UR5e model + meshes (fetched; git-ignored)
sim/
  zigzag_demo.py      # v1: load UR5e, open viewer, scripted zigzag
  ik.py               # stretch: Cartesian wall-plane target -> joint angles (DLS IK)
```

## Roadmap
- **v1** (this): scripted troweling zigzag in a window. Screen-record = the demo.
- **v1.5**: drive a real wall-plane Cartesian zigzag via `sim/ik.py`.
- **v2**: WebSocket bridge so the Angular app sends paths / embeds a view.
- **v3**: retarget *real captured IMU motion* — needs positioning (IMU position
  drifts), see the capture pilot notes. The hard, fundable part.

## Notes
- Tested target: `mujoco>=3.1` (native arm64 wheels), Python 3.10+.
- `sim/ik.py` is a starting stub — it needs the end-effector **site name** from
  `models/ur5e/ur5e.xml` (look for an `attachment_site` / wrist site) and likely
  joint-limit clamping. Not wired into v1.
