# Catalog Range Filters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add inclusive `start_time_s` range filtering (`--start-after` / `--start-before`) to `htdp catalog-query`.

**Architecture:** Extend the existing `query_catalog` function in `src/htdp/catalog.py` with two keyword-only `float | None` params that add `>=` / `<=` polars filter branches, and surface them as two new typer options on the `catalog_query` CLI command. Read-only; reuses the slice-12 AND-merge pattern and the data-driven "empty match is not an error" rule.

**Tech Stack:** Python, polars (core dep), typer (CLI), pytest.

## Global Constraints

- No new dependency, no new module, no persisted-schema change → no JSON-Schema re-export.
- `src/htdp/catalog.py` is already in the mypy gate — code must pass `mypy` strict.
- Bounds are raw `float` Unix seconds; no date/time string parsing.
- Inclusive bounds: `start_after` → `>=`, `start_before` → `<=`.
- Inverted / out-of-range bounds match no rows (empty output, exit 0) — never an error.
- Results sorted by `session_id` (unchanged behavior).
- Synth sessions all have `start_time_s=0.0` (`src/htdp/synth/generate.py:155`); range tests must NOT use synth — build a controlled Parquet directly.
- `tests/test_catalog.py` already imports `Path`, `polars as pl`, `pytest`, and defines `_COLUMNS` (the 9 catalog columns) at module top.

---

### Task 1: Range filter logic in `query_catalog`

**Files:**
- Modify: `src/htdp/catalog.py:74-101` (`query_catalog`)
- Test: `tests/test_catalog.py` (append)

**Interfaces:**
- Consumes: existing `query_catalog(catalog_path, *, protocol, qc_status, participant, processing_status, modality) -> list[str]`.
- Produces: `query_catalog(..., start_after: float | None = None, start_before: float | None = None) -> list[str]` — two new keyword-only params; `start_after` keeps rows with `start_time_s >= start_after`, `start_before` keeps rows with `start_time_s <= start_before`; both AND with each other and all existing filters.

- [ ] **Step 1: Write a test helper + the failing range tests**

Append to `tests/test_catalog.py`:

```python
def _write_catalog(path: Path) -> Path:
    """Write a controlled 2-row catalog Parquet with distinct start_time_s.

    Synth hardcodes start_time_s=0.0, so range tests build the Parquet directly.
    """
    df = pl.DataFrame(
        {
            "session_id": ["session-a", "session-b"],
            "participant_id": ["p01", "p02"],
            "protocol_id": ["p", "p"],
            "device_config_id": ["d", "d"],
            "consent_form_version": ["v1", "v1"],
            "qc_status": ["pass", "pass"],
            "processing_status": ["raw", "raw"],
            "start_time_s": [100.0, 200.0],
            "modalities": ["events,motion", "events,motion"],
        }
    ).select(_COLUMNS)
    df.write_parquet(path)
    return path


def test_query_start_after(tmp_path: Path):
    from htdp.catalog import query_catalog

    cat = _write_catalog(tmp_path / "c.parquet")
    assert query_catalog(cat, start_after=150.0) == ["session-b"]


def test_query_start_before(tmp_path: Path):
    from htdp.catalog import query_catalog

    cat = _write_catalog(tmp_path / "c.parquet")
    assert query_catalog(cat, start_before=150.0) == ["session-a"]


def test_query_range_inclusive_both_ends(tmp_path: Path):
    from htdp.catalog import query_catalog

    cat = _write_catalog(tmp_path / "c.parquet")
    assert query_catalog(cat, start_after=100.0, start_before=200.0) == [
        "session-a",
        "session-b",
    ]


def test_query_start_after_inclusive_boundary(tmp_path: Path):
    from htdp.catalog import query_catalog

    cat = _write_catalog(tmp_path / "c.parquet")
    assert query_catalog(cat, start_after=200.0) == ["session-b"]


def test_query_inverted_range_empty(tmp_path: Path):
    from htdp.catalog import query_catalog

    cat = _write_catalog(tmp_path / "c.parquet")
    assert query_catalog(cat, start_after=200.0, start_before=100.0) == []


def test_query_range_and_existing_filter(tmp_path: Path):
    from htdp.catalog import query_catalog

    cat = _write_catalog(tmp_path / "c.parquet")
    assert query_catalog(cat, start_after=100.0, protocol="p") == [
        "session-a",
        "session-b",
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_catalog.py -k "start or range" -v`
Expected: FAIL — `TypeError: query_catalog() got an unexpected keyword argument 'start_after'`.

- [ ] **Step 3: Add the two params + filter branches**

In `src/htdp/catalog.py`, edit the `query_catalog` signature to add the two keyword-only params after `modality`:

```python
def query_catalog(
    catalog_path: Path,
    *,
    protocol: str | None = None,
    qc_status: str | None = None,
    participant: str | None = None,
    processing_status: str | None = None,
    modality: str | None = None,
    start_after: float | None = None,
    start_before: float | None = None,
) -> list[str]:
```

Then add two filter branches immediately after the existing `modality` branch (before the `return` line):

