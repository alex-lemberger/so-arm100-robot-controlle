# EEG → rosbag2 Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `htdp export-release-rosbag` so each per-session bag also carries EEG: per-stream `/eeg/<stream>` (custom `htdp_msgs/msg/EegSample`, one msg per sample) plus a one-shot `/eeg/<stream>/labels` (`std_msgs/String`). EEG appears only when the consent-filtered session kept it.

**Architecture:** Extend `src/htdp/export/rosbag.py` only. Register a custom message type from an inline msgdef on the module's existing `_TYPESTORE`; copy the slice-6 `_read_eeg_csv`; add an EEG loop inside `_write_session_bag` after the events loop. No new CLI command, no new dependency (numpy ships with rosbags), no schema change.

**Tech Stack:** Python ≥3.11, pydantic v2, typer, pytest. `rosbags` (extra `rosbag`) + `pyxdf` (extra `ingest`) for the gated tests; `numpy` (transitive via rosbags).

## Global Constraints

Copied verbatim from `AGENTS.md` + the spec:

- Python `>=3.11`. mypy `strict = true` (global); `src/htdp/export` is in the gate target.
- ruff: `line-length = 100`, `line-ending = lf`. Clean `format --check` + `check`.
- **No partial writes:** EEG is additive inside the existing `Writer` context; the slice-8 source-validation order is unchanged.
- **No persisted-schema change** → no JSON-Schema re-export. **No `pyproject.toml` change** (no new dependency).
- Edits limited to `src/htdp/export/rosbag.py`, new test `tests/test_eeg_rosbag_export.py`, and docs. Do NOT touch `export/bids.py`, `export/eeg_bids.py`, the motion/events code paths' behaviour, `ingest`, `release`, `synth`, `schemas`, etc.
- EEG is **additive**: motion + events topics in EEG-bearing bags are unchanged; bags without EEG are byte-unaffected.
- Determinism is **logical** (topics, counts, values), NOT byte-identical (mcap embeds a library-version string). Tests read the bag back; never hash bytes.
- **CRITICAL false-green guard:** these tests need BOTH `rosbags` AND `pyxdf`. Before claiming green, run `uv sync --extra rosbag --extra ingest --extra dev` and confirm the new tests **RUN, not SKIP**. A prior slice shipped 3 defects hidden behind skipped optional-dep tests.

**Verified `rosbags` custom-msgdef API (probed against the installed lib, v0.11.x):**
```python
from rosbags.typesys import Stores, get_typestore, get_types_from_msg
ts = get_typestore(Stores.ROS2_HUMBLE)
ts.register(get_types_from_msg("float64 stamp\nfloat32[] data\n", "htdp_msgs/msg/EegSample"))
EegSample = ts.types["htdp_msgs/msg/EegSample"]
import numpy as np
msg = EegSample(stamp=1.5, data=np.array([1.0, 2.0, 3.0], dtype=np.float32))  # float32[] needs numpy float32 array
```
Write via `ts.serialize_cdr(msg, "htdp_msgs/msg/EegSample")`; read via a typestore that re-registers the same def, then `ts.deserialize_cdr(raw, conn.msgtype)`. Round-trip confirmed live.

**Reference — existing `rosbag.py` (slice 8), unchanged parts:** module imports `Writer`, `StoragePlugin`, the static `ros2_humble` message classes (`PoseStamped`, `Header`, `Time`, `Point`, `Pose`, `Quaternion`, `StringMsg`), `sanitize`, `Session`, `DeviceConfig`; defines `_TYPESTORE = get_typestore(Stores.ROS2_HUMBLE)`, `RosbagExportError`, `_read_csv`, `_ns`, `_pose_stamped`, `_write_session_bag`, `export_release_rosbag`. The EEG loop is added inside the existing `with Writer(...) as writer:` block in `_write_session_bag`, after the events loop.

