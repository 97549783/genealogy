"""Загрузка демо-групп тематических блоков для анализа статей."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import pandas as pd

ARTICLE_ANALYSIS_BLOCK_GROUP_PATHS = [
    "core/classifier/article_analysis_blocks.json",
    "article_analysis_blocks.json",
    "db_articles/article_analysis_blocks.json",
]
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _read_json_dict(path: Path) -> dict[str, Any]:
    """Читает JSON-словарь из файла конфигурации тематических блоков."""
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"Файл тематических блоков должен содержать JSON-объект: {path}")
    return data


def load_article_analysis_block_groups() -> dict:
    """Загружает группы тематических блоков для демо-анализа статей."""
    for path_str in ARTICLE_ANALYSIS_BLOCK_GROUP_PATHS:
        for path in (Path(path_str), _REPO_ROOT / path_str):
            if path.exists():
                return _read_json_dict(path)
    raise FileNotFoundError("Не найден файл core/classifier/article_analysis_blocks.json с группами анализа статей")


ARTICLE_ANALYSIS_BLOCK_GROUPS = load_article_analysis_block_groups()


def get_available_block_columns(
    df: pd.DataFrame,
    classifier_labels: dict[str, str] | None = None,
    block_group_ids: Optional[list[str]] = None,
) -> list[dict]:
    """Возвращает блоки, которые есть в данных статей и имеют подпись в классификаторе."""
    if df is None or df.empty or not classifier_labels:
        return []

    allowed_columns = set(df.columns.astype(str))
    block_groups = load_article_analysis_block_groups()
    group_ids = block_group_ids or list(block_groups.keys())
    blocks: list[dict] = []

    for group_id in group_ids:
        group = block_groups.get(group_id)
        if not isinstance(group, dict):
            continue
        group_label = str(group.get("label", "")).strip()
        codes = group.get("codes", [])
        if not group_label or not isinstance(codes, list):
            continue
        for raw_code in codes:
            code = str(raw_code).strip()
            label = str(classifier_labels.get(code, "")).strip()
            if code in allowed_columns and label:
                blocks.append({"code": code, "label": label, "group": group_label})

    return blocks
