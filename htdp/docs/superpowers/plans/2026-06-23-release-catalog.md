# Release-Level Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `htdp catalog-releases <releases_dir> <out.parquet>` — a deterministic one-row-per-release Parquet inventory built from each release's `manifest.json`.

**Architecture:** Extend `src/htdp/catalog.py` with `scan_releases` + `build_release_catalog`, mirroring the slice-11 `scan_sessions`/`build_catalog` pattern (fail-fast `CatalogError`, sorted determinism, `pl.DataFrame(...).select(...).write_parquet`). Manifest-driven — read the `DatasetRelease` model from `manifest.json`, no walk of `data/`. Add a `catalog-releases` CLI command.

**Tech Stack:** Python, polars (core), pydantic (manifest validation), typer (CLI), pytest.

## Global Constraints

- No new dependency, no new module, no schema change → no JSON-Schema re-export.
- `src/htdp/catalog.py` is already in the mypy gate — code must pass `mypy` strict.
- Build-only (no query — query is a separate potential slice).
- Manifest-driven: read `release_dir/manifest.json` as `DatasetRelease`; do not walk `data/`.
- Determinism: rows sorted by `release_name`; `session_ids` and `absent_modalities` sorted before comma-joining; `polars.write_parquet` byte-identical for identical input.
- Fail-fast: missing/not-a-dir releases dir → `CatalogError`; no release subdirs (none contain `manifest.json`) → `CatalogError`; malformed manifest → `CatalogError`.
- A subdir WITHOUT `manifest.json` is silently skipped (not a release), not an error.
- Verified live: `package_release([...], "relA", ReleaseProfile.COMMERCIAL_DATASET, raw_root, releases_root)` returns the release dir; its `manifest.json` has `profile="commercial_dataset"`, `session_ids=["synth-0001"]`, `absent_modalities=["eeg","video"]`, and a `manifest_sha256`. The release dir is named by the passed name (`relA`) directly under `releases_root`.
- `DatasetRelease` fields (`src/htdp/schemas/models.py`): `release_name: str`, `profile: str`, `session_ids: list[str]`, `absent_modalities: list[str]`, `manifest_sha256: str`.
- `src/htdp/catalog.py` currently imports `from pathlib import Path`, `import polars as pl`, `from pydantic import ValidationError`, `from htdp.schemas.models import DeviceConfig, Session`.

---

### Task 1: `scan_releases` + `build_release_catalog`

**Files:**
- Modify: `src/htdp/catalog.py` (add `DatasetRelease` import, `_RELEASE_COLUMNS`, `scan_releases`, `build_release_catalog`)
- Test: `tests/test_catalog.py` (append)

**Interfaces:**
- Consumes: `DatasetRelease` from `htdp.schemas.models`; existing `CatalogError`.
- Produces:
  - `scan_releases(releases_dir: Path) -> list[dict[str, str | int]]` — one dict per release, sorted by `release_name`, keys = `_RELEASE_COLUMNS`.
  - `build_release_catalog(releases_dir: Path, out_path: Path) -> Path` — writes the Parquet, returns `out_path`.
  - `_RELEASE_COLUMNS = ["release_name", "profile", "n_sessions", "session_ids", "absent_modalities", "manifest_sha256"]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_catalog.py` (the imports `Path`, `pl`, `pytest`, `generate_session`, `build_catalog` are already at the top; add the two new imports inside the test or at top as shown):

```python
def _two_releases(tmp_path: Path) -> Path:
    from htdp.release.package import package_release
    from htdp.schemas.enums import ReleaseProfile

    generate_session(tmp_path / "raw", seed=1)
    generate_session(tmp_path / "raw", seed=2)
    releases = tmp_path / "releases"
    package_release(["synth-0001"], "relA", ReleaseProfile.COMMERCIAL_DATASET, tmp_path / "raw", releases)
    package_release(
        ["synth-0001", "synth-0002"], "relB", ReleaseProfile.COMMERCIAL_DATASET, tmp_path / "raw", releases
    )
    return releases


def test_scan_releases_rows(tmp_path: Path):
    from htdp.catalog import scan_releases

    rows = scan_releases(_two_releases(tmp_path))
    assert [r["release_name"] for r in rows] == ["relA", "relB"]  # sorted
    by_name = {r["release_name"]: r for r in rows}
    assert by_name["relA"]["profile"] == "commercial_dataset"
    assert by_name["relA"]["n_sessions"] == 1
    assert by_name["relA"]["session_ids"] == "synth-0001"
    assert by_name["relA"]["absent_modalities"] == "eeg,video"
    assert by_name["relB"]["n_sessions"] == 2
    assert by_name["relB"]["session_ids"] == "synth-0001,synth-0002"


def test_build_release_catalog(tmp_path: Path):
    import json

    from htdp.catalog import _RELEASE_COLUMNS, build_release_catalog

    releases = _two_releases(tmp_path)
    out = build_release_catalog(releases, tmp_path / "rel.parquet")
    df = pl.read_parquet(out)
    assert df.columns == _RELEASE_COLUMNS
    assert df.height == 2
    sha = json.loads((releases / "relA" / "manifest.json").read_text(encoding="utf-8"))[
        "manifest_sha256"
    ]
    got = df.filter(pl.col("release_name") == "relA")["manifest_sha256"].to_list()[0]
    assert got == sha


def test_build_release_catalog_deterministic(tmp_path: Path):
    from htdp.catalog import build_release_catalog

    releases = _two_releases(tmp_path)
    a = build_release_catalog(releases, tmp_path / "a.parquet")
    b = build_release_catalog(releases, tmp_path / "b.parquet")
    assert a.read_bytes() == b.read_bytes()


def test_scan_releases_missing_dir_raises(tmp_path: Path):
    from htdp.catalog import CatalogError, scan_releases

    with pytest.raises(CatalogError):
        scan_releases(tmp_path / "nope")


def test_scan_releases_empty_dir_raises(tmp_path: Path):
    from htdp.catalog import CatalogError, scan_releases

    (tmp_path / "empty").mkdir()
    with pytest.raises(CatalogError):
        scan_releases(tmp_path / "empty")


def test_scan_releases_skips_non_release_subdir(tmp_path: Path):
    from htdp.catalog import CatalogError, scan_releases

    root = tmp_path / "releases"
    (root / "not-a-release").mkdir(parents=True)  # no manifest.json
    with pytest.raises(CatalogError):  # no release subdirs at all
        scan_releases(root)
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_catalog.py -k "release" -v`
Expected: FAIL — `ImportError: cannot import name 'scan_releases'` (and `build_release_catalog`, `_RELEASE_COLUMNS`).

