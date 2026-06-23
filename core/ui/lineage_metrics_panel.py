from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from core.lineage.metric_definitions import get_metric_definitions, get_metric_source_caption, get_used_metric_sources
from core.lineage.metric_tables import METRIC_STATUS_LABELS, build_generation_counts_df, build_lineage_metrics_summary_df, build_proliferation_df
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
    with cols[0]:
        _card("Прямые ученики", metrics.direct_students, "A-score / плодовитость (fecundity)")
    with cols[1]:
        _card("Ученики-продолжатели", metrics.continuing_students, "Фертильность: прямые ученики, ставшие руководителями")
    with cols[2]:
        _card("Доля продолжателей", metrics.continuing_rate_percent, "Фертильность / прямые ученики", "%")
    with cols[3]:
        _card("Все потомки", metrics.descendants, "T-score / descendants")

    cols = st.columns(4)
    with cols[0]:
        _card("Поколений потомков", metrics.descendant_generations, "G-score / generations")
    with cols[1]:
        _card("Максимальная ширина", metrics.max_width, "W-score: максимум участников в одном поколении")
    with cols[2]:
        _card("Прямые потомки у ученика", metrics.second_generation_descendants_per_direct_student, "Среднее число прямых потомков у ученика")
    with cols[3]:
        _card("Потомки у ученика", metrics.indirect_descendants_per_direct_student, "Среднее число всех потомков у ученика")


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
    st.write("Эти показатели помогают дополнительно интерпретировать ветвление, форму дерева, динамику и состав научной линии.")
    df = build_lineage_metrics_summary_df(metrics, include_extended=True, include_technical=False)
    extra = df[df["Тип метрики"] == "Дополнительная"].drop(columns=["key"], errors="ignore")
    st.dataframe(extra, hide_index=True, use_container_width=True)


def _render_quality(metrics: LineageMetrics) -> None:
    from core.lineage.metric_definitions import get_metric_definition
    rows = [{"Показатель": get_metric_definition(v.key).title, "Значение": v.value, "Единица": v.unit, "Статус": METRIC_STATUS_LABELS[v.status]} for v in metrics.technical_values]
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    for warning in metrics.warnings:
        st.warning(warning)


def _export_buttons(metrics: LineageMetrics, key_prefix: str) -> None:
    df = build_lineage_metrics_summary_df(metrics, include_extended=True, include_technical=False)
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
        tabs = st.tabs(["Обзор", "По поколениям", "Динамика", "Дополнительно"] if include_extended else ["Обзор", "По поколениям", "Динамика"])
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
        if show_export_buttons:
            _export_buttons(metrics, key_prefix)


def show_lineage_metrics_help_dialog(*, include_extended: bool = True) -> None:
    @st.dialog("Количественные метрики научного руководства", width="large")
    def _show() -> None:
        with st.container(height=650):
            st.markdown("### Как приложение учитывает несколько руководителей")
            st.markdown("- Каждый потомок учитывается один раз.\n- Если от выбранного руководителя до одного потомка есть несколько путей, поколение определяется по кратчайшему пути.\n- Значения относятся только к текущему отфильтрованному и отображаемому графу.\n\nЭто позволяет корректно считать показатели для случаев совместного научного руководства.")
            st.markdown("### Используемые обозначения")
            st.markdown("- `r` — выбранный руководитель;\n- `V_r` — множество участников текущего отображаемого графа, достижимых из `r`;\n- `E_r` — множество связей научного руководства в текущем отображаемом графе;\n- `Ch(v)` — множество прямых учеников участника `v`;\n- `Desc(r)` — множество всех потомков `r` без самого `r`;\n- `g(v)` — поколение участника `v`, то есть кратчайшее расстояние от `r` до `v`;\n- `W_k` — число участников `k`-го поколения;\n- `W_1` — число прямых учеников;\n- `W_2` — число потомков второго поколения;\n- `y(v)` — год защиты участника `v`;\n- `n_t` — число новых потомков в году `t`;\n- `P(t)` — накопленное число потомков к году `t`.")
            st.markdown("### Основные термины")
            st.write(
                "A-score и плодовитость показывают число прямых учеников руководителя. "
                "Фертильность показывает число прямых учеников, которые сами стали научными руководителями. "
                "G-score показывает число поколений потомков. W-score показывает максимум участников в одном поколении."
            )
            st.markdown("### Список источников, в которых описаны реализованные метрики")
            for source in get_used_metric_sources(include_extended=include_extended, include_technical=False):
                suffix = f" DOI/URL: {source.doi_or_url}" if source.doi_or_url else ""
                st.caption(f"{source.full_citation}{suffix}")
            for definition in get_metric_definitions(include_extended=include_extended, include_technical=False):
                st.markdown(f"#### {definition.title}")
                if definition.aliases:
                    st.write("Синонимы: " + ", ".join(definition.aliases))
                st.write(definition.short_description)
                st.markdown(definition.formula_markdown)
                st.write(definition.interpretation)
                for caveat in definition.caveats:
                    st.warning(caveat)
                st.caption(get_metric_source_caption(definition.key))
    _show()
