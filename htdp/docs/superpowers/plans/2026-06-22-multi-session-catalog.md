# Multi-Session Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `htdp catalog <sessions_dir> <out.parquet>`: scan a directory of raw session folders → a deterministic one-row-per-session Parquet index (9 columns), the inventory view queryable by any Parquet tool.

**Architecture:** New single module `src/htdp/catalog.py` (mirrors `validate.py`). `scan_sessions` parses each session's `session.json` + `device_config.json` via the existing pydantic models and emits a row; `build_catalog` writes the rows to Parquet via polars. A new typer CLI command wraps it. No new dependency (polars is core).

**Tech Stack:** Python ≥3.11, pydantic v2, typer, polars, pytest.

## Global Constraints

Copied verbatim from `AGENTS.md` + the spec:

- Python `>=3.11`. ruff: `line-length = 100`, `line-ending = lf`. Clean `format --check` + `check`.
- mypy `strict = true` (global). `src/htdp/catalog.py` joins the mypy gate target (core, no optional dep).
- Edits limited to new `src/htdp/catalog.py`, new `tests/test_catalog.py`, `src/htdp/cli.py`, `AGENTS.md` (mypy line), and docs. Do NOT touch other modules or any schema.
- **No new dependency** (polars already core). **No persisted-schema change** → no JSON-Schema re-export.
- Build-only (no query filters). Raw sessions dir only (not releases).
- Deterministic: sessions sorted by id, modalities sorted, fixed column order → byte-identical Parquet rebuilds (verified: `polars.write_parquet` is byte-deterministic).
- No optional-dep gate on the catalog tests — polars + synth are in the base env, so the tests RUN unconditionally; there is no skip to guard against.

**Verified facts (probed against the repo):**
- `session.json` keys: `consent_form_version, device_config_id, participant_id, processing_status, protocol_id, qc_status, session_id, start_time_s`.
- `Session.qc_status.value == "pass"`, `Session.processing_status.value == "raw"` (string enums).
- `device_config.json` has `device_config_id, frame, streams`; each stream has a `role`. Synth roles `{motion, events}` → sorted modalities string `"events,motion"`.
- There is **NO session-level `source` field** (it exists only per-row inside events.csv). The catalog has NO `source` column.
- `polars.write_parquet` produces byte-identical files for identical input.
- Current mypy gate (`AGENTS.md`): `uv run mypy src/htdp/schemas src/htdp/consent src/htdp/release src/htdp/io src/htdp/ingest src/htdp/export`.

**Fixed column order (9):**
`session_id, participant_id, protocol_id, device_config_id, consent_form_version, qc_status, processing_status, start_time_s, modalities`

---

### Task 1: `catalog.py` — `scan_sessions` + `build_catalog`

**Files:**
- Create: `src/htdp/catalog.py`
- Test: `tests/test_catalog.py`

**Interfaces:**
- Consumes: `Session`, `DeviceConfig` (from `htdp.schemas.models`); `polars`.
- Produces:
  - `CatalogError(RuntimeError)`
  - `scan_sessions(sessions_dir: Path) -> list[dict[str, str | float]]` — one row dict per session (the 9 columns), sorted by `session_id`. Raises on missing dir / no sessions / malformed metadata.
  - `build_catalog(sessions_dir: Path, out_path: Path) -> Path` — writes the Parquet, returns `out_path`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_catalog.py
from pathlib import Path

import polars as pl
import pytest

from htdp.catalog import CatalogError, build_catalog, scan_sessions
from htdp.synth.generate import generate_session

_COLUMNS = [
    "session_id",
    "participant_id",
    "protocol_id",
    "device_config_id",
    "consent_form_version",
    "qc_status",
    "processing_status",
    "start_time_s",
    "modalities",
]


def test_build_catalog(tmp_path: Path):
    generate_session(tmp_path / "raw", seed=1)
    generate_session(tmp_path / "raw", seed=2)
    out = build_catalog(tmp_path / "raw", tmp_path / "catalog.parquet")
    df = pl.read_parquet(out)
    assert df.columns == _COLUMNS
    assert df.height == 2
    assert df["session_id"].to_list() == ["synth-0001", "synth-0002"]
    assert df["modalities"].to_list() == ["events,motion", "events,motion"]
    assert df["qc_status"].to_list() == ["pass", "pass"]
    assert df["processing_status"].to_list() == ["raw", "raw"]


def test_deterministic(tmp_path: Path):
    generate_session(tmp_path / "raw", seed=1)
    a = build_catalog(tmp_path / "raw", tmp_path / "a.parquet")
    b = build_catalog(tmp_path / "raw", tmp_path / "b.parquet")
    assert a.read_bytes() == b.read_bytes()


