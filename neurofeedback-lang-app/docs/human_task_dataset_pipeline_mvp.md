# Consent-Based Human-Task Dataset Pipeline for Robotics

## 1. Project Summary

This project is a **data-platform-first system** for collecting, validating, processing, annotating, packaging, and distributing multimodal human-task datasets for robotics, industrial automation, human-robot interaction, ergonomics, and adaptive systems.

The goal is not to build a polished SaaS product first. The goal is to build a small, reliable local **data factory** that can produce high-quality, reproducible human-task dataset releases.

The first product unit is not an app. The first product unit is a dataset release.

The first target dataset should be:

**Human Reach-Grasp-Place Dataset v0.1**

This dataset should capture participants performing controlled physical tasks such as reaching for an object, grasping it, moving it, placing it, correcting an error, hesitating, choosing between objects, repeating a task, or adapting under mild fatigue.

The dataset should initially include motion tracking, object tracking, reference video, event markers, metadata, annotations, quality-control reports, and export packages. EEG can be added after the basic motion and event pipeline is stable.

---

## 2. Main Thesis

The future bottleneck in robotics is not only robot hardware or model architecture. A major bottleneck is **high-quality human-task data**.

Robots need structured examples of how humans perform tasks: reaching, grasping, placing, correcting errors, hesitating, handing over objects, using tools, inspecting quality, and adapting under fatigue or uncertainty.

The project should therefore focus on creating a reusable, consent-based **Task Library** and **Dataset Pipeline** rather than a generic web application.

The long-term product can become a subscription-style data platform for robotics teams, but the first milestone is a clean, reproducible dataset pipeline.

A useful positioning statement:

**Consent-based human-task data infrastructure for human-aware robotics.**

Or:

**A Task Library and dataset pipeline for human-aware robotics.**

---

## 3. Product Direction

The long-term product is a Task Library and dataset subscription platform for human-aware robotics.

Potential customers include:

- robotics labs;
- cobot companies;
- warehouse automation vendors;
- industrial R&D teams;
- ergonomics teams;
- adaptive automation teams;
- robot-learning researchers;
- simulation and robot foundation model teams.

The product may eventually provide:

- dataset subscriptions;
- custom task capture;
- baseline models;
- ROS exports;
- simulation-ready packages;
- skill-ready data packages;
- task protocol libraries;
- quality-control tooling;
- consent-aware dataset governance.

The moat is not the frontend. The moat is the repeatable capture protocol, quality of synchronization, consent-based data governance, Task Library, annotations, QC reports, and accumulated human-task dataset releases.

---

## 4. MVP Philosophy

The MVP should be local-first and pipeline-first.

The goal is to build a small data factory that can record, validate, process, annotate, package, and export 10–20 high-quality sessions.

The web dashboard is secondary. The core product is the repeatable dataset pipeline.

The first MVP should not attempt to solve full robot learning. It should create the infrastructure that produces useful training and evaluation data for future robot-learning systems.

Do not start with Kubernetes, a cloud deployment, marketplace features, billing, complex authentication, or large ML models.

Start with a reproducible pipeline.

---

## 5. MVP Hardware Landscape

The MVP hardware should stay under approximately **3,000 EUR** if possible.

The goal is not lab-grade optical motion capture. The goal is a practical, portable, reproducible capture setup.

### 5.1 Motion Tracking Core

Use HTC VIVE Ultimate Trackers or a similar 6DoF tracker system.

A good starting setup:

- one VIVE Ultimate Tracker 3+1 Kit;
- two or three additional trackers;
- target: five to six total trackers.

Suggested tracker placement:

- right wrist;
- left wrist;
- torso or pelvis;
- one object or tool;
- optional head, chest, ankle, or second object.

The MVP does not need perfect full-body skeleton tracking. It should prioritize reliable tracking of hands, torso, and manipulated objects.

### 5.2 Mounting and Straps

Order:

- wrist straps;
- waist straps;
- universal tracker mounts;
- Velcro;
- object mounts;
- small adjustable holders;
- optionally 3D-printable holders later.

Mounting quality is important. Bad mounting creates noisy data, slipping trackers, and poor repeatability.

### 5.3 Reference Video

Use at least one reference camera.

A normal webcam, phone camera, action camera, or USB camera is enough for the first MVP.

