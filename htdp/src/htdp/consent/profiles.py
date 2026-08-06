from htdp.schemas.enums import ReleaseProfile
from htdp.schemas.models import Consent

REQUIRED_FLAGS: dict[ReleaseProfile, tuple[str, ...]] = {
    ReleaseProfile.INTERNAL_RESEARCH: (),
    ReleaseProfile.PUBLIC_SAMPLE: ("public_release",),
    ReleaseProfile.COMMERCIAL_DATASET: ("commercial_use", "model_training", "third_party_access"),
}


def check_consent(consent: Consent, profile: ReleaseProfile) -> list[str]:
    return [flag for flag in REQUIRED_FLAGS[profile] if not getattr(consent, flag)]
