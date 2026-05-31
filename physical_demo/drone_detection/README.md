# Drone Detection Service — Iteration 2 (open-world anomaly detection)

RTL-SDR capture → per-window spectrum → an **anomaly detector that learns the
ambient RF and flags novel emitters** a signature library would miss — behind the
same `:5001/status` + multicast contract as Iterations 0/1. Two detectors are
selectable: `--detector anomaly` (the product) and `--detector energy`
(Iteration 1's occupied-bandwidth threshold, kept for contrast). The stubbed
`/sim` path remains as a manual override / on-stage fallback. See `PLAN.md`.

**Hardware:** two interchangeable SDR backends behind one capture seam
(`--sdr`):
- **NooElec NESDR SMArt v5** (RTL-SDR, RTL2832U + R820T2, 100 kHz–1.75 GHz) —
  `--sdr rtl` (default). 2.4 GHz is **out of range**; demo target is a **key fob**
  (315 MHz US / 433 MHz EU).
- **ADALM-Pluto** (AD9363, via pyadi-iio/libiio) — `--sdr pluto`. Reaches **2.4
  GHz** (WiFi/BT band); talks to the device over libiio's **USB backend** (no
  network gadget needed). Needs a **2.4 GHz SMA antenna on the RX port**.

## How the anomaly detector works
- **Signal/features:** each ~10 ms IQ window → Welch PSD (256 bins) → dB →
  subtract the per-window median (spectral *shape*, robust to gain/level drift).
- **Learn (~30 s, target OFF):** fit a per-frequency-bin baseline (mean/std).
- **Watch:** flag a window when any bin's power rises far above its learned
  baseline (max z-score ≥ `Z_THRESHOLD`). Stationary spurs/ambient are baked into
  the baseline → not flagged; a novel emitter (narrow or wide) spikes a bin →
  flagged. (IsolationForest was evaluated and rejected — it can't isolate a single
  anomalous bin among 256 dims.)

## Contract
- **Service:** `GET http://<host>:5001/status` →
  `{ "detected": bool, "anomaly_score": float, "since": "<ISO8601>"|null }`
- **Multicast:** detection-event JSON published to **`239.1.1.1:5000`** (UDP) —
  the port the teammate's relay listens on. `center_freq_hz`, `snr_db` and
  `occupied_bw_hz` are now **real** (from the SDR); the schema is frozen:
  ```json
  { "node_id": "node-1", "timestamp": "2026-05-30T12:00:00.123Z",
    "center_freq_hz": 100100000, "band": "FM", "anomaly_score": 0.61,
    "threshold": 0.50, "classification": "unknown", "label": null,
    "confidence": 0.91, "snr_db": 18.3, "occupied_bw_hz": 180000 }
  ```

## Setup
```bash
brew install librtlsdr        # RTL backend: provides the rtl_sdr / rtl_test CLI
pip install -r requirements.txt
```
RTL capture shells out to the `rtl_sdr` CLI (not pyrtlsdr — see `requirements.txt`).

For the **Pluto backend** (`--sdr pluto`), also install the native **libiio**
(not in Homebrew — use Analog Devices' macOS `.pkg`):
```bash
# arm64 macOS, matches Pluto fw v0.26:
curl -sL -o /tmp/libiio.pkg \
  https://github.com/analogdevicesinc/libiio/releases/download/v0.26/libiio-0.26.ga0eca0d-macOS-13-arm64.pkg
sudo installer -pkg /tmp/libiio.pkg -target /
iio_info -s          # confirm the Pluto is seen over USB
```

## Run
```bash
# Find the key fob's frequency: press it repeatedly during this sweep, note the spike
rtl_power -f 300M:450M:20k -g 49.6 -1 scan.csv      # 315 (US) vs 433.92 MHz (EU)

# Iteration 2 — anomaly detector (the product). Keep the fob OFF during the learn phase:
python main.py --source live --detector anomaly --freq 433920000 --gain 49.6
#   ...~30 s ambient learning -> "watching" -> press the fob -> /status flips true
python main.py --source live --detector anomaly --freq 433920000 --save-model fob.npz   # learn once, reuse
python main.py --source live --detector anomaly --freq 433920000 --load-model fob.npz   # skip learning

# Iteration 1 — energy detector (contrast: misses the narrowband fob):
python main.py --source live --detector energy --freq 433920000 --gain 49.6

# 2.4 GHz via ADALM-Pluto — anomaly detector at WiFi ch 6 (2.437 GHz default):
python main.py --source live --sdr pluto --detector anomaly
#   ...learns the busy 2.4 GHz ambient -> "watching" -> introduce a novel emitter
python main.py --source live --sdr pluto --freq 2412000000   # tune elsewhere in-band

# Fallback (manual control, no SDR):
python main.py --source sim
```
Flags: `--source {sim,live}`, `--detector {anomaly,energy}`, `--freq HZ`,
`--gain {auto,<dB>}`, `--learn-seconds`, `--load-model/--save-model`, `--sample-rate`,
`--port`, `--publish-interval`. Most also overridable via `DRONE_*` env vars (`config.py`).

## Verify
```bash
# 1. Device is seen:
rtl_test -t                         # lists the NESDR SMArt v5 + R820T2 tuner

# 2. Live FM proof — tune onto a strong station, watch /status flip:
python main.py --source live --freq <local-FM-Hz> &
curl -s localhost:5001/status       # -> detected:true with real metrics on a station
                                    # -> detected:false on an empty frequency
```

### Watch the multicast stream (no socat needed)
```bash
python - <<'PY'
import socket, struct
g, p = "239.1.1.1", 5000
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("", p))
s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
             struct.pack("4sl", socket.inet_aton(g), socket.INADDR_ANY))
print(f"listening on {g}:{p}")
while True:
    print(s.recv(65535).decode())
PY
```

### Manual /sim (fallback path)
```bash
curl -s -X POST localhost:5001/sim -H 'content-type: application/json' -d '{"detected":true}'
curl -s -X POST localhost:5001/sim -H 'content-type: application/json' -d '{"detected":false}'
```

## Tests
```bash
python -m pytest    # 35 tests + 1 hardware smoke test (skips without a device)
```
Covers: state (+metrics, thread-safe), publisher (real multicast, metric/stub
fallback), HTTP status/sim, auto-toggle, both detectors on synthetic IQ (energy
occupancy; anomaly learn/watch incl. spur-as-normal + novel-burst + save/load),
and the capture→detect loop (debounce on/off hangover, anomaly learn→flip).
