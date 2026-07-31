"""Экспорт семантического сравнения научных школ в Excel."""

from __future__ import annotations

from io import BytesIO
import json

import pandas as pd

from tabs.school_comparison.semantic import SemanticSchoolComparisonResult
from tabs.dissertation_characteristics.labels import SECTION_LABELS_RU

PARAMETERS_RU = {
    "representation": "Представление", "schools": "Научные школы", "scope": "Охват",
    "science_fields": "Отрасли науки", "sections_mode": "Режим выбора характеристик",
    "section_keys": "Разделы характеристик", "minimum_coverage": "Минимальное покрытие",
    "database_signature": "Подпись основной базы", "section_database_signature": "Подпись базы разделов",
    "matrix_signature": "Подпись матрицы", "model_name": "Модель векторов",
    "normalized": "Векторы нормализованы",
}


def _dissertations(frame: pd.DataFrame, include_silhouette: bool) -> pd.DataFrame:
    """Выбирает только локализованные пользовательские поля диссертаций."""
    mapping = {
        "Школа": "Научная школа", "candidate_name": "Автор", "title": "Название", "year": "Год",
        "degree.science_field": "Отрасль науки", "science_field": "Отрасль науки",
        "coverage": "Полнота характеристик, %", "Причина исключения": "Причина исключения",
    }
    if include_silhouette:
        mapping["Коэффициент силуэта"] = "Коэффициент силуэта"
    result = pd.DataFrame({label: frame[key] for key, label in mapping.items() if key in frame})
    if "Полнота характеристик, %" in result:
        result["Полнота характеристик, %"] *= 100.0
    return result


def build_semantic_school_comparison_excel(
    result: SemanticSchoolComparisonResult, parameters: dict[str, object],
) -> bytes:
    """Создаёт книгу с русскими параметрами, таблицами и диагностикой."""
    parameter_rows = []
    value_labels = {"classifier": "Тематические профили по классификатору", "characteristics": "Векторы характеристик",
                    "direct": "Прямые ученики", "all": "Все поколения", "selected": "Выбранные разделы"}
    for key, value in sorted(parameters.items()):
        if key not in PARAMETERS_RU:
            continue
        if isinstance(value, bool):
            value = "Да" if value else "Нет"
        elif isinstance(value, str):
            value = value_labels.get(value, value)
        elif key == "section_keys":
            value = [SECTION_LABELS_RU.get(str(item), str(item)) for item in value]
        parameter_rows.append({"Параметр": PARAMETERS_RU[key], "Значение": json.dumps(value, ensure_ascii=False, default=str)})
    diagnostic_rows = [{"Диагностика": message} for message in result.diagnostics]
    diagnostic_rows.append({"Диагностика": f"Причина попарного расчёта: {result.pairwise_diagnostics.reason}"})
    diagnostic_rows.append({"Диагностика": f"Предел числа диссертаций: {result.pairwise_diagnostics.maximum_pairwise_items}"})
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(parameter_rows).to_excel(writer, sheet_name="Параметры", index=False)
        result.school_summary.to_excel(writer, sheet_name="Сводка по школам", index=False)
        _dissertations(result.dissertation_silhouettes, True).to_excel(writer, sheet_name="Силуэт по диссертациям", index=False)
        result.per_section_silhouette.to_excel(writer, sheet_name="Силуэт по разделам", index=False)
        _dissertations(result.excluded_dissertations, False).to_excel(writer, sheet_name="Исключённые диссертации", index=False)
        pd.DataFrame(diagnostic_rows).to_excel(writer, sheet_name="Диагностика", index=False)
    return output.getvalue()
