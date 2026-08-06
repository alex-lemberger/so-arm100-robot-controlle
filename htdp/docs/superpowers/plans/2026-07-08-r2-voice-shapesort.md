# R2 Voice Shape-Sort — Software-Only Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and unit-test every piece of the R2 voice-shape-sort pipeline that does NOT require the real SO-ARM101, a live camera, a live microphone, or a fine-tuned SmolVLA checkpoint: the command→target lookup, the classical color/shape/orientation detector (used both as the fallback grasp path and as the hole-outline locator), the control-loop/retry/fallback orchestrator, and the trial-eval aggregator (Wilson CI + failure taxonomy). Everything hardware/model-dependent is scoped out to a follow-up doc, not faked with mocked "integration" tests.

**Architecture:** New `src/htdp/shapesort/` package, following the existing `src/htdp/learn/` conventions (typer CLI wired into `src/htdp/cli.py`, `from __future__ import annotations`, a package-local `errors.py` for optional-dependency guards, `wilson_ci` reused from `htdp.learn.eval` rather than reimplemented). The orchestrator is written against `Callable` protocols for every hardware-facing operation (listen+transcribe, SmolVLA pick, classical pick, insert) so its retry/fallback logic is fully testable with plain Python fakes — no hardware, no mocking framework needed.

**Tech Stack:** Python 3.11, typer (existing), opencv-python-headless (new, contour/shape/color detection), numpy (already a transitive dep via `learn` extra), Pillow (new, only used in tests to synthesize fixture images), openai-whisper (new, declared as a dependency now so the extra is complete, but its actual `transcribe()` call is NOT exercised by any test in this plan — see Task 7).

## Global Constraints