def test_missing_dir_raises(tmp_path: Path):
    with pytest.raises(CatalogError):
        scan_sessions(tmp_path / "nope")


def test_empty_dir_raises(tmp_path: Path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(CatalogError):
        scan_sessions(tmp_path / "empty")


def test_malformed_session_raises(tmp_path: Path):
    bad = tmp_path / "raw" / "synth-9999"
    bad.mkdir(parents=True)
    (bad / "session.json").write_text("{}", encoding="utf-8")  # no device_config.json
    with pytest.raises(CatalogError):
        scan_sessions(tmp_path / "raw")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_catalog.py -v`
Expected: FAIL — `ImportError: cannot import name 'CatalogError'` (module does not exist yet).

- [ ] **Step 3: Write minimal implementation**

Create `src/htdp/catalog.py`:

```python
from __future__ import annotations

from pathlib import Path

import polars as pl
from pydantic import ValidationError

from htdp.schemas.models import DeviceConfig, Session

_COLUMNS = [
    "session_id",
    "participant_id",
    "protocol_id",
    "device_config_id",
    "consent_form_version",
    "qc_status",
    "processing_status",
    "start_time_s",
    "modalities",
]


class CatalogError(RuntimeError):
    """Raised when a sessions directory cannot be cataloged."""


def scan_sessions(sessions_dir: Path) -> list[dict[str, str | float]]:
    if not sessions_dir.is_dir():
        raise CatalogError(f"not a directory: {sessions_dir}")
    session_dirs = sorted(
        p for p in sessions_dir.iterdir() if p.is_dir() and (p / "session.json").exists()
    )
    if not session_dirs:
        raise CatalogError(f"no sessions found in {sessions_dir}")

    rows: list[dict[str, str | float]] = []
    for sd in session_dirs:
        device_path = sd / "device_config.json"
        if not device_path.exists():
            raise CatalogError(f"session missing device_config.json: {sd}")
        try:
            session = Session.model_validate_json(
                (sd / "session.json").read_text(encoding="utf-8")
            )
            device = DeviceConfig.model_validate_json(
                device_path.read_text(encoding="utf-8")
            )
        except ValidationError as exc:
            raise CatalogError(f"invalid session metadata in {sd}: {exc}") from exc

        modalities = ",".join(sorted({s.role for s in device.streams}))
        rows.append(
            {
                "session_id": session.session_id,
                "participant_id": session.participant_id,
                "protocol_id": session.protocol_id,
                "device_config_id": session.device_config_id,
                "consent_form_version": session.consent_form_version,
                "qc_status": session.qc_status.value,
                "processing_status": session.processing_status.value,
                "start_time_s": session.start_time_s,
                "modalities": modalities,
            }
        )
    return sorted(rows, key=lambda r: r["session_id"])


def build_catalog(sessions_dir: Path, out_path: Path) -> Path:
    rows = scan_sessions(sessions_dir)
    df = pl.DataFrame(rows).select(_COLUMNS)
    df.write_parquet(out_path)
    return out_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_catalog.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Lint + type-check**

Run:
```bash
uv run ruff format src/htdp/catalog.py tests/test_catalog.py
uv run ruff check src/htdp/catalog.py tests/test_catalog.py
uv run mypy src/htdp/catalog.py
```
Expected: ruff clean; mypy `Success`. If mypy flags the polars `DataFrame(rows)` call under strict, resolve with a narrow annotation on `rows` (already `list[dict[str, str | float]]`) — do not add a blanket ignore. If `qc_status.value` / `processing_status.value` trips mypy (enum value typing), it is `str` by construction; cast is unnecessary — re-read the error before acting.

- [ ] **Step 6: Commit**

```bash
git add src/htdp/catalog.py tests/test_catalog.py
git commit -m "feat(catalog): scan_sessions + build_catalog parquet index"
```

---

### Task 2: CLI `catalog`

**Files:**
- Modify: `src/htdp/cli.py` (add command)
- Test: `tests/test_catalog.py` (append)

**Interfaces:**
- Consumes: `build_catalog`, `CatalogError`.
- Produces: `htdp catalog <sessions_dir> <out_path>`; exit 1 on `CatalogError`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_catalog.py`:

```python
def test_cli_catalog(tmp_path: Path):
    from typer.testing import CliRunner

    from htdp.cli import app

    generate_session(tmp_path / "raw", seed=1)
    generate_session(tmp_path / "raw", seed=2)
    runner = CliRunner()
    ok = runner.invoke(app, ["catalog", str(tmp_path / "raw"), str(tmp_path / "c.parquet")])
    assert ok.exit_code == 0, ok.output
    assert "2 sessions" in ok.output
    assert (tmp_path / "c.parquet").exists()

    bad = runner.invoke(app, ["catalog", str(tmp_path / "nope"), str(tmp_path / "c2.parquet")])
    assert bad.exit_code == 1
    assert "error:" in bad.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_catalog.py -k cli_catalog -v`
Expected: FAIL — no command `catalog` (usage error / exit 2).

- [ ] **Step 3: Write minimal implementation**

Add to `src/htdp/cli.py` (after an existing command, e.g. `validate` or `replay`):

```python
@app.command()
def catalog(sessions_dir: Path, out_path: Path) -> None:
    """Build a multi-session Parquet catalog from a raw sessions directory."""
    import polars as pl

    from htdp.catalog import CatalogError, build_catalog

    try:
        out = build_catalog(sessions_dir, out_path)
    except CatalogError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    n = pl.read_parquet(out).height
    typer.echo(f"wrote {out} ({n} sessions)")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_catalog.py -k cli_catalog -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add src/htdp/cli.py tests/test_catalog.py
git commit -m "feat(catalog): add htdp catalog CLI command"
```

---

### Task 3: Docs + mypy gate + full gate

**Files:**
- Modify: `AGENTS.md` (mypy gate line + usage), `docs/ARCHITECTURE.md` (or `docs/DATA_CONTRACT.md`), `docs/ROADMAP.md`

**Interfaces:** none.

- [ ] **Step 1: Update the mypy gate + docs**

In `AGENTS.md`, append `src/htdp/catalog.py` to the typecheck command so it reads:
```
Typecheck: `uv run mypy src/htdp/schemas src/htdp/consent src/htdp/release src/htdp/io src/htdp/ingest src/htdp/export src/htdp/catalog.py`
```
Also add usage to `AGENTS.md`: `htdp catalog <sessions_dir> <out.parquet>` — builds a
one-row-per-session Parquet inventory of a raw sessions directory (read-only).

`docs/ARCHITECTURE.md` — add a "Multi-session catalog" note: `htdp catalog` scans a raw
sessions directory into a deterministic 9-column Parquet index (session metadata +
derived `modalities`); the inventory/query view; build-only (query via the Parquet).

`docs/ROADMAP.md` — mark "Multi-session queryable catalog" as done.

- [ ] **Step 2: Run the full gate**

Run:
```bash
uv run ruff format --check . && uv run ruff check .
uv run pytest
uv run mypy src/htdp/schemas src/htdp/consent src/htdp/release src/htdp/io src/htdp/ingest src/htdp/export src/htdp/catalog.py
```
Expected: ruff clean; pytest all pass (the catalog tests RUN — no optional-dep gate; only the pre-existing mujoco-replay test may skip if the `replay` extra binary is absent); mypy `Success` including `catalog.py`.

- [ ] **Step 3: Commit**

```bash
git add AGENTS.md docs/ARCHITECTURE.md docs/ROADMAP.md
git commit -m "docs(catalog): document multi-session catalog + add to mypy gate"
```

---

## Self-Review

**Spec coverage** (`2026-06-22-multi-session-catalog-design.md`):
- `scan_sessions` (parse session.json + device_config.json via pydantic, row per session, sorted, errors) → Task 1 Step 3. ✓
- `build_catalog` writes 9-column Parquet → Task 1 Step 3. ✓
- 9-column schema, enums as `.value`, `modalities` = sorted unique roles, NO `source` column → Task 1 Step 3 + `_COLUMNS`. ✓
- Errors (missing dir, empty dir, malformed session) → Task 1 tests + raises. ✓
- Determinism (byte-identical rebuild) → Task 1 `test_deterministic`. ✓
- CLI `catalog` (exit 1 on `CatalogError`, prints `(n sessions)`) → Task 2. ✓
- mypy gate gains `catalog.py` → Task 3 Step 1. ✓
- Docs (ARCHITECTURE, AGENTS, ROADMAP), no schema re-export, no new dep → Task 3 + Global Constraints. ✓
- Non-goals (releases, query DSL, duration columns, append) — none implemented. ✓

**No-touch check:** edits limited to new `catalog.py`, new `tests/test_catalog.py`, `cli.py`, `AGENTS.md`, docs. Other modules and schemas untouched.

**Placeholder scan:** none — every column, value (`"pass"`, `"raw"`, `"events,motion"`), error condition, and the polars build are concrete and probed.

**Type consistency:** `_COLUMNS` identical in `catalog.py` and the test; `scan_sessions -> list[dict[str, str | float]]` feeds `pl.DataFrame(rows).select(_COLUMNS)`; `build_catalog(sessions_dir, out_path) -> Path` matches the Task 2 CLI call (`build_catalog(sessions_dir, out_path)`); `CatalogError` raised in `catalog.py`, caught in the CLI; enum `.value` strings (`"pass"`, `"raw"`) match the test assertions.
