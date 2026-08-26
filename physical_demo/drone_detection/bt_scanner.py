"""Case 2 - Bluetooth-scanner detection source.

The ELEGOO car's HC-05 is a *cooperative, discoverable* Bluetooth Classic device,
so the reliable way to detect it is to ask, not overhear: run a BT inquiry and
push a detection event when a target device appears. This is the right tool for a
known-protocol device (vs the SDR, which only sees "Bluetooth-like energy").

Detection is via the macOS `blueutil --inquiry` CLI (Classic discovery; CoreBlue-
tooth/`bleak` are BLE-only and won't see an HC-05). The scan function is injected
so the source logic is testable without blueutil/hardware. Pushes standardized
events to the DetectionBus like any other source - the mesh sink does the rest.
"""
import json
import subprocess
import threading

import config


class BtScannerSource:
    def __init__(
        self,
        bus,
        target: str = None,
        scan=None,
        inquiry_seconds: int = 8,
        source_name: str = "bt-scanner",
        blueutil_bin: str = "blueutil",
    ) -> None:
        self.bus = bus
        # Match by name or address substring (case-insensitive). None/"" = any BT device.
        self.target = (target or "").lower()
        self._scan = scan or self._blueutil_inquiry
        self.inquiry_seconds = inquiry_seconds
        self.source_name = source_name
        self.blueutil_bin = blueutil_bin

    def _blueutil_inquiry(self):
        """Run a Classic BT inquiry via blueutil and return [{address, name}, ...]."""
        out = subprocess.run(
            [self.blueutil_bin, "--inquiry", str(self.inquiry_seconds), "--format", "json"],
            capture_output=True, text=True, timeout=self.inquiry_seconds + 10,
        ).stdout.strip()
        if not out:
            return []
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            return []

    def _matches(self, device: dict) -> bool:
        if not self.target:
            return True
        hay = f"{device.get('name', '')} {device.get('address', '')}".lower()
        return self.target in hay

    def _event(self, device: dict) -> dict:
        return {
            "source": self.source_name,
            "anomaly_score": 1.0,  # a protocol-level device match is a confident detection
            "classification": "bluetooth",
            "label": device.get("name") or device.get("address"),
            "center_freq_hz": 2_440_000_000,  # nominal BT band center (BT hops 2402-2480)
            "snr_db": 0.0,        # not applicable to a scan detection (honest, not a stub)
            "occupied_bw_hz": 0,
        }

    def step(self):
        """Run one inquiry; push an event for each matching device. Returns matches."""
        matches = [d for d in self._scan() if self._matches(d)]
        for d in matches:
            self.bus.publish(self._event(d))
        return matches

    def run(self, stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            try:
                self.step()
            except Exception as exc:  # a flaky inquiry shouldn't kill the source
                print(f"[bt-scanner] inquiry error: {exc}")
            stop_event.wait(0.1)
