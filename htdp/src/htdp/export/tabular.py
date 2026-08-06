from __future__ import annotations

SUFFIXES: tuple[str, ...] = ("x_m", "y_m", "z_m", "qw", "qx", "qy", "qz", "quality")


def motion_wide(
    rows: list[dict[str, str]],
    trackers: list[str],
) -> tuple[list[str], list[list[str]]]:
    by_tracker: dict[str, dict[str, dict[str, str]]] = {}
    for r in rows:
        by_tracker.setdefault(r["tracker_id"], {})[r["timestamp_s"]] = r
    all_ts = sorted({r["timestamp_s"] for r in rows}, key=float)
    header = ["timestamp_s"] + [f"{t}_{s}" for t in trackers for s in SUFFIXES]
    matrix: list[list[str]] = []
    for ts in all_ts:
        out_row = [ts]
        for t in trackers:
            cell = by_tracker.get(t, {}).get(ts)
            for s in SUFFIXES:
                out_row.append(cell[s] if cell is not None else "n/a")
        matrix.append(out_row)
    return header, matrix


def matrix_to_tsv(header: list[str], matrix: list[list[str]]) -> str:
    lines = ["\t".join(header)]
    lines.extend("\t".join(row) for row in matrix)
    return "\n".join(lines) + "\n"


SUFFIX_META: dict[str, tuple[str, str, str]] = {
    "x_m": ("POS", "x", "m"),
    "y_m": ("POS", "y", "m"),
    "z_m": ("POS", "z", "m"),
    "qw": ("ORNT", "quat_w", "n/a"),
    "qx": ("ORNT", "quat_x", "n/a"),
    "qy": ("ORNT", "quat_y", "n/a"),
    "qz": ("ORNT", "quat_z", "n/a"),
    "quality": ("MISC", "n/a", "n/a"),
}
CHANNELS_HEADER: list[str] = [
    "name",
    "type",
    "component",
    "tracked_point",
    "units",
    "sampling_frequency",
]


def channels_rows(trackers: list[str], fps: float) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for t in trackers:
        for s in SUFFIXES:
            typ, component, units = SUFFIX_META[s]
            rows.append(
                {
                    "name": f"{t}_{s}",
                    "type": typ,
                    "component": component,
                    "tracked_point": t,
                    "units": units,
                    "sampling_frequency": str(fps),
                }
            )
    return rows


def dicts_to_tsv(header: list[str], rows: list[dict[str, str]]) -> str:
    lines = ["\t".join(header)]
    lines.extend("\t".join(r[h] for h in header) for r in rows)
    return "\n".join(lines) + "\n"


EVENTS_HEADER: list[str] = ["onset", "duration", "trial_type", "value"]


def events_rows(events: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "onset": e["timestamp_s"],
            "duration": "n/a",
            "trial_type": e["label"],
            "value": e["event_id"],
        }
        for e in events
    ]
