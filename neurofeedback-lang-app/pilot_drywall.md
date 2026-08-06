# Field Pilot: Handwerk Skill Capture — Drywall Crew

**Status:** Proposed · **Vertical:** Handwerk skill capture (the `modules/capture/` platform, *not* the language-learning app) · **Partner:** a friend's drywall firm (warm intro, genuine interest)

## 1. The bet

Commercial robots that *do* drywall already exist and are leasable today (Okibo EG7, Canvas 1200CX, Hilti Jaibot). They are **appliances** — pre-programmed / BIM-driven, they do not learn from how a human works.

The robots that *learn a craft from human demonstration* (Vision-Language-Action models, imitation learning — Figure, Apptronik Apollo) are in pilots in **manufacturing and logistics**, not the trades, and not buyable for drywall now.

Our platform sits **upstream of both**: it captures what a skilled worker actually does — hand/arm **motion** (IMU), **focus/calm** (EEG), and **video** — as a time-aligned record of expert execution. That dataset is the raw material a learning robot would eventually train on, and in the near term it doubles as objective skill assessment and training material for human crews.

**Honest timeline:** the "captured skill trains a robot" payoff rides the learning-humanoid wave reaching the trades — a 2026+ bet, not this quarter. What is *real this quarter* is the capture pilot itself: build the dataset, prove workers will wear the kit, learn what good data looks like.

## 2. What the platform captures

Per worker, per session (already implemented, Phase 1):
- **Motion** — BLE IMU on each glove (left/right), raw streams → `imu_left.bin` / `imu_right.bin` in Supabase Storage.
- **EEG focus/calm** — headset stream → per-tick rows in the `eeg_ticks` table (FK → `captures`, cascade delete), gated behind a signal-quality check (≥3/4 good electrodes).
- **Video** — device camera → `video.mp4` in Storage, for ground-truth labelling of what the hands were doing.

Orchestrated by `CaptureSessionService`; the wizard is a hardware-gated state machine (`CaptureState.status`), so a worker is walked step-by-step and cannot proceed until each sensor is good. Consent is captured first (`worker-consent` component).

## 3. Pilot in two stages

### Stage 0 — Mock walkthrough (ready now, zero hardware)
The platform runs end-to-end in **mock mode** (`environment.device === 'mock'`, `CaptureModeService.isMock`). Use this to:
- Walk the friend + a worker or two through the exact flow (consent → setup → capture → upload → done).
- Validate the UX and the consent script with real trade people before any gear is bought.
- De-risk: confirm interest and gather "would my crew actually wear this?" feedback.

**Blocker to clear for Stage 0:** the app is localhost-only — no hosting exists. Either demo on our machine, or stand up a hosted HTTPS build (see §5).

### Stage 1 — Real capture (hardware-gated)
Workers wear the real kit on an actual job. Requires the hardware below and a hosted HTTPS deployment. This is the data-generating pilot.

## 4. Hardware kit & hard constraints

**Per capture station (1 worker):**
- 1× EEG headset — **Muse 2 or Muse S**, works today via the `muse-js` adapter (`environment.device = 'muse'`). Muse S = comfier soft band for field wear; Muse 2 = cheaper. Neurosity also supported.
- **2× custom IMU gloves — built, not bought** (see below).
- 1× camera device (the Android phone/tablet running the app has one).
- 1× **Android device running Chrome** to run the app.

> **The IMU gloves are a build, not a purchase.** `ImuService` speaks a *custom* BLE protocol, not any commercial sensor: the peripheral must advertise as `GloveLeft` / `GloveRight`, expose service UUID `12345678-…-9abc` (characteristic `…9abd` — placeholder UUIDs, i.e. the gloves were always intended as a custom build), and send each sample as **12 bytes = 6× int16 little-endian** (`ax, ay, az, gx, gy, gz`, scaled ×100). No off-the-shelf glove advertises this.
>
> **Build path:** 2× **Seeed XIAO nRF52840 Sense** (~€17 each — thumbnail board with onboard 6-axis IMU/LSM6DS3TR-C + BLE 5.0; Arduino Nano 33 BLE Sense is a larger alternative) + 2× small LiPo + the carrier gloves below. **Firmware (to be written)** flashes each board to match the protocol above; the app then connects with zero code changes.

