import json

import pytest

from htdp.ingest.session import build_event_rows


def _payloads():
    return [
        json.dumps(
            {"event_id": 0, "label": "start", "phase": "approach", "confidence": 1.0, "notes": ""},
            sort_keys=True,
        ),
        json.dumps(
            {"event_id": 1, "label": "grasp", "phase": "grasp", "confidence": 0.9, "notes": "x"},
            sort_keys=True,
        ),
    ]


def test_build_event_rows_decodes_and_rebases():
    rows = build_event_rows([1000.0, 1001.0], _payloads(), 1000.0)
    assert rows[0]["timestamp_s"] == pytest.approx(0.0)
    assert rows[1]["timestamp_s"] == pytest.approx(1.0)
    assert rows[0]["label"] == "start"
    assert rows[1]["event_id"] == 1
    assert rows[1]["confidence"] == 0.9
    assert rows[1]["notes"] == "x"


def test_build_event_rows_sets_source_real():
    rows = build_event_rows([1000.0], _payloads()[:1], 1000.0)
    assert rows[0]["source"] == "real"
