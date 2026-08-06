# IK Trajectory Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist the joint trajectory `htdp replay-ik` already computes to a CSV hand-off file via a new optional `--out PATH` (with `--force`).

**Architecture:** Enrich `IkResult` (in `src/htdp/replay/ik.py`) to carry per-step timestamps, targets, and errors that the solve loop already produces but currently discards; add a pure stdlib-`csv` writer `write_ik_trajectory` (no mujoco/mink import, so its tests run without the optional extra); wire `--out`/`--force` into the existing `replay_ik` CLI command.

**Tech Stack:** Python, stdlib `csv`, typer (CLI), pytest. IK compute uses the optional `replay` extra (mink/mujoco/daqp) — unchanged.

## Global Constraints

- No new dependency (stdlib `csv` only), no new source module, no schema change → no JSON-Schema re-export.
- `src/htdp/replay/` stays OUT of the mypy gate (unchanged policy).
- CSV only. `--out` omitted → behavior identical to today (run IK, print summary).
- `--force` mirrors the `export-release-*` overwrite convention: refuse to overwrite an existing path without it.
- Position-only IK, the vendored 5-hinge arm, `max_steps`/`ik_iters` semantics — all unchanged.
- Joint-column count derived from `len(joint_trajectory[0])` (0 if empty) — never hardcode 5 in the writer.
- The writer imports NO optional dep, so its unit tests must NOT be gated and must RUN.
- `tests/test_ik_replay.py` has a module-level `pytest.importorskip("mink")` (line 10); tests appended there inherit that gate.
- `replay_release_ik(release_dir, max_steps=50, ik_iters=10) -> IkResult` is the existing solve entry point; `IkUnavailable` is raised when the extra is missing.

---

### Task 1: Enrich `IkResult` + pure CSV writer

**Files:**
- Modify: `src/htdp/replay/ik.py` (dataclass fields, solve-loop population, new `write_ik_trajectory`)
- Create: `tests/test_ik_export.py` (writer unit tests — NOT gated)
- Test: `tests/test_ik_replay.py` (append one gated population test)

**Interfaces:**
- Consumes: existing `IkResult{joint_trajectory, max_error}`, `replay_release_ik`.
- Produces:
  - `IkResult{joint_trajectory: list[list[float]], max_error: float, timestamps: list[float], targets: list[tuple[float, float, float]], errors: list[float]}` — all four per-step lists equal length.
  - `write_ik_trajectory(result: IkResult, out_path: Path, *, force: bool = False) -> Path` — writes CSV `timestamp_s, q0..q{J-1}, target_x, target_y, target_z, tracking_error_m`; raises `FileExistsError` if `out_path` exists and not `force`.

- [ ] **Step 1: Write the writer unit tests (NOT gated)**

Create `tests/test_ik_export.py`:

```python
import csv
from pathlib import Path

import pytest

from htdp.replay.ik import IkResult, write_ik_trajectory


def _sample() -> IkResult:
    return IkResult(
        joint_trajectory=[[0.1, 0.2], [0.3, 0.4]],
        max_error=0.5,
        timestamps=[0.0, 0.1],
        targets=[(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)],
        errors=[0.1, 0.5],
    )


def test_writes_header_and_rows(tmp_path: Path):
    out = write_ik_trajectory(_sample(), tmp_path / "t.csv")
    rows = list(csv.reader(out.open(encoding="utf-8")))
    assert rows[0] == [
        "timestamp_s", "q0", "q1", "target_x", "target_y", "target_z", "tracking_error_m"
    ]
    assert len(rows) == 3
    assert rows[1] == ["0.0", "0.1", "0.2", "1.0", "2.0", "3.0", "0.1"]


def test_refuses_overwrite_without_force(tmp_path: Path):
    p = tmp_path / "t.csv"
    write_ik_trajectory(_sample(), p)
    with pytest.raises(FileExistsError):
        write_ik_trajectory(_sample(), p)


def test_force_overwrites(tmp_path: Path):
    p = tmp_path / "t.csv"
    p.write_text("OLD", encoding="utf-8")
    write_ik_trajectory(_sample(), p, force=True)
    assert "OLD" not in p.read_text(encoding="utf-8")


def test_empty_result_header_only(tmp_path: Path):
    out = write_ik_trajectory(IkResult([], 0.0, [], [], []), tmp_path / "e.csv")
    rows = list(csv.reader(out.open(encoding="utf-8")))
    assert rows == [["timestamp_s", "target_x", "target_y", "target_z", "tracking_error_m"]]
```

- [ ] **Step 2: Write the gated population test**

Append to `tests/test_ik_replay.py` (module already has `pytest.importorskip("mink")`):

```python
def test_result_carries_per_step_metadata(tmp_path: Path):
    res = replay_release_ik(_release(tmp_path), max_steps=10)
    n = len(res.joint_trajectory)
    assert n == 10
    assert len(res.timestamps) == n
    assert len(res.targets) == n
    assert len(res.errors) == n
    assert res.max_error == max(res.errors)
    assert all(len(t) == 3 for t in res.targets)
```

- [ ] **Step 3: Run both to verify they fail**