**Reference — EEG raw format (verified):** `role == "eeg"` stream, wide CSV `streams/eeg_<id>.csv` with header `timestamp_s,<label1>,<label2>,…`, one row per sample, `rate_hz = None`. The ingest fixture names the stream `"eeg"` → `sanitize("eeg") == "eeg"` → topic `/eeg/eeg`.

**Reference — slice-6 `_read_eeg_csv` (copy verbatim into `rosbag.py`):**
```python
def _read_eeg_csv(path: Path) -> tuple[list[str], list[float], list[list[float]]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    labels = lines[0].split(",")[1:]
    timestamps: list[float] = []
    samples: list[list[float]] = []
    for line in lines[1:]:
        if not line:
            continue
        cells = line.split(",")
        timestamps.append(float(cells[0]))
        samples.append([float(c) for c in cells[1:]])
    return labels, timestamps, samples
```

---

### Task 1: `rosbag.py` — EEG support + tests

**Files:**
- Modify: `src/htdp/export/rosbag.py` (add numpy import, `get_types_from_msg` import, custom-type registration, `_read_eeg_csv`, EEG loop in `_write_session_bag`)
- Test: `tests/test_eeg_rosbag_export.py`

**Interfaces:**
- Consumes: existing `_write_session_bag`, `export_release_rosbag`, `_TYPESTORE`, `_ns`, `sanitize`, `StringMsg`, `Session`, `DeviceConfig`.
- Produces (new, internal): module constants `_EEG_SAMPLE_TYPE = "htdp_msgs/msg/EegSample"`, `_EEG_SAMPLE_MSGDEF = "float64 stamp\nfloat32[] data\n"`, registered type `_EEG_SAMPLE`; helper `_read_eeg_csv(path) -> tuple[list[str], list[float], list[list[float]]]`. `_write_session_bag` now also writes, per `role=="eeg"` stream: topic `/eeg/<sanitize(name)>` (`htdp_msgs/msg/EegSample`, one msg/sample) and `/eeg/<sanitize(name)>/labels` (`std_msgs/String`, one msg).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_eeg_rosbag_export.py
import json
from pathlib import Path

import pytest

pytest.importorskip("pyxdf")
pytest.importorskip("rosbags")

import numpy as np  # noqa: E402
from rosbags.rosbag2 import Reader  # noqa: E402
from rosbags.typesys import Stores, get_types_from_msg, get_typestore  # noqa: E402

from htdp.export.rosbag import export_release_rosbag  # noqa: E402
from htdp.io.checksums import write_checksums  # noqa: E402
from htdp.ingest.session import ingest_xdf  # noqa: E402
from htdp.release.package import package_release  # noqa: E402
from htdp.schemas.enums import ReleaseProfile  # noqa: E402
from htdp.synth.generate import generate_session  # noqa: E402
from tests._xdf_writer import build_sidecar, write_xdf  # noqa: E402

_EEG_SAMPLE_TYPE = "htdp_msgs/msg/EegSample"
_EEG_SAMPLE_MSGDEF = "float64 stamp\nfloat32[] data\n"


def _reader_typestore():
    ts = get_typestore(Stores.ROS2_HUMBLE)
    ts.register(get_types_from_msg(_EEG_SAMPLE_MSGDEF, _EEG_SAMPLE_TYPE))
    return ts