```python
    if start_after is not None:
        df = df.filter(pl.col("start_time_s") >= start_after)
    if start_before is not None:
        df = df.filter(pl.col("start_time_s") <= start_before)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_catalog.py -k "start or range" -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Run full catalog suite + lint + types**

Run: `uv run pytest tests/test_catalog.py -v && uv run ruff check src/htdp/catalog.py && uv run mypy src/htdp/catalog.py`
Expected: all pass, no ruff/mypy findings.

- [ ] **Step 6: Commit**

```bash
git add src/htdp/catalog.py tests/test_catalog.py
git commit -m "feat(catalog): start_time_s range filters in query_catalog"
```

---

### Task 2: CLI `--start-after` / `--start-before` options

**Files:**
- Modify: `src/htdp/cli.py:205-230` (`catalog_query` command)
- Test: `tests/test_catalog.py` (append)

**Interfaces:**
- Consumes: `query_catalog(..., start_after, start_before)` from Task 1.
- Produces: CLI `htdp catalog-query <catalog_path> [...] [--start-after SECONDS] [--start-before SECONDS]`, passing the floats through by name.

- [ ] **Step 1: Write the failing CLI test**

Append to `tests/test_catalog.py`:

```python
def test_cli_catalog_query_range(tmp_path: Path):
    from typer.testing import CliRunner

    from htdp.cli import app

    cat = _write_catalog(tmp_path / "c.parquet")
    runner = CliRunner()

    after = runner.invoke(app, ["catalog-query", str(cat), "--start-after", "150"])
    assert after.exit_code == 0, after.output
    assert after.output.split() == ["session-b"]

    before = runner.invoke(app, ["catalog-query", str(cat), "--start-before", "150"])
    assert before.exit_code == 0, before.output
    assert before.output.split() == ["session-a"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_catalog.py::test_cli_catalog_query_range -v`
Expected: FAIL — typer reports `No such option: --start-after` (exit code 2), so `exit_code == 0` assertion fails.

- [ ] **Step 3: Add the two options to the CLI command**

In `src/htdp/cli.py`, add two options to the `catalog_query` signature after `modality` (mirror the existing `typer.Option` style, but typed `float | None`):

```python
    modality: str | None = typer.Option(None, "--modality"),
    start_after: float | None = typer.Option(None, "--start-after"),
    start_before: float | None = typer.Option(None, "--start-before"),
) -> None:
```

And pass them through in the `query_catalog(...)` call, after `modality=modality,`:

```python
            modality=modality,
            start_after=start_after,
            start_before=start_before,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_catalog.py::test_cli_catalog_query_range -v`
Expected: PASS.

- [ ] **Step 5: Run full catalog suite + lint + types**

Run: `uv run pytest tests/test_catalog.py -v && uv run ruff check src/htdp/cli.py && uv run mypy src/htdp/catalog.py`
Expected: all pass. (`cli.py` is not in the mypy gate; the type-checked surface is `catalog.py`.)

- [ ] **Step 6: Commit**

```bash
git add src/htdp/cli.py tests/test_catalog.py
git commit -m "feat(catalog): add --start-after/--start-before to catalog-query CLI"
```

---

### Task 3: Docs

**Files:**
- Modify: `docs/ARCHITECTURE.md` (catalog-query section)
- Modify: `AGENTS.md` (command list / catalog notes)
- Modify: `docs/ROADMAP.md` (catalog line)

**Interfaces:** none (docs only).

- [ ] **Step 1: Locate the catalog-query references**

Run: `grep -rn "catalog-query" docs/ARCHITECTURE.md AGENTS.md docs/ROADMAP.md`
Expected: lines describing the existing `catalog-query` command and its filters.

- [ ] **Step 2: Document the range options**

In each file, where the `catalog-query` filters are listed, add `--start-after SECONDS` and `--start-before SECONDS` (inclusive `start_time_s` lower/upper bounds, raw Unix seconds, AND-combined with other filters). Keep wording consistent with the existing filter descriptions in that file. In `docs/ROADMAP.md`, update the catalog query line to note range filters landed.

- [ ] **Step 3: Verify no stale "range filters are a non-goal" text remains**

Run: `grep -rn "range" docs/ARCHITECTURE.md AGENTS.md docs/ROADMAP.md`
Expected: any mention now reflects that range filters EXIST (no leftover "deferred"/"non-goal" claim about range filters).

- [ ] **Step 4: Commit**

```bash
git add docs/ARCHITECTURE.md AGENTS.md docs/ROADMAP.md
git commit -m "docs(catalog): document catalog-query range filters"
```

---

## Self-Review

**1. Spec coverage:**
- Two `query_catalog` params + filter branches → Task 1. ✅
- Inclusive `>=` / `<=` semantics → Task 1 Step 3, asserted by `test_query_range_inclusive_both_ends` + `test_query_start_after_inclusive_boundary`. ✅
- AND with existing filters + each other → `test_query_range_and_existing_filter`, `test_query_range_inclusive_both_ends`. ✅
- Inverted range → empty, not error → `test_query_inverted_range_empty`. ✅
- CLI `--start-after` / `--start-before` float options → Task 2. ✅
- Controlled Parquet (not synth, since `start_time_s=0.0`) → `_write_catalog` helper. ✅
- Docs (ARCHITECTURE/AGENTS/ROADMAP) → Task 3. ✅
- No new dep / module / schema → no JSON-Schema task needed. ✅

**2. Placeholder scan:** No TBD/TODO; every code step shows full code; every command has expected output. ✅

**3. Type consistency:** `start_after` / `start_before` are `float | None` everywhere (function params, CLI options, call-through). Helper `_write_catalog` writes `start_time_s` as floats (`100.0`, `200.0`). Function name `query_catalog` and `_write_catalog` used consistently. ✅