Run: `uv run pytest tests/test_ik_export.py tests/test_ik_replay.py::test_result_carries_per_step_metadata -v`
Expected: FAIL — `test_ik_export.py` fails at import (`cannot import name 'write_ik_trajectory'`); the population test fails with `IkResult.__init__() missing ... arguments` / `AttributeError` for `timestamps`.

- [ ] **Step 4: Enrich the dataclass**

In `src/htdp/replay/ik.py`, replace the `IkResult` dataclass:

```python
@dataclass
class IkResult:
    joint_trajectory: list[list[float]]
    max_error: float
    timestamps: list[float]
    targets: list[tuple[float, float, float]]
    errors: list[float]
```

- [ ] **Step 5: Populate the new lists in the solve loop**

In `replay_release_ik`, replace the loop and return (from `n = min(...)` through `return IkResult(...)`):

```python
    n = min(max_steps, len(wrist))
    trajectory: list[list[float]] = []
    timestamps: list[float] = []
    targets: list[tuple[float, float, float]] = []
    errors: list[float] = []
    max_error = 0.0
    for i in range(n):
        t, x, y, z = wrist[i]
        target = np.array([x, y, z])
        task.set_target(SE3.from_translation(target))
        for _ in range(ik_iters):
            vel = mink.solve_ik(cfg, [task], dt, "daqp", limits=limits)
            cfg.integrate_inplace(vel, dt)
        mujoco.mj_forward(model, cfg.data)
        trajectory.append([float(q) for q in cfg.data.qpos])
        err = float(np.linalg.norm(cfg.data.xpos[eid] - target))
        timestamps.append(float(t))
        targets.append((float(x), float(y), float(z)))
        errors.append(err)
        max_error = max(max_error, err)
    return IkResult(
        joint_trajectory=trajectory,
        max_error=max_error,
        timestamps=timestamps,
        targets=targets,
        errors=errors,
    )
```

- [ ] **Step 6: Add the pure CSV writer**

Add to the top of `src/htdp/replay/ik.py`, after `from pathlib import Path`:

```python
import csv
```

Add this function at module level (e.g. after `replay_release_ik`):