> **The glove is just a carrier — you don't buy "sensor gloves".** The XIAO *is* the sensor; the glove holds it on the hand.
> - **Glove:** snug-fitting work gloves with a flat back-of-hand panel — **Mechanix-style** (Original/FastFit) are ideal (tight, durable, common on sites); thin **nitrile-coated** work gloves work where finishing dexterity matters. *Snug is essential* — a loose glove flops and the IMU measures the glove, not the hand. Buy per worker's hand size.
> - **Mount:** on the **back of the hand** (dorsal, over the metacarpals), **not** the fingers — fingers flex too much and obstruct the trade; the back of the hand tracks motion/orientation cleanly and keeps palm + fingers free. Hold the XIAO + LiPo in a small velcro pouch or a 3D-printed clip.
> - **Orientation matters for the data:** mount both gloves the **same way** (board axes aligned identically left/right) so the two hands are comparable. The firmware will document the expected axis convention.
>
> **Buyable parts list (XIAO build, no 3D printer) — German/EU stores.** Assembly = solder the LiPo to the XIAO BAT pads + flash firmware over USB-C.
> - **XIAO nRF52840 Sense** ×2 — [Reichelt 406868](https://www.reichelt.de/de/de/shop/produkt/xiao_nrf52840_sense_bt5_0_mit_header-406868)
> - **LiPo 3.7 V, 350–500 mAh, JST-PH** ×2 — [BerryBase LP-503035 (500 mAh)](https://www.berrybase.de/en/lp-503035-lithium-polymer-lipo-battery-3.7v-500mah-with-2-pin-jst-connector) (solder leads to the BAT pads)
> - **Heat-shrink 30 mm 3:1 with internal adhesive** — [isolatech 30 mm set](https://isolatech.de/Schrumpfschlauch-3-zu-1-mit-Kleber-20cm-Set-30mm-schwarz-06m3Stk-x-20cm) or [Reichelt category](https://www.reichelt.com/de/en/shop/category/heat-shrink_tubing_internal_adhesives-5750) — the **no-print enclosure** (wrap board+LiPo, leave the USB-C end open)
> - **Velcro tape** (hook + loop) — mount on the glove back
> - **Work gloves** (snug) ×2 pairs — [Mechanix EU FastFit](https://www.mechanix.com/de-de/handschuhe/collections/fastfit/MFF-05-010.html) or [Amazon.de](https://www.amazon.de/Mechanix-Herren-FastFit-Tactical-Handschuhe/dp/B07MFT5W6M) (crew sizes)
> - **Muse 2 / Muse S** ×1 — [Muse EU store](https://eu.choosemuse.com/products/muse-2) · [Amazon.de](https://www.amazon.de/Muse-Das-Brain-Sensing-Stirnband/dp/B08H5BST41) · [mindtecstore (DE)](https://www.mindtecstore.com/neurofeedback/eeg-headsets_en)
> - **USB-C cable** + **soldering iron/solder** — for flashing + the LiPo joint (likely on hand)

**Non-negotiable browser constraints (verified in code):**
- `ImuService` uses **Web Bluetooth** and `VideoRecorderService` uses **getUserMedia/MediaRecorder** — both require a **secure context (HTTPS)** and are **Chrome/Android only**. No iPhone, no Safari. localhost is the only HTTP exception.
- → Every real-capture device must be **Android + Chrome**, and the app must be served over **HTTPS**.

## 5. Deployment & access

The app is a static Angular SPA; the Supabase backend is already **live (Frankfurt, eu-central-1)**.
- Needs a **hosted HTTPS URL** (Firebase Hosting / Netlify / Vercel / Cloudflare Pages — any static host with TLS). This unblocks both the Stage 0 remote demo and Stage 1 on-site use.
- No deploy pipeline exists in the repo today; "push to prod" is a manual/external step (owner-driven).

## 6. Consent, privacy, GDPR

EEG + video of identifiable workers is **sensitive biometric data** under GDPR — treat it seriously from day one.
- Supabase is in **Frankfurt (EU)** — data residency is already on the right side.
- `worker-consent` runs first in the wizard; the consent **text must be reviewed for GDPR** (purpose, retention, withdrawal, who sees it) before any real session — ideally with the firm's sign-off, since these are *their* employees.
- Decide and document: retention period, who can access recordings, deletion-on-request path (the `eeg_ticks` cascade-delete already supports clean teardown per capture).

## 7. On-site logistics & protocol (Stage 1 draft)

- **Tasks to capture:** the core drywall motions — hanging, **taping**, **mudding/finishing**, sanding. Start with one task (e.g. taping) to keep variables low.
- **Workers:** 2–3 experienced finishers > one. Variation across skilled people is signal, not noise.
- **Session shape:** short, repeated captures of the *same* task beat one long messy one.
- **Operator:** one of us on-site for the first sessions to run the wizard and watch signal quality — do not hand an unproven flow to a busy crew unattended.

## 8. Success criteria (what makes the pilot a win)

1. **Workers accept the kit** — they'll wear EEG + gloves and keep working naturally. (If not, nothing else matters — find this out in Stage 0.)
2. **Clean, time-aligned data** — IMU + EEG + video that actually line up, with good signal quality, for ≥ a handful of complete task sessions.
3. **Coverage** — at least one full drywall task captured across 2–3 workers.
4. **A "so what"** — the data visibly distinguishes expert vs. less-expert execution, or flags focus dips. Proof it carries usable signal.

## 9. Risks & open questions

- **Wearability** — gloves + headset vs. real physical labour, dust, sweat, movement. Biggest unknown; Stage 0 partly answers it.
- **Signal quality in the field** — EEG is motion-sensitive; a moving worker is a hostile environment for clean electrodes. May constrain which tasks are capturable.
- **No hosting yet** — must be solved before anyone off-site touches it.
- **Hardware availability** — gloves/headset procurement + lead time (the long pole; currently the blocker).
- **Consent/legal** — needs real review before recording employees.
- **Open:** how many sessions = a useful dataset? What's the labelling plan for the video? Who owns the captured data — us, the firm, or shared?

## 10. Next steps

- [ ] Stage 0 demo: decide host vs. demo-on-our-machine; if hosting, ship an HTTPS static build (backend already live).
- [ ] Walk the friend + a worker through the mock flow; capture their reaction (wearability, consent, "would the crew do this?").
- [ ] Review & finalise the `worker-consent` text for GDPR; get the firm's sign-off.
- [x] Hardware specified: **Muse 2/S** + **2× Seeed XIAO nRF52840 Sense** (custom gloves) + Android/Chrome device. **Owner is procuring.**
- [ ] Write + flash the **glove firmware** to match the `ImuService` BLE protocol — after the boards arrive.
- [ ] Add drywall task types (`drywall_taping`, `mudding`, `sanding`, `hanging`) to `TASK_TYPES` — currently generic trades only.
- [ ] Pick the first task to capture (recommend: taping) and a session protocol.
- [ ] Define data ownership + retention with the firm in writing.

---

### Market context (why now)
- Buyable drywall robots today are appliances, not learners: [Okibo](https://okibo.com/), [Okibo EG7+ launch](https://www.robotics247.com/article/okibo_launches_autonomous_ai_guided_painting_and_drywall_finishing_eg7_robot).
- Learning-from-demonstration humanoids are pilot-stage in manufacturing/logistics, targeting commercial units in 2026: [Apptronik commercialization](https://humanoid.guide/apptronik-adds-executives-for-humanoid-robot-commercialization/), [Humanoid market 2026](https://www.technerdo.com/blog/humanoid-robots-market-2026). The skill-data layer they will eventually need is what this pilot starts building.