Depth cameras such as Intel RealSense can be added later, but they are not mandatory for Dataset v0.1.

The camera is used for human inspection, annotation, and quality control, not as the primary ground-truth motion source.

### 5.4 Event Marker Hardware

Use an ESP32 or Arduino board with physical buttons and an LED marker.

Buttons can represent events such as:

- start;
- stop;
- grasp;
- release;
- error;
- correction;
- task phase boundary.

The LED marker can be visible in the video to help verify synchronization manually.

Event markers should eventually be sent into the recording system through LSL.

### 5.5 Storage and Connectivity

Use a recording laptop or mini-PC with:

- ideally 32 GB RAM;
- fast internal SSD storage;
- enough USB ports;
- powered USB hub;
- stable Wi-Fi or Ethernet.

Use at least one 2 TB external SSD for backups.

Raw data should never exist in only one place.

### 5.6 Experimental Task Station

Use:

- a small table;
- fixed camera position;
- stable lighting;
- marked start and target zones;
- simple objects;
- tools;
- boxes;
- screws;
- blocks;
- containers;
- repeatable task layouts.

The first lab space can be small, around 3 by 3 meters or 4 by 4 meters. Repeatability is more important than size.

### 5.7 EEG Hardware

EEG can be added after the basic motion and event pipeline works.

The first MVP can be motion-first. EEG should not block the project.

When EEG is added, it should be recorded through LSL if possible and synchronized with motion streams and event markers.

EEG should be treated as an additional modality, not as the first dependency.

### 5.8 Hardware Upgrade Strategy

Do not buy expensive sensors before proving the pipeline.

Avoid buying the following at the very beginning:

- MANUS gloves;
- Xsens;
- OptiTrack;
- Vicon;
- Qualisys;
- full optical mocap room;
- expensive depth camera setups;
- large NAS or server hardware.

Suggested stages:

1. Stage 1: VIVE trackers, video, event markers.
2. Stage 2: better hand tracking, possibly Rokoko or MANUS gloves.
3. Stage 3: EEG.
4. Stage 4: Xsens or another full-body inertial system.
5. Stage 5: optical mocap such as OptiTrack, Vicon, or Qualisys for dataset-grade ground truth.

---

## 6. Software and Infrastructure Landscape

The MVP infrastructure should be local-first.

The system should run on one development machine or local workstation using Docker Compose.

Core software layers:

1. acquisition layer;
2. processing layer;
3. metadata layer;
4. object-storage layer;
5. backend API;
6. dashboard;
7. CLI layer.

---

## 7. Acquisition Layer

Use **LSL** and **LabRecorder** as the initial acquisition backbone.

Streams may include:

- motion trackers;
- EEG;
- event markers;
- external sensors;
- reference signals;
- optionally video timestamps or camera-related signals.

Raw multimodal recordings should be stored as **XDF** files.

Video should be stored separately as MP4 or another common video format.

Device configuration should be stored as JSON.

The acquisition layer should be simple, reliable, and reproducible.

---

## 8. Processing Layer

Use Python as the main processing language.

Python is preferred because EEG, biosignal processing, time-series handling, scientific computing, quality-control reporting, and machine-learning baselines are best supported by the Python ecosystem.

Useful libraries:

- pyxdf;
- MNE;
- NumPy;
- SciPy;
- Pandas or Polars;
- PyArrow;
- Pydantic;
- scikit-learn later;
- PyTorch later;
- Jupyter for exploration.

The processing pipeline should handle:

- loading raw recordings;
- validating streams;
- aligning timestamps;
- checking missing data;
- checking drift;
- extracting events;
- exporting Parquet files;
- generating QC reports;
- packaging dataset releases.

Python is not necessarily the entire backend. Python is the data-processing engine.

---

## 9. Metadata Layer

Use **PostgreSQL** for metadata.

PostgreSQL must not store raw EEG, motion, video, or large time-series files.

PostgreSQL should store:

- participants;
- sessions;
- task protocols;
- devices;
- files;
- annotations;
- consent status;
- QC status;
- dataset releases;
- processing jobs;
- file references;
- checksums;
- processing state.

Signals and large files belong in object storage or a structured file system.

---

## 10. Object Storage Layer

