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
