"""Read-only servo bus scan: which motors answer, and what do they report?

Written after a 2026-08-14 eval aborted during connect() with

    ConnectionError: Failed to write 'Lock' on id_=4 with '1' after 1 tries.
    [TxRxResult] There is no status packet!

"No status packet" means that motor did not reply at all, which is a different
failure from the `Overload error!` seen earlier on id_=3 -- that one replied and
reported a fault. This scans both ports so a port swap (leader vs follower) shows
up as "the wrong set of IDs answered" rather than being mistaken for a dead servo.

Read-only by construction: it pings and reads, and never enables torque or
writes anything.

    ./hw_docker.sh python robot_learning/scan_servos.py
"""

import argparse

DEFAULT_PORTS = ["/dev/ttyACM0", "/dev/ttyACM1"]
READINGS = ["Present_Voltage", "Present_Temperature", "Present_Position", "Torque_Enable"]


def scan_port(port: str, ids: list[int]) -> None:
    from lerobot.motors import Motor, MotorNormMode
    from lerobot.motors.feetech import FeetechMotorsBus

    print(f"\n=== {port} ===")
    motors = {f"id{i}": Motor(i, "sts3215", MotorNormMode.RANGE_M100_100) for i in ids}
    bus = FeetechMotorsBus(port=port, motors=motors)
    try:
        bus.connect(handshake=False)
    except Exception as exc:  # noqa: BLE001 -- report, don't abort the other port
        print(f"  could not open: {type(exc).__name__}: {exc}")
        return

    try:
        responded = []
        for i in ids:
            name = f"id{i}"
            try:
                model = bus.ping(i)
                responded.append(i)
                vals = {}
                for reg in READINGS:
                    try:
                        vals[reg] = bus.read(reg, name, normalize=False)
                    except Exception as exc:  # noqa: BLE001
                        vals[reg] = f"<{type(exc).__name__}>"
                volts = vals.get("Present_Voltage")
                volt_str = f"{volts / 10:.1f}V" if isinstance(volts, (int, float)) else str(volts)
                print(f"  id {i}: OK   model={model}  {volt_str}  "
                      f"{vals.get('Present_Temperature')}C  "
                      f"pos={vals.get('Present_Position')}  "
                      f"torque={vals.get('Torque_Enable')}")
            except Exception as exc:  # noqa: BLE001
                print(f"  id {i}: NO RESPONSE  ({type(exc).__name__})")
        missing = [i for i in ids if i not in responded]
        print(f"  -> responded: {responded or 'none'}")
        if missing:
            print(f"  -> SILENT: {missing}")
    finally:
        try:
            bus.disconnect()
        except Exception:  # noqa: BLE001, S110
            pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ports", nargs="*", default=DEFAULT_PORTS)
    ap.add_argument("--ids", nargs="*", type=int, default=[1, 2, 3, 4, 5, 6])
    args = ap.parse_args()

    print("Read-only scan. No torque is enabled and nothing is written.")
    for port in args.ports:
        scan_port(port, args.ids)

    print("\nReading the result:")
    print("  - one port with all 6 IDs and the other with all 6  -> both arms fine;")
    print("    if loop.py's CONFIG has them the wrong way round, run ./verify_ports.sh")
    print("  - a single silent ID -> that servo or its daisy-chain link is the fault;")
    print("    check the cable to it and to the one before it in the chain")
    print("  - several silent IDs from one point onward -> the break is at the first")
    print("    silent one; everything downstream of it loses the bus")
    print("  - all silent -> power, or the wrong port entirely")


if __name__ == "__main__":
    main()