def _ingest_eeg_session(tmp_path: Path, *, keep_eeg: bool) -> Path:
    src = generate_session(tmp_path / "sr", seed=1)
    eeg = ("eeg", ["Fp1", "Fp2", "Cz"], [0.0, 0.004], [[1.0, 2.0, 3.0], [1.5, 2.5, 3.5]])
    write_xdf(src, tmp_path / "x.xdf", eeg=eeg)
    sc = tmp_path / "i.json"
    sc.write_text(
        json.dumps(build_sidecar(src, eeg=("eeg", ["Fp1", "Fp2", "Cz"]))), encoding="utf-8"
    )
    session = ingest_xdf(tmp_path / "x.xdf", sc, tmp_path / "raw" / "real-0001")
    consent = session / "consent.json"
    data = json.loads(consent.read_text(encoding="utf-8"))
    data.update(
        {
            "distribute_raw_eeg": keep_eeg,
            "commercial_use": True,
            "model_training": True,
            "third_party_access": True,
            "public_release": True,
            "internal_only": False,
        }
    )
    consent.write_text(json.dumps(data), encoding="utf-8")
    write_checksums(session)
    return package_release(
        ["real-0001"], "rel", ReleaseProfile.COMMERCIAL_DATASET,
        tmp_path / "raw", tmp_path / "releases",
    )


def test_eeg_samples_and_labels_in_bag(tmp_path: Path):
    rel = _ingest_eeg_session(tmp_path, keep_eeg=True)
    out = export_release_rosbag(rel, tmp_path / "bags")
    bag = next(p for p in out.iterdir() if p.is_dir())
    ts = _reader_typestore()
    counts: dict[str, int] = {}
    first_data: list[float] = []
    labels = ""
    with Reader(bag) as rd:
        for conn, _t, raw in rd.messages():
            counts[conn.topic] = counts.get(conn.topic, 0) + 1
            if conn.topic == "/eeg/eeg" and not first_data:
                first_data = list(ts.deserialize_cdr(raw, conn.msgtype).data)
            if conn.topic == "/eeg/eeg/labels":
                labels = ts.deserialize_cdr(raw, conn.msgtype).data
    assert counts["/eeg/eeg"] == 2  # two sample rows
    assert counts["/eeg/eeg/labels"] == 1  # one-shot labels
    assert any(t.startswith("/motion/") for t in counts)  # motion still present
    assert first_data == pytest.approx([1.0, 2.0, 3.0], abs=1e-6)
    assert labels == "Fp1,Fp2,Cz"


