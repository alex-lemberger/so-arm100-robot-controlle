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
