#проверочная вкладка
"""Графики для режимов анализа статей."""

from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd


def create_yearly_articles_chart(yearly_df: pd.DataFrame) -> plt.Figure:
    """Создаёт столбчатый график количества статей по годам."""
    fig, ax = plt.subplots(figsize=(10, 4))
    if yearly_df is not None and not yearly_df.empty:
        ax.bar(yearly_df["Год"].astype(str), yearly_df["Количество статей"])
    ax.set_xlabel("Год")
    ax.set_ylabel("Количество статей")
    ax.set_title("Динамика публикаций по годам")
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    return fig


def create_block_scores_chart(block_scores_df: pd.DataFrame) -> plt.Figure:
    """Создаёт горизонтальный график средних баллов тематических блоков."""
    fig, ax = plt.subplots(figsize=(10, max(4, 0.35 * len(block_scores_df) if block_scores_df is not None else 4)))
    if block_scores_df is not None and not block_scores_df.empty:
        data = block_scores_df.sort_values("Средний балл")
        ax.barh(data["Блок"], data["Средний балл"])
    ax.set_xlabel("Средний балл")
    ax.set_title("Тематический профиль школы")
    fig.tight_layout()
    return fig
