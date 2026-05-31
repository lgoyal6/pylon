# Drone Detection Service — Iteration 0 (plumbing)

Real plumbing, stubbed detector. Stands up the contract so the teammate's relay
has a live feed on day one. **No SDR.** See `PLAN.md` for the full roadmap.

## Contract
- **Service:** `GET http://<host>:5001/status` →
  `{ "detected": bool, "anomaly_score": float, "since": "<ISO8601>"|null }`
- **Multicast:** detection-event JSON published to **`239.1.1.1:5000`** (UDP) —
  the port the teammate's relay listens on. Event shape:
  ```json
  { "node_id": "node-1", "timestamp": "2026-05-30T12:00:00.123Z",
    "center_freq_hz": 2437000000, "band": "2.4GHz", "anomaly_score": 0.87,
    "threshold": 0.50, "classification": "unknown", "label": null,
    "confidence": 0.91, "snr_db": 14.2, "occupied_bw_hz": 2000000 }
  ```
  (RF fields are static stubs in Iteration 0; the schema is what's frozen.)

## Setup
```bash
pip install -r requirements.txt
```

## Run
```bash
python main.py                 # serve on :5001, publish to 239.1.1.1:5000
python main.py --auto-toggle 5 # hands-free: flip detection every 5s
```
Overridable via env vars (`DRONE_SERVICE_PORT`, `DRONE_MCAST_GROUP`,
`DRONE_MCAST_PORT`, `DRONE_NODE_ID`, `DRONE_PUBLISH_INTERVAL_S`) or flags
(`--port`, `--publish-interval`, `--auto-toggle`).

## Drive it (demo)
```bash
curl -s localhost:5001/status                                  # -> detected:false
curl -s -X POST localhost:5001/sim -H 'content-type: application/json' \
     -d '{"detected":true}'                                    # flip on (+ multicast)
curl -s localhost:5001/status                                  # -> detected:true, since set
curl -s -X POST localhost:5001/sim -H 'content-type: application/json' \
     -d '{"detected":false}'                                   # flip off
```

## Verify the multicast stream (no socat needed)
While detection is on you should see ~1 event/sec. Listener:
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

## Tests
```bash
python -m pytest        # 13 tests: state, publisher (real multicast), HTTP, toggle
```
