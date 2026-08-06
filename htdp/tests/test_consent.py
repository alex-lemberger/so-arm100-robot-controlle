from htdp.schemas.models import Consent
from htdp.schemas.enums import ReleaseProfile
from htdp.consent.profiles import check_consent


def _full_consent(**over) -> Consent:
    base = dict(
        consent_form_version="v1",
        commercial_use=True,
        model_training=True,
        third_party_access=True,
        public_release=True,
        internal_only=False,
    )
    base.update(over)
    return Consent(**base)


def test_commercial_profile_allows_when_flags_set():
    assert check_consent(_full_consent(), ReleaseProfile.COMMERCIAL_DATASET) == []


def test_commercial_profile_blocks_when_flag_missing():
    missing = check_consent(_full_consent(model_training=False), ReleaseProfile.COMMERCIAL_DATASET)
    assert "model_training" in missing


def test_internal_research_profile_minimal():
    assert check_consent(Consent(consent_form_version="v1"), ReleaseProfile.INTERNAL_RESEARCH) == []
