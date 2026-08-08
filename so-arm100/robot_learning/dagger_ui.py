"""A usable front-end for `lerobot-rollout --strategy.type=dagger`.

Four DAgger sessions on 2026-08-09 recorded zero corrections. Nothing was
broken -- keys reached the process, the state machine worked -- but the
operator could not see any of it. `Phase transition: x -> y` is logged
(dagger.py:655), and so is every save (:551), but both scrolled past under
roughly three warnings per second of RTC and clamp noise. An unacknowledged
keypress is indistinguishable from a hung program, and the failure mode is
silent and total: no data at all.

So this wraps the child process and turns its log stream into a display:

- the two known-benign spam warnings are dropped (counted, not hidden)
- every phase change becomes an unmissable banner saying what to press next
- saves are counted and echoed
- the full raw stream is always written to a log file, so a failed session can
  be diagnosed without asking for another one

Nothing here reimplements DAgger. The child owns the robot, the keyboard and
the state machine; this only reformats what it says. Pass --raw to bypass it.

Important: stdin is deliberately left attached to the terminal. The child's
keyboard backend needs a TTY on stdin (keyboard_input.py:382); piping only its
stdout is safe, and was confirmed working on 2026-08-09.
"""

# loop.py runs under the system python (3.9 on this Mac), which evaluates
# annotations eagerly and would choke on `Path | None` at import time.
from __future__ import annotations

import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Benign and extremely frequent. Both were investigated on 2026-08-09:
# `Indexes diff` is RTC's off-by-one between latency-derived delay and actions
# actually consumed (action_queue.py:243 trusts the latency figure and carries
# on); the clamp warning is max_relative_target rate-limiting the transit from
# the rest pose. Neither needs the operator's attention, and together they
# buried everything that did.
SPAM = re.compile(r"Indexes diff is not equal to real delay|Relative goal position magnitude")
# The clamp warning prints a multi-line dict after its header; swallow those.
SPAM_CONT = re.compile(r"^\s*[{'\s]|^\s*'?\w+'?:\s*{|^\s*}\s*,?\s*$")

PHASE = re.compile(r"Phase transition: (\w+) -> (\w+)")
SAVED = re.compile(r"Correction (\d+) saved")
KEYBOARD_OK = re.compile(r"Using terminal keyboard input|Keyboard listener started")
KEYBOARD_DEAD = re.compile(r"Keyboard controls unavailable")

BANNERS = {
    "autonomous": ("POLICY IS DRIVING", "press SPACE to take over"),
    "paused": ("YOU HAVE THE ARM", "press TAB to start recording  (SPACE = give it back)"),
    "correcting": ("RECORDING YOUR CORRECTION", "drive the fix, then press TAB to save it"),
}


def _banner(title: str, hint: str, extra: str = "") -> str:
    line = "=" * 62
    out = f"\n{line}\n  {title}\n  -> {hint}\n"
    if extra:
        out += f"  {extra}\n"
    return out + line


