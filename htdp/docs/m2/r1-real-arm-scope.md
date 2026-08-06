# R1 — Real-Arm Imitation Mile (SO-ARM101) — scoped milestone

**Goal:** a real robot arm picks and places a real object from camera + proprio, driven by an
ACT policy trained on self-collected teleop demos — with the same eval discipline as the sim
loop (n≥20 real trials, Wilson 95% CI). Upgrades the portfolio from "sim person" to "robotics
engineer": the headline video becomes pixels → real friction grasp on a desk.

**Path decision: real-data imitation, NOT sim-to-real transfer.** M1 proved the 5-DOF SO-ARM
geometry cannot reproduce the Franka policy's top-down grasp (15–27 cm error across mount
heights), so the sim visuomotor policy does not transfer 1:1. The standard LeRobot workflow —
teleop the follower with a leader arm, record real demos, train ACT on them — sidesteps the
mismatch entirely (the human demonstrates whatever grasp the arm can actually do) and is the
exact skill profile of the LeRobot ecosystem. Sim-to-real with an SO-ARM sim model + C1 DR is a
possible R2, not this mile.

## Hardware (ends the 0€ rule — order during C1, lead time overlaps sim work)

| option | contents | est. cost |
|--------|----------|-----------|
| EU shop (Eckstein, DE, ships 1–3 days) | leader €199–229 + follower €199–259 (7.4V std / 12V pro), incl. printed parts, control boards, PSUs, clamps | **~€400–490** |
| Seeed Studio (DE warehouse) | dual-arm servo kit $240 + printed-parts set $35 — needs no printer but check both-arms inclusion at checkout | ~€260–300 + shipping |
| AutoDiscovery EU / WowRobo / Hiwonder | parts-only or assembled configurable | login/quote |

Plus: 1–2 USB webcams (~€25 each; one wrist-ish, one third-person), USB hub, a cube-sized
object. **Realistic total ~€350–550.** Pick the **7.4V standard** dual-arm kit (12V pro torque
unneeded for cube pick-place). Assembled > DIY if the delta is < €80 — assembly+calibration is
the classic time sink, and the mile's value is the learning loop, not the soldering.

## Software plan

- **Drivers/teleop/recording: upstream `lerobot`** (SO-ARM101 natively supported: calibration,
  leader-follower teleop, dataset recording, ACT training). Do NOT reimplement drivers in htdp —
  de-risk with the maintained path.
- **htdp's role:** the dataset lands in LeRobot format — the same layout our sim demos use.
  Evaluate with our `wilson_ci` machinery; write the result doc in the SIM_LOOP style.
- **Stretch (optional, only if R1c lands early):** train our compact htdp ACT on the same real
  dataset and compare to upstream ACT — "my from-scratch implementation matches upstream on real
  data" is a strong portfolio line.

## Build order

1. **R1a — bring-up:** assemble (if DIY), calibrate both arms, teleop smoke test, webcam
   mounting + `lerobot` config committed to a new `htdp-real` notes dir. Exit: smooth teleop
   video clip.
2. **R1b — dataset:** record ~50 teleop pick-place episodes (fixed target zone, varied cube
   start poses — mirror the sim task), visually audit a sample, push dataset to HF hub (private
   or public; public = free portfolio artifact).
3. **R1c — train + eval:** upstream ACT on the 50 episodes; evaluate with **n≥20 scripted-start
   real trials** (marked start grid on the desk, manual resets), report success + Wilson CI +
   failure taxonomy. Gate: policy beats zero; honest number reported whatever it is (real-world
   first-try ACT numbers of 50–80% are normal — do not chase sim's 87.5%).
4. **R1d — portfolio packaging:** headline video (teleop demo → autonomous rollout side by
   side), result doc linked from SIM_LOOP.md ("Where it could go" → done), README headline
   gains the real-arm line.

## Risks / watch-items

- **Assembly + calibration eats sessions.** Budget one full session for R1a alone; buy
  assembled if reasonable.
- **macOS serial/USB:** two motor-control boards over USB-C serial — verify `lerobot` macOS
  support early (R1a day 1); fallback = a spare Linux box/RPi as the robot host.
- **Real eval is manual labor:** 20+ trials with resets ≈ an hour per eval run. Define success
  criterion (cube fully inside marked zone) BEFORE the first trial; no post-hoc rubric bending.
- **Demo quality dominates policy quality** (sim lesson repeats): jerky teleop = bad ACT. Praxis
  episodes before recording the real 50.
- **Servo QC / spares:** Feetech STS3215 singles ~€25 at Eckstein — order 1 spare with the kit.
- Camera placement fixed across record and eval — the sim loop's "same camera at train and
  test" rule applies verbatim.

## Sequencing

Order kit now-ish (during C1) → C1 + OOD test while shipping → R1a–d → portfolio packaging.
R1 does not block C1/OOD; it replaces "real SO-ARM100 optional" with a committed mile.
