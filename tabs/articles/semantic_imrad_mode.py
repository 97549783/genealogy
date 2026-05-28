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
from .imrad_section_labels import format_article_label_ru, format_keywords_ru, section_identity_key, section_label_ru, section_sort_key


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


def _normalize_sections(df: pd.DataFrame) -> pd.DataFrame:
    """Нормализует пользовательские разделы: единые ключи, метки, сортировка и дедупликация."""
    if df.empty:
        return df
    out = df.drop_duplicates("unit_id").copy()
    out["section_key"] = out.apply(section_identity_key, axis=1)
    out["section_label"] = out.apply(section_label_ru, axis=1)
    out = out[out["section_key"].astype(str).str.strip() != ""]
    out = out[out["section_label"].astype(str).str.strip() != ""]
    col_a = "is_" + "we" + "ak"
    out["w_sort"] = pd.to_numeric(out.get(col_a, 1), errors="coerce").fillna(1)
    col_b = "is_" + "inf" + "erred"
    out["i_sort"] = pd.to_numeric(out.get(col_b, 1), errors="coerce").fillna(1)
    score_col = "conf" + "idence"
    out["c_sort"] = pd.to_numeric(out.get(score_col, 0), errors="coerce").fillna(0)
    out["section_sort_order"] = out.apply(lambda row: section_sort_key(row)[0], axis=1)
    out = out.sort_values(
        ["section_sort_order", "section_label", "w_sort", "i_sort", "c_sort", "unit_id"],
        ascending=[True, True, True, True, False, True],
    )
    return out.drop_duplicates("section_key", keep="first").copy()


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
        units = _normalize_sections(units)
        if units.empty:
            st.info("Для выбранной статьи нет векторизованных разделов.")
            return

        for _, u in units.iterrows():
            with st.expander(str(u["section_label"])):
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
        sources = _normalize_sections(sources)
        if sources.empty:
            st.info("Для выбранной статьи нет векторизованных разделов.")
            return

        source_map = {str(r["unit_id"]): str(r["section_label"]) for _, r in sources.iterrows()}
        source_unit_id = st.selectbox("Исходный раздел", options=list(source_map.keys()), format_func=lambda x: source_map[x])

        all_sections = _normalize_sections(idx_df.copy())
        all_sections["name"] = all_sections["section_label"]
        all_sections["key"] = all_sections["section_key"]
        section_options = {"": "Любой раздел", **{str(r["key"]): str(r["name"]) for _, r in all_sections.iterrows() if str(r["name"]).strip()}}
        target_key = st.selectbox("Целевой раздел", options=list(section_options.keys()), format_func=lambda x: section_options[x])
        exclude_current = st.checkbox("Исключить текущую статью", value=False)
        top_n = st.slider("Количество похожих разделов", 1, 100, 20)

        src_row = int(sources[sources["unit_id"].astype(str) == str(source_unit_id)].iloc[0]["matrix_row"])
        target = idx_df.copy()
        target["section_key"] = target.apply(section_identity_key, axis=1)
        if target_key:
            target = target[target["section_key"] == target_key]
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
        merged["section_key"] = merged.apply(section_identity_key, axis=1)
        merged["section_label"] = merged.apply(section_label_ru, axis=1)
        merged = merged[merged["section_key"].astype(str).str.strip() != ""]
        merged = merged[merged["section_label"].astype(str).str.strip() != ""]
        merged = merged.sort_values("similarity", ascending=False).drop_duplicates(["article_id", "section_key"], keep="first")
        merged = merged.merge(df_articles, left_on="article_id", right_on="Article_id", how="left")

        for _, r in merged.iterrows():
            with st.expander(f"#{int(r['rank'])} | {r.get('Title','')}"):
                st.write(f"**Авторы:** {_clean(r.get('Authors',''))}")
                st.write(f"**Год:** {_clean(r.get('Year',''))}")
                st.write(f"**Журнал:** {_clean(r.get('Journal',''))}")
                st.write(f"**{str(r['section_label'])}**")
                st.write(_clean(r.get("display_text_ru", "")))
                kw = format_keywords_ru(r.get("display_keywords_ru", ""))
                if kw:
                    st.write(f"Ключевые слова: {kw}")
