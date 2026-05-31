"""Service configuration: constants with environment-variable overrides.

These are the values agreed in the contract (see PLAN.md). Override any of them
at runtime via environment variables of the same name, e.g.::

    DRONE_MCAST_GROUP=239.2.2.2 python main.py
"""
import os

# --- Network contract -------------------------------------------------------
SERVICE_PORT = int(os.environ.get("DRONE_SERVICE_PORT", "5001"))
MCAST_GROUP = os.environ.get("DRONE_MCAST_GROUP", "239.1.1.1")
MCAST_PORT = int(os.environ.get("DRONE_MCAST_PORT", "5000"))  # teammate's relay listens here
MCAST_TTL = int(os.environ.get("DRONE_MCAST_TTL", "1"))

# --- Node identity ----------------------------------------------------------
NODE_ID = os.environ.get("DRONE_NODE_ID", "node-1")


def _parse_relay(spec: str):
    """'host:port' -> (host, int(port)); empty -> None. The mesh sensor-relay
    ingress (relay_system/sensor_relay.py) we forward detection events to."""
    if not spec:
        return None
    host, _, port = spec.rpartition(":")
    return (host, int(port)) if host and port else None


# Optional: also forward each detection event (UDP unicast) to a mesh sensor
# relay's ingress, which rebroadcasts it as `sensor:<json>` across the mesh.
RELAY_ADDR = _parse_relay(os.environ.get("DRONE_RELAY_ADDR", ""))

# --- Stubbed RF fields (Iteration 0) ----------------------------------------
# Real values arrive in Iteration 1 (SDR capture). For now these are static so
# the detection-event schema is stable for the teammate's relay.
CENTER_FREQ_HZ = 2_437_000_000  # stub fallback only; live detector reports the tuned freq
BAND = os.environ.get("DRONE_BAND", "FM")  # coarse label; matches the chain-proof target
THRESHOLD = 0.50
CLASSIFICATION = "unknown"
LABEL = None
CONFIDENCE = 0.91
SNR_DB = 14.2
OCCUPIED_BW_HZ = 2_000_000

# Default anomaly score reported when /sim flips detection on without one.
DEFAULT_ANOMALY_SCORE = 0.87

# How often (seconds) to re-publish a detection event while detected.
PUBLISH_INTERVAL_S = float(os.environ.get("DRONE_PUBLISH_INTERVAL_S", "1.0"))

# --- SDR capture (Iteration 1) ----------------------------------------------
# NooElec NESDR SMArt v5 (RTL2832U + R820T2, 100 kHz-1.75 GHz). 2.4 MHz is the
# stable sample rate; 2.56/3.2 MHz drop samples. FM band is the chain-proof target.
SAMPLE_RATE_HZ = int(os.environ.get("DRONE_SAMPLE_RATE_HZ", "2400000"))
DEFAULT_CENTER_FREQ_HZ = int(os.environ.get("DRONE_CENTER_FREQ_HZ", "100100000"))  # ~FM
GAIN = os.environ.get("DRONE_GAIN", "auto")  # "auto" or a dB value like "30"
WINDOW_SAMPLES = int(os.environ.get("DRONE_WINDOW_SAMPLES", "24576"))  # ~10 ms @ 2.4 MHz

# --- ADALM-Pluto capture (2.4 GHz, Iteration 3) -----------------------------
# The Pluto reaches 2.4 GHz where the RTL can't. Selected with --sdr pluto; talks
# to the device over libiio's USB backend (no network gadget / RNDIS needed).
PLUTO_URI = os.environ.get("DRONE_PLUTO_URI", "usb:")  # or "ip:192.168.2.1"
PLUTO_DEFAULT_CENTER_FREQ_HZ = int(os.environ.get("DRONE_PLUTO_CENTER_FREQ_HZ", "2437000000"))  # WiFi ch 6

# --- Energy-threshold detector (Iteration 1) --------------------------------
# Detection is by occupied bandwidth, not peak SNR: on RTL-SDR a single-bin spur
# matches a strong station in peak-over-floor, but a real emitter occupies real
# bandwidth. Tuned for FM (~200 kHz wide) vs quiet/spurs (~25 kHz) — retune
# MIN_OCCUPIED_BW_HZ for a narrowband emitter band later.
FFT_NPERSEG = int(os.environ.get("DRONE_FFT_NPERSEG", "4096"))
OCCUPANCY_MARGIN_DB = float(os.environ.get("DRONE_OCCUPANCY_MARGIN_DB", "6.0"))  # bins this far above floor count as occupied
MIN_OCCUPIED_BW_HZ = float(os.environ.get("DRONE_MIN_OCCUPIED_BW_HZ", "80000"))  # >= this occupied bandwidth -> detected
OCCUPANCY_SCORE_SCALE_HZ = float(os.environ.get("DRONE_SCORE_SCALE_HZ", "300000"))  # occupied bw mapped to anomaly_score=1.0
DEBOUNCE_WINDOWS = int(os.environ.get("DRONE_DEBOUNCE_WINDOWS", "3"))  # consecutive windows to flip state
# Burst-friendly debounce (Iteration 2 fob): flip on fast, hold through a press.
DEBOUNCE_ON = int(os.environ.get("DRONE_DEBOUNCE_ON", "2"))
DEBOUNCE_OFF = int(os.environ.get("DRONE_DEBOUNCE_OFF", "10"))  # ~1 s hangover at ~10 ms/window

# --- Anomaly detector (Iteration 2, the product) ----------------------------
# Open-world novelty detection: learn a per-frequency-bin baseline (mean/std of
# the ambient PSD shape), then flag a window when any bin's power rises far above
# its learned baseline (max z-score). Stationary spurs/ambient are baked into the
# baseline -> not flagged; a novel emitter (narrow or wide) spikes some bin ->
# flagged. (IsolationForest was evaluated and rejected: it cannot isolate a
# single anomalous bin among ~256 dims.)
N_FEATURE_BINS = int(os.environ.get("DRONE_N_FEATURE_BINS", "256"))  # PSD bins = feature dimension
LEARN_SECONDS = float(os.environ.get("DRONE_LEARN_SECONDS", "30"))  # ambient-learning duration
Z_THRESHOLD = float(os.environ.get("DRONE_Z_THRESHOLD", "8.0"))  # max per-bin z above baseline -> detect
Z_SCORE_SCALE = float(os.environ.get("DRONE_Z_SCORE_SCALE", "20.0"))  # max-z mapped to anomaly_score=1.0
SIGMA_FLOOR_DB = float(os.environ.get("DRONE_SIGMA_FLOOR_DB", "1.0"))  # floor on per-bin std (dB) to avoid over-sensitivity

# --- Emitter characterization (jamming-vs-comms) ----------------------------
# Coarse behavioral label for a flagged anomaly (detector.classify_emitter):
# wide occupancy -> "jamming-like"; narrow/channelized -> "comms-like". Spectral
# flatness is reported alongside but does not gate (see classify_emitter).
# Heuristic threshold — tune against the live ambient.
JAMMING_BW_FRAC = float(os.environ.get("DRONE_JAMMING_BW_FRAC", "0.3"))  # occupied/captured bandwidth fraction
