from __future__ import annotations

PARTICIPANTS_HEADER: list[str] = ["participant_id", "cohort"]


def dataset_description(session_id: str) -> dict[str, object]:
    return {
        "Name": session_id,
        "BIDSVersion": "1.10.0",
        "DatasetType": "raw",
        "GeneratedBy": [{"Name": "htdp"}],
    }


def motion_json(task: str, tracksys: str, trackers: list[str], fps: float) -> dict[str, object]:
    n = len(trackers)
    return {
        "TaskName": task,
        "SamplingFrequency": fps,
        "TrackingSystemName": tracksys,
        "MotionChannelCount": 8 * n,
        "POSChannelCount": 3 * n,
        "ORNTChannelCount": 4 * n,
        "ACCELChannelCount": 0,
        "GYROChannelCount": 0,
        "MAGNChannelCount": 0,
        "SpatialAxes": "RFU",
    }


def participants_rows(sub: str, cohort: str) -> list[dict[str, str]]:
    return [{"participant_id": f"sub-{sub}", "cohort": cohort}]


def readme_text(session_id: str) -> str:
    return (
        f"# Motion-BIDS export of {session_id}\n\n"
        "Single-session export from the htdp pipeline. Motion is stored with an "
        "explicit `timestamp_s` column and `n/a` for missing samples (irregular "
        "sampling preserved, not resampled).\n"
    )
