# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] — 2026-06-23

Real-hardware ingest, multi-format export, robot-arm replay, a queryable catalog, and
per-session consent governance — added one modality/capability at a time on top of the v0.1
synthetic spine, with the downstream `validate → process → qc → package` pipeline unchanged.

### Added

- **Ingest (real hardware).** `htdp ingest` adapts an LSL `.xdf` recording (+ operator
  sidecar) into the raw representation; `htdp ingest-video` augments a session with an MP4;
  EEG streams ingest through the same XDF path. (`pyxdf` optional extra.)
- **BIDS export.** `htdp export-bids` (single session) and `htdp export-release-bids`
  (multi-subject release) write Motion-BIDS + BrainVision EEG-BIDS trees; read-only.
- **ROS 2 export.** `htdp export-release-rosbag` writes one rosbag2 (mcap) bag per session —
  motion, events, and EEG (custom `EegSample` message). (`rosbags` optional extra.)
- **Robot-arm replay.** `htdp replay-ik` drives a vendored arm's end-effector along a
  release's wrist path via `mink` differential IK; `--out` writes the per-step joint
  trajectory CSV; `--orientation-cost` enables full-pose (position + orientation) tracking on
  a 6-DOF arm. (`replay` optional extra: mujoco + mink + daqp.)
- **Catalog.** `htdp catalog` builds a one-row-per-session Parquet inventory;
  `htdp catalog-query` filters it (protocol/qc/participant/processing-status/modality + an
  inclusive `start_time_s` range); `htdp catalog-releases` builds a one-row-per-release
  inventory from each release's manifest.
- **End-to-end integration test** threading the whole CLI pipeline, with gated segments for
  the optional-extra stages.

### Changed

- **Consent filtering is now per-session.** A disallowed modality's files are dropped only
  from the sessions whose consent forbids it (was a release-wide union). The release manifest
  gains `absent_modalities_by_session`; release-wide `absent_modalities` now means "absent
  from every session." The profile consent gate (block-on-conflict) is unchanged.
- The vendored IK arm was upgraded from a 5-DOF placeholder to a 6-DOF arm so orientation IK
  can reach full pose.

### Notes

- The CLI pipeline is anchored to a `data/` working directory (`process`/`package` use
  `data/raw`, `data/processed`, `data/releases`).
- Optional extras stay optional: core install and core tests require none of
  `ingest`/`replay`/`rosbag`.

## [0.1.0]

Initial synthetic spine: seeded synthetic session generator with deliberate defect injection,
Pydantic schemas + JSON-Schema export, checksum-based immutability, `htdp validate` /
`process` / `qc` / `package` (consent-gated, reproducible releases), and MuJoCo mocap-body
`htdp replay`. Filesystem-only; no servers.