def test_consent_dropped_eeg_has_no_eeg_topics(tmp_path: Path):
    rel = _ingest_eeg_session(tmp_path, keep_eeg=False)
    out = export_release_rosbag(rel, tmp_path / "bags")
    bag = next(p for p in out.iterdir() if p.is_dir())
    with Reader(bag) as rd:
        topics = {c.topic for c in rd.connections}
    assert not any(t.startswith("/eeg") for t in topics)
    assert any(t.startswith("/motion/") for t in topics)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra rosbag --extra ingest --extra dev pytest tests/test_eeg_rosbag_export.py -v`
Expected: `test_eeg_samples_and_labels_in_bag` FAILS — `KeyError: '/eeg/eeg'` (no EEG topics written yet). NOT skipped (`pyxdf` + `rosbags` installed). `test_consent_dropped_eeg_has_no_eeg_topics` may already pass (no EEG written) — that is fine; the suite as a whole is red.

- [ ] **Step 3: Write minimal implementation**

In `src/htdp/export/rosbag.py`:

(a) Add a numpy import after `from pathlib import Path`:
```python
import numpy as np
```

(b) Extend the typesys import to include `get_types_from_msg`:
```python
from rosbags.typesys import Stores, get_types_from_msg, get_typestore
```

(c) Replace the existing `_TYPESTORE = get_typestore(Stores.ROS2_HUMBLE)` line with the constant block + registration:
```python
_EEG_SAMPLE_TYPE = "htdp_msgs/msg/EegSample"
_EEG_SAMPLE_MSGDEF = "float64 stamp\nfloat32[] data\n"
_TYPESTORE = get_typestore(Stores.ROS2_HUMBLE)
_TYPESTORE.register(get_types_from_msg(_EEG_SAMPLE_MSGDEF, _EEG_SAMPLE_TYPE))
_EEG_SAMPLE = _TYPESTORE.types[_EEG_SAMPLE_TYPE]
```

(d) Add `_read_eeg_csv` after the existing `_read_csv` function (copy verbatim):
```python
def _read_eeg_csv(path: Path) -> tuple[list[str], list[float], list[list[float]]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    labels = lines[0].split(",")[1:]
    timestamps: list[float] = []
    samples: list[list[float]] = []
    for line in lines[1:]:
        if not line:
            continue
        cells = line.split(",")
        timestamps.append(float(cells[0]))
        samples.append([float(c) for c in cells[1:]])
    return labels, timestamps, samples
```

(e) Inside `_write_session_bag`, add the EEG stream selection alongside the existing
`motion_streams` / `event_streams` lines (after `event_streams = ...`):
```python
    eeg_streams = [s for s in device.streams if s.role == "eeg"]
```

(f) Inside the same `with Writer(...) as writer:` block, after the events loop, add the
EEG loop:
```python
        for stream in eeg_streams:
            labels, timestamps, samples = _read_eeg_csv(raw_dir / stream.path)
            topic = f"/eeg/{sanitize(stream.name)}"
            conn = writer.add_connection(topic, _EEG_SAMPLE_TYPE, typestore=_TYPESTORE)
            for ts_s, row in zip(timestamps, samples):
                msg = _EEG_SAMPLE(stamp=ts_s, data=np.array(row, dtype=np.float32))  # type: ignore[call-arg]
                writer.write(conn, _ns(ts_s), _TYPESTORE.serialize_cdr(msg, _EEG_SAMPLE_TYPE))
            label_conn = writer.add_connection(
                f"{topic}/labels", StringMsg.__msgtype__, typestore=_TYPESTORE
            )
            first_ns = _ns(timestamps[0]) if timestamps else 0
            writer.write(
                label_conn,
                first_ns,
                _TYPESTORE.serialize_cdr(StringMsg(data=",".join(labels)), StringMsg.__msgtype__),
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --extra rosbag --extra ingest --extra dev pytest tests/test_eeg_rosbag_export.py -v`
Expected: PASS (2 passed, 0 skipped). If any test SKIPs, STOP — an extra is not synced.

- [ ] **Step 5: Lint + type-check**

Run:
```bash
uv run ruff format src/htdp/export/rosbag.py tests/test_eeg_rosbag_export.py
uv run ruff check src/htdp/export/rosbag.py tests/test_eeg_rosbag_export.py
uv run --extra rosbag --extra ingest mypy src/htdp/export
```
Expected: ruff clean; mypy `Success`. The `# type: ignore[call-arg]` on the `_EEG_SAMPLE(...)` construction covers the dynamically-fetched custom type. If mypy reports the ignore is **unused**, remove it; if it reports a different code, change the bracketed code to match mypy's reported error. Do not broaden to a bare `# type: ignore`.

- [ ] **Step 6: Commit**

```bash
git add src/htdp/export/rosbag.py tests/test_eeg_rosbag_export.py
git commit -m "feat(export): add EEG (EegSample + labels) to release rosbag2 export"
```

---

### Task 2: Docs + full gate

**Files:**
- Modify: `docs/DATA_CONTRACT.md`, `AGENTS.md`, `docs/ROADMAP.md`

**Interfaces:** none.

- [ ] **Step 1: Update docs**

`docs/DATA_CONTRACT.md` — extend the rosbag2 note: EEG-bearing sessions also emit, per
EEG stream, a sample topic `/eeg/<stream>` (custom message `htdp_msgs/msg/EegSample` =
`float64 stamp` + `float32[] data`, one message per sample) and a one-shot
`/eeg/<stream>/labels` (`std_msgs/String`, comma-joined channel names). The custom
message definition is embedded in the mcap file. EEG topics appear only when the release
kept EEG (consent inheritance).

`AGENTS.md` — note that `export-release-rosbag` now includes EEG (custom `EegSample`
message) when present; still a read-only export needing the `rosbag` extra.

`docs/ROADMAP.md` — update the "ROS 2 / rosbag2 export" line to note EEG is now included
(motion + events + EEG).

- [ ] **Step 2: Run the full gate**

Run:
```bash
uv sync --extra rosbag --extra ingest --extra dev --extra replay
uv run ruff format --check . && uv run ruff check .
uv run pytest
uv run mypy src/htdp/schemas src/htdp/consent src/htdp/release src/htdp/io src/htdp/ingest src/htdp/export
```
Expected: ruff clean; pytest all pass — the new EEG-rosbag tests RUN (not skip) because `rosbags` + `pyxdf` are synced; only the pre-existing mujoco-replay test may skip if its binary is unavailable; mypy `Success`.

**Verification gate (false-green guard):** confirm the EEG-rosbag tests show as PASSED:
`uv run pytest -rs | grep -iE "eeg_rosbag|rosbag"` must show no `SKIPPED` next to any rosbag/eeg-rosbag test.

- [ ] **Step 3: Commit**

```bash
git add docs/DATA_CONTRACT.md AGENTS.md docs/ROADMAP.md
git commit -m "docs(export): document EEG in release rosbag2 export"
```

---

## Self-Review

**Spec coverage** (`2026-06-22-eeg-rosbag-export-design.md`):
- Custom `htdp_msgs/msg/EegSample` (`float64 stamp` + `float32[] data`) registered inline → Task 1 Step 3(c). ✓
- EEG folded into `export-release-rosbag` (no new command) → Task 1 (extends `_write_session_bag`; CLI untouched). ✓
- `/eeg/<stream>` per-sample + one-shot `/eeg/<stream>/labels` String → Task 1 Step 3(f). ✓
- `data` is float32 numpy; stamp + log-time = ns → Task 1 Step 3(f). ✓
- `_read_eeg_csv` copied (no-touch on `eeg_bids.py`) → Task 1 Step 3(d). ✓
- Consent inheritance (kept → topics; dropped → none) → Task 1 both tests. ✓
- Zero-sample EEG → labels at log time 0, no samples, no raise → Task 1 Step 3(f) `first_ns = ... if timestamps else 0`; the `zip` over empty lists writes no samples. ✓
- Motion/events unchanged, EEG additive → Task 1 test asserts motion topics still present. ✓
- Determinism = read-back, not byte hash → Task 1 tests reopen via `Reader`. ✓
- Double-gated tests must RUN not SKIP → Global Constraints + Task 1 Steps 2/4 + Task 2 Step 2 grep. ✓
- No new dependency / no schema re-export / no `pyproject.toml` change → Global Constraints; Task 1 touches only `rosbag.py` + test. ✓
- Docs (DATA_CONTRACT, AGENTS, ROADMAP) → Task 2. ✓
- Non-goals (new command, sensor_msgs, fs sidecar, per-channel topics, single-raw cmd) — none implemented. ✓

**No-touch check:** edits limited to `export/rosbag.py`, new `tests/test_eeg_rosbag_export.py`, docs. `export/bids.py`, `export/eeg_bids.py`, motion/events behaviour, ingest, release, synth, schemas untouched.

**Placeholder scan:** none — msgdef, topic names, field mapping, the copied `_read_eeg_csv`, the consent flags, and the fixture are all concrete and use the probed `rosbags` API.

**Type consistency:** `_EEG_SAMPLE_TYPE` / `_EEG_SAMPLE_MSGDEF` constants match between the module (Task 1 Step 3c) and the test's reader registration (Step 1); `_read_eeg_csv` return shape `(labels, timestamps, samples)` matches its use in the EEG loop; topic `/eeg/<sanitize(name)>` + `/labels` suffix consistent between writer (Step 3f) and test assertions; `_EEG_SAMPLE(stamp=…, data=np.float32 array)` matches the verified construction signature; `StringMsg` reused from slice 8 for `/labels`.
