from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from core.lineage.metric_definitions import get_metric_definitions
from core.lineage.metric_tables import build_generation_counts_df, build_lineage_metrics_summary_df, build_proliferation_df
from core.lineage.metrics import LineageMetrics


def _fmt(value, kind: str = "") -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    if kind == "%":
        return f"{float(value):.1f}%"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _card(title: str, value, subtitle: str, kind: str = "") -> None:
    st.metric(title, _fmt(value, kind), help=subtitle)
    st.caption(subtitle)


def _render_overview(metrics: LineageMetrics) -> None:
    cols = st.columns(4)
    with cols[0]: _card("Прямые ученики", metrics.direct_students, "A-score / плодовитость (fecundity)")
    with cols[1]: _card("Ученики-продолжатели", metrics.continuing_students, "C-score / фертильность (fertility)")
    with cols[2]: _card("Доля продолжателей", metrics.continuing_rate_percent, "C-score / A-score", "%")
    with cols[3]: _card("Все потомки", metrics.descendants, "Уникальные потомки во всех поколениях")
    cols = st.columns(4)
    with cols[0]: _card("Поколений потомков", metrics.descendant_generations, "Максимальное расстояние от корня")
    with cols[1]: _card("Уровней с корнем", metrics.levels_including_root, "Корень включён как уровень 0")
    with cols[2]: _card("Максимальная ширина", metrics.max_width, "Максимум участников в одном поколении")
    with cols[3]: _card("G-score", metrics.g_score, "Формула уточняется по первоисточнику")


def _render_dynamics(metrics: LineageMetrics) -> None:
    df = build_proliferation_df(metrics)
    if df.empty:
        st.info("Для временного анализа нет валидных годов защиты. Структурные метрики рассчитаны полностью.")
        return
    st.line_chart(df, x="Год", y="Накоплено")
    st.dataframe(df, hide_index=True, use_container_width=True)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("С валидным годом", metrics.dated_descendants)
    c2.metric("Без валидного года", metrics.undated_descendants)
    c3.metric("Первый год", _fmt(metrics.first_observed_year))
    c4.metric("Последний год", _fmt(metrics.last_observed_year))
    c5.metric("Среднее за год", _fmt(metrics.mean_new_descendants_per_year))


def _render_values(metrics: LineageMetrics) -> None:
    st.write("Эти показатели не входят в основной набор метрик главы, но помогают интерпретировать структуру дерева и качество данных.")
    df = build_lineage_metrics_summary_df(metrics, include_extended=True)
    extra = df[df["Входит в диссертационный набор"] == False].drop(columns=["key"], errors="ignore")
    st.dataframe(extra, hide_index=True, use_container_width=True)


def _render_quality(metrics: LineageMetrics) -> None:
    from core.lineage.metric_definitions import get_metric_definition
    status_names = {"available": "доступно", "not_applicable": "не применимо", "source_required": "нужен первоисточник", "insufficient_data": "недостаточно данных"}
    rows = [{"Показатель": get_metric_definition(v.key).title, "Значение": v.value, "Единица": v.unit, "Статус": status_names[v.status]} for v in metrics.technical_values]
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    for warning in metrics.warnings:
        st.warning(warning)


def _export_buttons(metrics: LineageMetrics, key_prefix: str) -> None:
    df = build_lineage_metrics_summary_df(metrics, include_extended=True)
    st.download_button("Скачать метрики CSV", df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"), file_name=f"{key_prefix}.lineage_metrics.csv", mime="text/csv", key=f"{key_prefix}_metrics_csv")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Метрики")
        build_generation_counts_df(metrics).to_excel(writer, index=False, sheet_name="Поколения")
        build_proliferation_df(metrics).to_excel(writer, index=False, sheet_name="Динамика")
    st.download_button("Скачать метрики XLSX", buf.getvalue(), file_name=f"{key_prefix}.lineage_metrics.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"{key_prefix}_metrics_xlsx")


def render_lineage_metrics_panel(metrics: LineageMetrics, *, key_prefix: str, context_label: str | None = None, expanded: bool = False, include_extended: bool = True, include_help_button: bool = True, show_export_buttons: bool = False) -> None:
    with st.expander("Количественные метрики научного руководства", expanded=expanded):
        if context_label:
            st.write(f"Метрики рассчитаны для показанного выше дерева: {context_label}")
        st.caption("Метрики рассчитаны для текущего отображаемого графа. Корень — поколение 0; вершины с несколькими руководителями учитываются один раз.")
        st.caption("Корень — поколение 0; при нескольких путях поколение определяется по кратчайшему пути.")
        for warning in metrics.warnings:
            st.warning(warning)
        if include_help_button and st.button("ℹ️ Как рассчитываются метрики?", key=f"{key_prefix}_metrics_help"):
            show_lineage_metrics_help_dialog(include_extended=include_extended)
        tabs = st.tabs(["Обзор", "По поколениям", "Динамика", "Дополнительно", "Качество данных"] if include_extended else ["Обзор", "По поколениям", "Динамика"])
        with tabs[0]: _render_overview(metrics)
        with tabs[1]:
            gen_df = build_generation_counts_df(metrics)
            if gen_df.empty:
                st.info("Метрики поколений недоступны.")
            else:
                st.dataframe(gen_df, hide_index=True, use_container_width=True)
                st.bar_chart(gen_df, x="Поколение", y="Участников")
        with tabs[2]: _render_dynamics(metrics)
        if include_extended:
            with tabs[3]: _render_values(metrics)
            with tabs[4]: _render_quality(metrics)
        if show_export_buttons:
            _export_buttons(metrics, key_prefix)


def show_lineage_metrics_help_dialog(*, include_extended: bool = True) -> None:
    @st.dialog("Количественные метрики научного руководства", width="large")
    def _show() -> None:
        st.markdown("### Как приложение работает с несколькими руководителями")
        st.markdown("- Показанная структура может быть направленным ациклическим графом, а не строгим деревом.\n- Каждый потомок учитывается один раз.\n- Если от корня до вершины есть несколько путей, поколение определяется по кратчайшему пути.\n- Число рёбер может превышать число потомков.\n- Значения относятся только к текущему отфильтрованному и отображаемому графу.")
        st.markdown("### Эквивалентные термины")
        st.write("В реализованной формализации A-score равен плодовитости, а C-score равен фертильности, поэтому они не дублируются отдельными карточками.")
        for definition in get_metric_definitions(include_extended=include_extended, include_technical=include_extended):
            st.markdown(f"#### {definition.title}")
            if definition.aliases:
                st.write("Синонимы: " + ", ".join(definition.aliases))
            st.write(definition.short_description)
            st.markdown(definition.formula_markdown)
            st.write(definition.interpretation)
            for caveat in definition.caveats:
                st.warning(caveat)
            status_names = {"verified": "проверено", "source_required": "нужен первоисточник", "standard": "стандартная формализация", "derived": "производная метрика"}
            st.caption("; ".join(f"{s.short_citation}: {status_names[s.status]}" for s in definition.sources))
    _show()