- [ ] **Step 3: Add the import + column list**

In `src/htdp/catalog.py`, change the models import line:

```python
from htdp.schemas.models import DatasetRelease, DeviceConfig, Session
```

Add after the existing `_COLUMNS = [...]` block:

```python
_RELEASE_COLUMNS = [
    "release_name",
    "profile",
    "n_sessions",
    "session_ids",
    "absent_modalities",
    "manifest_sha256",
]
```

- [ ] **Step 4: Add `scan_releases` + `build_release_catalog`**

Add to `src/htdp/catalog.py` (after `build_catalog`, before `query_catalog`):

```python
def scan_releases(releases_dir: Path) -> list[dict[str, str | int]]:
    """Scan a directory of packaged releases and return one row dict per release."""
    if not releases_dir.is_dir():
        raise CatalogError(f"not a directory: {releases_dir}")
    release_dirs = sorted(
        p for p in releases_dir.iterdir() if p.is_dir() and (p / "manifest.json").exists()
    )
    if not release_dirs:
        raise CatalogError(f"no releases found in {releases_dir}")

    rows: list[dict[str, str | int]] = []
    for rd in release_dirs:
        try:
            release = DatasetRelease.model_validate_json(
                (rd / "manifest.json").read_text(encoding="utf-8")
            )
        except ValidationError as exc:
            raise CatalogError(f"invalid release manifest in {rd}: {exc}") from exc
        rows.append(
            {
                "release_name": release.release_name,
                "profile": release.profile,
                "n_sessions": len(release.session_ids),
                "session_ids": ",".join(sorted(release.session_ids)),
                "absent_modalities": ",".join(sorted(release.absent_modalities)),
                "manifest_sha256": release.manifest_sha256,
            }
        )
    return sorted(rows, key=lambda r: r["release_name"])


def build_release_catalog(releases_dir: Path, out_path: Path) -> Path:
    """Build a Parquet release inventory from the given releases directory."""
    rows = scan_releases(releases_dir)
    df = pl.DataFrame(rows).select(_RELEASE_COLUMNS)
    df.write_parquet(out_path)
    return out_path
```

- [ ] **Step 5: Run to verify they pass**

Run: `uv run pytest tests/test_catalog.py -k "release" -v`
Expected: PASS (6 tests).

- [ ] **Step 6: Lint + types + full catalog suite**

Run: `uv run pytest tests/test_catalog.py -v && uv run ruff check src/htdp/catalog.py tests/test_catalog.py && uv run mypy src/htdp/catalog.py`
Expected: all pass, no ruff/mypy findings.

- [ ] **Step 7: Commit**

```bash
git add src/htdp/catalog.py tests/test_catalog.py
git commit -m "feat(catalog): scan_releases + build_release_catalog inventory"
```

---

### Task 2: `catalog-releases` CLI command

**Files:**
- Modify: `src/htdp/cli.py` (add `catalog_releases` command near `catalog`)
- Test: `tests/test_catalog.py` (append CLI tests)

**Interfaces:**
- Consumes: `build_release_catalog` + `CatalogError` from Task 1.
- Produces: CLI `htdp catalog-releases <releases_dir> <out_path>`.

- [ ] **Step 1: Write the failing CLI tests**

Append to `tests/test_catalog.py`:

```python
def test_cli_catalog_releases(tmp_path: Path):
    from typer.testing import CliRunner

    from htdp.cli import app

    releases = _two_releases(tmp_path)
    runner = CliRunner()
    ok = runner.invoke(app, ["catalog-releases", str(releases), str(tmp_path / "rel.parquet")])
    assert ok.exit_code == 0, ok.output
    assert "2 releases" in ok.output
    assert (tmp_path / "rel.parquet").exists()

    bad = runner.invoke(app, ["catalog-releases", str(tmp_path / "nope"), str(tmp_path / "x.parquet")])
    assert bad.exit_code == 1
    assert "error:" in bad.output
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_catalog.py::test_cli_catalog_releases -v`
Expected: FAIL — typer reports `No such command 'catalog-releases'` (exit code 2), so `exit_code == 0` fails.

- [ ] **Step 3: Add the CLI command**

In `src/htdp/cli.py`, add after the existing `catalog` command (mirror its structure):

```python
@app.command()
def catalog_releases(releases_dir: Path, out_path: Path) -> None:
    """Build a one-row-per-release Parquet inventory from a directory of releases."""
    import polars as pl

    from htdp.catalog import CatalogError, build_release_catalog

    try:
        out = build_release_catalog(releases_dir, out_path)
    except CatalogError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    n = pl.read_parquet(out).height
    typer.echo(f"wrote {out} ({n} releases)")
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_catalog.py::test_cli_catalog_releases -v`
Expected: PASS.

- [ ] **Step 5: Full gate**

Run: `uv run ruff format --check . && uv run ruff check . && uv run pytest && uv run mypy src/htdp/schemas src/htdp/consent src/htdp/release src/htdp/io src/htdp/ingest src/htdp/export src/htdp/catalog.py`
Expected: all pass. (Run `uv sync --extra dev --extra rosbag` first if `mypy` reports a missing numpy stub on `export/rosbag.py` — that is an env artifact, not this slice.)

- [ ] **Step 6: Commit**

```bash
git add src/htdp/cli.py tests/test_catalog.py
git commit -m "feat(catalog): add htdp catalog-releases CLI command"
```

---

### Task 3: Docs

**Files:**
- Modify: `docs/ARCHITECTURE.md` (catalog section)
- Modify: `AGENTS.md` (command list)
- Modify: `docs/ROADMAP.md` (catalog line)

**Interfaces:** none (docs only).

- [ ] **Step 1: Locate the catalog references**

Run: `grep -rn "htdp catalog" docs/ARCHITECTURE.md AGENTS.md docs/ROADMAP.md`
Expected: lines describing `catalog` / `catalog-query`.

- [ ] **Step 2: Document `catalog-releases`**

In `AGENTS.md` add a bullet: `htdp catalog-releases <releases_dir> <out.parquet>` — builds a one-row-per-release Parquet inventory (release_name, profile, n_sessions, session_ids, absent_modalities, manifest_sha256) from a directory of packaged releases (read-only). In `docs/ARCHITECTURE.md`, add to the catalog section a sentence describing the release-grain inventory and its columns alongside the session catalog. In `docs/ROADMAP.md`, note the release-level catalog landed on the catalog line. Keep wording consistent with each file's existing catalog description.

- [ ] **Step 3: Verify columns documented**

Run: `grep -rn "catalog-releases\|manifest_sha256" docs/ARCHITECTURE.md AGENTS.md`
Expected: the command and the column appear.

- [ ] **Step 4: Commit**

```bash
git add docs/ARCHITECTURE.md AGENTS.md docs/ROADMAP.md
git commit -m "docs(catalog): document catalog-releases release inventory"
```

---

## Self-Review

**1. Spec coverage:**
- `scan_releases` (fail-fast, sorted, manifest-driven) → Task 1 Step 4. ✅
- `build_release_catalog` (`select(_RELEASE_COLUMNS).write_parquet`) → Task 1 Step 4. ✅
- Columns release_name/profile/n_sessions/session_ids/absent_modalities/manifest_sha256 → `_RELEASE_COLUMNS` (Task 1 Step 3), asserted by `test_scan_releases_rows`/`test_build_release_catalog`. ✅
- n_sessions int + session_ids comma-joined sorted → asserted (`relB` → `"synth-0001,synth-0002"`, n=2). ✅
- absent_modalities comma-joined sorted (`"eeg,video"`) → asserted. ✅
- manifest_sha256 read back, not hardcoded → `test_build_release_catalog`. ✅
- Determinism → `test_build_release_catalog_deterministic`. ✅
- Errors: missing dir, empty dir, no-release subdir → three error tests. ✅
- Subdir without manifest.json skipped → `test_scan_releases_skips_non_release_subdir` (only such subdir → empty → CatalogError). ✅
- CLI `catalog-releases` + error path → Task 2. ✅
- Docs → Task 3. ✅
- No new dep/module/schema → no JSON-Schema task. ✅

**2. Placeholder scan:** No TBD/TODO; full code in every step; commands have expected output. ✅

**3. Type consistency:** `_RELEASE_COLUMNS` identical in module, `build_release_catalog.select`, and `test_build_release_catalog`. `scan_releases -> list[dict[str, str | int]]` (n_sessions int, rest str) consistent with row construction and assertions. `DatasetRelease` field names (`release_name`, `profile`, `session_ids`, `absent_modalities`, `manifest_sha256`) match the model. CLI `build_release_catalog(releases_dir, out_path)` matches Task 1's signature. ✅
