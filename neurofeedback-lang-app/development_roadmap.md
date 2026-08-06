# Development Roadmap: NeuroAdaptive Learning

This document maps the Marketability Strategy to a technical execution plan, divided into three developmental phases.

## 1. Technical Specification (The "Unified Sensor" Architecture)

To support both tiers, the application must move from a hardware-dependent model to a **Sensor Agnostic Interface**.

### Existing assets to build on (do not reinvent)
The repo already ships several layers this plan should *compose*, not replace:
*   **`BrainDevice` abstraction** — already decouples `focus$`/`calm$` from any single headset (Neurosity, Muse, Mock adapters). The premium engagement source wraps this, not `NeurosityService` directly.
*   **`ExerciseSource` strategy pattern** — already the seam for swapping exercise content/difficulty (the hook Phase 3's adaptive engine drives).
*   **Flow detection** — already implemented; the "Flow State" narrative is partly built, not greenfield.
*   **Capture telemetry pipeline** — the capture module already streams time-series biometrics to Supabase Storage + tables; reuse this ingestion path for high-frequency interaction logs rather than building a new one.

### Core Architectural Shift: `EngagementProvider` Pattern
Add an abstraction layer *on top of* the existing `BrainDevice` layer — do not bypass it.
*   **Interface:** `IEngagementSource`
    *   `getFocusScore(): Observable<number>`
    *   `getCalmScore(): Observable<number>`
    *   `getInteractionMetrics(): Observable<UserActivityMetrics>`
*   **Implementations:**
    1.  `EEGEngagementSource`: (Premium) Wraps the existing `BrainDevice` abstraction (Neurosity/Muse), **not** `NeurosityService` directly.
    2.  `InteractionEngagementSource`: (Standard) Tracks response latency, error rate, and session cadence.
    3.  `WebcamEngagementSource`: (Research spike) Optional, consent-gated CV gaze signal — see Phase 1 caveat. Never a launch dependency.

---

## 2. Phased Development Plan

### Phase 1: Foundation & Standard Tier (The "Minimum Viable Product")
**Goal:** Release a high-quality, hardware-agnostic language learning app that creates the initial user base and data stream.

*   **[Infrastructure] Refactor State Management:** Update `CaptureState` and `ExerciseState` to consume the new `IEngagementSource` interface — which itself sits on the existing `BrainDevice` layer (reuse, don't replace).
*   **[Feature] Interaction Analytics Engine:** Implement a service to track:
    *   Response Latency (Time between prompt and answer).
    *   Error Clustering (Identifying patterns in linguistic mistakes).
    *   Session Cadence (Rhythm of interaction).
*   **[Research Spike] Computer Vision (Opt-in):** Prototype `MediaPipe` gaze estimation as an *optional, consent-gated* signal — experimental only. Gaze is a weak engagement proxy and always-on webcam carries GDPR weight (EU/Frankfurt). **Not** a launch dependency for the Standard tier; ship interaction analytics first.
*   **[Backend] Standardized Telemetry Schema:** Update Supabase tables to store high-frequency interaction logs (no longer strictly tied to EEG timestamps).

### Phase 2: Premium Tier & Hardware Optimization
**Goal:** Bridge the gap between software metrics and neurofeedback for power users.

*   **[Feature] Advanced Neuro-Features:** Implement advanced Signal Processing in `NeurosityService` (e.g., Alpha/Beta ratio calculation, spectral density analysis).
*   **[UI/UX] Real-time Biometric Dashboard:** Develop premium D3 visualizations that sync EEG waveforms with linguistic performance timelines.
*   **[Feature] Hardware Onboarding Flow:** Create a seamless "Connect Headset" wizard within the app.

### Phase 2.5: Validation Gate (Prove the Hypothesis)
**Goal:** Before building the adaptive engine, prove the core scientific claim — that EEG/proxy engagement signals actually correlate with learning outcomes. Phase 3 is gated on this passing.

*   **[Data Science] Correlation Study:** Using the Premium cohort's EEG + outcome data, measure correlation between engagement signals and retention/error-reduction. Define a go/no-go threshold *before* running it.
*   **[Data Science] Proxy Calibration:** Test whether interaction proxies (latency/cadence/error) can approximate the EEG ground truth well enough to drive adaptation in the hardware-free tier. This is the actual moat — validate it.
*   **Exit criteria:** Documented effect size + a usable proxy↔EEG mapping. If it fails, revisit the thesis rather than shipping unvalidated "neuro" claims.

### Phase 3: The Adaptive Intelligence (The "Moat")
**Goal:** Fully automate the difficulty adjustment using the *validated* dataset (gated on Phase 2.5).

*   **[ML/AI] Adaptive Difficulty Engine:** Develop an algorithm that uses the `EngagementScore` to trigger `ExerciseSource` changes (e.g., if Focus < 0.3, switch to "Simplified" mode).
*   **[Data Science] Longitudinal Analysis:** Build tools to analyze long-term correlation between neural state stability and language retention rates.
*   **[Product] Personalized Learning Profiles:** Generate user reports showing the relationship between their cognitive habits (e.g., "You learn best when your Calm score is > 0.7") and their progress.

---

## 3. Key Milestones & Deliverables

| Milestone | Primary Deliverable | Target Audience |
| :--- | :--- | :--- |
| **M1: The Core Engine** | Unified `IEngagementSource` architecture. | Internal Devs |
| **M2: MVP Release** | Web-based, interaction-only learning app. | Mass Market (Standard) |
| **M3: Neuro-Integration** | Full EEG connectivity & Premium Dashboard. | Biohackers (Premium) |
| **M3.5: Validation Gate** | Correlation study + proxy calibration (go/no-go). | Internal / Research |
| **M4: Adaptive Autonomy** | Automated difficulty scaling based on telemetry. | All Users |

*(Note: milestones above are sequence-only — no dates, effort, or team sizing yet. Add timeboxes and owners before treating this as a commitment.)*

## 4. Success Metrics
*   **Retention (Standard):** Day 30 retention rate of software-only users.
*   **Engagement (Premium):** Percentage of sessions utilizing active neurofeedback.
*   **Accuracy (System):** Correlation coefficient between `IEngagementSource` scores and actual linguistic performance changes.

## 5. Risks & Constraints
*   **Moat timing (chicken-and-egg):** The true differentiator (adaptive engine) ships last and needs data the early product generates. Sequence so the Premium cohort starts producing labeled data as early as possible.
*   **Standard-tier parity:** Software-only adaptive difficulty is table stakes for Duolingo/Babbel. Defensibility comes from the EEG-calibrated proxy engine (Phase 2.5/3), not from the Standard tier alone.
*   **Scientific validation:** Core "neuro" claims are unproven until M3.5. Do not market predictive/overload claims before the validation gate passes.
*   **Privacy & regulatory:** EEG and webcam data are sensitive (GDPR; EU/Frankfurt Supabase). Keep CV opt-in and consent-gated. Keep messaging non-clinical — "training," not "treatment" — and avoid safety-critical verticals (pilots/surgeons) absent a medical-device path.
*   **Scope reconciliation:** The existing capture module (Handwerk skill-capture: EEG + IMU + video) is not reflected in this plan. Decide explicitly whether it is a parallel product line to keep, a telemetry asset to reuse, or scope to retire.
