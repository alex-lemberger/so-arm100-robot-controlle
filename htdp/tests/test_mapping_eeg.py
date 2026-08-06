import pytest

from htdp.ingest.mapping import EegStreamMap, MappingError, parse_ingest_map

_MCH = {"x_m": 0, "y_m": 1, "z_m": 2, "qw": 3, "qx": 4, "qy": 5, "qz": 6, "quality": 7}


def _raw(eeg_entry):
    return {
        "wrist": {"role": "motion", "tracker_id": "right_wrist", "channels": dict(_MCH)},
        "brain": eeg_entry,
        "marker": {"role": "events"},
    }


def test_parse_resolves_eeg_entry():
    im = parse_ingest_map(_raw({"role": "eeg", "eeg_id": "eeg", "channels": {"Fp1": 0, "Cz": 1}}))
    assert "brain" in im.eeg
    assert im.eeg["brain"] == EegStreamMap(eeg_id="eeg", channels={"Fp1": 0, "Cz": 1})


def test_eeg_is_optional():
    im = parse_ingest_map(
        {
            "wrist": {"role": "motion", "tracker_id": "right_wrist", "channels": dict(_MCH)},
            "marker": {"role": "events"},
        }
    )
    assert im.eeg == {}


def test_eeg_missing_id_raises():
    with pytest.raises(MappingError, match="eeg_id"):
        parse_ingest_map(_raw({"role": "eeg", "channels": {"Fp1": 0}}))


def test_eeg_empty_channels_raises():
    with pytest.raises(MappingError, match="channels"):
        parse_ingest_map(_raw({"role": "eeg", "eeg_id": "eeg", "channels": {}}))


from htdp.ingest.mapping import extract_eeg  # noqa: E402
from htdp.ingest.reader import XdfStream  # noqa: E402


def _eeg_stream():
    return XdfStream(
        name="brain",
        type="eeg",
        channel_format="double64",
        time_stamps=[5.0, 5.004],
        time_series=[[1.0, 2.0, 3.0], [1.1, 2.1, 3.1]],
    )


def test_extract_eeg_builds_labelled_rows():
    m = EegStreamMap(eeg_id="eeg", channels={"Fp1": 0, "Fp2": 1, "Cz": 2})
    labels, rows = extract_eeg(_eeg_stream(), m)
    assert labels == ["Fp1", "Fp2", "Cz"]
    assert rows[0] == {"raw_ts": 5.0, "Fp1": 1.0, "Fp2": 2.0, "Cz": 3.0}
    assert rows[1]["Cz"] == 3.1


def test_extract_eeg_rejects_string_stream():
    m = EegStreamMap(eeg_id="eeg", channels={"Fp1": 0})
    bad = XdfStream(
        name="brain", type="eeg", channel_format="string", time_stamps=[0.0], time_series=["x"]
    )
    with pytest.raises(MappingError, match="numeric"):
        extract_eeg(bad, m)


def test_extract_eeg_channel_out_of_range():
    m = EegStreamMap(eeg_id="eeg", channels={"Fp1": 9})
    with pytest.raises(MappingError, match="out of range"):
        extract_eeg(_eeg_stream(), m)