- Reuse `wilson_ci` from `src/htdp/learn/eval.py` verbatim — do not reimplement a CI formula.
- New optional-dependency group named `shapesort` in `pyproject.toml`; do not add these deps to the base `dependencies` list or to `learn`.
- `uv sync` must be run with `--all-extras` when testing locally — `uv sync --extra X` strips other extras declaratively (known project landmine).
- Classical color/shape detection stays in the codebase permanently as the fallback path per the approved design — it is not scaffolding to delete once SmolVLA works.
- The 4-hole color/shape table (`COLOR_SHAPE_TO_HOLE`) is a placeholder built from the product photo, not the physical toy — mark it clearly in code comments as needing confirmation once the toy is in hand (open risk in the design doc).
- Every dataclass uses `@dataclass(frozen=True)` and full type hints (repo's mypy config is `strict = True`).
- No test in this plan may open a camera, a microphone, or call a network/model API. Any test needing an image uses a synthetically drawn PIL fixture; any test needing hardware behavior uses an injected fake function.

---

### Task 1: Package scaffold, optional dependency, errors module

**Files:**
- Modify: `pyproject.toml`
- Create: `src/htdp/shapesort/__init__.py`
- Create: `src/htdp/shapesort/errors.py`
- Test: `tests/shapesort/__init__.py`
- Test: `tests/shapesort/test_errors.py`

**Interfaces:**
- Produces: `htdp.shapesort.errors.ShapesortUnavailable` (a `RuntimeError` subclass), importable with no optional deps installed.

- [ ] **Step 1: Add the `shapesort` extra to `pyproject.toml`**

Edit the `[project.optional-dependencies]` table to add a new line:

```toml
shapesort = ["opencv-python-headless>=4.9", "openai-whisper>=20231117", "pillow>=10.0"]
```

- [ ] **Step 2: Create the package `__init__.py`**

```python
"""Voice-commanded shape-sort mile (R2): command grounding, classical color/shape
detection, control-loop orchestration, and trial eval. See
docs/superpowers/specs/2026-07-08-r2-voice-shapesort-design.md."""
```

Path: `src/htdp/shapesort/__init__.py`

- [ ] **Step 3: Write the failing test for the errors module**

Path: `tests/shapesort/__init__.py` — empty file (test package marker).

Path: `tests/shapesort/test_errors.py`:

```python
from __future__ import annotations

from htdp.shapesort.errors import ShapesortUnavailable


def test_shapesort_unavailable_default_message() -> None:
    err = ShapesortUnavailable()
    assert "uv sync --extra shapesort" in str(err)


def test_shapesort_unavailable_is_runtime_error() -> None:
    assert issubclass(ShapesortUnavailable, RuntimeError)
```

- [ ] **Step 4: Run test to verify it fails**

Run: `.venv/bin/pytest tests/shapesort/test_errors.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'htdp.shapesort.errors'`

- [ ] **Step 5: Write the errors module**

Path: `src/htdp/shapesort/errors.py`:

```python
from __future__ import annotations


class ShapesortUnavailable(RuntimeError):
    """Raised when an optional shapesort dependency (opencv/whisper) is not installed."""

    def __init__(self, msg: str = "install with: uv sync --extra shapesort") -> None:
        super().__init__(msg)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv/bin/pytest tests/shapesort/test_errors.py -v`
Expected: 2 passed

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/htdp/shapesort/__init__.py src/htdp/shapesort/errors.py tests/shapesort/__init__.py tests/shapesort/test_errors.py
git commit -m "feat(shapesort): package scaffold + optional dependency group"
```

---

### Task 2: Command → target-hole lookup (`vocab.py`)

**Files:**
- Create: `src/htdp/shapesort/vocab.py`
- Test: `tests/shapesort/test_vocab.py`

**Interfaces:**
- Consumes: nothing (pure module).
- Produces: `COLOR_SHAPE_TO_HOLE: dict[tuple[str, str], str]`, `parse_target(text: str) -> str | None` — used by Task 4's orchestrator and Task 3's `detect_hole`/`detect_piece` callers.

- [ ] **Step 1: Write the failing tests**

Path: `tests/shapesort/test_vocab.py`:

```python
from __future__ import annotations

import pytest

from htdp.shapesort.vocab import COLOR_SHAPE_TO_HOLE, parse_target


def test_parse_target_matches_color_and_shape() -> None:
    assert parse_target("put the green triangle into the box") == "hole_triangle_green"


def test_parse_target_case_insensitive() -> None:
    assert parse_target("PUT THE RED CIRCLE IN THE BOX") == "hole_circle_red"


def test_parse_target_ignores_extra_words() -> None:
    assert parse_target("please gently place the yellow square somewhere") == "hole_square_yellow"


def test_parse_target_unknown_color_returns_none() -> None:
    assert parse_target("put the purple triangle in the box") is None


def test_parse_target_unknown_shape_returns_none() -> None:
    assert parse_target("put the green pentagon in the box") is None


def test_parse_target_no_recognizable_phrase_returns_none() -> None:
    assert parse_target("what time is it") is None


@pytest.mark.parametrize("hole_id", list(COLOR_SHAPE_TO_HOLE.values()))
def test_every_hole_id_is_unique(hole_id: str) -> None:
    assert list(COLOR_SHAPE_TO_HOLE.values()).count(hole_id) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/shapesort/test_vocab.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'htdp.shapesort.vocab'`

- [ ] **Step 3: Write the vocab module**

Path: `src/htdp/shapesort/vocab.py`:

```python
from __future__ import annotations

# Placeholder 4-hole table built from the product photo (circle/red, square/yellow,
# triangle/green, rectangle/blue outline). CONFIRM against the physical toy during R1a
# bring-up and edit this table if the real hole colors differ — open risk noted in
# docs/superpowers/specs/2026-07-08-r2-voice-shapesort-design.md.
COLOR_SHAPE_TO_HOLE: dict[tuple[str, str], str] = {
    ("red", "circle"): "hole_circle_red",
    ("yellow", "square"): "hole_square_yellow",
    ("green", "triangle"): "hole_triangle_green",
    ("blue", "rectangle"): "hole_rectangle_blue",
}

_COLORS = {color for color, _ in COLOR_SHAPE_TO_HOLE}
_SHAPES = {shape for _, shape in COLOR_SHAPE_TO_HOLE}


def parse_target(text: str) -> str | None:
    """Extract a known (color, shape) pair from free text and map it to a hole id.

    Returns None rather than guessing when the text does not contain exactly one known
    color word and one known shape word — the orchestrator (Task 4) treats None as an
    ASR-miss and asks again instead of acting on an ambiguous command.
    """
    words = text.lower().split()
    colors_found = [w for w in words if w in _COLORS]
    shapes_found = [w for w in words if w in _SHAPES]
    if len(colors_found) != 1 or len(shapes_found) != 1:
        return None
    return COLOR_SHAPE_TO_HOLE.get((colors_found[0], shapes_found[0]))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/shapesort/test_vocab.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/htdp/shapesort/vocab.py tests/shapesort/test_vocab.py
git commit -m "feat(shapesort): color+shape command lookup (parse_target)"
```

---

### Task 3: Classical color/shape/orientation detector (`classical_detect.py`)

**Files:**
- Create: `src/htdp/shapesort/classical_detect.py`
- Test: `tests/shapesort/test_classical_detect.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (color/shape name strings only, not `vocab.py` types).
- Produces: `Detection` dataclass (`cx: int`, `cy: int`, `angle_deg: float`, `confidence: float`), `detect_piece(image: np.ndarray, color: str, shape: str) -> Detection | None`, `detect_hole(image: np.ndarray, color: str, shape: str) -> Detection | None` (alias of `detect_piece`). Consumed by Task 4's fallback/insert fakes in tests, and — later, hardware-gated — by the live grasp/insert code in Task 7's follow-up.

- [ ] **Step 1: Write the test fixture helper and failing tests**

Path: `tests/shapesort/test_classical_detect.py`:

```python
from __future__ import annotations

import math

import numpy as np
import pytest

pytest.importorskip("cv2")
pytest.importorskip("PIL")

from PIL import Image, ImageDraw

from htdp.shapesort.classical_detect import Detection, detect_hole, detect_piece

CANVAS = 200

_RGB = {
    "red": (220, 30, 30),
    "yellow": (230, 210, 20),
    "green": (30, 180, 60),
    "blue": (30, 90, 220),
}


def _blank_canvas() -> Image.Image:
    return Image.new("RGB", (CANVAS, CANVAS), (200, 200, 200))


def _rotated_square_points(cx: float, cy: float, half: float, deg: float) -> list[tuple[float, float]]:
    corners = [(-half, -half), (half, -half), (half, half), (-half, half)]
    rad = math.radians(deg)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    return [(cx + x * cos_a - y * sin_a, cy + x * sin_a + y * cos_a) for x, y in corners]


def _draw_square(draw: ImageDraw.ImageDraw, color: str, cx: float, cy: float, half: float, deg: float) -> None:
    draw.polygon(_rotated_square_points(cx, cy, half, deg), fill=_RGB[color])


def _draw_triangle(draw: ImageDraw.ImageDraw, color: str, cx: float, cy: float, size: float) -> None:
    pts = [(cx, cy - size), (cx - size, cy + size), (cx + size, cy + size)]
    draw.polygon(pts, fill=_RGB[color])


def _draw_circle(draw: ImageDraw.ImageDraw, color: str, cx: float, cy: float, r: float) -> None:
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=_RGB[color])


def _to_bgr(img: Image.Image) -> np.ndarray:
    arr = np.array(img)  # HWC, RGB
    return arr[:, :, ::-1].copy()  # BGR for cv2


def test_detect_piece_finds_single_shape() -> None:
    img = _blank_canvas()
    draw = ImageDraw.Draw(img)
    _draw_triangle(draw, "red", 100, 100, 40)
    det = detect_piece(_to_bgr(img), "red", "triangle")
    assert det is not None
    assert abs(det.cx - 100) <= 4
    assert abs(det.cy - 100) <= 4
    assert det.confidence > 0.0


def test_detect_piece_picks_correct_target_among_distractors() -> None:
    img = _blank_canvas()
    draw = ImageDraw.Draw(img)
    _draw_triangle(draw, "red", 40, 40, 25)
    _draw_square(draw, "blue", 150, 60, 25, 0)
    _draw_circle(draw, "yellow", 60, 150, 25)
    det = detect_piece(_to_bgr(img), "blue", "square")
    assert det is not None
    assert abs(det.cx - 150) <= 4
    assert abs(det.cy - 60) <= 4


def test_detect_piece_returns_none_when_target_absent() -> None:
    img = _blank_canvas()
    draw = ImageDraw.Draw(img)
    _draw_triangle(draw, "red", 100, 100, 40)
    det = detect_piece(_to_bgr(img), "green", "triangle")
    assert det is None


def test_detect_piece_tracks_relative_rotation() -> None:
    def angle_diff_mod90(a: float, b: float) -> float:
        d = abs(a - b) % 90
        return min(d, 90 - d)

    img0 = _blank_canvas()
    _draw_square(ImageDraw.Draw(img0), "blue", 100, 100, 30, 0)
    det0 = detect_piece(_to_bgr(img0), "blue", "square")
    assert det0 is not None

    img1 = _blank_canvas()
    _draw_square(ImageDraw.Draw(img1), "blue", 100, 100, 30, 25)
    det1 = detect_piece(_to_bgr(img1), "blue", "square")
    assert det1 is not None

    # The two detected angles should differ by ~25 degrees (mod 90, since a square has
    # 4-fold rotational symmetry and cv2's minAreaRect angle convention isn't fixed
    # across versions) -- this is robust to that convention instead of hardcoding it.
    assert angle_diff_mod90(det0.angle_deg + 25, det1.angle_deg) < 5.0


def test_detect_hole_is_same_detector_as_detect_piece() -> None:
    img = _blank_canvas()
    _draw_circle(ImageDraw.Draw(img), "red", 100, 100, 30)
    det = detect_hole(_to_bgr(img), "red", "circle")
    assert det is not None
    assert detect_hole is detect_piece
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/shapesort/test_classical_detect.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'htdp.shapesort.classical_detect'`

- [ ] **Step 3: Write the classical detector module**

Path: `src/htdp/shapesort/classical_detect.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

try:
    import cv2
except ImportError as exc:  # pragma: no cover - exercised via ShapesortUnavailable path
    from htdp.shapesort.errors import ShapesortUnavailable

    raise ShapesortUnavailable() from exc

# HSV bounds (OpenCV convention: H in [0,179], S/V in [0,255]). Red wraps hue 0, so it
# needs two ranges. Tuned against the synthetic fixtures in test_classical_detect.py, not
# against real camera footage yet -- expect to retune once real images exist (R1a+).
_HSV_RANGES: dict[str, list[tuple[tuple[int, int, int], tuple[int, int, int]]]] = {
    "red": [((0, 80, 60), (10, 255, 255)), ((170, 80, 60), (179, 255, 255))],
    "yellow": [((20, 80, 60), (35, 255, 255))],
    "green": [((40, 80, 60), (85, 255, 255))],
    "blue": [((90, 80, 60), (130, 255, 255))],
}

_MIN_AREA_PX = 200


@dataclass(frozen=True)
class Detection:
    cx: int
    cy: int
    angle_deg: float
    confidence: float


def _color_mask(hsv: np.ndarray, color: str) -> np.ndarray:
    mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
    for lo, hi in _HSV_RANGES[color]:
        mask |= cv2.inRange(hsv, np.array(lo), np.array(hi))
    return mask


def _classify_shape(contour: np.ndarray) -> str:
    perimeter = cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, 0.03 * perimeter, True)
    vertices = len(approx)
    if vertices == 3:
        return "triangle"
    if vertices == 4:
        _, (w, h), _ = cv2.minAreaRect(contour)
        return "square" if 0.85 <= (w / h if h else 0) <= 1.15 else "rectangle"
    return "circle"


def _find_colored_shape_contour(image: np.ndarray, color: str, shape: str) -> np.ndarray | None:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = _color_mask(hsv, color)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = [
        c for c in contours if cv2.contourArea(c) > _MIN_AREA_PX and _classify_shape(c) == shape
    ]
    if not candidates:
        return None
    return max(candidates, key=cv2.contourArea)


def _detection_from_contour(contour: np.ndarray, image_area: int) -> Detection:
    moments = cv2.moments(contour)
    cx = int(moments["m10"] / moments["m00"])
    cy = int(moments["m01"] / moments["m00"])
    _, _, angle = cv2.minAreaRect(contour)
    confidence = min(1.0, cv2.contourArea(contour) / image_area * 20)
    return Detection(cx=cx, cy=cy, angle_deg=float(angle), confidence=confidence)


def detect_piece(image: np.ndarray, color: str, shape: str) -> Detection | None:
    """Locate the piece matching (color, shape) in a frame, or None if not present.

    Used both as the fallback grasp path when SmolVLA fails, and (aliased as
    detect_hole) to locate a hole's colored outline ring -- both are colored polygonal
    regions in the frame and share the same geometric primitive.
    """
    contour = _find_colored_shape_contour(image, color, shape)
    if contour is None:
        return None
    return _detection_from_contour(contour, image.shape[0] * image.shape[1])


detect_hole = detect_piece
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/shapesort/test_classical_detect.py -v`
Expected: 5 passed (skipped entirely if `cv2`/`PIL` aren't installed — run `uv sync --all-extras` first, per Global Constraints)

- [ ] **Step 5: Commit**

```bash
git add src/htdp/shapesort/classical_detect.py tests/shapesort/test_classical_detect.py
git commit -m "feat(shapesort): classical color+shape+orientation detector"
```

---

### Task 4: Control-loop orchestrator (`orchestrator.py`)

**Files:**
- Create: `src/htdp/shapesort/orchestrator.py`
- Test: `tests/shapesort/test_orchestrator.py`

**Interfaces:**
- Consumes: `htdp.shapesort.vocab.parse_target`.
- Produces: `PickResult`, `InsertResult`, `TrialResult` dataclasses, `run_trial(...)`. Consumed by Task 5's `TrialLog`/`aggregate` (same `outcome`/`used_fallback` field names) and by the CLI in Task 6.

- [ ] **Step 1: Write the failing tests**

Path: `tests/shapesort/test_orchestrator.py`:

```python
from __future__ import annotations

from htdp.shapesort.orchestrator import InsertResult, PickResult, run_trial


def test_asr_miss_never_calls_pick_or_insert() -> None:
    calls = {"pick": 0, "insert": 0}

    def listen() -> str:
        return "what time is it"

    def smolvla(_task: str) -> PickResult:
        calls["pick"] += 1
        return PickResult(success=True, height_gain_m=0.1)

    def classical(_hole: str) -> PickResult:
        calls["pick"] += 1
        return PickResult(success=True, height_gain_m=0.1)

    def insert(_hole: str) -> InsertResult:
        calls["insert"] += 1
        return InsertResult(success=True, aborted_stall=False)

    result = run_trial(listen, smolvla, classical, insert)
    assert result.outcome == "asr_miss"
    assert calls == {"pick": 0, "insert": 0}


def test_success_on_first_smolvla_attempt() -> None:
    def listen() -> str:
        return "put the green triangle in the box"

    def smolvla(_task: str) -> PickResult:
        return PickResult(success=True, height_gain_m=0.1)

    def classical(_hole: str) -> PickResult:
        raise AssertionError("classical fallback should not be called")

    def insert(_hole: str) -> InsertResult:
        return InsertResult(success=True, aborted_stall=False)

    result = run_trial(listen, smolvla, classical, insert)
    assert result.outcome == "success"
    assert result.used_fallback is False
    assert result.pick_attempts == 1


def test_falls_back_to_classical_after_smolvla_exhausts_retries() -> None:
    attempts = {"smolvla": 0}

    def listen() -> str:
        return "put the blue rectangle in the box"

    def smolvla(_task: str) -> PickResult:
        attempts["smolvla"] += 1
        return PickResult(success=False, height_gain_m=0.0)

    def classical(_hole: str) -> PickResult:
        return PickResult(success=True, height_gain_m=0.1)

    def insert(_hole: str) -> InsertResult:
        return InsertResult(success=True, aborted_stall=False)

    result = run_trial(listen, smolvla, classical, insert, max_pick_retries=2)
    assert attempts["smolvla"] == 2
    assert result.outcome == "success"
    assert result.used_fallback is True


def test_grasp_fail_when_both_paths_fail_never_calls_insert() -> None:
    calls = {"insert": 0}

    def listen() -> str:
        return "put the yellow square in the box"

    def smolvla(_task: str) -> PickResult:
        return PickResult(success=False, height_gain_m=0.0)

    def classical(_hole: str) -> PickResult:
        return PickResult(success=False, height_gain_m=0.0)

    def insert(_hole: str) -> InsertResult:
        calls["insert"] += 1
        return InsertResult(success=True, aborted_stall=False)

    result = run_trial(listen, smolvla, classical, insert)
    assert result.outcome == "grasp_fail"
    assert result.used_fallback is True
    assert calls["insert"] == 0


def test_insert_fail_reported_distinctly() -> None:
    def listen() -> str:
        return "put the red circle in the box"

    def smolvla(_task: str) -> PickResult:
        return PickResult(success=True, height_gain_m=0.1)

    def classical(_hole: str) -> PickResult:
        raise AssertionError("classical fallback should not be called")

    def insert(_hole: str) -> InsertResult:
        return InsertResult(success=False, aborted_stall=True)

    result = run_trial(listen, smolvla, classical, insert)
    assert result.outcome == "insert_fail"
    assert result.used_fallback is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/shapesort/test_orchestrator.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'htdp.shapesort.orchestrator'`

- [ ] **Step 3: Write the orchestrator module**

Path: `src/htdp/shapesort/orchestrator.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from htdp.shapesort.vocab import parse_target

Outcome = Literal["success", "asr_miss", "grasp_fail", "insert_fail"]


@dataclass(frozen=True)
class PickResult:
    success: bool
    height_gain_m: float


@dataclass(frozen=True)
class InsertResult:
    success: bool
    aborted_stall: bool


@dataclass(frozen=True)
class TrialResult:
    outcome: Outcome
    used_fallback: bool
    pick_attempts: int


def run_trial(
    listen_and_transcribe: Callable[[], str],
    smolvla_pick: Callable[[str], PickResult],
    classical_pick: Callable[[str], PickResult],
    insert: Callable[[str], InsertResult],
    *,
    max_pick_retries: int = 2,
) -> TrialResult:
    """Run one voice-command trial: ASR -> lookup -> SmolVLA pick (+classical fallback)
    -> insert. Never guesses a target and never inserts on an unsuccessful pick -- see
    the Error handling section of docs/superpowers/specs/2026-07-08-r2-voice-shapesort-design.md.
    """
    text = listen_and_transcribe()
    hole_id = parse_target(text)
    if hole_id is None:
        return TrialResult(outcome="asr_miss", used_fallback=False, pick_attempts=0)

    attempts = 0
    picked = False
    for _ in range(max_pick_retries):
        attempts += 1
        if smolvla_pick(text).success:
            picked = True
            break

    used_fallback = False
    if not picked:
        used_fallback = True
        attempts += 1
        picked = classical_pick(hole_id).success

    if not picked:
        return TrialResult(outcome="grasp_fail", used_fallback=used_fallback, pick_attempts=attempts)

    if not insert(hole_id).success:
        return TrialResult(outcome="insert_fail", used_fallback=used_fallback, pick_attempts=attempts)

    return TrialResult(outcome="success", used_fallback=used_fallback, pick_attempts=attempts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/shapesort/test_orchestrator.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/htdp/shapesort/orchestrator.py tests/shapesort/test_orchestrator.py
git commit -m "feat(shapesort): control-loop orchestrator with retry+fallback"
```

---

### Task 5: Trial-eval aggregator (`eval.py`)

**Files:**
- Create: `src/htdp/shapesort/eval.py`
- Test: `tests/shapesort/test_eval.py`

**Interfaces:**
- Consumes: `htdp.learn.eval.wilson_ci`; `outcome`/`used_fallback` field names from Task 4's `TrialResult` (mirrored here as `TrialLog` so the eval module has no import dependency on the orchestrator's dataclass, matching this repo's `learn` module's pattern of small standalone eval inputs).
- Produces: `TrialLog`, `aggregate(trials: list[TrialLog]) -> dict[str, object]`. Consumed by Task 6's CLI command.

- [ ] **Step 1: Write the failing tests**

Path: `tests/shapesort/test_eval.py`:

```python
from __future__ import annotations

from htdp.learn.eval import wilson_ci
from htdp.shapesort.eval import TrialLog, aggregate


def test_aggregate_empty_list() -> None:
    report = aggregate([])
    assert report["n"] == 0
    assert report["success_rate"] == 0.0
    assert report["ci95"] == [0.0, 1.0]
    assert report["failure_taxonomy"] == {}
    assert report["fallback_trigger_rate"] == 0.0


def test_aggregate_mixed_outcomes() -> None:
    trials = [
        TrialLog(outcome="success", used_fallback=False),
        TrialLog(outcome="success", used_fallback=True),
        TrialLog(outcome="success", used_fallback=False),
        TrialLog(outcome="asr_miss", used_fallback=False),
        TrialLog(outcome="insert_fail", used_fallback=True),
    ]
    report = aggregate(trials)
    assert report["n"] == 5
    assert report["success_rate"] == 3 / 5
    assert report["failure_taxonomy"] == {"success": 3, "asr_miss": 1, "insert_fail": 1}
    assert report["fallback_trigger_rate"] == 2 / 5
    assert report["ci95"] == list(wilson_ci(3, 5))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/shapesort/test_eval.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'htdp.shapesort.eval'`

- [ ] **Step 3: Write the eval module**

Path: `src/htdp/shapesort/eval.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from htdp.learn.eval import wilson_ci


@dataclass(frozen=True)
class TrialLog:
    outcome: str
    used_fallback: bool


def aggregate(trials: list[TrialLog]) -> dict[str, object]:
    """Aggregate trial logs into the report shape used by R1c/E1/C1/OOD1: success rate +
    Wilson 95% CI, per-outcome failure taxonomy, and the SmolVLA-fallback trigger rate.
    """
    n = len(trials)
    successes = sum(1 for t in trials if t.outcome == "success")
    lo, hi = wilson_ci(successes, n)

    taxonomy: dict[str, int] = {}
    for t in trials:
        taxonomy[t.outcome] = taxonomy.get(t.outcome, 0) + 1

    fallback_n = sum(1 for t in trials if t.used_fallback)

    return {
        "n": n,
        "success_rate": successes / n if n else 0.0,
        "ci95": [lo, hi],
        "failure_taxonomy": taxonomy,
        "fallback_trigger_rate": fallback_n / n if n else 0.0,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/shapesort/test_eval.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/htdp/shapesort/eval.py tests/shapesort/test_eval.py
git commit -m "feat(shapesort): trial-eval aggregator (Wilson CI + failure taxonomy)"
```

---

### Task 6: CLI command `shapesort-eval-report`

**Files:**
- Modify: `src/htdp/cli.py`
- Test: `tests/test_cli_shapesort.py`

**Interfaces:**
- Consumes: `htdp.shapesort.eval.TrialLog`, `aggregate` (Task 5); `htdp.shapesort.errors.ShapesortUnavailable` (Task 1).
- Produces: `shapesort-eval-report` typer command, following the exact lazy-import-with-try/except pattern already used by `eval-policy` (`src/htdp/cli.py:301-317`).

- [ ] **Step 1: Write the failing test**

Path: `tests/test_cli_shapesort.py`:

```python
import json

from typer.testing import CliRunner

from htdp.cli import app

runner = CliRunner()


def test_cli_shapesort_eval_report(tmp_path):
    trials_path = tmp_path / "trials.jsonl"
    trials_path.write_text(
        "\n".join(
            [
                json.dumps({"outcome": "success", "used_fallback": False}),
                json.dumps({"outcome": "success", "used_fallback": True}),
                json.dumps({"outcome": "asr_miss", "used_fallback": False}),
            ]
        )
    )
    out_path = tmp_path / "report.json"

    result = runner.invoke(
        app,
        ["shapesort-eval-report", "--trials", str(trials_path), "--out", str(out_path)],
    )
    assert result.exit_code == 0, result.output
    report = json.loads(out_path.read_text())
    assert report["n"] == 3
    assert report["success_rate"] == 2 / 3
    assert report["failure_taxonomy"] == {"success": 2, "asr_miss": 1}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_cli_shapesort.py -v`
Expected: FAIL — `No such command 'shapesort-eval-report'`

- [ ] **Step 3: Add the command to `src/htdp/cli.py`**

Append to the end of `src/htdp/cli.py`:

```python
@app.command(name="shapesort-eval-report")
def shapesort_eval_report(
    trials: Path = typer.Option(..., "--trials", help="JSONL file, one {outcome, used_fallback} object per line"),
    out: Path = typer.Option(..., "--out", help="report JSON path"),
) -> None:
    """Aggregate R2 shape-sort trial logs into a success-rate + Wilson-CI report."""
    try:
        from htdp.shapesort.eval import TrialLog, aggregate
    except ImportError as exc:
        from htdp.shapesort.errors import ShapesortUnavailable
        typer.echo(f"error: {ShapesortUnavailable()}", err=True)
        raise typer.Exit(1) from exc

    import json

    logs = []
    for line in trials.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        logs.append(TrialLog(outcome=row["outcome"], used_fallback=row["used_fallback"]))

    report = aggregate(logs)
    out.write_text(json.dumps(report, indent=2))
    typer.echo(f"n={report['n']} success_rate={report['success_rate']:.3f} ci95={report['ci95']}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_cli_shapesort.py -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add src/htdp/cli.py tests/test_cli_shapesort.py
git commit -m "feat(shapesort): shapesort-eval-report CLI command"
```

---

### Task 7: State doc — hardware-gated remainder

**Files:**
- Create: `docs/m2/r2-shapesort-state.md`

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: nothing consumed by other tasks — this is the plan's terminal task, recording what is and is not done.

- [ ] **Step 1: Write the state doc**

Path: `docs/m2/r2-shapesort-state.md`:

```markdown
# R2 — Voice Shape-Sort: software-foundation state

**Done (this plan, all unit-tested offline, no hardware/model dependency):**
- `htdp.shapesort.vocab.parse_target` — command → target-hole lookup.
- `htdp.shapesort.classical_detect.detect_piece`/`detect_hole` — HSV+contour color/shape/
  orientation detector, tested against synthetic PIL fixtures (single shape, distractor
  scene, absent target, relative-rotation tracking).
- `htdp.shapesort.orchestrator.run_trial` — retry + classical-fallback + insert control
  loop, tested with injected fakes covering every branch in the design doc's error-handling
  section.
- `htdp.shapesort.eval.aggregate` — Wilson-CI + failure-taxonomy + fallback-rate report,
  reusing `htdp.learn.eval.wilson_ci`.
- CLI: `htdp shapesort-eval-report --trials trials.jsonl --out report.json`.

**Explicitly NOT done — hardware/model-gated, deferred until R1 closes and hardware/GPU
are available (per the design doc's sequencing decision):**
- Live ASR wiring: `openai-whisper`'s `model.transcribe(audio_path)` call itself is
  untested by this plan — only the vocab parser downstream of it is. Wire + smoke-test
  once a mic is on the rig.
- SmolVLA fine-tuning and the real `smolvla_pick` callable — needs ~40-60 real teleop
  demos and single-GPU (A100-class) access; both unresolved resource dependencies noted
  in the design doc.
- Live camera integration of `detect_piece`/`detect_hole` — the HSV ranges in
  `classical_detect.py` are tuned against synthetic fixtures, NOT real camera footage;
  expect to retune `_HSV_RANGES` once real images exist.
- The real insertion servo loop (wrist rotation + closed-loop visual servo + stall/
  current-limit abort) — `InsertResult.aborted_stall` exists as a field for this to
  report into, but no hardware-side implementation exists yet.
- `COLOR_SHAPE_TO_HOLE` in `vocab.py` is a 4-entry placeholder from the product photo —
  confirm against the physical toy and edit if wrong.
- The real n>=20 trial eval run itself (the `shapesort-eval-report` CLI is ready to
  consume its output once trials exist).

**Next session, once R1 closes and hardware is available:** R1a-style bring-up for this
mile — confirm toy hole colors, wire live ASR, record SmolVLA fine-tune demos, retune HSV
ranges against real footage, then build the live insertion servo loop.
```

- [ ] **Step 2: Commit**

```bash
git add docs/m2/r2-shapesort-state.md
git commit -m "docs(shapesort): state doc marking hardware-gated remainder"
```

---

## Self-Review Notes

**Spec coverage:** ASR/command-parsing (Task 2), classical color+shape+orientation detection incl. distractor discrimination (Task 3), control loop with retry/fallback/error-handling branches (Task 4), eval discipline — Wilson CI + failure taxonomy + fallback rate (Task 5), CLI surface (Task 6). Explicitly NOT covered by a task, by design: SmolVLA fine-tuning, live ASR, live camera, live insertion servo, real toy hole confirmation, real n>=20 eval run — all recorded in Task 7 rather than faked.

**Placeholder scan:** no TBD/TODO; the one explicitly-labeled placeholder (`COLOR_SHAPE_TO_HOLE`) is real, working code with a comment stating why it's provisional, not an empty stub.

**Type consistency:** `TrialResult.outcome`/`used_fallback` (Task 4) and `TrialLog.outcome`/`used_fallback` (Task 5) share field names by design (documented in Task 5's Interfaces) even though they're separate dataclasses — the eval module intentionally has no import dependency on the orchestrator module. `detect_hole is detect_piece` (Task 3) is asserted directly in a test, not just implied by a docstring.
