import sys
from pathlib import Path

import pytest

from htdp.ingest.reader import IngestUnavailable, XdfStream, load_xdf_streams


def test_ingest_unavailable_is_runtime_error():
    assert issubclass(IngestUnavailable, RuntimeError)


def test_xdf_stream_dataclass_fields():
    s = XdfStream(
        name="m",
        type="motion",
        channel_format="double64",
        time_stamps=[0.0, 0.01],
        time_series=[[1.0], [2.0]],
    )
    assert s.name == "m" and s.time_stamps[1] == 0.01


def test_missing_pyxdf_raises_ingest_unavailable(monkeypatch):
    monkeypatch.setitem(sys.modules, "pyxdf", None)  # forces ImportError on `import pyxdf`
    with pytest.raises(IngestUnavailable):
        load_xdf_streams(Path("nonexistent.xdf"))
