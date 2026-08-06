# Catalog Query Filters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `htdp catalog-query <catalog.parquet> [filters]`: read the slice-11 catalog Parquet, AND-filter by field, and print the matching `session_id`s one per line (sorted).

**Architecture:** Extend `src/htdp/catalog.py` with `query_catalog` (polars `read_parquet` + per-filter `.filter(...)`, AND semantics, `modality` via list-contains on the comma-joined `modalities` column). A new typer CLI command wraps it and prints ids to stdout. No new module, no new dependency.

**Tech Stack:** Python ≥3.11, typer, polars, pytest.

## Global Constraints

Copied verbatim from `AGENTS.md` + the spec:

- Python `>=3.11`. ruff: `line-length = 100`, `line-ending = lf`. Clean `format --check` + `check` (no `select` set → default E/F/W rules; broad `except` is allowed).
- mypy `strict = true`; `src/htdp/catalog.py` is already in the gate target.
- Edits limited to `src/htdp/catalog.py`, `src/htdp/cli.py`, `tests/test_catalog.py`, and docs. Do NOT touch other modules or any schema.
- **No new dependency** (polars core). **No persisted-schema change** → no JSON-Schema re-export.
- AND semantics across filters; `modality` = set membership on the comma-joined `modalities`; equality for the other filters. Unknown filter values match nothing (not an error). Empty result is valid (exit 0).
- Deterministic: results sorted by `session_id`.

**Verified facts (probed against the repo):**
- Catalog Parquet columns: `session_id, participant_id, protocol_id, device_config_id, consent_form_version, qc_status, processing_status, start_time_s, modalities`.
- Synth sessions (seed 1 & 2): `protocol_id="reach-grasp-place"`, `qc_status="pass"`, `modalities="events,motion"`, ids `synth-0001`/`synth-0002`.
- polars filter expressions verified live:
  - scalar: `df.filter(pl.col("protocol_id") == protocol)`
  - modality membership: `df.filter(pl.col("modalities").str.split(",").list.contains(modality))`
  - chaining `.filter(...).filter(...)` = AND.
- `polars.read_parquet` on a missing path raises `FileNotFoundError` (covered by an `is_file` guard).
- `src/htdp/catalog.py` already defines `CatalogError`, `scan_sessions`, `build_catalog`.

---

### Task 1: `catalog.py` — `query_catalog`

**Files:**
- Modify: `src/htdp/catalog.py` (add `query_catalog`)
- Test: `tests/test_catalog.py` (append)

**Interfaces:**
- Consumes: `build_catalog`, `CatalogError` (existing); `polars`.
- Produces: `query_catalog(catalog_path: Path, *, protocol: str | None = None, qc_status: str | None = None, participant: str | None = None, processing_status: str | None = None, modality: str | None = None) -> list[str]` — sorted matching `session_id`s; AND across provided filters; `modality` = membership in the comma-joined modalities; missing/unreadable catalog → `CatalogError`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_catalog.py`:

```python
def test_query_no_filters_returns_all(tmp_path: Path):
    generate_session(tmp_path / "raw", seed=1)
    generate_session(tmp_path / "raw", seed=2)
    cat = build_catalog(tmp_path / "raw", tmp_path / "c.parquet")
    from htdp.catalog import query_catalog

    assert query_catalog(cat) == ["synth-0001", "synth-0002"]


def test_query_protocol_filter(tmp_path: Path):
    generate_session(tmp_path / "raw", seed=1)
    cat = build_catalog(tmp_path / "raw", tmp_path / "c.parquet")
    from htdp.catalog import query_catalog

    assert query_catalog(cat, protocol="reach-grasp-place") == ["synth-0001"]
    assert query_catalog(cat, protocol="nope") == []


def test_query_modality_membership(tmp_path: Path):
    generate_session(tmp_path / "raw", seed=1)
    generate_session(tmp_path / "raw", seed=2)
    cat = build_catalog(tmp_path / "raw", tmp_path / "c.parquet")
    from htdp.catalog import query_catalog

    assert query_catalog(cat, modality="motion") == ["synth-0001", "synth-0002"]
    assert query_catalog(cat, modality="eeg") == []


