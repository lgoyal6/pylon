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

# --- Stubbed RF fields (Iteration 0) ----------------------------------------
# Real values arrive in Iteration 1 (SDR capture). For now these are static so
# the detection-event schema is stable for the teammate's relay.
CENTER_FREQ_HZ = 2_437_000_000  # 2.4 GHz, WiFi ch. 6 / typical RC-link region
BAND = "2.4GHz"
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
