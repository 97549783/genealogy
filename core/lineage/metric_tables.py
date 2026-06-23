from __future__ import annotations

import pandas as pd

from core.lineage.metric_definitions import get_metric_definition
from core.lineage.metrics import LineageMetrics, MetricValue

METRIC_STATUS_LABELS = {
    "available": "доступно",
    "not_applicable": "не выводится",
    "source_required": "нужен источник",
    "insufficient_data": "недостаточно данных",
}

_COLUMNS = ["key", "Группа", "Метрика", "Значение", "Единица", "Интерпретация", "Статус", "Тип метрики"]


def _metric_type(scope: str) -> str:
    if scope == "chapter":
        return "Основная"
    if scope == "extended":
        return "Дополнительная"
    if scope == "technical":
        return "Качество данных"
    return "Метрика"


def _status_for(metrics: LineageMetrics, key: str, value) -> str:
    if value is None:
        return "insufficient_data"
    return "available"


def _row(metrics: LineageMetrics, key: str, value, unit: str = "") -> dict:
    definition = get_metric_definition(key)
    status = _status_for(metrics, key, value)
    return {"key": key, "Группа": definition.group, "Метрика": definition.title, "Значение": value, "Единица": unit, "Интерпретация": definition.interpretation, "Статус": METRIC_STATUS_LABELS[status], "Тип метрики": _metric_type(definition.scope)}


def _metric_value_row(item: MetricValue) -> dict:
    definition = get_metric_definition(item.key)
    return {"key": item.key, "Группа": definition.group, "Метрика": definition.title, "Значение": item.value, "Единица": item.unit, "Интерпретация": definition.interpretation, "Статус": METRIC_STATUS_LABELS[item.status], "Тип метрики": _metric_type(definition.scope)}


def build_lineage_metrics_summary_df(metrics: LineageMetrics, *, include_extended: bool = True, include_technical: bool = False) -> pd.DataFrame:
    rows = [
        _row(metrics, "direct_students", metrics.direct_students),
        _row(metrics, "continuing_students", metrics.continuing_students),
        _row(metrics, "continuing_rate_percent", metrics.continuing_rate_percent, "%"),
        _row(metrics, "descendants", metrics.descendants),
        _row(metrics, "descendant_generations", metrics.descendant_generations),
        _row(metrics, "levels_including_root", metrics.levels_including_root),
        _row(metrics, "max_width", metrics.max_width),
        _row(metrics, "indirect_descendants_per_direct_student", metrics.indirect_descendants_per_direct_student, "потомков"),
        _row(metrics, "second_generation_descendants_per_direct_student", metrics.second_generation_descendants_per_direct_student, "потомков"),
        _row(metrics, "academic_proliferation", metrics.mean_new_descendants_per_year, "потомков в год"),
    ]
    if include_extended:
        rows.extend(_metric_value_row(v) for v in metrics.extended_values)
    if include_technical:
        rows.extend(_metric_value_row(v) for v in metrics.technical_values)
    return pd.DataFrame(rows, columns=_COLUMNS)


def build_generation_counts_df(metrics: LineageMetrics) -> pd.DataFrame:
    total = max(metrics.descendants, 1)
    rows = []
    for item in metrics.generation_counts:
        if item.generation == 0:
            interp = "Корень"
            share = None
        elif item.generation == 1:
            interp = "Прямые ученики"
            share = item.members / total * 100
        else:
            interp = f"Потомки {item.generation}-го поколения"
            share = item.members / total * 100
        rows.append({"Поколение": item.generation, "Участников": item.members, "Доля всех потомков, %": share, "Интерпретация": interp})
    return pd.DataFrame(rows, columns=["Поколение", "Участников", "Доля всех потомков, %", "Интерпретация"])


def build_proliferation_df(metrics: LineageMetrics) -> pd.DataFrame:
    return pd.DataFrame([{"Год": p.year, "Новых потомков": p.new_descendants, "Накоплено": p.cumulative_descendants} for p in metrics.proliferation_points], columns=["Год", "Новых потомков", "Накоплено"])


def build_first_level_branches_df(metrics: LineageMetrics) -> pd.DataFrame:
    values = [v for v in metrics.extended_values if v.key in {"branch_balance", "largest_branch_share_percent", "structural_h_index"}]
    return pd.DataFrame([{"Метрика": get_metric_definition(v.key).title, "Значение": v.value, "Единица": v.unit} for v in values], columns=["Метрика", "Значение", "Единица"])