def test_query_and_semantics(tmp_path: Path):
    generate_session(tmp_path / "raw", seed=1)
    cat = build_catalog(tmp_path / "raw", tmp_path / "c.parquet")
    from htdp.catalog import query_catalog

    assert query_catalog(cat, protocol="reach-grasp-place", qc_status="pass") == ["synth-0001"]
    assert query_catalog(cat, protocol="reach-grasp-place", qc_status="fail") == []


def test_query_missing_catalog_raises(tmp_path: Path):
    from htdp.catalog import CatalogError, query_catalog

    with pytest.raises(CatalogError):
        query_catalog(tmp_path / "nope.parquet")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_catalog.py -k query -v`
Expected: FAIL — `ImportError: cannot import name 'query_catalog'`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/htdp/catalog.py` (the module already imports `polars as pl`, `Path`, and defines `CatalogError`):

```python
def query_catalog(
    catalog_path: Path,
    *,
    protocol: str | None = None,
    qc_status: str | None = None,
    participant: str | None = None,
    processing_status: str | None = None,
    modality: str | None = None,
) -> list[str]:
    if not catalog_path.is_file():
        raise CatalogError(f"catalog not found: {catalog_path}")
    try:
        df = pl.read_parquet(catalog_path)
    except Exception as exc:  # noqa: BLE001 -- surface any unreadable parquet as CatalogError
        raise CatalogError(f"cannot read catalog {catalog_path}: {exc}") from exc

    if protocol is not None:
        df = df.filter(pl.col("protocol_id") == protocol)
    if qc_status is not None:
        df = df.filter(pl.col("qc_status") == qc_status)
    if participant is not None:
        df = df.filter(pl.col("participant_id") == participant)
    if processing_status is not None:
        df = df.filter(pl.col("processing_status") == processing_status)
    if modality is not None:
        df = df.filter(pl.col("modalities").str.split(",").list.contains(modality))

    return sorted(df["session_id"].to_list())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_catalog.py -k query -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Lint + type-check**

Run:
```bash
uv run ruff format src/htdp/catalog.py tests/test_catalog.py
uv run ruff check src/htdp/catalog.py tests/test_catalog.py
uv run mypy src/htdp/catalog.py
```
Expected: ruff clean; mypy `Success`. (The `# noqa: BLE001` is harmless if ruff's default ruleset doesn't enable BLE001 — ruff ignores unknown-but-valid noqa codes silently. If `ruff check` reports the noqa itself as **unused** (RUF100), remove the `# noqa: BLE001` comment and re-run.)

- [ ] **Step 6: Commit**

```bash
git add src/htdp/catalog.py tests/test_catalog.py
git commit -m "feat(catalog): query_catalog AND-filter returning session_ids"
```

---

### Task 2: CLI `catalog-query` + docs + gate

**Files:**
- Modify: `src/htdp/cli.py` (add command)
- Test: `tests/test_catalog.py` (append)
- Modify: docs — `docs/ARCHITECTURE.md`, `AGENTS.md`, `docs/ROADMAP.md`

