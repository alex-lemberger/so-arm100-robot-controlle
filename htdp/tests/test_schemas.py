import pytest
from pydantic import ValidationError
from htdp.schemas.enums import EventLabel, ReleaseProfile
from htdp.schemas.models import Consent, Session


def test_consent_requires_form_version():
    with pytest.raises(ValidationError):
        Consent()  # type: ignore[call-arg]


def test_consent_defaults_are_restrictive():
    c = Consent(consent_form_version="v1")
    assert c.commercial_use is False
    assert c.model_training is False


def test_event_label_enum_values():
    assert {e.value for e in EventLabel} == {"start", "grasp", "release", "place", "stop"}


def test_session_round_trips_json():
    s = Session(
        session_id="s-001",
        participant_id="p-001",
        protocol_id="reach-grasp-place",
        consent_form_version="v1",
        device_config_id="vive-synth",
        start_time_s=0.0,
        qc_status="pass",
        processing_status="processed",
    )
    assert Session.model_validate_json(s.model_dump_json()) == s


def test_release_profiles_exist():
    assert {p.value for p in ReleaseProfile} == {
        "internal_research",
        "public_sample",
        "commercial_dataset",
    }
