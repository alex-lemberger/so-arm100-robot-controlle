# htdp-capture

Hardware-free VIVE -> LSL -> XDF capture app. Emits a contract-conforming
`.xdf` + `ingest.json` consumable by `htdp ingest`. Mock pose/marker sources
make it runnable with no hardware; the OpenVR adapter is a later milestone.

See `docs` in human-task-dataset-pipeline for the design spec/plan.


## Real-hardware capture (OpenVR)

`OpenVRPoseSource` reads VIVE tracker poses from SteamVR via OpenVR and is a
drop-in `PoseSource` for `run_capture`. Install the extra on the SteamVR machine:

    uv sync --extra openvr

Map each physical tracker's serial to a contract tracker_id and pass it as
`CaptureConfig.device_map`, e.g. `{"LHR-1A2B3C4D": "right_wrist"}`. Only mapped,
connected devices are captured; HMD/controllers/base stations are ignored.

**Platform note:** `import openvr` requires an x86_64 build of the OpenVR runtime
and a running SteamVR; it fails to import on Apple Silicon. The conversion and
adapter logic are unit-tested hardware-free with an injected system handle — the
real `openvr.init()` path runs on the SteamVR capture box.

Deferred to the live-hardware mile: CLI wiring, a real-tracker smoke test, and
`frame_transform` calibration against the measured world origin.