Use **MinIO** as local S3-compatible object storage during MVP development.

Large files should be stored in MinIO or in a structured local file system.

Large files include:

- XDF;
- MP4;
- Parquet;
- ROS bags;
- HTML reports;
- dataset archives;
- generated exports.

This makes the project cloud-ready without requiring cloud infrastructure during the MVP.

---

## 11. Backend Layer

Use **FastAPI** for the MVP backend because it integrates naturally with Python processing.

FastAPI should expose APIs for:

- sessions;
- participants;
- protocols;
- files;
- annotations;
- consent;
- processing status;
- QC reports;
- dataset releases;
- export links.

A Spring Boot backend can be introduced later if the project needs a more enterprise-oriented platform layer.

If Spring Boot is used later, it should manage platform workflows, users, permissions, business logic, dataset catalog, and possibly billing. Python workers should remain responsible for signal processing and dataset generation.

---

## 12. Frontend Layer

Use **Angular** for the dashboard.

The first Angular dashboard should not be a polished marketplace.

It should be a dataset operations dashboard.

It should show:

- sessions;
- task protocols;
- participants;
- consent status;
- file status;
- processing status;
- QC warnings;
- annotations;
- dataset releases;
- export links;
- download links.

The dashboard is useful, but the pipeline and CLI should work without it.

---

## 13. CLI Layer

The project should have a command-line interface before the dashboard becomes complex.

Important CLI commands:

- create a new session;
- validate a session;
- generate checksums;
- extract streams;
- export Parquet;
- generate a QC report;
- package a dataset release;
- optionally export ROS bags later.

The CLI makes the pipeline reproducible, testable, and easier for a coding agent to modify safely.

---

## 14. Data Formats

The system should use layered data formats.

### 14.1 Raw Layer

Use:

- XDF for synchronized LSL recordings;
- MP4 or similar for reference video;
- JSON for device configuration;
- notes or markdown files for human-readable recording notes.

### 14.2 Processed Layer

Use:

- Parquet for motion samples, events, annotations, features, and ML-friendly tables;
- HTML for QC reports;
- JSON or YAML for manifests and metadata.

### 14.3 Research-Standard Layer

Eventually support:

- EEG-BIDS for EEG datasets;
- Motion-BIDS for motion data.

### 14.4 Robotics Layer

Eventually support:

- ROS 2 / rosbag2 export.

Robotics users should be able to replay motion, object, event, and possibly derived signal streams inside their ROS workflows.

### 14.5 Dataset Release Layer

Each dataset release should include:

- README;
- license;
- protocol description;
- participants table;
- sessions table;
- device configuration;
- manifest;
- checksums;
- raw data references;
- processed files;
- annotations;
- QC reports;
- export packages.

---

## 15. Core Data Model

A session is a first-class entity.

Each session should have:

- participant id;
- session id;
- protocol id;
- consent id;
- device configuration;
- start time;
- file list;
- annotations;
- QC status;
- processing status;
- checksums.

Raw data should be immutable once recorded.

Derived data can be regenerated.

A dataset release is a versioned package built from one or more validated sessions.

A task protocol is also a first-class entity.

---

## 16. Task Library

The **Task Library** is a central concept of the product.

It defines reusable human-task protocols.

Initial tasks may include:

- reach-grasp-place;
- handover;
- tool use;
- assembly;
- inspection;
- correction;
- fatigue loop;
- hesitation;
- uncertainty;
- object sorting;
- object alignment;
- insert-and-fasten;
- quality check;
- error detection and correction.

Each task protocol should define:

- goal;
- setup;
- objects;
- participant instructions;
- event markers;
- expected phases;
- optional error conditions;
- number of repetitions;
- annotation rules;
- safety notes;
- required sensors;
- optional sensors.

Public tutorials and videos can be used as sources of task knowledge, but not as raw commercial dataset data unless properly licensed.

A safer method is **video-guided task capture**: a participant watches or learns from a public or licensed instruction, then performs a new demonstration in the project’s controlled setup with explicit consent.

The dataset contains the newly recorded demonstration, not the original video.

---

## 17. Consent and Ethics

Consent must be part of the infrastructure from the beginning.

Every participant and every session must have consent metadata.

Consent is not optional text. It is a data constraint.

Dataset export must check consent rules before packaging data.