def run_with_status(cmd: list[str], target_episodes: int, log_path: Path | None = None) -> int:
    """Run the DAgger child process, showing state instead of log spam."""
    if log_path is None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        log_path = REPO_ROOT / "data" / "local" / "logs" / f"dagger-{stamp}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"\nFull log: {log_path}")
    print("Starting up -- the arms and cameras take a few seconds.\n", flush=True)

    saved = 0
    suppressed = 0
    phase = "autonomous"
    in_spam_block = False
    started = time.time()

    with log_path.open("w") as log:
        # stdin is NOT redirected: the child needs the TTY to read keys.
        proc = subprocess.Popen(
            cmd,
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                log.write(line)
                log.flush()
                stripped = line.rstrip()

                if SPAM.search(stripped):
                    suppressed += 1
                    in_spam_block = True
                    continue
                # The clamp warning's payload dict follows on later lines.
                if in_spam_block and SPAM_CONT.match(stripped):
                    suppressed += 1
                    continue
                in_spam_block = False

                if m := PHASE.search(stripped):
                    phase = m.group(2)
                    title, hint = BANNERS.get(phase, (phase.upper(), ""))
                    extra = f"saved {saved}/{target_episodes}" if phase != "correcting" else ""
                    print(_banner(title, hint, extra), flush=True)
                    continue

                if m := SAVED.search(stripped):
                    saved = int(m.group(1))
                    print(f"\n  *** CORRECTION {saved} of {target_episodes} SAVED ***\n", flush=True)
                    continue

                if KEYBOARD_DEAD.search(stripped):
                    print(_banner("KEYBOARD IS DEAD", "stop now (ESC) -- keys will not work"), flush=True)
                    continue

                if KEYBOARD_OK.search(stripped):
                    print(_banner("READY -- POLICY IS DRIVING",
                                  "press SPACE to take over",
                                  "keep this terminal focused"), flush=True)
                    continue

                # Anything unrecognised is either an error or something new;
                # both are worth seeing. Only INFO-level chatter is dropped.
                if not stripped.startswith("INFO"):
                    print(stripped, flush=True)

            return proc.wait()
        except KeyboardInterrupt:
            proc.terminate()
            return proc.wait()
        finally:
            mins = (time.time() - started) / 60
            print(f"\n{'=' * 62}")
            print(f"  {saved} correction(s) saved in {mins:.1f} min")
            print(f"  {suppressed} routine warnings hidden")
            print(f"  Full log: {log_path}")
            print("=" * 62)
            if saved == 0:
                print("\nNothing was recorded. A correction is only written by the")
                print("full sequence:  SPACE -> TAB -> drive -> TAB")
                print(f"The log above shows every key that registered.\n")


def rehearse(target: int = 3) -> int:
    """Practise the key sequence with no robot, no cameras, nothing to break.

    Imports the real transition table from LeRobot rather than restating it, so
    this cannot drift from what the actual session does.
    """
    from lerobot.rollout.strategies.dagger import _DAGGER_TRANSITIONS, DAggerPhase
    from lerobot.utils.keyboard_input import create_key_listener

    state = {"phase": DAggerPhase.AUTONOMOUS, "saved": 0, "done": False}

    def dispatch(name: str) -> None:
        if name == "esc":
            state["done"] = True
            return
        event = {"space": "pause_resume", "tab": "correction"}.get(name)
        if event is None:
            print(f"  ({name!r} does nothing here)", flush=True)
            return

        key = (state["phase"], event)
        new_phase = _DAGGER_TRANSITIONS.get(key)
        if new_phase is None:
            # This is the silent drop that cost four sessions. Say it out loud.
            print(f"\n  '{name}' IGNORED -- not valid while {state['phase'].value.upper()}."
                  f"\n  From here, press {'SPACE' if state['phase'] is DAggerPhase.AUTONOMOUS else 'TAB'}.\n",
                  flush=True)
            return

        if state["phase"] is DAggerPhase.CORRECTING and new_phase is DAggerPhase.PAUSED:
            state["saved"] += 1
            print(f"\n  *** CORRECTION {state['saved']} of {target} SAVED ***\n", flush=True)

        state["phase"] = new_phase
        title, hint = BANNERS[new_phase.value]
        print(_banner(title, hint, f"saved {state['saved']}/{target}"), flush=True)

        if state["saved"] >= target:
            print("\n  That's the rhythm. Press ESC to finish.\n", flush=True)

    listener = create_key_listener(dispatch, controls_help="space / tab, ESC to quit")
    if listener is None:
        sys.exit("No keyboard backend available in this terminal -- run it in a real terminal window.")

    print(_banner("REHEARSAL -- no robot connected",
                  "press SPACE to take over",
                  f"save {target} pretend corrections, then ESC"))
    print("\nThe sequence is:  SPACE -> TAB -> (drive) -> TAB -> SPACE\n", flush=True)

    try:
        while not state["done"]:
            time.sleep(0.05)
    finally:
        listener.stop()

    print(f"\nRehearsal over: {state['saved']} correction(s) saved.")
    if state["saved"] >= target:
        print("You have the sequence. The real thing behaves identically.\n")
    return 0


if __name__ == "__main__":
    # Entry point for `loop.py dagger --rehearse`, which re-execs this file
    # with the venv python: rehearse() imports lerobot, and loop.py itself runs
    # under the system python.
    import argparse

    ap = argparse.ArgumentParser(description="Practise the DAgger key sequence, no robot.")
    ap.add_argument("--target", type=int, default=3)
    raise SystemExit(rehearse(target=ap.parse_args().target))
