"""Режим Streamlit для анализа по разделам статьи."""

from __future__ import annotations

import re

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
from .imrad_query_search import (
    collect_non_empty_queries,
    encode_user_queries,
    get_query_encoder_device,
    is_query_encoder_enabled,
    search_sections_by_query_vector,
)
from .imrad_section_labels import format_article_label_ru, format_keywords_ru, section_identity_key, section_label_ru, section_sort_key



RUSSIAN_VOWELS = "аеёиоуыэюя"
MIN_STEM_LENGTH = 3


def normalize_article_search_text(value: object) -> str:
    """Нормализует текст для поиска статьи."""
    text = str(value or "").casefold().replace("ё", "е")
    text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def _is_cyrillic_token(token: str) -> bool:
    return bool(re.search(r"[а-я]", token))


def make_flexible_search_token(token: str) -> str:
    """Убирает мягкий знак и до двух конечных гласных для гибкого поиска."""
    stem = normalize_article_search_text(token)
    if not stem:
        return ""
    if not _is_cyrillic_token(stem):
        return stem
    if stem.endswith("ь") and len(stem) > MIN_STEM_LENGTH:
        stem = stem[:-1]
    removed = 0
    while len(stem) > MIN_STEM_LENGTH and removed < 2 and stem[-1] in RUSSIAN_VOWELS:
        stem = stem[:-1]
        removed += 1
    return stem


def article_label_matches_query(label: str, query: str) -> bool:
    """Проверяет, подходит ли метка статьи под пользовательский запрос."""
    normalized_label = normalize_article_search_text(label)
    normalized_query = normalize_article_search_text(query)
    if not normalized_query:
        return True
    if normalized_query in normalized_label:
        return True

    query_tokens = [make_flexible_search_token(t) for t in normalized_query.split() if t.strip()]
    label_tokens = [t for t in normalized_label.split() if t.strip()]
    if not query_tokens or not label_tokens:
        return False

    for q_token in query_tokens:
        if not q_token:
            continue
        if not any(token.startswith(q_token) for token in label_tokens):
            return False
    return True


def filter_articles_by_search_query(labels: dict[str, str], query: str) -> list[str]:
    """Возвращает идентификаторы статей, подходящих под запрос."""
    if not query.strip():
        return list(labels.keys())
    return [aid for aid, label in labels.items() if article_label_matches_query(label, query)]


def _display_text_for_result(row: pd.Series) -> str:
    """Возвращает пользовательский русский текст для карточки результата."""
    if str(row.get("section_key", "")) == "article":
        return _clean(row.get("Abstract", ""))
    return _clean(row.get("display_text_ru", ""))


def _display_keywords_for_result(row: pd.Series) -> str:
    """Возвращает пользовательские ключевые слова для карточки результата."""
    if str(row.get("section_key", "")) == "article":
        return format_keywords_ru(row.get("Keywords", ""))
    return format_keywords_ru(row.get("display_keywords_ru", ""))


def _reset_article_search(query_key: str) -> None:
    """Очищает поле поиска статьи."""
    st.session_state[query_key] = ""


def _select_article(df_articles: pd.DataFrame, key_prefix: str) -> str | None:
    labels = {str(r.Article_id): format_article_label_ru(r) for _, r in df_articles.iterrows()}
    query_key = f"{key_prefix}_article_query"
    query = st.text_input("Поиск статьи", key=query_key)
    if query.strip():
        st.button(
            "Сбросить поиск",
            key=f"{key_prefix}_reset_search",
            on_click=_reset_article_search,
            args=(query_key,),
        )
    ids = filter_articles_by_search_query(labels, st.session_state.get(query_key, ""))
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