```python
def write_ik_trajectory(result: IkResult, out_path: Path, *, force: bool = False) -> Path:
    """Write an IkResult to a CSV trajectory file. Pure stdlib — no IK deps."""
    if out_path.exists() and not force:
        raise FileExistsError(f"refusing to overwrite {out_path} (use --force)")
    joint_count = len(result.joint_trajectory[0]) if result.joint_trajectory else 0
    header = (
        ["timestamp_s"]
        + [f"q{j}" for j in range(joint_count)]
        + ["target_x", "target_y", "target_z", "tracking_error_m"]
    )
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for i in range(len(result.joint_trajectory)):
            tx, ty, tz = result.targets[i]
            writer.writerow(
                [result.timestamps[i], *result.joint_trajectory[i], tx, ty, tz, result.errors[i]]
            )
    return out_path
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `uv run pytest tests/test_ik_export.py tests/test_ik_replay.py -v`
Expected: all PASS, `test_ik_export.py` 4 tests RUN (not skipped); `test_ik_replay.py` tests RUN (mink present).

- [ ] **Step 8: Lint**

Run: `uv run ruff format --check src/htdp/replay/ik.py tests/test_ik_export.py && uv run ruff check src/htdp/replay/ik.py tests/test_ik_export.py`
Expected: pass (format the files with `uv run ruff format <files>` first if needed, then re-check).

- [ ] **Step 9: Commit**

```bash
git add src/htdp/replay/ik.py tests/test_ik_export.py tests/test_ik_replay.py
git commit -m "feat(replay): enrich IkResult + write_ik_trajectory CSV writer"
```

---

### Task 2: CLI `--out` / `--force`

**Files:**
- Modify: `src/htdp/cli.py:174-186` (`replay_ik` command)
- Test: `tests/test_ik_replay.py` (append gated CLI tests)

**Interfaces:**
- Consumes: `write_ik_trajectory(result, out, *, force)` and `IkResult` from Task 1.
- Produces: CLI `htdp replay-ik <release_dir> [--max-steps N] [--out PATH] [--force]`.

- [ ] **Step 1: Write the failing gated CLI tests**

Append to `tests/test_ik_replay.py`:

```python
def test_cli_replay_ik_out(tmp_path: Path):
    from typer.testing import CliRunner

    from htdp.cli import app

    rel = _release(tmp_path)
    out = tmp_path / "traj.csv"
    runner = CliRunner()
    result = runner.invoke(app, ["replay-ik", str(rel), "--max-steps", "10", "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert "wrote" in result.output

    import csv

    rows = list(csv.reader(out.open(encoding="utf-8")))
    assert len(rows) == 11  # header + 10 steps
    assert [c for c in rows[0] if c.startswith("q")] == ["q0", "q1", "q2", "q3", "q4"]


def test_cli_replay_ik_out_refuses_overwrite(tmp_path: Path):
    from typer.testing import CliRunner

    from htdp.cli import app

    rel = _release(tmp_path)
    out = tmp_path / "traj.csv"
    out.write_text("OLD", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(app, ["replay-ik", str(rel), "--max-steps", "5", "--out", str(out)])
    assert result.exit_code == 1
    assert "error:" in result.output

    forced = runner.invoke(
        app, ["replay-ik", str(rel), "--max-steps", "5", "--out", str(out), "--force"]
    )
    assert forced.exit_code == 0, forced.output
    assert "OLD" not in out.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_ik_replay.py -k "out" -v`
Expected: FAIL — typer reports `No such option: --out` (exit code 2), so `exit_code == 0` / `== 1` assertions fail.

- [ ] **Step 3: Extend the CLI command**

In `src/htdp/cli.py`, replace the `replay_ik` command (lines ~174-186):

```python
@app.command()
def replay_ik(
    release_dir: Path,
    max_steps: int = 50,
    out: Path | None = typer.Option(None, "--out"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Drive a robot arm along a release's wrist path via IK (headless)."""
    from htdp.replay.ik import IkUnavailable, replay_release_ik, write_ik_trajectory

    try:
        result = replay_release_ik(release_dir, max_steps=max_steps)
    except IkUnavailable as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        f"stepped {len(result.joint_trajectory)} steps, max tracking error {result.max_error:.4f} m"
    )
    if out is not None:
        try:
            written = write_ik_trajectory(result, out, force=force)
        except FileExistsError as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(1) from exc
        typer.echo(f"wrote {written} ({len(result.joint_trajectory)} steps)")
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_ik_replay.py -k "out" -v`
Expected: both PASS.

- [ ] **Step 5: Full gate**

Run: `uv run ruff format --check . && uv run ruff check . && uv run pytest`
Expected: all pass. (No mypy line needed — `replay/` and `cli.py` are not in the mypy gate.)

- [ ] **Step 6: Commit**

```bash
git add src/htdp/cli.py tests/test_ik_replay.py
git commit -m "feat(replay): add --out/--force trajectory export to replay-ik CLI"
```

---

### Task 3: Docs

**Files:**
- Modify: `docs/ARCHITECTURE.md` (replay-ik section)
- Modify: `AGENTS.md` (command list)
- Modify: `docs/ROADMAP.md` (IK / replay line)

**Interfaces:** none (docs only).

- [ ] **Step 1: Locate replay-ik references**

Run: `grep -rn "replay-ik" docs/ARCHITECTURE.md AGENTS.md docs/ROADMAP.md`
Expected: lines describing the current `replay-ik` command.

- [ ] **Step 2: Document `--out` / `--force`**

In each file, update the `replay-ik` description to note `--out PATH` writes the per-step joint trajectory CSV (`timestamp_s, q0..qN, target_x/y/z, tracking_error_m`) and `--force` overwrites an existing file. Keep wording consistent with the existing replay/export descriptions in that file. In `docs/ROADMAP.md`, note IK trajectory export landed on the IK/replay line.

- [ ] **Step 3: Verify the CSV column list is documented accurately**

Run: `grep -rn "tracking_error_m\|q0" docs/ARCHITECTURE.md AGENTS.md`
Expected: the column header appears, matching the writer's output.

- [ ] **Step 4: Commit**

```bash
git add docs/ARCHITECTURE.md AGENTS.md docs/ROADMAP.md
git commit -m "docs(replay): document replay-ik --out trajectory export"
```

---

## Self-Review

**1. Spec coverage:**
- Enrich `IkResult` (timestamps/targets/errors) → Task 1 Step 4–5; verified by `test_result_carries_per_step_metadata`. ✅
- Pure `csv` writer, no optional dep → Task 1 Step 6; `tests/test_ik_export.py` is ungated → RUNS. ✅
- Header layout + per-row format → `test_writes_header_and_rows` (exact strings). ✅
- Empty trajectory → header-only file → `test_empty_result_header_only`. ✅
- `--force` overwrite guard (`FileExistsError`) → writer + `test_refuses_overwrite_without_force` / `test_force_overwrites` + CLI `test_cli_replay_ik_out_refuses_overwrite`. ✅
- CLI `--out`/`--force`, unchanged when omitted → Task 2 Step 3 (the `if out is not None` branch leaves the existing summary path intact); existing `test_cli_replay_ik` still asserts the no-`--out` path. ✅
- Joint count derived not hardcoded → `len(result.joint_trajectory[0]) if ... else 0`. ✅
- Gated e2e/CLI tests inherit module `importorskip("mink")` → Tasks 1–2 append to `tests/test_ik_replay.py`. ✅
- Docs (ARCHITECTURE/AGENTS/ROADMAP) → Task 3. ✅
- No new dep/module/schema → no JSON-Schema task. ✅

**2. Placeholder scan:** No TBD/TODO; every code step shows full code; every command lists expected output. ✅

**3. Type consistency:** `IkResult` field names (`timestamps`, `targets`, `errors`) identical across dataclass, solve loop, writer, and tests. `write_ik_trajectory(result, out_path, *, force=False) -> Path` signature identical in writer, CLI call, and tests. `targets` is `list[tuple[float,float,float]]` everywhere; writer unpacks `tx, ty, tz`. ✅
