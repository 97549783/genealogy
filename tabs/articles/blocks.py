"""Выбранные тематические блоки для анализа статей."""

from __future__ import annotations

from typing import Optional

import pandas as pd


def _items(codes: list[str], prefix: str) -> list[dict]:
    return [{"code": code, "label": f"{prefix}: тематический блок {idx}"} for idx, code in enumerate(codes, start=1)]

ARTICLE_ANALYSIS_BLOCK_GROUPS = {
    "education_level": {
        "label": "Уровень формального образования",
        "codes": _items([
            "1.1.1", "1.1.1.1", "1.1.1.2", "1.1.1.2.1", "1.1.1.2.2", "1.1.1.2.3",
            "1.1.1.3", "1.1.1.4", "1.1.1.4.1", "1.1.1.4.2", "1.1.1.4.3", "1.1.1.5",
            "1.1.1.5.1", "1.1.1.5.2", "1.1.1.6", "1.1.1.6.1", "1.1.1.6.2", "1.1.1.7", "1.1.1.8",
        ], "Уровень формального образования"),
    },
    "subject_area": {
        "label": "Предметная область / направление подготовки",
        "codes": _items([
            "1.1.2", "1.1.2.1", "1.1.2.1.1", "1.1.2.1.2", "1.1.2.1.3", "1.1.2.1.4", "1.1.2.1.5", "1.1.2.1.6",
            "1.1.2.1.7", "1.1.2.2", "1.1.2.3", "1.1.2.4", "1.1.2.5", "1.1.2.6", "1.1.2.7", "1.1.2.8",
            "1.1.2.9", "1.1.2.9.1", "1.1.2.9.2", "1.1.2.10", "1.1.2.11", "1.1.2.12", "1.1.2.13", "1.1.2.14",
        ], "Предметная область"),
    },
    "digital_technologies": {
        "label": "Цифровые технологии в образовании",
        "codes": _items([
            "2.2", "2.2.1", "2.2.1.1", "2.2.1.2", "2.2.1.3", "2.2.1.4", "2.2.1.5", "2.2.1.6", "2.2.1.7",
            "2.2.2", "2.2.2.1", "2.2.2.2", "2.2.2.3", "2.2.2.4", "2.2.2.5", "2.2.2.6", "2.2.2.7",
            "2.2.3", "2.2.3.1", "2.2.3.2", "2.2.3.3", "2.2.3.4", "2.2.3.5", "2.2.3.6", "2.2.3.7", "2.2.3.8",
            "2.2.4", "2.2.4.1", "2.2.4.2", "2.2.4.3", "2.2.4.4", "2.2.5", "2.2.5.1", "2.2.5.2", "2.2.5.3",
            "2.2.5.4", "2.2.5.5", "2.2.5.6", "2.2.6", "2.2.6.1", "2.2.6.2", "2.2.6.3", "2.2.6.4", "2.2.6.5", "2.2.6.6",
        ], "Цифровые технологии"),
    },
}


def get_available_block_columns(df: pd.DataFrame, block_group_ids: Optional[list[str]] = None) -> list[dict]:
    """Возвращает только блоки, для которых есть столбцы с баллами статей."""
    if df is None or df.empty:
        return []
    allowed = set(df.columns.astype(str))
    group_ids = block_group_ids or list(ARTICLE_ANALYSIS_BLOCK_GROUPS.keys())
    blocks: list[dict] = []
    for group_id in group_ids:
        group = ARTICLE_ANALYSIS_BLOCK_GROUPS.get(group_id)
        if not group:
            continue
        for item in group["codes"]:
            if item["code"] in allowed:
                block = dict(item)
                block["group"] = group["label"]
                blocks.append(block)
    return blocks
