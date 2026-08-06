from htdp.export.labels import entity_stem, sanitize


def test_sanitize_strips_non_alphanumeric():
    assert sanitize("p-0001") == "p0001"
    assert sanitize("reach-grasp-place") == "reachgraspplace"
    assert sanitize("vive_synth 2") == "vivesynth2"


def test_entity_stem_format():
    assert entity_stem("p0001", "reachgraspplace", "vivesynth") == (
        "sub-p0001_task-reachgraspplace_tracksys-vivesynth"
    )
