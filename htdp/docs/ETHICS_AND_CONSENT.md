# Ethics and Consent

This document describes the consent model, release profiles, and ethics principles
governing data collected and packaged by the Human-Task Dataset Pipeline.

---

## Consent model

Each raw session folder contains a `consent.json` that records the participant's
granular permissions at the time of data collection. The schema is defined in
`src/htdp/schemas/models.py` (`Consent`) and exported to `docs/schemas/Consent.schema.json`.

### Consent flags

| Flag | Description |
|------|-------------|
| `commercial_use` | Data may be used for commercial purposes |
| `distribute_raw_video` | Raw video may be distributed (empty slot in v0.1) |
| `distribute_raw_eeg` | Raw EEG may be distributed (empty slot in v0.1) |
| `derived_features_only` | Only derived features (not raw sensor data) may be shared |
| `model_training` | Data may be used to train machine-learning models |
| `public_release` | Data may be released publicly |
| `internal_only` | Data must remain internal to the collecting organization |
| `third_party_access` | Data may be shared with third parties |
| `delete_after` | ISO date after which data must be deleted (optional) |
| `consent_form_version` | Version string of the consent form shown to participant |

All flags default to the most restrictive interpretation (absent = false).

---

## Release profiles

The `package` command requires a `--profile` argument. The profile declares the
intended use of the release and triggers consent enforcement.

| Profile | Required consent flags |
|---------|----------------------|
| `internal_research` | None beyond consent being present |
| `public_sample` | `public_release` |
| `commercial_dataset` | `commercial_use`, `model_training`, `third_party_access` |

### Block-on-conflict rule

If any required flag is absent or false in `consent.json`, `package` **refuses and
writes nothing**. There is no partial output. The error message names the missing flag
explicitly. This is the core safety guarantee of the pipeline.

### Modality filtering

Permission flags (`commercial_use`, `model_training`, `third_party_access`,
`public_release`) **block** — a session whose consent lacks a required permission
flag is excluded from the release entirely, and nothing is written.

Modality flags (`distribute_raw_video`, `distribute_raw_eeg`) **filter per-session** —
a session remains included but its disallowed modality files are omitted from the
staged release and recorded in `manifest.absent_modalities_by_session`. The
release-wide `absent_modalities` lists only modalities absent from **every** session
(intersection), so a modality kept by at least one session is not listed as globally
absent. Motion data is never filtered.

---

## Atomicity guarantee

`package` writes to a staging directory first. Only after all validations, consent
checks, manifest generation, and checksums pass does it atomically move staging into
`data/releases/<name>`. A failed `package` leaves **no** release directory on disk.
This prevents partial or inconsistent releases from being treated as valid.

---

## Absent modalities

Video and EEG are empty schema slots in v0.1. Their absence does **not** block
packaging, but it is recorded in the release manifest so downstream consumers know these
modalities were not captured.

---

## Principles

1. **Consent is the gate, not an afterthought.** Every release is blocked unless all
   required permissions are explicitly present.
2. **Raw data is immutable.** Once a session folder is written and checksummed, its
   contents must not change. `process` reads raw data but never writes to it.
3. **Errors must be explicit.** A failed consent check names the missing flag. A
   checksum mismatch names the file. No silent failures.
4. **No data is collected in v0.1.** The synthetic spine proves the factory before any
   human participant data exists. All consent machinery is tested against synthetic
   `consent.json` records generated with full permissions.
5. **Delete-after must be honoured.** The `delete_after` field is present on the schema
   and must be enforced in any production deployment (out of scope for v0.1).