Consent metadata should describe:

- whether commercial use is allowed;
- whether raw video may be distributed;
- whether raw EEG may be shared;
- whether only derived features may be exported;
- whether third-party access is allowed;
- whether data can be used for model training;
- whether data can be used for public release;
- whether data can be used only internally;
- whether data must be deleted after a certain period;
- which consent form version applies.

The project should explicitly avoid:

- workplace surveillance;
- individual productivity scoring;
- hidden employee evaluation;
- non-consensual biometric collection;
- uncontrolled sharing of raw video or raw EEG.

Preferred ethical positioning:

**Consent-based human-task data infrastructure for human-aware robotics.**

Purpose:

- safer robotics;
- better ergonomics;
- adaptive automation;
- preservation of human task knowledge;
- better human-robot interaction;
- reduced physical burden;
- more transparent robotics datasets.

---

## 18. Demographic and Industrial Context

A strong product argument is that aging industrial societies face demographic pressure, skilled-labor shortages, and loss of tacit knowledge.

In old industrial economies, the problem is not simply that robots replace people. The problem is that experienced workers retire, younger workers are fewer, and tacit knowledge disappears.

This project can be positioned as a way to preserve and structure human working knowledge:

- how experienced workers move;
- how they avoid mistakes;
- how they handle tools;
- how they detect quality problems;
- how they correct errors;
- how fatigue changes motion;
- how safe handovers happen;
- how human task expertise can be documented.

Useful positioning:

**Human-task data infrastructure for aging industrial societies.**

Or:

**Preserving human task knowledge for safer, human-aware automation.**

---

## 19. Video-Guided Task Capture

Existing public tutorials or archived videos can be useful as sources of task knowledge.

However, the project should not treat unlicensed YouTube videos as commercial dataset data.

The safer method is:

1. Use public or licensed video as inspiration or instruction.
2. Convert the task into a project-owned protocol.
3. Ask a consenting participant to perform the task in the controlled capture setup.
4. Record the new demonstration with project sensors.
5. Store only the newly recorded demonstration in the dataset.
6. Keep the source video out of the commercial dataset unless properly licensed.

This can be called:

- video-guided task capture;
- instruction-derived human-task capture;
- task-knowledge recapture.

This allows the project to use the internet as a source of task ideas while keeping the dataset consent-based and legally cleaner.

---

## 20. Agent-Orchestrated Pipeline

Technologies like Hermes or OpenClaw-like agent runtimes can be used as an orchestration layer, but not as the core data pipeline.

The core pipeline should remain explicit, testable, and command-driven.

Agent layer responsibilities may include:

- creating new task protocol drafts;
- creating new session templates;
- launching validation commands;
- launching QC generation;
- summarizing QC reports;
- checking whether consent metadata is present;
- creating dataset release notes;
- updating documentation;
- creating coding-agent tasks;
- managing a project skill library.

The agent should not silently:

- delete raw data;
- modify raw data;
- bypass consent checks;
- publish dataset releases;
- upload sensitive data externally;
- change licensing rules;
- rewrite manifests without validation.

A safe architecture:

- agent layer: Hermes/OpenClaw-like coordinator;
- command layer: explicit CLI commands;
- data layer: immutable raw data, manifests, checksums, consent metadata;
- human approval: required for deletion, publication, commercial export, and external sharing.

---

## 21. Repository Structure

The codebase should be organized around the dataset pipeline.

Suggested top-level areas:

- `acquisition`: LSL streams, event markers, tracker adapters, session recording helpers.
- `processing`: XDF loading, stream extraction, synchronization checks, Parquet export, QC reports.
- `backend`: FastAPI APIs, metadata management, processing jobs, dataset release management.
- `frontend`: Angular dashboard.
- `schemas`: Pydantic models and JSON schemas for sessions, manifests, devices, consent, files, annotations, and dataset releases.
- `protocols`: Task Library definitions and task protocol documents.
- `docs`: architecture, roadmap, ethics, data contracts, setup instructions.
- `tests`: unit tests and integration tests.
- `sample-data`: small synthetic fixtures only, not real large data.

The repository should include:

