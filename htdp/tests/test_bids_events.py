from htdp.export.tabular import EVENTS_HEADER, dicts_to_tsv, events_rows


def _ev(ts: str, eid: str, label: str) -> dict[str, str]:
    return {
        "timestamp_s": ts,
        "event_id": eid,
        "label": label,
        "phase": "p",
        "source": "synthetic",
        "confidence": "1.000000",
        "notes": "",
    }


def test_events_rows_mapping():
    rows = events_rows([_ev("0.000000", "0", "start"), _ev("1.000000", "1", "grasp")])
    assert rows[0] == {"onset": "0.000000", "duration": "n/a", "trial_type": "start", "value": "0"}
    assert rows[1]["trial_type"] == "grasp"


def test_events_serialize_with_header():
    text = dicts_to_tsv(EVENTS_HEADER, events_rows([_ev("0.000000", "0", "start")]))
    assert text.splitlines()[0] == "onset\tduration\ttrial_type\tvalue"
