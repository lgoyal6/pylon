"""BtScannerSource: detects Bluetooth Classic devices and pushes to the bus.

The scan function is injected, so these test the source logic (match + event +
push) without blueutil or hardware.
"""
from bt_scanner import BtScannerSource
from bus import DetectionBus


def _src(bus, devices, target=None):
    return BtScannerSource(bus, target=target, scan=lambda: devices)


def test_pushes_bluetooth_event_when_target_found():
    bus = DetectionBus()
    _src(bus, [{"address": "AA-BB", "name": "HC-05"}], target="HC-05").step()
    ev = bus.get(timeout=0.1)
    assert ev is not None
    assert ev["source"] == "bt-scanner"
    assert ev["classification"] == "bluetooth"
    assert ev["label"] == "HC-05"
    assert "anomaly_score" in ev  # required by build_event


def test_no_event_when_target_absent():
    bus = DetectionBus()
    _src(bus, [{"address": "CC-DD", "name": "Speaker"}], target="HC-05").step()
    assert bus.get(timeout=0.02) is None


def test_matches_by_address_substring_case_insensitive():
    bus = DetectionBus()
    _src(bus, [{"address": "AA-BB-CC", "name": ""}], target="aa-bb").step()
    ev = bus.get(timeout=0.1)
    assert ev is not None
    assert ev["label"] == "AA-BB-CC"  # label falls back to address when name is empty


def test_no_target_matches_any_bluetooth_device():
    bus = DetectionBus()
    _src(bus, [{"address": "X", "name": "AnyBT"}], target=None).step()
    assert bus.get(timeout=0.1) is not None


def test_empty_scan_pushes_nothing():
    bus = DetectionBus()
    _src(bus, [], target=None).step()
    assert bus.get(timeout=0.02) is None
