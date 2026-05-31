from __future__ import annotations

import os

import config
import evaluate


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
