"""Check manifest lineage and bounded raw IQ loading in recordings.py.
Build small local recordings shared with the held-out study tests.
Reject leakage, corrupt bytes and conversion overflow; accept supported formats.
"""
import copy
import hashlib
import json

import numpy as np
import pytest

from recordings import load_iq, load_manifest


def write_manifest(tmp_path):
    rows = []
    rng = np.random.default_rng(42)
    for role, day in zip(("train", "calibration", "test"), ("01", "02", "03")):
        for target in (False, True):
            name = f"{role}-{target}"
            iq = (rng.normal(size=8192) + 1j * rng.normal(size=8192)).astype(np.complex64)
            if target:
                iq += np.exp(2j * np.pi * np.arange(len(iq)) * .17) * 5
            path = tmp_path / f"{name}.npy"
            np.save(path, iq)
            rows.append(dict(recording_id=name, session_id=role, site_id=role,
                             device_id=role, day=f"2026-10-{day}", emitter_id="known" if target else "background",
                             label="target" if target else "ambient", license="LOCAL-SYNTHETIC",
                             source="seed42 test fixture", evidence_kind="synthetic", path=path.name,
                             sha256=hashlib.sha256(path.read_bytes()).hexdigest(), role=role, target=target,
                             n_samples=len(iq), sample_rate_hz=2_048_000, center_freq_hz=915_000_000,
                             gain_db=0., clock_ppm=0., dropped_samples=0))
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(dict(schema_version=1, holdout_axes=["site_id", "device_id", "day"], captures=rows)))
    return path, rows


def test_valid_manifest_and_iq(tmp_path):
    path, rows = write_manifest(tmp_path)
    assert len(load_manifest(path)["captures"]) == 6
    assert load_iq(rows[0], tmp_path).shape == (8192,)


@pytest.mark.parametrize("field,value,error", [
    ("session_id", "train", "session_id leakage"),
    ("sha256", "duplicate", "sha256 leakage"),
    ("device_id", "train", "device_id leakage"),
    ("dropped_samples", 1, "capture loss"),
    ("gain_db", "auto", "gain_db"),
    ("clock_ppm", float("nan"), "clock_ppm"),
    ("evidence_kind", "unknown", "evidence_kind"),
    ("day", "invalid", "Invalid isoformat"),
    ("sample_rate_hz", 1_000_000, "mixed RF geometry"),
])
def test_invalid_provenance_and_leakage_rejected(tmp_path, field, value, error):
    path, rows = write_manifest(tmp_path)
    if field == "sha256":
        value = rows[0][field]
    rows[-1][field] = value
    manifest = json.loads(path.read_text())
    manifest["captures"] = rows
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match=error):
        load_manifest(path)


def test_test_emitter_is_not_novel_if_seen_during_fit(tmp_path):
    path, rows = write_manifest(tmp_path)
    manifest = json.loads(path.read_text())
    manifest["captures"][-1]["novel"] = True
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="novel emitter identity leaked"):
        load_manifest(path)


@pytest.mark.parametrize("fault", ["checksum", "count", "escape", "bound", "nonfinite", "real"])
def test_corrupt_or_unbounded_iq_is_rejected(tmp_path, fault):
    _, rows = write_manifest(tmp_path)
    row = copy.deepcopy(rows[0])
    if fault == "checksum": row["sha256"] = "0" * 64
    if fault == "count": row["n_samples"] += 1
    if fault == "escape": row["path"] = "../elsewhere.npy"
    if fault in ("nonfinite", "real"):
        np.save(tmp_path / row["path"], np.full(8192, np.nan + 1j) if fault == "nonfinite" else np.ones(8192))
        row["sha256"] = hashlib.sha256((tmp_path / row["path"]).read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        load_iq(row, tmp_path, max_bytes=1 if fault == "bound" else 64 * 1024 * 1024)


@pytest.mark.parametrize("fmt,data,expected", [
    ("cf32_le", np.array([1+2j, 3+4j], dtype="<c8").tobytes(), [1+2j, 3+4j]),
    ("ci16_le", np.array([0, 32767, -32768, 0], dtype="<i2").tobytes(), [32767j/32768, -1]),
    ("cu8", bytes([0, 255, 255, 0]), [-1+1j, 1-1j]),
])
def test_native_iq_encodings(tmp_path, fmt, data, expected):
    path = tmp_path / "iq.bin"
    path.write_bytes(data)
    row = dict(path=path.name, sha256=hashlib.sha256(data).hexdigest(), format=fmt, n_samples=2)
    np.testing.assert_allclose(load_iq(row, tmp_path), expected)


def test_dropped_half_iq_pair_is_rejected(tmp_path):
    path = tmp_path / "iq.bin"
    path.write_bytes(b"123")
    with pytest.raises(ValueError, match="truncated IQ pair"):
        load_iq(dict(path=path.name, sha256=hashlib.sha256(b"123").hexdigest(), format="ci16_le", n_samples=1), tmp_path)


def test_finite_input_that_overflows_complex64_is_rejected(tmp_path):
    path = tmp_path / "overflow.npy"
    np.save(path, np.full(4, 1e100 + 1j, dtype=np.complex128))
    row = dict(path=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(), n_samples=4)
    with pytest.raises(ValueError, match="complex64"):
        load_iq(row, tmp_path)
