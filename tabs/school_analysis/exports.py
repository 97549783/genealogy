"""Экспортные функции вкладки «Анализ научной школы»."""

from __future__ import annotations

import io
from typing import Dict, Optional

import pandas as pd


def _safe_sheet_name(prefix: str, label: str) -> str:
    invalid = set('[]:*?/\\')
    cleaned = "".join("_" if ch in invalid else ch for ch in label).strip()
    name = f"{prefix} {cleaned}" if cleaned else prefix
    return name[:31]


def _localized_semantic_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Удаляет технические поля и приводит покрытие к процентам."""
    result = frame.drop(columns=["Code", "eligible", "invalid_vector_row_count"], errors="ignore").rename(columns={
        "candidate_name": "Автор", "title": "Название", "year": "Год",
        "coverage": "Покрытие, %", "available_section_count": "Доступно разделов",
        "selected_section_count": "Выбрано разделов",
    }).copy()
    if "Покрытие, %" in result:
        result["Покрытие, %"] = pd.to_numeric(result["Покрытие, %"], errors="coerce") * 100.0
    return result


def build_excel_report(
    metrics_df: pd.DataFrame,
    generations_df: pd.DataFrame,
    yearly_df: pd.DataFrame,
    city_df: pd.DataFrame,
    institutional: Dict[str, pd.DataFrame],
    opponents_df: pd.DataFrame,
    continuity_df: pd.DataFrame,
    thematic_groups: Optional[Dict[str, pd.DataFrame]] = None,
    semantic_summary: pd.DataFrame | None = None,
    semantic_dissertations: pd.DataFrame | None = None,
    semantic_generations: pd.DataFrame | None = None,
    semantic_generation_dissertations: pd.DataFrame | None = None,
    semantic_branches: pd.DataFrame | None = None,
    semantic_branch_dissertations: pd.DataFrame | None = None,
    semantic_branch_similarity: pd.DataFrame | None = None,
    semantic_branch_silhouette: pd.DataFrame | None = None,
    semantic_excluded: pd.DataFrame | None = None,
    semantic_ambiguous: pd.DataFrame | None = None,
    semantic_diagnostics: pd.DataFrame | None = None,
) -> bytes:
    """
    Формирует Excel-файл со всеми листами анализа.
    Возвращает bytes для передачи в st.download_button.
    """
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        metrics_df.to_excel(writer, index=False, sheet_name="Метрики")

        if not generations_df.empty:
            generations_df.to_excel(writer, index=False, sheet_name="Поколения")

        if not yearly_df.empty:
            yearly_df.to_excel(writer, index=False, sheet_name="По годам")

        if not city_df.empty:
            city_df.to_excel(writer, index=False, sheet_name="По городам")

        if not institutional.get("institution_prepared", pd.DataFrame()).empty:
            institutional["institution_prepared"].to_excel(
                writer, index=False, sheet_name="Орг выполнения"
            )
        if not institutional.get("defense_location", pd.DataFrame()).empty:
            institutional["defense_location"].to_excel(
                writer, index=False, sheet_name="Место защиты"
            )
        if not institutional.get("leading_organization", pd.DataFrame()).empty:
            institutional["leading_organization"].to_excel(
                writer, index=False, sheet_name="Ведущая орг"
            )
        if not institutional.get("specialties", pd.DataFrame()).empty:
            institutional["specialties"].to_excel(
                writer, index=False, sheet_name="Специальности"
            )

        if not opponents_df.empty:
            opponents_df.to_excel(writer, index=False, sheet_name="Оппоненты")

        for i, (group_label, group_df) in enumerate((thematic_groups or {}).items(), start=1):
            if group_df.empty:
                continue
            sheet_df = pd.concat(
                [
                    pd.DataFrame([{"Название": group_label, "Средний балл": ""}]),
                    group_df,
                ],
                ignore_index=True,
            )
            sheet_df.to_excel(
                writer,
                index=False,
                sheet_name=_safe_sheet_name(f"Тема {i}", group_label),
            )

        if not continuity_df.empty:
            continuity_df.to_excel(
                writer, index=False, sheet_name="Ученики-руководители"
            )

        semantic_sheets = (
            (semantic_summary, "Семантическая сводка"),
            (semantic_dissertations, "Семантика диссертаций"),
            (semantic_generations, "Семантика поколений"),
            (semantic_generation_dissertations, "Диссертации поколений"),
            (semantic_branches, "Семантика ветвей"),
            (semantic_branch_dissertations, "Диссертации ветвей"),
            (semantic_branch_similarity, "Сходство ветвей"),
            (semantic_branch_silhouette, "Силуэт ветвей"),
            (semantic_ambiguous, "Неоднозначные диссертации"),
            (semantic_excluded, "Исключённые диссертации"),
            (semantic_diagnostics, "Диагностика семантики"),
        )
        for semantic_df, sheet_name in semantic_sheets:
            if semantic_df is not None and not semantic_df.empty:
                _localized_semantic_frame(semantic_df).to_excel(writer, index=False, sheet_name=sheet_name[:31])

    return buf.getvalue()