**Interfaces:**
- Consumes: `query_catalog`, `CatalogError`.
- Produces: `htdp catalog-query <catalog_path> [--protocol] [--qc] [--participant] [--processing-status] [--modality]`; prints matching session_ids one per line; exit 1 on `CatalogError`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_catalog.py`:

```python
def test_cli_catalog_query(tmp_path: Path):
    from typer.testing import CliRunner

    from htdp.cli import app

    generate_session(tmp_path / "raw", seed=1)
    generate_session(tmp_path / "raw", seed=2)
    build_catalog(tmp_path / "raw", tmp_path / "c.parquet")
    runner = CliRunner()
    ok = runner.invoke(app, ["catalog-query", str(tmp_path / "c.parquet"), "--modality", "motion"])
    assert ok.exit_code == 0, ok.output
    assert ok.output.split() == ["synth-0001", "synth-0002"]

    bad = runner.invoke(app, ["catalog-query", str(tmp_path / "missing.parquet")])
    assert bad.exit_code == 1
    assert "error:" in bad.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_catalog.py -k cli_catalog_query -v`
Expected: FAIL — no command `catalog-query` (usage error / exit 2).

- [ ] **Step 3: Write minimal implementation**

Add to `src/htdp/cli.py` after the `catalog` command:

```python
@app.command()
def catalog_query(
    catalog_path: Path,
    protocol: str | None = typer.Option(None, "--protocol"),
    qc: str | None = typer.Option(None, "--qc"),
    participant: str | None = typer.Option(None, "--participant"),
    processing_status: str | None = typer.Option(None, "--processing-status"),
    modality: str | None = typer.Option(None, "--modality"),
) -> None:
    """Print session_ids from a catalog matching the given filters (AND)."""
    from htdp.catalog import CatalogError, query_catalog

    try:
        ids = query_catalog(
            catalog_path,
            protocol=protocol,
            qc_status=qc,
            participant=participant,
            processing_status=processing_status,
            modality=modality,
        )
    except CatalogError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    for session_id in ids:
        typer.echo(session_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_catalog.py -k cli_catalog_query -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Update docs**

`docs/ARCHITECTURE.md` — extend the catalog note: `htdp catalog-query <catalog.parquet>`
filters the catalog by `--protocol/--qc/--participant/--processing-status/--modality`
(AND semantics; `--modality` is set membership on the comma-joined modalities) and prints
matching `session_id`s one per line for piping.

`AGENTS.md` — add usage `htdp catalog-query <catalog.parquet> [--protocol P] [--qc Q] [--participant PID] [--processing-status S] [--modality M]`.

`docs/ROADMAP.md` — note catalog query filters landed (under the multi-session catalog item).

- [ ] **Step 6: Run the full gate**

Run:
```bash
uv run ruff format --check . && uv run ruff check .
uv run pytest
uv run mypy src/htdp/schemas src/htdp/consent src/htdp/release src/htdp/io src/htdp/ingest src/htdp/export src/htdp/catalog.py
```
Expected: ruff clean; pytest all pass (catalog tests RUN — no optional-dep gate; only the pre-existing mujoco-replay test may skip if the `replay` binary is absent); mypy `Success`.

- [ ] **Step 7: Commit**

```bash
git add src/htdp/cli.py tests/test_catalog.py docs/ARCHITECTURE.md AGENTS.md docs/ROADMAP.md
git commit -m "feat(catalog): add htdp catalog-query CLI command + docs"
```

---

## Self-Review

**Spec coverage** (`2026-06-22-catalog-query-filters-design.md`):
- `query_catalog(catalog_path, *, protocol, qc_status, participant, processing_status, modality) -> list[str]`, AND semantics, modality membership, sorted ids → Task 1 Step 3. ✓
- Missing/unreadable catalog → `CatalogError` → Task 1 (`is_file` guard + read try/except) + test. ✓
- Unknown filter value = empty match (not error) → Task 1 tests (`protocol="nope"`, `qc_status="fail"`, `modality="eeg"` → `[]`). ✓
- CLI `catalog-query` (`--qc`→qc_status, `--processing-status`→processing_status), session_ids one per line, exit 1 on error → Task 2. ✓
- Determinism (sorted) → Task 1 Step 3 `sorted(...)` + tests. ✓
- Docs (ARCHITECTURE, AGENTS, ROADMAP), no new dep, no schema re-export → Task 2 + Global Constraints. ✓
- Non-goals (range filters, OR, other output formats, re-scan, rebuild) — none implemented. ✓

**No-touch check:** edits limited to `catalog.py`, `cli.py`, `tests/test_catalog.py`, docs. Other modules and schemas untouched.

**Placeholder scan:** none — every filter, the polars expressions, the synth expected ids, and the CLI option mapping are concrete and probed.

**Type consistency:** `query_catalog` keyword names (`qc_status`, `processing_status`, …) match the CLI call mapping (`--qc`→`qc_status=qc`, `--processing-status`→`processing_status=processing_status`); return `list[str]` feeds the CLI `for session_id in ids` loop and the test's `== [...]` / `.split()` assertions; `CatalogError` raised in `catalog.py`, caught in CLI; column names in the filters match the slice-11 catalog schema.
```

(end of plan)
