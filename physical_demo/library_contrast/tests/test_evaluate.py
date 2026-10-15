"""Check the synthetic evaluation and its output artifacts.
Exercise evaluate.py with generated IQ and direct split boundary cases.
Require real test observations before reporting any miss-rate result.
"""
from __future__ import annotations

import os

import config
import evaluate
import numpy as np
import pytest


def test_empty_test_set_cannot_report_zero_miss():
    with pytest.raises(ValueError, match="empty"):
        evaluate._miss_rate_on(lambda x: np.zeros(len(x), bool), np.empty((0, 69)), True)


@pytest.mark.parametrize("fraction", [0, 1, -0.1, 1.1, float("nan")])
def test_invalid_split_fraction_is_rejected(fraction):
    with pytest.raises(ValueError, match="train_fraction"):
        evaluate._train_test_split({"ambient": np.ones((10, 69))}, fraction, np.random.default_rng(1))


def test_split_requires_nonempty_train_and_test():
    with pytest.raises(ValueError, match="at least"):
        evaluate._train_test_split({"ambient": np.ones((1, 69))}, .6, np.random.default_rng(1))


def test_end_to_end_evaluate_and_artifacts(tmp_path, short_duration):
    result = evaluate.evaluate(duration_s=short_duration)
    names = [r.name for r in result.per_class]
    assert set(names) == set(config.ALL_CLASSES)
    # The whole experiment exists to show this gap on novel:
    assert result.anomaly_overall_novel_miss < result.library_overall_novel_miss

    chart_path = tmp_path / "chart.png"
    table_path = tmp_path / "table.md"
    evaluate.write_chart(result, str(chart_path))
    evaluate.write_table(result, str(table_path))
    assert chart_path.exists() and chart_path.stat().st_size > 0
    assert table_path.exists() and table_path.stat().st_size > 0
    body = table_path.read_text()
    assert "Library miss" in body and "Anomaly miss" in body


def test_main_writes_outputs(tmp_path, short_duration):
    out = tmp_path / "out"
    rc = evaluate.main(
        ["--output-dir", str(out), "--duration-s", str(short_duration)]
    )
    assert rc == 0
    assert (out / config.CHART_FILENAME).exists()
    assert (out / config.TABLE_FILENAME).exists()