def _normalize_sections_per_article(df: pd.DataFrame) -> pd.DataFrame:
    """Нормализует разделы для корпусного поиска: один раздел каждого типа на статью."""
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
        ["article_id", "section_sort_order", "section_label", "w_sort", "i_sort", "c_sort", "unit_id"],
        ascending=[True, True, True, True, True, False, True],
    )
    return out.drop_duplicates(["article_id", "section_key"], keep="first").copy()


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

    tab_units, tab_similar, tab_query = st.tabs(["Разделы статьи", "Поиск похожих разделов", "Нейросетевой поиск по разделам"])
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
        units = units[units["section_key"].astype(str) != "article"].copy()
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
        top_n = st.slider("Количество похожих разделов", 1, 100, 20)

        source_row = sources[sources["unit_id"].astype(str) == str(source_unit_id)].iloc[0]
        source_section_key = str(source_row["section_key"])
        src_row = int(source_row["matrix_row"])
        target = idx_df.copy()
        target["section_key"] = target.apply(section_identity_key, axis=1)
        if target_key:
            target = target[target["section_key"] == target_key]
        target = target[
            ~(
                (target["article_id"].astype(str) == str(article_id))
                & (target["section_key"].astype(str) == source_section_key)
            )
        ]
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
        merged["section_key"] = merged.apply(section_identity_key, axis=1)
        merged["section_label"] = merged.apply(section_label_ru, axis=1)
        merged = merged[merged["section_key"].astype(str).str.strip() != ""]
        merged = merged[merged["section_label"].astype(str).str.strip() != ""]
        merged = merged.sort_values("similarity", ascending=False).drop_duplicates(["article_id", "section_key"], keep="first")
        merged = merged.merge(df_articles, left_on="article_id", right_on="Article_id", how="left")
        merged["render_text_ru"] = merged.apply(_display_text_for_result, axis=1)
        merged = merged[merged["render_text_ru"].astype(str).str.strip() != ""]

        for _, r in merged.iterrows():
            with st.expander(f"#{int(r['rank'])} | {r.get('Title','')}"):
                st.write(f"**Авторы:** {_clean(r.get('Authors',''))}")
                st.write(f"**Год:** {_clean(r.get('Year',''))}")
                st.write(f"**Журнал:** {_clean(r.get('Journal',''))}")
                st.write(f"**{str(r['section_label'])}**")
                text = _clean(r.get("render_text_ru", ""))
                if text:
                    st.write(text)
                kw = _display_keywords_for_result(r)
                if kw:
                    st.write(f"Ключевые слова: {kw}")


    with tab_query:
        idx_df = load_imrad_text_index(str(opt["language"]), str(opt["text_role"]), str(opt["embedding_model_id"]), str(opt["matrix_file_id"]))
        if idx_df.empty:
            st.warning("Нет доступных данных для поиска по разделам.")
            return
        allowed_article_ids = set(df_articles["Article_id"].astype(str))
        idx_df = idx_df[idx_df["article_id"].astype(str).isin(allowed_article_ids)].copy()
        if idx_df.empty:
            st.warning("Нет доступных данных для поиска по разделам.")
            return

        idx_norm = _normalize_sections(idx_df.copy())
        section_options = {str(r["section_key"]): str(r["section_label"]) for _, r in idx_norm.iterrows()}

        query_count_key = "imrad_neural_query_count"
        if query_count_key not in st.session_state:
            st.session_state[query_count_key] = 1
        count = max(1, min(5, int(st.session_state[query_count_key])))
        st.session_state[query_count_key] = count

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Добавить запрос", key="imrad_add_query", disabled=count >= 5):
                st.session_state[query_count_key] = min(5, count + 1)
                st.rerun()
        with c2:
            if st.button("Удалить последний запрос", key="imrad_remove_query", disabled=count <= 1):
                st.session_state[query_count_key] = max(1, count - 1)
                st.rerun()

        with st.form("imrad_neural_search_form"):
            target_key = st.selectbox("Целевой раздел", options=list(section_options.keys()), format_func=lambda x: section_options[x], key="imrad_query_target")
            st.markdown("Введите ключевые слова, характеризующие Ваш запрос")
            st.caption("Можно вводить запросы на русском языке. Поиск выполняется смысловым сопоставлением, а не только по точному совпадению слов.")
            query_values = [st.text_input(f"Запрос {i + 1}", key=f"imrad_neural_query_{i}") for i in range(count)]
            top_n = st.slider("Количество найденных статей", 1, 100, 20)
            submitted = st.form_submit_button("Найти")

        if not submitted:
            st.info("Введите запросы и нажмите «Найти».")
            return

        queries = collect_non_empty_queries(query_values)
        if not queries:
            st.info("Введите хотя бы один запрос.")
            return

        if not is_query_encoder_enabled():
            st.error("Нейросетевой поиск недоступен: не установлен или не настроен энкодер запросов.")
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

        normalized_flag = str(opt.get("normalized", 1)).lower() in {"1", "true", "yes"}
        try:
            query_vectors = encode_user_queries(queries, model_name=str(opt["model_name"]), normalize_embeddings=normalized_flag, device=get_query_encoder_device())
        except Exception:
            st.error("Нейросетевой поиск недоступен: не установлен или не настроен энкодер запросов.")
            return

        if query_vectors.shape[1] != matrix.shape[1]:
            st.error("Размерность запроса не совпадает с размерностью матрицы эмбеддингов.")
            return

        target = idx_df.copy()
        target["section_key"] = target.apply(section_identity_key, axis=1)
        target = target[target["section_key"] == target_key]
        target = _normalize_sections_per_article(target)
        if target.empty:
            st.info("По заданному запросу не найдено разделов с русским текстом для отображения.")
            return

        result = search_sections_by_query_vector(query_vectors, matrix, target, top_n, normalized=normalized_flag)
        ru = load_imrad_display_texts_ru(result["unit_id"].astype(str).tolist())
        result = result.merge(ru, on="unit_id", how="left")
        result = result.merge(df_articles, left_on="article_id", right_on="Article_id", how="left")
        result["render_text_ru"] = result.apply(_display_text_for_result, axis=1)
        result["render_keywords_ru"] = result.apply(_display_keywords_for_result, axis=1)
        result = result[result["render_text_ru"].astype(str).str.strip() != ""]
        if result.empty:
            st.info("По заданному запросу не найдено разделов с русским текстом для отображения.")
            return

        for _, r in result.iterrows():
            with st.expander(f"#{int(r['rank'])} | {r.get('Title','')}"):
                st.write(f"**Авторы:** {_clean(r.get('Authors',''))}")
                st.write(f"**Год:** {_clean(r.get('Year',''))}")
                st.write(f"**Журнал:** {_clean(r.get('Journal',''))}")
                st.write(f"**Раздел:** {str(r.get('section_label',''))}")
                st.write(_clean(r.get("render_text_ru", "")))
                kw = _clean(r.get("render_keywords_ru", ""))
                if kw:
                    st.write(f"Ключевые слова: {kw}")
                if len(queries) > 1:
                    st.write("Вклад запросов:")
                    for i in range(len(queries)):
                        w = float(r.get(f"query_weight_{i+1}", 0.0))
                        st.write(f"Запрос {i + 1}: {w:.0f}%")
