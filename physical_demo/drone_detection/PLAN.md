# Drone Detection Service — Plan (my component)

## Context
Track 2 (software-only) RF drone detection. Our wedge: **open-world / anomaly
detection** — we catch *unknown* emitters that a signature library (Dedrone,
DroneShield) would miss. My piece is the **detection service** that captures RF,
decides "is there an anomalous emitter," and publishes detections. Teammate owns
the multicast relay that propagates those detections across nodes — out of scope
here.

Target: a real low-power 2.4 GHz emitter (RC car controller / FPV link / drone
control link — all the same RF class). One SDR, one antenna, one band.

## What I own vs. what I don't
- **Mine:** SDR capture → spectrogram → anomaly detection → service on **:5001**
  exposing a minimal **detected / not-detected** status → *publish* detection
  events to the UDP multicast group.
- **Not mine:** any dashboard/visualization, and the relay that *consumes*
  multicast and propagates across nodes (teammate). Locating/triangulation
  (needs multiple nodes — roadmap).

## Architecture
```
SDR (HackRF, one antenna, 2.4 GHz, ~20 MHz wide)
      │  IQ samples
      ▼
Chop into ~10 ms windows  →  FFT  →  SPECTROGRAM (freq × time × power)
      ▼
  LEARN phase: collect windows of ambient RF (WiFi/BT) = "normal", fit model
  WATCH phase: each window → anomaly score; score spike → detection
      ▼
Detection service (port 5001)  — NO dashboard, just status
  ├─► GET :5001/status → { "detected": true|false, ... }   (binary state)
  └─► publishes detection JSON → UDP multicast group  (teammate's relay reads)
```

Single sensor is enough: WiFi / Bluetooth / RC-link separate in **frequency and
time pattern**, not in space. The model flags the emitter whose time-frequency
pattern doesn't fit the learned ambient baseline — that's why it works on an
emitter we never trained on (open-world).

## The contract (agree with teammate before building)
- **Service port:** `5001` (TCP) — single endpoint `GET /status` returning the
  binary state:
```json
{ "detected": true, "anomaly_score": 0.87, "since": "2026-05-30T12:00:00.123Z" }
```
- **Multicast group:** e.g. `239.1.1.1:5005` (UDP — agree on exact value).
- **Detection event JSON** (what I publish on a detection, what his relay expects):
```json
{
  "node_id": "node-1",
  "timestamp": "2026-05-30T12:00:00.123Z",
  "center_freq_hz": 2437000000,
  "band": "2.4GHz",
  "anomaly_score": 0.87,
  "threshold": 0.50,
  "classification": "unknown",
  "label": null,
  "confidence": 0.91,
  "snr_db": 14.2,
  "occupied_bw_hz": 2000000
}
```

## Iterative implementation
Principle: **every iteration is a complete, running system** — `:5001/status`
responds and detections publish to multicast the whole way through. Each
iteration only swaps in a smarter detector behind the same interface, so we
always have something demoable and the interface never changes under our feet.

- **Iteration 0 — real plumbing, fake detector.**
  Service on `:5001` (`GET /status`) + the UDP multicast publisher. Detection is
  *stubbed* — a keypress / timer flips `detected` true↔false. No SDR yet.
  → *Proves the contract and the teammate hand-off on day one; he can build his
  relay against a live feed immediately.*

- **Iteration 1 — real RF, dumb detection.**
  Swap the stub for real input: HackRF capture (SoapySDR) → ~10 ms windows →
  FFT → spectrogram → **energy threshold** above the noise floor flips `/status`.
  Quiet band, power on the emitter → `detected: true`.
  → *Same interface, now driven by real radio. Just a power meter — that's fine
  for now.*

- **Iteration 2 — anomaly detector (the product).**
  Add a **learn phase** (collect ambient WiFi/BT windows = "normal", fit
  IsolationForest / OC-SVM), then a **watch phase** (score each window). Replace
  the fixed threshold with the anomaly score. Now it flags the novel emitter
  *amid* noise — open-world detection, the actual product.

- **Iteration 3 — library contrast (the pitch metric, if time).**
  Run a supervised "signature library" classifier alongside the anomaly
  detector. Introduce a *different* emitter as the unknown: library says "not
  recognized," we catch it. **The one metric:** miss-rate on the novel emitter,
  library vs. us.

Each iteration ships behind the same `/status` + multicast contract, so we can
stop at any point and still have a working demo.

## Stack
Python · HackRF via SoapySDR/libhackrf · numpy/scipy (STFT) · scikit-learn
(IsolationForest/OC-SVM) · FastAPI on :5001 (one `/status` endpoint) · `socket`
for UDP multicast publish.

## Demo run-of-show
1. Start service → `:5001/status` reads `detected: false`.
2. Learn phase: ambient room RF (WiFi/BT) — score stays low, still `false`.
3. Power on the emitter (RC controller / VTX) → anomaly score spikes →
   `:5001/status` flips to `detected: true` AND a detection event publishes to
   teammate's relay.
4. (if built) Show library baseline missing the *unknown* emitter while we catch it.

## Risks & mitigations
- **Crowded 2.4 GHz** — RC hopping can resemble Bluetooth; this is the real
  discrimination challenge (and why the claim is defensible, not trivial).
  Mitigate: pick an emitter distinct from ambient, or a cleaner sub-band.
- **Live capture fails on stage** — driver/USB/antenna risk. Mitigate:
  **record our own live captures during setup; replay them as fallback** (still
  real data). Highest-priority safety net.
- **One band at a time** — HackRF is single-channel; center on the emitter's
  band (2.4 GHz for an RC controller).
- **Need normal *before* the target** — bake a learn phase into the run-of-show.

## Verification
- Plumbing: quiet band, power on emitter → `:5001/status` flips to
  `detected: true` + a packet on the multicast group (confirm with a
  `socat`/netcat multicast listener, then with teammate's relay).
- Anomaly: run learn phase in a noisy room → `/status` stays `false` on ambient
  → flips `true` only when the target emitter turns on (low false-alarm on
  WiFi/BT).
- Contrast: report miss-rate of library baseline vs. anomaly detector on the
  held-out emitter.
