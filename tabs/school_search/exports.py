"""Формирование локализованных книг семантического поиска школ."""

from __future__ import annotations

from io import BytesIO
import json

import pandas as pd

from tabs.dissertation_characteristics.labels import SECTION_LABELS_RU
from tabs.school_search.semantic import SemanticSchoolQueryResult, SimilarSchoolResult

PARAMETER_LABELS = {
    "queries": "Запросы", "source_root": "Исходная научная школа", "scope": "Охват",
    "ranking_mode": "Цель ранжирования", "relevance_threshold": "Порог релевантности",
    "shrinkage_strength": "Сила сглаживания", "minimum_school_size": "Минимальный размер школы",
    "minimum_profiled_dissertations": "Минимум диссертаций с векторами", "top_n": "Число результатов",
    "year_from": "Год от", "year_to": "Год до", "degree_levels": "Уровни учёной степени",
    "section_mode": "Режим выбора характеристик", "section_keys": "Разделы характеристик",
    "section_weights": "Веса разделов", "minimum_coverage": "Минимальное покрытие",
    "hide_near_duplicates": "Скрывать совпадающие школы", "near_duplicate_jaccard": "Порог Жаккара",
    "main_database_signature": "Подпись основной базы", "lineage_context_key": "Контекст отраслевого фильтра",
    "section_database_signature": "Подпись базы разделов", "matrix_signature": "Подпись матрицы",
    "model_name": "Модель векторов", "normalized": "Векторы нормализованы",
}

QUERY_SCHOOL_COLUMNS = {
    "rank": "Ранг", "root": "Научный руководитель", "ranking_score": "Оценка ранжирования",
    "total_members": "Всего членов школы", "filtered_members": "Членов после фильтров",
    "covered_dissertations": "Диссертаций с векторами", "coverage_ratio": "Полнота данных, %",
    "mean_similarity": "Среднее сходство", "median_similarity": "Медианное сходство",
    "upper_quartile_similarity": "Верхний квартиль сходства", "top_20_percent_mean": "Среднее лучших 20 %",
    "share_above_threshold": "Доля выше порога, %", "maximum_similarity": "Максимальное сходство",
    "year_range": "Период активности",
}

SIMILAR_SCHOOL_COLUMNS = {
    "rank": "Ранг", "root": "Научный руководитель", "semantic_similarity": "Семантическое сходство",
    "common_section_count": "Общих разделов характеристик", "profiled_dissertations": "Диссертаций с векторами",
    "source_coverage_ratio": "Полнота исходной школы, %",
    "coverage_ratio": "Полнота данных, %", "jaccard_overlap": "Пересечение состава по Жаккару",
    "total_members": "Всего членов школы", "year_range": "Период активности",
}


def _parameters_frame(parameters: dict[str, object]) -> pd.DataFrame:
    """Переводит названия и значения параметров для пользователя."""
    values = {"direct": "Прямые ученики", "broad": "Широкая специализация",
              "focused": "Сильное направление", "selected": "Выбранные разделы"}
    rows = []
    for key, value in sorted(parameters.items()):
        if key not in PARAMETER_LABELS:
            continue
        if isinstance(value, bool):
            value = "Да" if value else "Нет"
        elif isinstance(value, str):
            if key == "section_mode" and value == "all":
                value = "Все доступные характеристики"
            elif key == "scope" and value == "all":
                value = "Все поколения"
            else:
                value = values.get(value, SECTION_LABELS_RU.get(value, value))
        elif key == "section_keys":
            value = [SECTION_LABELS_RU.get(str(item), str(item)) for item in value]
        elif key == "section_weights":
            value = [[SECTION_LABELS_RU.get(str(item[0]), str(item[0])), item[1]] for item in value]
        if key in {"minimum_coverage", "relevance_threshold", "near_duplicate_jaccard"} and isinstance(value, (int, float)):
            value = f"{float(value) * 100:.1f} %"
        rows.append({"Параметр": PARAMETER_LABELS[key], "Значение": json.dumps(value, ensure_ascii=False, default=str)})
    return pd.DataFrame(rows, columns=["Параметр", "Значение"])


