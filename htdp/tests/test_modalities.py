from htdp.consent.modalities import resolve_absent
from htdp.schemas.models import Consent


def _c(**over) -> Consent:
    base = dict(consent_form_version="v1", distribute_raw_video=True, distribute_raw_eeg=True)
    base.update(over)
    return Consent(**base)


def test_allowed_and_present_is_not_absent():
    absent, drop = resolve_absent([_c()], {"video", "eeg"})
    assert absent == []
    assert drop == []


def test_forbidden_and_present_is_absent_and_dropped():
    absent, drop = resolve_absent([_c(distribute_raw_video=False)], {"video", "eeg"})
    assert absent == ["video"]
    assert drop == ["video/**/*"]


def test_not_present_is_absent_but_not_dropped():
    absent, drop = resolve_absent([_c()], set())  # nothing present
    assert absent == ["eeg", "video"]
    assert drop == []  # nothing on disk to remove


def test_release_level_union_one_forbidding_consent_drops_for_all():
    consents = [_c(), _c(distribute_raw_video=False)]  # one allows, one forbids
    absent, drop = resolve_absent(consents, {"video", "eeg"})
    assert absent == ["video"]
    assert drop == ["video/**/*"]


def test_absent_list_is_sorted():
    absent, _ = resolve_absent(
        [_c(distribute_raw_video=False, distribute_raw_eeg=False)], {"video", "eeg"}
    )
    assert absent == ["eeg", "video"]
