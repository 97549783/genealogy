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


def build_excel_report(
    metrics_df: pd.DataFrame,
    generations_df: pd.DataFrame,
    yearly_df: pd.DataFrame,
    city_df: pd.DataFrame,
    institutional: Dict[str, pd.DataFrame],
    opponents_df: pd.DataFrame,
    continuity_df: pd.DataFrame,
    thematic_groups: Optional[Dict[str, pd.DataFrame]] = None,
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

    return buf.getvalue()
