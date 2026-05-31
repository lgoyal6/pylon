"""Case 3 — train the RF classifier on a feature dataset collected by collect.py.

    python train.py --dataset dataset.npz --out model.joblib

Dataset is an npz with X (rows x 8 features) and y (string labels). Prints
held-out accuracy + a per-class confusion summary; saves the model for
ClassifierSource (main.py --detector classifier --classify-model model.joblib).
"""
import argparse
from collections import Counter

import numpy as np

from classifier import RFClassifier


def train_model(X, y, test_frac: float = 0.25, seed: int = 0):
    """Fit on a train split; return (RFClassifier, held-out accuracy). Testable."""
    X = np.asarray(X, dtype=float)
    y = np.asarray(y)
    n = len(y)
    idx = np.random.default_rng(seed).permutation(n)
    n_test = max(1, int(n * test_frac))
    test_idx, train_idx = idx[:n_test], idx[n_test:]
    clf = RFClassifier()
    clf.fit(X[train_idx], y[train_idx])
    correct = sum(clf.predict(X[i]) == y[i] for i in test_idx)
    return clf, correct / len(test_idx)


def main() -> None:
    parser = argparse.ArgumentParser(prog="train", description="Train the RF signal classifier.")
    parser.add_argument("--dataset", required=True, help="npz with X (features) and y (labels)")
    parser.add_argument("--out", default="model.joblib", help="output model path")
    parser.add_argument("--test-frac", type=float, default=0.25)
    args = parser.parse_args()

    data = np.load(args.dataset, allow_pickle=True)
    X, y = data["X"], data["y"]
    print(f"dataset: {len(y)} rows, classes {dict(Counter(y))}")
    clf, acc = train_model(X, y, test_frac=args.test_frac)
    print(f"held-out accuracy: {acc:.1%}")
    clf.fit(X, y)  # refit on all data for the saved model
    clf.save(args.out)
    print(f"saved model -> {args.out}")


if __name__ == "__main__":
    main()
