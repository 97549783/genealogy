"""Метрики для демо-анализа статей."""

from __future__ import annotations

import re
from typing import Any, Set

import numpy as np
import pandas as pd

METADATA_COLS = {"Article_id", "Authors", "Title", "Journal", "ISSN", "Volume", "Issue", "school", "Year", "Year_num", "Abstract", "Keywords", "DOI", "Pages", "Funding"}


def get_article_feature_columns(df: pd.DataFrame) -> list[str]:
    """Возвращает столбцы классификатора, исключая метаданные."""
    if df is None or df.empty:
        return []
    return [str(col) for col in df.columns if str(col) not in METADATA_COLS and re.fullmatch(r"[\d\.]+", str(col))]


def compute_block_score_summary(df: pd.DataFrame, blocks: list[dict], threshold: float = 3.0, show_all: bool = False) -> pd.DataFrame:
    """Считает средние и максимальные баллы по тематическим блокам."""
    rows = []
    if df is None or df.empty:
        return pd.DataFrame(columns=["Блок", "Средний балл", "Максимальный балл", "Статей с баллом ≥ порога", "Доля статей с баллом ≥ порога"])
    for block in blocks:
        code = block.get("code")
        if code not in df.columns:
            continue
        values = pd.to_numeric(df[code], errors="coerce").fillna(0)
        mean_score = float(values.mean()) if len(values) else 0.0
        if not show_all and mean_score < threshold:
            continue
        count = int((values >= threshold).sum())
        rows.append({
            "Блок": block.get("label", ""),
            "Средний балл": mean_score,
            "Максимальный балл": float(values.max()) if len(values) else 0.0,
            "Статей с баллом ≥ порога": count,
            "Доля статей с баллом ≥ порога": float(count / len(values)) if len(values) else 0.0,
        })
    return pd.DataFrame(rows)


def build_school_vector(df: pd.DataFrame, feature_columns: list[str]) -> np.ndarray:
    """Строит вектор средних баллов школы по выбранным признакам."""
    if df is None or df.empty or not feature_columns:
        return np.array([], dtype=float)
    work = df.reindex(columns=feature_columns).apply(pd.to_numeric, errors="coerce").fillna(0.0)
    return work.mean(axis=0).to_numpy(dtype=float)


def normalize_keyword(keyword: Any) -> str:
    """Минимально нормализует ключевое слово без записи в базу."""
    if keyword is None or pd.isna(keyword):
        return ""
    return re.sub(r"\s+", " ", str(keyword).strip().lower().replace("ё", "е"))


def compute_keyword_overlap(source_keywords: Set[str], target_keywords: Set[str]) -> dict:
    """Вычисляет пересечение и индекс Жаккара для двух наборов ключевых слов."""
    source = {normalize_keyword(v) for v in source_keywords if normalize_keyword(v)}
    target = {normalize_keyword(v) for v in target_keywords if normalize_keyword(v)}
    intersection = sorted(source & target)
    union = source | target
    return {"intersection_count": len(intersection), "jaccard": float(len(intersection) / len(union)) if union else 0.0, "intersection_keywords": intersection}


def cosine_similarity_safe(a: np.ndarray, b: np.ndarray) -> float:
    """Безопасно считает косинусную близость, возвращая 0 для пустых и нулевых векторов."""
    if a.size == 0 or b.size == 0 or a.shape != b.shape:
        return 0.0
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)
