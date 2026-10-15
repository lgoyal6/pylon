"""Compare signature and anomaly detectors on manifest-defined captures.
recordings.py checks provenance; features.py supplies shared spectral inputs.
Freeze source and split hashes, isolate calibration, and retain all arms.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path

import numpy as np

import config
from anomaly_detector import AnomalyDetector
from features import iq_to_features
from library_baseline import LibraryBaseline, NO_MATCH
from recordings import load_iq, load_manifest


def source_hashes() -> dict:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob("*.py")}


def budget_threshold(scores: np.ndarray, seconds: float, alerts_per_hour: float) -> float:
    """Strict > boundary, conservative ties; never fit on final test scores."""
    scores = np.asarray(scores, dtype=float)
    if scores.size == 0 or np.isnan(scores).any() or seconds <= 0 or alerts_per_hour < 0:
        raise ValueError("invalid calibration scores or budget")
    allowed = min(int(alerts_per_hour * seconds / 3600), scores.size)
    if allowed == scores.size:
        return float("-inf")
    return float(np.sort(scores)[-(allowed + 1)])


def relative_power(X: np.ndarray) -> np.ndarray:
    """Named intervention: remove median log-power from bins and peak only."""
    out = X.copy()
    floor = np.median(out[:, :config.N_PSD_BINS], axis=1)
    out[:, :config.N_PSD_BINS] -= floor[:, None]
    out[:, config.N_PSD_BINS + 2] -= floor
    return out


def library_scores(model: LibraryBaseline, X: np.ndarray) -> np.ndarray:
    # Preserve the baseline's no-match rejection and ambient classification.
    # A matched signature's distance supplies a continuous calibration score.
    model._ensure_fit()
    dists, _ = model._nn.kneighbors((X - model._mu) / model._sigma, n_neighbors=1)
    scores = -dists[:, 0]
    predictions = model.predict(X)
    scores[(predictions == config.AMBIENT_CLASS) | (predictions == NO_MATCH)] = -np.inf
    return scores


def summarize(raw: list[dict], seed: int, repeats: int = 1000) -> dict:
    """Reconstruct all metrics from per-window decisions, clustered by session."""
    arms = list(raw[0]["flags"])
    result = {}
    for arm in arms:
        negatives = [r for r in raw if not r["target"]]
        targets = [r for r in raw if r["target"]]
        novel = [r for r in targets if r.get("novel")]
        negative_hours = sum(r["exposure_s"] for r in negatives) / 3600
        false_alerts = sum(sum(r["flags"][arm]) for r in negatives)
        recall = lambda rs: float(np.mean([np.mean(r["flags"][arm]) for r in rs])) if rs else None
        sessions = sorted({r["session_id"] for r in targets})
        rates = [np.mean([np.mean(r["flags"][arm]) for r in targets if r["session_id"] == s]) for s in sessions]
        rng = np.random.default_rng(seed)
        boot = [np.mean(rng.choice(rates, len(rates), replace=True)) for _ in range(repeats)]
        negative_sessions = sorted({r["session_id"] for r in negatives})
        neg_counts = np.array([sum(sum(r["flags"][arm]) for r in negatives if r["session_id"] == s) for s in negative_sessions])
        neg_hours = np.array([sum(r["exposure_s"] for r in negatives if r["session_id"] == s) / 3600 for s in negative_sessions])
        neg_boot = []
        for _ in range(repeats):
            idx = rng.integers(len(negative_sessions), size=len(negative_sessions))
            neg_boot.append(neg_counts[idx].sum() / neg_hours[idx].sum())
        delays = [next((i * r["hop_s"] for i, f in enumerate(r["flags"][arm]) if f), None) for r in targets]
        result[arm] = {"target_recording_macro_recall": recall(targets),
                       "novel_recording_macro_recall": recall(novel),
                       "false_alerted_windows": int(false_alerts), "negative_hours": negative_hours,
                       "false_alerted_windows_per_hour": false_alerts / negative_hours,
                       "false_alert_rate_session_bootstrap_95ci": np.quantile(neg_boot, [0.025, 0.975]).tolist() if len(negative_sessions) >= 2 else None,
                       "per_label_flag_fraction": {label: float(np.mean([np.mean(r["flags"][arm]) for r in raw if r["label"] == label])) for label in sorted({r["label"] for r in raw})},
                       "target_session_macro_recall": float(np.mean(rates)),
                       "target_session_bootstrap_95ci": np.quantile(boot, [0.025, 0.975]).tolist() if len(sessions) >= 2 else None,
                       "target_sessions": len(sessions), "target_recordings": len(targets),
                       "negative_sessions": len(negative_sessions), "bootstrap_min_sessions": 2,
                       "first_flag_delay_s": delays, "missed_recordings": sum(d is None for d in delays)}
    baseline = "library_budget"
    for arm in arms:
        # Paired session bootstrap keeps repeated windows out of the sample size.
        sessions = sorted({r["session_id"] for r in raw if r["target"]})
        diffs = [np.mean([np.mean(r["flags"][arm]) - np.mean(r["flags"][baseline])
                          for r in raw if r["target"] and r["session_id"] == s]) for s in sessions]
        rng = np.random.default_rng(seed)
        boot = [np.mean(rng.choice(diffs, len(diffs), replace=True)) for _ in range(repeats)]
        result[arm]["paired_recall_delta_vs_library_95ci"] = np.quantile(boot, [0.025, 0.975]).tolist() if len(sessions) >= 2 else None
    return result


def run(manifest_path: Path, protocol_path: Path, output: Path) -> dict:
    if output.exists():
        raise ValueError("output already exists; use a new experiment identity")
    protocol = json.loads(protocol_path.read_text())
    if protocol["source_sha256"] != source_hashes():
        raise ValueError("protocol source hashes differ; freeze a new experiment")
    manifest_bytes = manifest_path.read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != protocol["manifest_sha256"]:
        raise ValueError("protocol does not bind this manifest")
    manifest = load_manifest(manifest_path)
    window, hop = protocol["window_samples"], protocol["hop_samples"]
    if window <= 0 or hop <= 0 or hop > window or window < config.N_PSD_BINS:
        raise ValueError("invalid window geometry")
    captures = []
    total_windows = total_samples = 0
    for row in manifest["captures"]:
        total_samples += row["n_samples"]
        total_windows += max(0, 1 + (row["n_samples"] - window) // hop)
        if total_samples > 16_000_000 or total_windows > 500_000:
            raise ValueError("study exceeds bounded replay resources")
        iq = load_iq(row, manifest_path.parent)
        X = iq_to_features(iq, window_samples=window, hop_samples=hop)
        if len(X) == 0:
            raise ValueError("capture too short for study")
        captures.append({"row": row, "X": X})
    select = lambda role, target=None: [c for c in captures if c["row"]["role"] == role and (target is None or c["row"]["target"] == target)]
    train = select("train")
    X = np.concatenate([c["X"] for c in train])
    y = np.concatenate([np.full(len(c["X"]), c["row"]["label"] if c["row"]["target"] else config.AMBIENT_CLASS, dtype=object) for c in train])
    library = LibraryBaseline().fit(X, y)
    ambient = np.concatenate([c["X"] for c in select("train", False)])
    anomaly = AnomalyDetector(random_state=protocol["seed"])
    normalized = AnomalyDetector(random_state=protocol["seed"])
    # Cap internal sklearn workers even when launched inside the global lock.
    anomaly.model.n_jobs = normalized.model.n_jobs = 1
    anomaly.fit(ambient)
    normalized.fit(relative_power(ambient))
    scorers = {"library_budget": lambda x: library_scores(library, x),
               "anomaly_budget": anomaly.score,
               "relative_power_budget": lambda x: normalized.score(relative_power(x))}
    cal = select("calibration", False)
    cal_seconds = sum(len(c["X"]) * hop / c["row"]["sample_rate_hz"] for c in cal)
    thresholds = {arm: budget_threshold(np.concatenate([score(c["X"]) for c in cal]), cal_seconds,
                                       protocol["false_alerted_windows_per_hour"]) for arm, score in scorers.items()}
    calibration = {arm: {"threshold": str(thresholds[arm]),
                         "false_alerted_windows_per_hour": sum(int((score(c["X"]) > thresholds[arm]).sum()) for c in cal) / cal_seconds * 3600}
                   for arm, score in scorers.items()}
    calibration_raw = [{"recording_id": c["row"]["recording_id"],
                        "exposure_s": len(c["X"]) * hop / c["row"]["sample_rate_hz"],
                        "scores": {arm: [str(v) for v in score(c["X"])] for arm, score in scorers.items()}}
                       for c in cal]
    raw = []
    for c in select("test"):
        row, X = c["row"], c["X"]
        flags = {arm: (score(X) > thresholds[arm]).tolist() for arm, score in scorers.items()}
        flags.update(library_native=library.is_detection(X).tolist(), anomaly_native=anomaly.is_detection(X).tolist())
        raw.append({**{k: row[k] for k in ("recording_id", "session_id", "site_id", "device_id", "day", "target", "evidence_kind", "label")},
                    "novel": row.get("novel", False), "hop_s": hop / row["sample_rate_hz"],
                    "exposure_s": len(X) * hop / row["sample_rate_hz"], "flags": flags})
    result = {"protocol_sha256": hashlib.sha256(protocol_path.read_bytes()).hexdigest(),
              "manifest_sha256": protocol["manifest_sha256"], "calibration": calibration,
              "calibration_raw": calibration_raw,
              "raw": raw, "summary": summarize(raw, protocol["seed"]),
              "environment": {"python": platform.python_version(), "platform": platform.platform(),
                              "packages": {p: importlib.metadata.version(p) for p in ("numpy", "scipy", "scikit-learn")}},
              "source_sha256": source_hashes(),
              "limits": ["Alerts are flagged windows, with hop-time exposure, not independent episodes.",
                         "First-flag delay is relative to recording start, not annotated target onset.",
                         "Calibration satisfies a budget; test false alerts can exceed it under shift.",
                         "Bootstrap resamples acquisition sessions; short exposures cannot establish a field alert rate."]}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, allow_nan=False))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("protocol", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    run(args.manifest, args.protocol, args.output)


if __name__ == "__main__":
    main()
