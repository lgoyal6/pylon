"""Testable cores of the collect/train CLIs (dataset append + model training)."""
import numpy as np

from collect import append_dataset
from train import train_model


def test_append_dataset_creates_then_appends(tmp_path):
    path = str(tmp_path / "ds.npz")
    append_dataset(path, [[1.0, 2.0]], ["wifi"])
    append_dataset(path, [[3.0, 4.0], [5.0, 6.0]], ["quiet", "hopper"])
    d = np.load(path, allow_pickle=True)
    assert d["X"].shape == (3, 2)
    assert list(d["y"]) == ["wifi", "quiet", "hopper"]


def test_train_model_learns_separable_classes():
    rng = np.random.default_rng(0)
    X = np.vstack([rng.normal(0, 0.5, (30, 3)), rng.normal(10, 0.5, (30, 3))])
    y = ["quiet"] * 30 + ["hopper"] * 30
    clf, acc = train_model(X, y, test_frac=0.3, seed=1)
    assert acc > 0.8                      # separable -> high held-out accuracy
    assert clf.predict([10, 10, 10]) == "hopper"
