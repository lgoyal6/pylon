# Demo Runbook - drone @ 8am, deadline 11am

Target: **Sharper Image 2.4 GHz RC Glow-Up Stunt Drone** - controller-based, nRF24/
Beken **GFSK frequency-hopper** (not WiFi/BT). **Band 2404–2476 MHz, center 2440**,
~1 Mbps. Detection is by *structure* (narrowband GFSK hops), not frequency.

The plan: **anomaly detector is the no-training safety net** (learn off → fly on →
flag). **Classifier is the upgrade** (retrain on real drone data - seconds to train,
minutes to collect). Don't debug the pipeline at 8am; rehearse tonight.

---

## TONIGHT (de-risk - do these before sleep)

1. **Hardware check:** Pluto on USB, antenna on RX, libiio OK:
   ```
   python -c "import adi; adi.Pluto('usb:'); print('pluto ok')"
   ```
2. **Dress rehearsal** with the hopper as a stand-in drone (proves the live chain):
   ```
   # T1: anomaly detector
   python main.py --source live --sdr pluto --freq 2440000000 --sample-rate 10000000 \
       --detector anomaly --baseline quantile --learn-seconds 20
   # T2 (after "watching"): hopper stand-in
   python beacon.py --freq 2440000000 --sample-rate 10000000 --waveform hopper --bitrate 1 --tx-dbm -50
   #   -> T1 should flag; stop beacon -> clears
   ```
3. **Pre-collect the classes that won't change** (so 8am only adds `drone`):
   ```
   python collect.py --label background --sdr pluto --freq 2440000000 --sample-rate 10000000 --stacks 200
   python collect.py --label wifi       --sdr pluto --freq 2440000000 --sample-rate 10000000 --stacks 200
   # (run while browsing/streaming for the wifi class)
   ```
4. **Mesh up:** `sensor_relay.py --bootstrap <peer> --sensor-port 5350` reachable; confirm events arrive.

---

## TOMORROW 8:00–11:00

- **8:00 - see it.** Power the drone + controller; confirm capture:
  ```
  python receiver.py --sdr pluto --freq 2440000000 --sample-rate 10000000
  ```
  Fly it CLOSE, antenna pointed at the **controller**. If nothing, try `--freq 2420000000` / `2460000000`.
- **8:10 - anomaly detector (BANK A WORKING DEMO):**
  ```
  python main.py --source live --sdr pluto --freq 2440000000 --sample-rate 10000000 \
      --detector anomaly --baseline quantile --learn-seconds 20 --relay 127.0.0.1:5350
  ```
  Learn with controller OFF → fly ON → `[detect] DETECTED` + mesh. *This is your guaranteed demo.*
- **8:30 - collect real drone data:**
  ```
  python collect.py --label drone --sdr pluto --freq 2440000000 --sample-rate 10000000 --stacks 200
  ```
  (fly it, close). Reuse last night's `background`/`wifi`.
- **8:45 - retrain (seconds):**
  ```
  python train.py --dataset dataset.npz --out model.joblib
  ```
  Read held-out accuracy + confusion. Drone separates from ambient? Good.
- **9:00 - classifier live:**
  ```
  python main.py --source live --sdr pluto --freq 2440000000 --sample-rate 10000000 \
      --detector classifier --classify-model model.joblib --relay 127.0.0.1:5350
  ```
  Validate it flags `drone` when flying, quiet otherwise.
- **9:30 - iterate** (collect more / retune margin) if needed.
- **10:00 - FREEZE. Dry-run the actual demo.** Leave a 1-hour buffer.

---

## Fallback ladder (if a step fails)
1. Classifier flaky → **anomaly detector** (no training) + before/after contrast.
2. Drone hard to catch → fly closer, point antenna at controller, confirm `--freq`.
3. Mesh down → detection still prints locally (`[detect] …`); demo from the console.
4. 2.4 GHz too noisy → raise `DRONE_QUANTILE_MARGIN_DB` (8→12) and rely on proximity.

## Knobs cheat-sheet
- detector: `--detector {anomaly,classifier,energy}`, `--baseline {zscore,quantile}`
- tuning: `DRONE_QUANTILE_MARGIN_DB=N`, `DRONE_DEBOUNCE_ON=N`
- beacon stand-in: `--waveform hopper --bitrate <Mbps> --tx-dbm <rx@1m> --distance <m> --duty <0-1>`
- run tests w/ node on 5000: `DRONE_MCAST_PORT=5055 python -m pytest`