def _select_columns(frame: pd.DataFrame, mapping: dict[str, str], percent: tuple[str, ...] = ()) -> pd.DataFrame:
    """Выбирает только разрешённые столбцы с русскими заголовками."""
    result = pd.DataFrame({label: frame[key] for key, label in mapping.items() if key in frame})
    for column in percent:
        if column in result:
            result[column] = result[column] * 100.0
    return result


def build_semantic_query_search_excel(result: SemanticSchoolQueryResult) -> bytes:
    """Экспортирует ранжирование школ и объясняющие диссертации."""
    schools = _select_columns(result.summary, QUERY_SCHOOL_COLUMNS, ("Полнота данных, %", "Доля выше порога, %"))
    detail_rows, contribution_rows = [], []
    for root, details in result.dissertation_details.items():
        for record in details.to_dict("records"):
            detail_rows.append({
                "Научный руководитель": root, "Автор": record.get("candidate_name"),
                "Название": record.get("title"), "Год": record.get("year"),
                "Отрасль науки": record.get("degree.science_field", record.get("science_field")),
                "Семантическое сходство": record.get("semantic_score"),
                "Полнота характеристик, %": float(record.get("coverage", 0)) * 100,
                "Лучший раздел": SECTION_LABELS_RU.get(record.get("best_section_key"), record.get("best_section_key")),
                "Сходство лучшего раздела": record.get("best_section_similarity"),
            })
            for key, score in (record.get("section_scores") or {}).items():
                contribution_rows.append({"Научный руководитель": root, "Автор": record.get("candidate_name"),
                                          "Название": record.get("title"), "Год": record.get("year"),
                                          "Раздел характеристики": SECTION_LABELS_RU.get(key, key), "Сходство": score})
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        _parameters_frame(result.parameters).to_excel(writer, "Параметры поиска", index=False)
        schools.to_excel(writer, "Научные школы", index=False)
        pd.DataFrame(detail_rows).to_excel(writer, "Лучшие диссертации", index=False)
        pd.DataFrame(contribution_rows).to_excel(writer, "Вклады разделов", index=False)
        pd.DataFrame({"Диагностика": result.diagnostics}).to_excel(writer, "Диагностика", index=False)
    return output.getvalue()


def build_similar_school_search_excel(result: SimilarSchoolResult) -> bytes:
    """Экспортирует сходство школ, разделов и репрезентативные работы."""
    schools = _select_columns(result.summary, SIMILAR_SCHOOL_COLUMNS, ("Полнота данных, %", "Полнота исходной школы, %"))
    sections = pd.concat([
        frame.assign(**{"Научный руководитель": root}) for root, frame in result.section_similarities.items()
    ], ignore_index=True) if result.section_similarities else pd.DataFrame()
    nearest_rows, representative_rows = [], []
    for root, frame in result.dissertation_details.items():
        for record in frame.to_dict("records"):
            row = {"Научный руководитель": root, "Автор": record.get("candidate_name"),
                   "Название": record.get("title"), "Год": record.get("year"),
                   "Расстояние до исходной школы": record.get("distance_to_source"),
                   "Полнота характеристик, %": float(record.get("coverage", 0)) * 100}
            nearest_rows.append(row)
            if record.get("representative"):
                representative_rows.append(row)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        _parameters_frame(result.parameters).to_excel(writer, "Параметры поиска", index=False)
        schools.to_excel(writer, "Научные школы", index=False)
        sections.to_excel(writer, "Сходство по разделам", index=False)
        pd.DataFrame(representative_rows).to_excel(writer, "Репрезентативные работы", index=False)
        pd.DataFrame(nearest_rows).to_excel(writer, "Ближайшие диссертации", index=False)
        pd.DataFrame({"Диагностика": result.diagnostics}).to_excel(writer, "Диагностика", index=False)
    return output.getvalue()
