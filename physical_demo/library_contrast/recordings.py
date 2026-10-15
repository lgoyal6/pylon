"""Load checksum-bound IQ and provenance for heldout_study.py.
Validate acquisition groups before converting supported raw formats.
Bound each file and reject loss, invalid samples or unsupported geometry.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path

import numpy as np

from site_holdout import validate_partitions

ROLES = ("train", "calibration", "test")


def load_manifest(path: str | Path) -> dict:
    path = Path(path).resolve()
    manifest = json.loads(path.read_text())
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported manifest schema")
    rows = manifest.get("captures", [])
    ids = set()
    for row in rows:
        for key in ("recording_id", "session_id", "site_id", "device_id", "day",
                    "emitter_id", "label", "license", "source", "path", "sha256"):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise ValueError(f"missing {key}")
        date.fromisoformat(row["day"])
        if not re.fullmatch(r"[0-9a-f]{64}", row["sha256"]):
            raise ValueError("invalid sha256")
        if type(row.get("n_samples")) is not int or row["n_samples"] <= 0:
            raise ValueError("invalid n_samples")
        if row["recording_id"] in ids:
            raise ValueError("duplicate recording_id")
        ids.add(row["recording_id"])
        if row.get("role") not in ROLES or type(row.get("target")) is not bool:
            raise ValueError("invalid role or target label")
        if row.get("evidence_kind") not in ("synthetic", "chamber", "field"):
            raise ValueError("explicit evidence_kind required")
        for key in ("sample_rate_hz", "center_freq_hz"):
            if not np.isfinite(row.get(key, np.nan)) or row[key] <= 0:
                raise ValueError(f"invalid {key}")
        if row.get("dropped_samples") != 0:
            raise ValueError("capture loss must be zero for comparative replay")
        if not isinstance(row.get("gain_db"), (int, float)) or not np.isfinite(row["gain_db"]):
            raise ValueError("fixed gain_db required; AGC captures need a separate protocol")
        if not np.isfinite(row.get("clock_ppm", np.nan)):
            raise ValueError("clock_ppm provenance required")
    parts = {role: [r for r in rows if r["role"] == role] for role in ROLES}
    axes = manifest.get("holdout_axes", [])
    if not isinstance(axes, list) or any(a not in ("site_id", "device_id", "day") for a in axes):
        raise ValueError("invalid holdout_axes")
    validate_partitions(parts, ("recording_id", "session_id", "sha256", *axes))
    # A novel emitter identity must be absent from fitting and calibration.
    seen = {r["emitter_id"] for r in rows if r["role"] != "test"}
    if any(r.get("novel", False) and r["emitter_id"] in seen for r in parts["test"]):
        raise ValueError("novel emitter identity leaked")
    for role in ROLES:
        if not any(not r["target"] for r in parts[role]):
            raise ValueError(f"negative captures required in {role}")
    if not any(r["target"] for r in parts["train"]) or not any(r["target"] for r in parts["test"]):
        raise ValueError("target captures required for signature baseline and test")
    geometry = {(r["sample_rate_hz"], r["center_freq_hz"]) for r in rows}
    if len(geometry) != 1:
        raise ValueError("mixed RF geometry requires an explicit resampling protocol")
    return manifest


def load_iq(row: dict, root: str | Path, max_bytes: int = 64 * 1024 * 1024) -> np.ndarray:
    root = Path(root).resolve()
    path = (root / row["path"]).resolve()
    if not path.is_relative_to(root):
        raise ValueError("recording path escapes manifest directory")
    size = path.stat().st_size
    if size == 0 or size > max_bytes:
        raise ValueError("recording size outside replay bound")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != row["sha256"]:
        raise ValueError("recording checksum mismatch")
    fmt = row.get("format", "npy")
    if fmt == "npy":
        # mmap checks declared shape against file size before allocating it.
        iq = np.load(path, mmap_mode="r", allow_pickle=False)
    elif fmt in ("cf32_le", "ci16_le", "cu8"):
        dtype = {"cf32_le": "<c8", "ci16_le": "<i2", "cu8": "u1"}[fmt]
        stride = {"cf32_le": 8, "ci16_le": 4, "cu8": 2}[fmt]
        if size % stride:
            raise ValueError("truncated IQ pair")
        samples = np.frombuffer(raw, dtype=dtype)
        if fmt == "cf32_le":
            iq = samples
        else:
            samples = samples.astype(np.float32)
            if fmt == "cu8":
                samples = (samples - 127.5) / 127.5
            else:
                samples /= 32768.0
            iq = samples[::2] + 1j * samples[1::2]
    else:
        raise ValueError("unsupported IQ format")
    if iq.ndim != 1 or not np.iscomplexobj(iq) or not np.isfinite(iq).all():
        raise ValueError("expected finite 1-D complex IQ")
    if iq.size != row.get("n_samples"):
        raise ValueError("sample count mismatch")
    with np.errstate(over="ignore"):
        converted = iq.astype(np.complex64)
    if not np.isfinite(converted).all():
        raise ValueError("IQ values cannot be represented as finite complex64")
    return converted
