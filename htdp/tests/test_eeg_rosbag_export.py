# tests/test_eeg_rosbag_export.py
import json
from pathlib import Path

import pytest

pytest.importorskip("pyxdf")
pytest.importorskip("rosbags")

from rosbags.rosbag2 import Reader  # noqa: E402
from rosbags.typesys import Stores, get_types_from_msg, get_typestore  # noqa: E402

from htdp.export.rosbag import export_release_rosbag  # noqa: E402
from htdp.io.checksums import write_checksums  # noqa: E402
from htdp.ingest.session import ingest_xdf  # noqa: E402
from htdp.release.package import package_release  # noqa: E402
from htdp.schemas.enums import ReleaseProfile  # noqa: E402
from htdp.synth.generate import generate_session  # noqa: E402
from tests._xdf_writer import build_sidecar, write_xdf  # noqa: E402

_EEG_SAMPLE_TYPE = "htdp_msgs/msg/EegSample"
_EEG_SAMPLE_MSGDEF = "float64 stamp\nfloat32[] data\n"


def _reader_typestore():
    ts = get_typestore(Stores.ROS2_HUMBLE)
    ts.register(get_types_from_msg(_EEG_SAMPLE_MSGDEF, _EEG_SAMPLE_TYPE))
    return ts


def _ingest_eeg_session(tmp_path: Path, *, keep_eeg: bool) -> Path:
    src = generate_session(tmp_path / "sr", seed=1)
    eeg = ("eeg", ["Fp1", "Fp2", "Cz"], [0.0, 0.004], [[1.0, 2.0, 3.0], [1.5, 2.5, 3.5]])
    write_xdf(src, tmp_path / "x.xdf", eeg=eeg)
    sc = tmp_path / "i.json"
    sc.write_text(
        json.dumps(build_sidecar(src, eeg=("eeg", ["Fp1", "Fp2", "Cz"]))), encoding="utf-8"
    )
    session = ingest_xdf(tmp_path / "x.xdf", sc, tmp_path / "raw" / "real-0001")
    consent = session / "consent.json"
    data = json.loads(consent.read_text(encoding="utf-8"))
    data.update(
        {
            "distribute_raw_eeg": keep_eeg,
            "commercial_use": True,
            "model_training": True,
            "third_party_access": True,
            "public_release": True,
            "internal_only": False,
        }
    )
    consent.write_text(json.dumps(data), encoding="utf-8")
    write_checksums(session)
    return package_release(
        ["real-0001"],
        "rel",
        ReleaseProfile.COMMERCIAL_DATASET,
        tmp_path / "raw",
        tmp_path / "releases",
    )


def test_eeg_samples_and_labels_in_bag(tmp_path: Path):
    rel = _ingest_eeg_session(tmp_path, keep_eeg=True)
    out = export_release_rosbag(rel, tmp_path / "bags")
    bag = next(p for p in out.iterdir() if p.is_dir())
    ts = _reader_typestore()
    counts: dict[str, int] = {}
    first_data: list[float] = []
    labels = ""
    with Reader(bag) as rd:
        for conn, _t, raw in rd.messages():
            counts[conn.topic] = counts.get(conn.topic, 0) + 1
            if conn.topic == "/eeg/eeg" and not first_data:
                first_data = list(ts.deserialize_cdr(raw, conn.msgtype).data)
            if conn.topic == "/eeg/eeg/labels":
                labels = ts.deserialize_cdr(raw, conn.msgtype).data
    assert counts["/eeg/eeg"] == 2  # two sample rows
    assert counts["/eeg/eeg/labels"] == 1  # one-shot labels
    assert any(t.startswith("/motion/") for t in counts)  # motion still present
    assert first_data == pytest.approx([1.0, 2.0, 3.0], abs=1e-6)
    assert labels == "Fp1,Fp2,Cz"


def test_consent_dropped_eeg_has_no_eeg_topics(tmp_path: Path):
    rel = _ingest_eeg_session(tmp_path, keep_eeg=False)
    out = export_release_rosbag(rel, tmp_path / "bags")
    bag = next(p for p in out.iterdir() if p.is_dir())
    with Reader(bag) as rd:
        topics = {c.topic for c in rd.connections}
    assert not any(t.startswith("/eeg") for t in topics)
    assert any(t.startswith("/motion/") for t in topics)
