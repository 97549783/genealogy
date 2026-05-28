"""Режим Streamlit для семантического поиска по IMRAD-зонам."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.db.imrad import (
    load_article_imrad_units,
    load_imrad_diagnostics,
    load_imrad_embedding_options,
    load_imrad_quotes,
    load_imrad_text_index,
)
from .imrad_search import filter_imrad_index, load_embedding_matrix, resolve_matrix_path, search_similar_units


def _label_article(row: pd.Series) -> str:
    return f"[{row.get('Article_id','')}] {row.get('Title','')} — {row.get('Authors','')} — {row.get('Year','')}"


def render_semantic_imrad_search_mode(df_articles: pd.DataFrame) -> None:
    st.markdown("### Семантический поиск по зонам")
    diag = load_imrad_diagnostics()
    with st.expander("Диагностика IMRAD-данных", expanded=False):
        counts = diag.get("счётчики", {})
        st.write(f"Количество строк article_imrad_units: {counts.get('article_imrad_units')}")
        st.write(f"Количество строк article_imrad_unit_texts: {counts.get('article_imrad_unit_texts')}")
        st.write(f"Количество строк article_imrad_embeddings: {counts.get('article_imrad_embeddings')}")
        options_df = load_imrad_embedding_options()
        if options_df.empty:
            st.warning("Таблицы эмбеддингов IMRAD недоступны или пусты.")
        else:
            st.dataframe(options_df, use_container_width=True)
            for _, row in options_df.iterrows():
                p = str(row.get("file_path", "") or "")
                rp = resolve_matrix_path(p) if p else None
                st.write(f"Матрица: {p} | существует: {bool(rp and rp.exists())} | форма: {row.get('matrix_shape')}")

    tab_units, tab_similar, tab_query = st.tabs(["Зоны выбранной статьи", "Поиск похожих зон", "Поиск по запросам"])

    with tab_units:
        if df_articles.empty:
            st.warning("Нет статей для отображения.")
        else:
            labels = {str(r.Article_id): _label_article(r) for _, r in df_articles.iterrows()}
            article_id = st.selectbox("Выберите статью", options=list(labels.keys()), format_func=lambda x: labels[x])
            row = df_articles[df_articles["Article_id"].astype(str) == str(article_id)].iloc[0]
            for key in ["Название", "Авторы", "Год", "Журнал", "DOI", "Сайт журнала", "PDF", "Аннотация", "Ключевые слова"]:
                colmap = {"Название": "Title", "Авторы": "Authors", "Год": "Year", "Журнал": "Journal", "DOI": "DOI", "Сайт журнала": "Article_URL", "PDF": "Article_PDF", "Аннотация": "Abstract", "Ключевые слова": "Keywords"}
                st.write(f"**{key}:** {row.get(colmap[key], '')}")
            units = load_article_imrad_units(str(article_id), language="en", text_role="compact_en")
            if units.empty:
                st.info("Для выбранной статьи IMRAD-данные не найдены.")
            else:
                quotes = load_imrad_quotes(units["unit_id"].astype(str).unique().tolist())
                for (block, subblock), group in units.groupby(["imrad_block", "imrad_subblock"], dropna=False):
                    with st.expander(f"Блок: {block} / Подблок: {subblock}"):
                        for _, u in group.iterrows():
                            st.markdown(f"**Unit:** {u.get('unit_id','')} | confidence={u.get('confidence','')} | weak={u.get('is_weak','')} | inferred={u.get('is_inferred','')}")
                            st.write(u.get("text", ""))
                            st.write(f"Ключевые слова: {u.get('keywords_json','')}")
                            st.write(f"Утверждения: {u.get('key_assertions_json','')}")
                            st.write(f"Извлечения: {u.get('extracted_json','')}")
                            st.write(f"Источник зон: {u.get('source_zone_ids_json','')}")
                            st.write(f"Файл источника: {u.get('source_file','')}")
                            q = quotes[quotes["unit_id"].astype(str) == str(u.get("unit_id", ""))] if not quotes.empty else pd.DataFrame()
                            if not q.empty:
                                st.write("Цитаты:")
                                st.dataframe(q[["quote_text", "section_guess", "page_guess", "importance"]], use_container_width=True)

    with tab_similar:
        options_df = load_imrad_embedding_options()
        if options_df.empty:
            st.warning("Нет доступных опций эмбеддингов для поиска похожих зон.")
            return
        options_df = options_df.copy().reset_index(drop=True)
        opt_idx = st.selectbox("Слой эмбеддингов", options=options_df.index.tolist(), format_func=lambda i: f"{options_df.loc[i,'language']} / {options_df.loc[i,'text_role']} / {options_df.loc[i,'model_name']}")
        selected_opt = options_df.loc[opt_idx]
        index_df = load_imrad_text_index(selected_opt["language"], selected_opt["text_role"], str(selected_opt["embedding_model_id"]), str(selected_opt["matrix_file_id"]))
        if index_df.empty:
            st.warning("Индекс IMRAD для выбранной опции пуст.")
        else:
            matrix_path = selected_opt.get("file_path")
            if not matrix_path:
                st.error("У выбранной опции отсутствует путь к файлу матрицы.")
                return
            try:
                matrix = load_embedding_matrix(resolve_matrix_path(str(matrix_path)))
            except FileNotFoundError as exc:
                st.error(f"{exc}")
                return
            labels = {str(r.Article_id): _label_article(r) for _, r in df_articles.iterrows()}
            source_article_id = st.selectbox("Исходная статья", options=list(labels.keys()), format_func=lambda x: labels[x], key="imrad_source_article")
            source_candidates = index_df[index_df["article_id"].astype(str) == str(source_article_id)]
            if source_candidates.empty:
                st.warning("Для выбранной статьи нет IMRAD-зон в текущем эмбеддинг-слое.")
                return
            unit_id = st.selectbox("Исходная зона", options=source_candidates["unit_id"].astype(str).tolist())
            source_row = int(source_candidates[source_candidates["unit_id"].astype(str) == str(unit_id)].iloc[0]["matrix_row"])
            exclude_current = st.checkbox("Исключить текущую статью", value=False)
            include_weak = st.checkbox("Включать слабые зоны", value=True)
            include_inferred = st.checkbox("Включать выведенные зоны", value=True)
            min_conf = st.number_input("Минимальная уверенность (0-1)", min_value=0.0, max_value=1.0, value=0.0, step=0.05)
            top_n = st.slider("Top-N", min_value=1, max_value=100, value=20)
            target = filter_imrad_index(index_df, include_weak=include_weak, include_inferred=include_inferred, min_confidence=min_conf, exclude_article_id=str(source_article_id) if exclude_current else None)
            target = target[target["unit_id"].astype(str) != str(unit_id)]
            if target.empty:
                st.warning("После фильтрации не осталось целевых зон.")
                return
            try:
                result = search_similar_units(source_row, matrix, index_df, target, top_n)
            except IndexError as exc:
                st.error(f"Ошибка индексов матрицы: {exc}")
                return
            merged = result.merge(df_articles, left_on="article_id", right_on="Article_id", how="left")
            st.dataframe(merged[["rank", "similarity", "Title", "Authors", "Year", "Journal", "unit_level", "imrad_block", "imrad_subblock", "rhetorical_zone_type", "text", "keywords_json", "confidence", "is_weak", "is_inferred", "Article_URL", "Article_PDF"]], use_container_width=True)

    with tab_query:
        st.warning("Поиск по запросам недоступен: в среде не загружен runtime-энкодер запросов.")
