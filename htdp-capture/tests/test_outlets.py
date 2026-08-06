import pytest

pytest.importorskip("pylsl")

from pylsl import cf_double64, cf_string  # noqa: E402

from htdp_capture.outlets import make_events_outlet, make_motion_outlet  # noqa: E402


def test_motion_outlet_has_8_channels_double64():
    outlet = make_motion_outlet("right_wrist", 100.0)
    info = outlet.get_info()
    assert info.name() == "right_wrist"
    assert info.type() == "motion"
    assert info.channel_count() == 8
    assert info.channel_format() == cf_double64


def test_motion_outlet_labels_in_contract_order():
    info = make_motion_outlet("torso", 100.0).get_info()
    ch = info.desc().child("channels").child("channel")
    labels = []
    while not ch.empty():
        labels.append(ch.child_value("label"))
        ch = ch.next_sibling()
    assert labels == ["x_m", "y_m", "z_m", "qw", "qx", "qy", "qz", "quality"]


def test_events_outlet_is_string_markers():
    info = make_events_outlet().get_info()
    assert info.name() == "events"
    assert info.type() == "Markers"
    assert info.channel_count() == 1
    assert info.channel_format() == cf_string
    assert info.nominal_srate() == 0.0


from htdp_capture.outlets import make_eeg_outlet  # noqa: E402


def test_eeg_outlet_double64_named_and_labeled():
    outlet = make_eeg_outlet("amp0", ["Fp1", "Fp2", "C3"], 250.0)
    info = outlet.get_info()
    assert info.name() == "eeg_amp0"
    assert info.type() == "eeg"
    assert info.channel_count() == 3
    assert info.channel_format() == 2  # cf_double64 == 2
    assert info.nominal_srate() == 250.0
    ch = info.desc().child("channels").child("channel")
    labels = []
    while not ch.empty():
        labels.append(ch.child_value("label"))
        ch = ch.next_sibling()
    assert labels == ["Fp1", "Fp2", "C3"]
