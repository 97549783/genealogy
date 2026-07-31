"""Экспорт семантического сравнения научных школ в Excel."""

from __future__ import annotations

from io import BytesIO
import json

import pandas as pd

from tabs.school_comparison.semantic import SemanticSchoolComparisonResult


def build_semantic_school_comparison_excel(
    result: SemanticSchoolComparisonResult, parameters: dict[str, object],
) -> bytes:
    """Создаёт книгу с фиксированными русскими листами отчёта."""
    parameter_rows = [{
        "Параметр": key,
        "Значение": json.dumps(value, ensure_ascii=False, default=str),
    } for key, value in sorted(parameters.items())]
    diagnostics = pd.DataFrame({"Диагностика": list(result.diagnostics)})
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(parameter_rows).to_excel(writer, sheet_name="Параметры", index=False)
        result.school_summary.to_excel(writer, sheet_name="Сводка по школам", index=False)
        result.dissertation_silhouettes.to_excel(writer, sheet_name="Силуэт по диссертациям", index=False)
        result.per_section_silhouette.to_excel(writer, sheet_name="Силуэт по разделам", index=False)
        result.excluded_dissertations.to_excel(writer, sheet_name="Исключённые диссертации", index=False)
        diagnostics.to_excel(writer, sheet_name="Диагностика", index=False)
    return output.getvalue()
