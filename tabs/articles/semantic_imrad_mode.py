"""Режим Streamlit для анализа по разделам статьи."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.db.imrad import (
    load_article_imrad_units,
    load_fully_vectorized_article_ids,
    load_imrad_display_texts_ru,
    load_imrad_embedding_options,
    load_imrad_text_index,
    select_default_imrad_embedding_option,
)
from .imrad_search import load_embedding_matrix, resolve_matrix_path, search_similar_units
from .imrad_section_labels import IMRAD_BLOCK_ORDER, format_article_label_ru, format_keywords_ru, section_filter_key, section_label_ru


def _select_article(df_articles: pd.DataFrame, key_prefix: str) -> str | None:
    labels = {str(r.Article_id): format_article_label_ru(r) for _, r in df_articles.iterrows()}
    query = st.text_input("Поиск статьи", key=f"{key_prefix}_article_query")
    ids = list(labels.keys())
    if query.strip():
        q = query.casefold()
        ids = [aid for aid in ids if q in labels[aid].casefold()]
    if not ids:
        st.info("Статьи по введённому фрагменту не найдены.")
        return None
    return st.selectbox("Выберите статью", options=ids, format_func=lambda x: labels[x], key=f"{key_prefix}_article_id")


def _clean(v: object) -> str:
    if v is None or pd.isna(v) or str(v).strip().lower() == "nan":
        return ""
    return str(v).strip()


def render_semantic_imrad_search_mode(df_articles: pd.DataFrame) -> None:
    st.markdown("### Анализ по разделам статьи")
    options_df = load_imrad_embedding_options().reset_index(drop=True)
    opt = select_default_imrad_embedding_option(options_df)
    if opt is None:
        st.warning("Нет доступных данных для поиска похожих разделов.")
        return

    fully_ids = load_fully_vectorized_article_ids(str(opt["language"]), str(opt["text_role"]), str(opt["embedding_model_id"]), str(opt["matrix_file_id"]))
    df_articles = df_articles[df_articles["Article_id"].astype(str).isin(fully_ids)].copy()
    if df_articles.empty:
        st.warning("Для выбранных журналов нет полностью векторизованных статей.")
        return

    tab_units, tab_similar = st.tabs(["Разделы статьи", "Поиск похожих разделов"])
    with tab_units:
        article_id = _select_article(df_articles, "imrad_units")
        if not article_id:
            return
        row = df_articles[df_articles["Article_id"].astype(str) == str(article_id)].iloc[0]
        for label, col in [("Название", "Title"), ("Авторы", "Authors"), ("Год", "Year"), ("Журнал", "Journal"), ("Номер", "Issue"), ("DOI", "DOI"), ("Аннотация", "Abstract"), ("Ключевые слова", "Keywords")]:
            value = _clean(row.get(col, ""))
            if value:
                st.write(f"**{label}:** {value}")

        units = load_article_imrad_units(str(article_id))
        display = load_imrad_display_texts_ru(units["unit_id"].astype(str).tolist()) if not units.empty else pd.DataFrame()
        units = units.merge(display, on="unit_id", how="left") if not units.empty else units
        units = units[units["display_text_ru"].fillna("").astype(str).str.strip() != ""]
        if units.empty:
            st.info("Для выбранной статьи нет векторизованных разделов.")
            return

        units["block_order"] = units["imrad_block"].astype(str).map({v: i for i, v in enumerate(IMRAD_BLOCK_ORDER)}).fillna(999)
        units["level_order"] = units["unit_level"].astype(str).map({"article": 0, "imrad_block": 1, "imrad_subblock": 2}).fillna(9)
        units = units.sort_values(["block_order", "level_order", "imrad_subblock", "unit_id"])
        for _, u in units.iterrows():
            with st.expander(section_label_ru(u)):
                st.write(_clean(u.get("display_text_ru", "")))
                kw = format_keywords_ru(u.get("display_keywords_ru", ""))
                if kw:
                    st.write(f"Ключевые слова: {kw}")

    with tab_similar:
        article_id = _select_article(df_articles, "imrad_similar")
        if not article_id:
            return
        idx_df = load_imrad_text_index(str(opt["language"]), str(opt["text_role"]), str(opt["embedding_model_id"]), str(opt["matrix_file_id"]))
        if idx_df.empty:
            st.warning("Нет доступных данных для поиска похожих разделов.")
            return
        allowed_article_ids = set(df_articles["Article_id"].astype(str))
        idx_df = idx_df[idx_df["article_id"].astype(str).isin(allowed_article_ids)].copy()
        if idx_df.empty:
            st.warning("Нет доступных данных для поиска похожих разделов.")
            return
        matrix_file_path = str(opt.get("file_path") or "").strip()
        if not matrix_file_path:
            st.error("У выбранного слоя эмбеддингов отсутствует путь к файлу матрицы.")
            return
        try:
            matrix = load_embedding_matrix(resolve_matrix_path(matrix_file_path))
        except FileNotFoundError as exc:
            st.error(str(exc))
            return
        except (OSError, ValueError) as exc:
            st.error(f"Не удалось загрузить файл матрицы: {exc}")
            return
        except Exception as exc:
            st.error(f"Неожиданная ошибка при чтении матрицы: {exc}")
            return

        sources = idx_df[idx_df["article_id"].astype(str) == str(article_id)].copy()
        source_display = load_imrad_display_texts_ru(sources["unit_id"].astype(str).tolist())
        sources = sources.merge(source_display, on="unit_id", how="left")
        sources = sources[sources["display_text_ru"].fillna("").astype(str).str.strip() != ""]
        if sources.empty:
            st.info("Для выбранной статьи нет векторизованных разделов.")
            return

        source_map = {str(r["unit_id"]): section_label_ru(r) for _, r in sources.iterrows()}
        source_unit_id = st.selectbox("Исходный раздел", options=list(source_map.keys()), format_func=lambda x: source_map[x])

        all_sections = idx_df[["imrad_block", "imrad_subblock"]].drop_duplicates().copy()
        all_sections["name"] = all_sections.apply(section_label_ru, axis=1)
        all_sections["key"] = all_sections.apply(section_filter_key, axis=1)
        section_options = {"": "Любой раздел", **{str(r["key"]): str(r["name"]) for _, r in all_sections.iterrows() if str(r["name"]).strip()}}
        target_key = st.selectbox("Целевой раздел", options=list(section_options.keys()), format_func=lambda x: section_options[x])
        exclude_current = st.checkbox("Исключить текущую статью", value=False)
        top_n = st.slider("Количество похожих разделов", 1, 100, 20)

        src_row = int(sources[sources["unit_id"].astype(str) == str(source_unit_id)].iloc[0]["matrix_row"])
        target = idx_df.copy()
        if target_key:
            b, s = target_key.split("::", 1)
            target = target[(target["imrad_block"].fillna("").astype(str) == b) & (target["imrad_subblock"].fillna("").astype(str) == s)]
        if exclude_current:
            target = target[target["article_id"].astype(str) != str(article_id)]
        target = target[target["unit_id"].astype(str) != str(source_unit_id)]
        if target.empty:
            st.warning("После применения фильтров целевые разделы не найдены.")
            return
        try:
            result = search_similar_units(src_row, matrix, idx_df, target, top_n)
        except IndexError as exc:
            st.error(f"Ошибка индексов матрицы: {exc}")
            return
        ru = load_imrad_display_texts_ru(result["unit_id"].astype(str).tolist())
        merged = result.merge(ru, on="unit_id", how="left")
        merged = merged[merged["display_text_ru"].fillna("").astype(str).str.strip() != ""]
        merged = merged.merge(df_articles, left_on="article_id", right_on="Article_id", how="left")

        for _, r in merged.iterrows():
            with st.expander(f"#{int(r['rank'])} | {r.get('Title','')}"):
                st.write(f"**Авторы:** {_clean(r.get('Authors',''))}")
                st.write(f"**Год:** {_clean(r.get('Year',''))}")
                st.write(f"**Журнал:** {_clean(r.get('Journal',''))}")
                st.write(f"**{section_label_ru(r)}**")
                st.write(_clean(r.get("display_text_ru", "")))
                kw = format_keywords_ru(r.get("display_keywords_ru", ""))
                if kw:
                    st.write(f"Ключевые слова: {kw}")
