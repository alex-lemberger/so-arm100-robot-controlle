import json

from htdp_capture.marker_source import MarkerEvent
from htdp_capture.scripted_marker import ScriptedMarkerSource, default_schedule


class FakeClock:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


def test_to_json_has_payload_keys_and_no_source():
    payload = json.loads(MarkerEvent(1, "start", "reach", 0.9, "n").to_json())
    assert payload == {
        "event_id": 1, "label": "start", "phase": "reach",
        "confidence": 0.9, "notes": "n",
    }
    assert "source" not in payload


def test_to_json_is_sorted():
    s = MarkerEvent(1, "start", "reach").to_json()
    assert s == json.dumps(json.loads(s), sort_keys=True)


def test_due_events_fire_after_their_offset():
    clock = FakeClock()
    src = ScriptedMarkerSource(
        [(0.0, MarkerEvent(1, "start", "p")), (0.5, MarkerEvent(2, "stop", "p"))],
        clock=clock,
    )
    first = src.poll()  # establishes start at t=100.0, offset 0.0 due
    assert [e.event_id for _, e in first] == [1]
    clock.t = 100.6
    second = src.poll()  # offset 0.5 now due
    assert [e.event_id for _, e in second] == [2]


def test_events_are_not_refired():
    clock = FakeClock()
    src = ScriptedMarkerSource([(0.0, MarkerEvent(1, "start", "p"))], clock=clock)
    assert len(src.poll()) == 1
    assert src.poll() == []


def test_marker_timestamp_is_start_plus_offset():
    clock = FakeClock()
    src = ScriptedMarkerSource([(0.25, MarkerEvent(1, "start", "p"))], clock=clock)
    src.poll()           # start = 100.0
    clock.t = 100.5
    [(ts, _)] = src.poll()
    assert ts == 100.25


def test_default_schedule_uses_event_label_vocab():
    labels = [e.label for _, e in default_schedule()]
    assert labels == ["start", "grasp", "place", "release", "stop"]