- `AGENTS.md` for coding-agent instructions;
- `README.md` for project overview;
- `ROADMAP.md` for milestones;
- `ARCHITECTURE.md` for system design;
- `DATA_CONTRACT.md` for data schemas and folder conventions;
- `ETHICS_AND_CONSENT.md` for consent rules;
- `TASK_LIBRARY.md` for task protocol catalog;
- `docker-compose.yml` for local infrastructure;
- `Makefile` or `Taskfile` for repeatable commands;
- `.env.example` for local environment variables.

---

## 22. Coding-Agent Harness

The coding agent should understand that this project is data-platform-first, not UI-first.

Recommended AGENTS.md principles:

- The project is a consent-based human-task dataset pipeline for robotics.
- The core goal is reproducible dataset production.
- UI is secondary to capture, validation, processing, QC, consent, and export.
- Do not store raw signals in PostgreSQL.
- Do not commit large raw data files.
- Do not add cloud dependencies unless explicitly requested.
- Do not bypass consent checks.
- Do not change data contracts without updating documentation and tests.
- Prefer local-first Docker Compose infrastructure.
- Prefer Python for signal processing, QC, conversion, and ML baselines.
- Keep sample fixtures small.
- Make errors explicit.
- Preserve manifests and checksums.
- Treat raw data as immutable.

The coding agent should optimize for:

- reproducibility;
- data integrity;
- clear schemas;
- local-first execution;
- testability;
- small vertical slices;
- documentation updates when contracts change.

---

## 23. First MVP Milestone

The first milestone should be:

**Dataset Pipeline v0.1**

It should include:

- session metadata schema;
- manifest schema;
- consent metadata schema;
- local folder convention;
- validation command;
- checksum generation;
- simple XDF or synthetic fixture extraction;
- Parquet export;
- HTML QC report;
- dataset package creation;
- small sample fixtures;
- tests;
- documentation.

The first dashboard can come after the CLI and pipeline are reliable.

The first dataset release should be small but clean.

---

## 24. MVP Success Criteria

The MVP is successful if it can:

1. record or simulate a small human-task session;
2. validate the session;
3. preserve raw data;
4. generate checksums;
5. extract streams;
6. export processed Parquet files;
7. produce a human-readable QC report;
8. enforce consent constraints;
9. package a reproducible dataset release;
10. allow a robotics engineer to inspect the result and understand how to use it.

The goal is not dataset size.

The goal is trust.

A robotics engineer should be able to say:

**This data is documented, synchronized, versioned, reproducible, and usable.**

---

## 25. Definition of Done

A code change is done only if:

- tests pass;
- schemas are updated;
- documentation is updated when data contracts change;
- sample fixtures remain small;
- no raw personal data is committed;
- no heavy raw data files are committed;
- errors are explicit;
- raw data is not silently modified;
- manifests and checksums are preserved;
- consent checks are not bypassed;
- validation rules still work;
- local setup remains reproducible.

Every new feature should support at least one of the following goals:

- capture;
- validation;
- processing;
- annotation;
- quality control;
- consent management;
- export;
- dataset release;
- Task Library growth.

If a feature does not support one of these goals, it is probably not needed for the MVP.

---

## 26. Practical First Build Order

Recommended first build order:

1. Create repository structure.
2. Add AGENTS.md, README.md, ROADMAP.md, DATA_CONTRACT.md, ETHICS_AND_CONSENT.md, and TASK_LIBRARY.md.
3. Define session schema.
4. Define manifest schema.
5. Define consent schema.
6. Define file reference schema.
7. Create small synthetic sample session.
8. Add CLI command to validate session folder.
9. Add checksum generation.
10. Add simple processing pipeline for sample data.
11. Export Parquet.
12. Generate QC HTML report.
13. Package Dataset v0.1.
14. Add FastAPI only after the CLI is stable.
15. Add Angular dashboard only after backend and data contracts are stable enough.

---

## 27. Summary

This project should start as a small, serious, consent-based data factory for human-task datasets.

The MVP is not a marketplace, not a robot brain, and not a full SaaS platform.

The MVP is a reproducible pipeline that turns controlled human task recordings into trusted dataset releases.

The long-term product is a Task Library and dataset platform for human-aware robotics.

The core values are:

- consent;
- reproducibility;
- synchronization quality;
- task structure;
- data integrity;
- human dignity;
- practical usefulness for robotics.
