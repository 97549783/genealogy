from __future__ import annotations

import json
from pathlib import Path

from tabs.articles.comparison import load_articles_classifier


def test_load_articles_classifier_prefers_core_classifier_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    classifier_dir = tmp_path / "core" / "classifier"
    classifier_dir.mkdir(parents=True)

    expected = {"1": "Раздел 1", "1.1": "Раздел 1.1"}
    (classifier_dir / "articles_classifier.json").write_text(
        json.dumps(expected, ensure_ascii=False),
        encoding="utf-8",
    )

    assert load_articles_classifier() == expected
