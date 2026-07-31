"""Формирование русскоязычных книг Excel семантического поиска школ."""

from __future__ import annotations

from io import BytesIO
import json

import pandas as pd

from tabs.dissertation_characteristics.labels import SECTION_LABELS_RU
from tabs.school_search.semantic import SemanticSchoolQueryResult, SimilarSchoolResult


QUERY_COLUMNS_RU = {
    "rank": "Ранг", "root": "Научный руководитель", "ranking_score": "Оценка ранжирования",
    "total_members": "Всего членов школы", "covered_dissertations": "Диссертаций с векторами",
    "coverage_ratio": "Полнота данных", "mean_similarity": "Среднее сходство",
    "median_similarity": "Медианное сходство", "upper_quartile_similarity": "Верхний квартиль сходства",
    "top_20_percent_mean": "Среднее лучших 20 %", "share_above_threshold": "Доля выше порога",
    "maximum_similarity": "Максимальное сходство", "year_range": "Период активности",
}

SIMILAR_COLUMNS_RU = {
    "rank": "Ранг", "root": "Научный руководитель", "semantic_similarity": "Семантическое сходство",
    "common_section_count": "Общих разделов характеристик",
    "profiled_dissertations": "Диссертаций с векторами", "coverage_ratio": "Полнота данных, %",
    "jaccard_overlap": "Пересечение состава по Жаккару", "total_members": "Всего членов школы",
    "year_range": "Период активности",
}


def _parameters_frame(parameters: dict[str, object]) -> pd.DataFrame:
    """Преобразует параметры в устойчивую двухколоночную таблицу."""
    return pd.DataFrame([
        {"Параметр": key, "Значение": json.dumps(value, ensure_ascii=False, default=str)}
        for key, value in sorted(parameters.items())
    ])


def _details_frames(details: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Разделяет лучшие диссертации и вклады характеристик."""
    rows, contributions = [], []
    for root, frame in details.items():
        for record in frame.to_dict("records"):
            scores = record.pop("section_scores", {}) or {}
            record["Научный руководитель"] = root
            rows.append(record)
            for key, score in scores.items():
                contributions.append({
                    "Научный руководитель": root, "Code": record.get("Code"),
                    "Раздел характеристики": SECTION_LABELS_RU.get(key, key), "Сходство": score,
                })
    return pd.DataFrame(rows), pd.DataFrame(contributions)


def _build_excel(
    summary: pd.DataFrame, details: dict[str, pd.DataFrame], diagnostics: tuple[str, ...],
    parameters: dict[str, object], columns: dict[str, str],
) -> bytes:
    """Собирает книгу с фиксированными русскими листами."""
    schools = summary.rename(columns=columns).copy()
    for column in ("Полнота данных, %",):
        if column in schools:
            schools[column] = schools[column] * 100.0
    dissertations, contributions = _details_frames(details)
    diagnostic_frame = pd.DataFrame({"Диагностика": list(diagnostics)})
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        _parameters_frame(parameters).to_excel(writer, sheet_name="Параметры поиска", index=False)
        schools.to_excel(writer, sheet_name="Научные школы", index=False)
        dissertations.to_excel(writer, sheet_name="Лучшие диссертации", index=False)
        contributions.to_excel(writer, sheet_name="Вклады разделов", index=False)
        diagnostic_frame.to_excel(writer, sheet_name="Диагностика", index=False)
    return output.getvalue()


def build_semantic_query_search_excel(result: SemanticSchoolQueryResult) -> bytes:
    """Экспортирует поиск школ по естественно-языковому запросу."""
    return _build_excel(result.summary, result.dissertation_details, result.diagnostics,
                        result.parameters, QUERY_COLUMNS_RU)


def build_similar_school_search_excel(result: SimilarSchoolResult) -> bytes:
    """Экспортирует поиск похожих научных школ."""
    return _build_excel(result.summary, result.dissertation_details, result.diagnostics,
                        result.parameters, SIMILAR_COLUMNS_RU)
