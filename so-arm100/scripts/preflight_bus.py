"""Deterministic read-only check of the servo bus and its calibration.

Container half of ./preflight.sh. The host half checks port ownership and device
identity first and only invokes this for ports it has proven are free -- this script
never steals a port and never writes to a servo.

Determinism is the whole point
------------------------------
Every value here is read TWICE and reported only if both reads agree. If they differ
the value is reported UNSTABLE and the check fails. That rule exists because of a
concrete incident on 2026-08-17: a sloppier version of this read (no input flush
between queries, a 0.15s timeout, and no validation that a reply even matched its
request) returned calibration values that looked exactly right, were wrong, and were
then trusted as ground truth for an hour of debugging in the wrong subsystem.

So every reply is checked for framing before its bytes are believed:
  - header 0xFF 0xFF
  - the id in the reply equals the id we asked
  - the length field equals the payload we asked for
A reply failing any of those is discarded, not decoded. A measurement tool that can
silently return a plausible wrong number is worse than no tool.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import serial

BAUD = 1_000_000
TIMEOUT_S = 0.3
SETTLE_S = 0.1
SERVO_IDS = range(1, 7)

# addr, length -- from lerobot.motors.feetech.tables.STS_SMS_SERIES_CONTROL_TABLE
REG = {
    "min": (9, 2),
    "max": (11, 2),
    "homing": (31, 2),
    "lock": (55, 1),
}
HOMING_SIGN_BIT = 11


def read_packet(sid: int, addr: int, n: int) -> bytes:
    length, inst = 4, 0x02
    return bytes([0xFF, 0xFF, sid, length, inst, addr, n,
                  (~(sid + length + inst + addr + n)) & 0xFF])


def ping_packet(sid: int) -> bytes:
    length, inst = 0x02, 0x01
    return bytes([0xFF, 0xFF, sid, length, inst, (~(sid + length + inst)) & 0xFF])


def decode_sign_magnitude(value: int, sign_bit: int = HOMING_SIGN_BIT) -> int:
    magnitude = value & ((1 << sign_bit) - 1)
    return -magnitude if (value >> sign_bit) & 1 else magnitude


def query(sp, sid: int, addr: int, n: int):
    """One validated register read, or None. Flushes first so a late reply from the
    previous query cannot be mistaken for this one -- that misalignment is exactly how
    the 2026-08-17 wrong reading happened."""
    sp.reset_input_buffer()
    sp.write(read_packet(sid, addr, n))
    sp.flush()
    expected_len = 4 + n + 2                      # FF FF ID LEN ERR payload.. CHK
    reply = sp.read(expected_len)
    if len(reply) != expected_len:
        return None
    if reply[0] != 0xFF or reply[1] != 0xFF:
        return None
    if reply[2] != sid:                           # answered by a different servo
        return None
    if reply[3] != n + 2:                         # not the payload size we asked for
        return None
    return reply[5] if n == 1 else reply[5] | (reply[6] << 8)


def read_twice(sp, sid: int, name: str):
    """A value both reads agree on, or the string UNSTABLE."""
    addr, n = REG[name]
    first = query(sp, sid, addr, n)
    second = query(sp, sid, addr, n)
    if first is None or second is None:
        return None
    if first != second:
        return "UNSTABLE"
    return decode_sign_magnitude(first) if name == "homing" else first


def ping_twice(sp, sid: int) -> bool:
    """Present on both attempts.

    A PING reply and the echo of a PING request are both 6 bytes starting FF FF <id>,
    so this cannot by itself prove a servo answered -- it proves something on the bus
    with that id responded. The calibration reads below are the real evidence, since
    an echo there would decode to the address we asked for rather than register data.
    """
    hits = 0
    for _ in range(2):
        sp.reset_input_buffer()
        sp.write(ping_packet(sid))
        sp.flush()
        reply = sp.read(6)
        if len(reply) == 6 and reply[0] == 0xFF and reply[1] == 0xFF and reply[2] == sid:
            hits += 1
    return hits == 2


def load_expected(calibration_path: Path):
    """{servo id: (name, range_min, range_max, homing_offset)} or None."""
    if not calibration_path.exists():
        return None
    data = json.loads(calibration_path.read_text())
    return {int(v["id"]): (k, int(v["range_min"]), int(v["range_max"]), int(v["homing_offset"]))
            for k, v in data.items()}


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: preflight_bus.py <port> <calibration.json>", file=sys.stderr)
        return 2
    port, calibration_path = sys.argv[1], Path(sys.argv[2])

    # Two severities, deliberately. A calibration that differs from the file makes the
    # arm unusable and must stop the flight. An unlocked EEPROM is a standing risk --
    # it is how the calibration got rewritten in the first place -- but it blocks
    # nothing, and a checker that cries NO-GO over it would be ignored within a day.
    problems: list[str] = []
    warnings: list[str] = []

    expected = load_expected(calibration_path)
    if expected is None:
        print(f"  FAIL  no calibration file at {calibration_path}")
        return 1

    try:
        sp = serial.Serial(port, BAUD, timeout=TIMEOUT_S)
    except Exception as exc:
        print(f"  FAIL  cannot open {port}: {exc}")
        return 1

    time.sleep(SETTLE_S)
    print(f"  {'servo':16s} {'ping':5s} {'min':>7s} {'max':>7s} {'homing':>8s} {'lock':>5s}  calibration")
    try:
        for sid in SERVO_IDS:
            name, want_min, want_max, want_homing = expected.get(sid, (f"id{sid}", None, None, None))
            present = ping_twice(sp, sid)
            got_min = read_twice(sp, sid, "min")
            got_max = read_twice(sp, sid, "max")
            got_homing = read_twice(sp, sid, "homing")
            got_lock = read_twice(sp, sid, "lock")

            values = (got_min, got_max, got_homing)
            if any(v == "UNSTABLE" for v in values):
                verdict = "UNSTABLE READ"
                problems.append(f"S{sid} gave different values on two consecutive reads")
            elif any(v is None for v in values):
                verdict = "NO REPLY"
                problems.append(f"S{sid} did not answer a register read")
            elif (got_min, got_max, got_homing) == (want_min, want_max, want_homing):
                verdict = "matches file"
            else:
                verdict = f"DIFFERS (file wants {want_min}-{want_max} h={want_homing})"
                problems.append(f"S{sid} calibration differs from {calibration_path.name}")

            if got_lock == 0:
                warnings.append(f"S{sid} EEPROM is unlocked (writable -- how the "
                                "calibration was rewritten on 2026-08-17)")

            fmt = lambda v: "----" if v is None else str(v)
            print(f"  {name:16s} {'yes' if present else 'NO':5s} {fmt(got_min):>7s} "
                  f"{fmt(got_max):>7s} {fmt(got_homing):>8s} {fmt(got_lock):>5s}  {verdict}")
    finally:
        sp.close()

    if problems:
        print()
        for item in problems:
            print(f"  BLOCKER  {item}")
    if warnings:
        print()
        for item in warnings:
            print(f"  warning  {item}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
