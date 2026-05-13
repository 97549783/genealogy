"""Режим поиска научных школ, похожих по статьям."""

from __future__ import annotations

import re
from typing import Dict, Optional, Set

import pandas as pd
import streamlit as st

from core.db.articles import load_article_keywords, load_articles_data
from core.ui.links import share_params_button
from .author_matching import compute_selectable_people, resolve_article_author_to_lineage_root
from .blocks import get_available_block_columns
from .data import build_articles_dataset_for_school
from .metrics import build_school_vector, compute_keyword_overlap, cosine_similarity_safe, get_article_feature_columns, normalize_keyword
from .query_params import parse_float_param, parse_int_param, query_params_signature, should_hydrate_query


def _keywords_for_dataset(dataset: pd.DataFrame, article_keywords: pd.DataFrame) -> Set[str]:
    if dataset is None or dataset.empty:
        return set()
    ids = set(dataset["Article_id"].astype(str)) if "Article_id" in dataset.columns else set()
    if article_keywords is not None and not article_keywords.empty:
        sub = article_keywords[article_keywords["Article_id"].astype(str).isin(ids)]
        return {normalize_keyword(v) for v in sub.get("Keyword", pd.Series(dtype=object)) if normalize_keyword(v)}
    keywords: Set[str] = set()
    for raw in dataset.get("Keywords", pd.Series(dtype=object)).fillna("").astype(str):
        keywords.update({normalize_keyword(part) for part in re.split(r"[;]", raw) if normalize_keyword(part)})
    return keywords


def _strong_block_labels(dataset: pd.DataFrame, blocks: list[dict], threshold: float) -> Set[str]:
    labels: Set[str] = set()
    for block in blocks:
        code = block.get("code")
        if code in dataset.columns and float(pd.to_numeric(dataset[code], errors="coerce").fillna(0).mean()) >= threshold:
            labels.add(str(block.get("label", "")))
    return labels


def render_similar_schools_mode(
    df_lineage: pd.DataFrame,
    idx_lineage: Dict[str, Set[int]],
    classifier_labels: Optional[Dict[str, str]] = None,
) -> None:
    """Отрисовывает режим поиска похожих школ."""
    st.markdown("### Исходная школа")
    options, options_meta = compute_selectable_people(df_lineage, include_without_descendants=True)
    if not options:
        st.warning("Не удалось найти школы или авторов, связанных со статьями.")
        return

    mode_options = ["profile", "keywords", "combined"]
    mode_labels = {"profile": "По тематическому профилю", "keywords": "По ключевым словам", "combined": "Комбинированный поиск"}
    signature = query_params_signature([
        "articles_mode",
        "aa_source_school",
        "aa_scope",
        "aa_similarity_mode",
        "aa_min_articles",
        "aa_top_n",
        "aa_threshold",
    ])
    if should_hydrate_query("aa_similar_query_signature", signature):
        source_q = str(st.query_params.get("aa_source_school", "")).strip()
        st.session_state["aa_source_school"] = source_q if source_q in options else None
        scope_q = str(st.query_params.get("aa_scope", "direct")).strip()
        st.session_state["aa_similar_scope"] = scope_q if scope_q in {"direct", "all"} else "direct"
        mode_q = str(st.query_params.get("aa_similarity_mode", "profile")).strip()
        st.session_state["aa_similarity_mode"] = mode_q if mode_q in mode_options else "profile"
        st.session_state["aa_min_articles"] = max(1, min(1000, parse_int_param(st.query_params.get("aa_min_articles", 1), 1)))
        st.session_state["aa_top_n"] = max(1, min(100, parse_int_param(st.query_params.get("aa_top_n", 20), 20)))
        st.session_state["aa_similar_threshold"] = max(0.0, min(10.0, parse_float_param(st.query_params.get("aa_threshold", 3.0), 3.0)))

    selected_value = st.session_state.get("aa_source_school")
    selected_index = options.index(selected_value) if selected_value in options else None
    source_school = st.selectbox(
        "Исходная научная школа",
        options=options,
        index=selected_index,
        placeholder="Выберите исходную научную школу",
        key="aa_source_school",
    )
    if source_school is None:
        st.info("Выберите исходную научную школу для поиска похожих школ.")
        return

    resolution = resolve_article_author_to_lineage_root(source_school, df_lineage)
    if resolution.ambiguous_full_names and not resolution.root_name:
        st.warning("Имя автора статьи соответствует нескольким людям в генеалогии. Выберите, чью школу использовать, или оставьте анализ только по этому автору.")
        choices = ["Анализировать только автора", *resolution.ambiguous_full_names]
        choice = st.selectbox("Уточнение автора в генеалогии", choices, key="aa_similar_disambiguation")
        disambiguation = dict(st.session_state.get("ac_disambiguation", {}))
        if choice == "Анализировать только автора":
            disambiguation.pop(resolution.canon_key, None)
        else:
            disambiguation[resolution.canon_key] = choice
        st.session_state["ac_disambiguation"] = disambiguation

    scope_value = st.session_state.get("aa_similar_scope", "direct")
    scope = st.radio(
        "Охват участников школы:",
        options=["direct", "all"],
        format_func=lambda value: "Только прямые ученики (1-й уровень)" if value == "direct" else "Все поколения школы",
        horizontal=True,
        index=1 if scope_value == "all" else 0,
        key="aa_similar_scope",
    )

    mode_value = st.session_state.get("aa_similarity_mode", "profile")
    similarity_mode = st.radio(
        "Способ поиска:",
        options=mode_options,
        format_func=lambda value: mode_labels[value],
        horizontal=True,
        index=mode_options.index(mode_value) if mode_value in mode_options else 0,
        key="aa_similarity_mode",
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        min_articles = st.number_input("Минимальное количество статей в школе", min_value=1, max_value=1000, value=int(st.session_state.get("aa_min_articles", 1)), step=1, key="aa_min_articles")
    with c2:
        top_n = st.number_input("Количество похожих школ", min_value=1, max_value=100, value=int(st.session_state.get("aa_top_n", 20)), step=1, key="aa_top_n")
    with c3:
        threshold = st.number_input("Порог среднего балла", min_value=0.0, max_value=10.0, value=float(st.session_state.get("aa_similar_threshold", 3.0)), step=0.1, key="aa_similar_threshold")

    df_articles = load_articles_data()
    source_dataset = build_articles_dataset_for_school(source_school, options_meta, df_lineage, idx_lineage, df_articles, scope)
    if source_dataset.empty:
        st.info("Для исходной школы статьи не найдены.")
        return

    article_keywords = load_article_keywords()
    feature_columns = get_article_feature_columns(df_articles)
    blocks = get_available_block_columns(df_articles, classifier_labels=classifier_labels)
    source_vector = build_school_vector(source_dataset, feature_columns)
    source_keywords = _keywords_for_dataset(source_dataset, article_keywords)
    source_strong = _strong_block_labels(source_dataset, blocks, float(threshold))

    rows = []
    with st.spinner("Идёт поиск похожих школ..."):
        for option in options:
            if option == source_school:
                continue
            dataset = build_articles_dataset_for_school(option, options_meta, df_lineage, idx_lineage, df_articles, scope)
            if len(dataset) < int(min_articles):
                continue
            target_vector = build_school_vector(dataset, feature_columns)
            cosine = cosine_similarity_safe(source_vector, target_vector)
            overlap = compute_keyword_overlap(source_keywords, _keywords_for_dataset(dataset, article_keywords))
            target_strong = _strong_block_labels(dataset, blocks, float(threshold))
            common_strong = sorted(source_strong & target_strong)
            different = sorted((source_strong | target_strong) - (source_strong & target_strong))
            rows.append({
                "Школа": option,
                "Косинусная близость": cosine,
                "Количество статей": len(dataset),
                "Общие сильные блоки": "; ".join(common_strong),
                "Отличающиеся блоки": "; ".join(different[:10]),
                "Общих ключевых слов": overlap["intersection_count"],
                "Jaccard": overlap["jaccard"],
                "Пересекающиеся ключевые слова": "; ".join(overlap["intersection_keywords"][:20]),
                "Итоговая близость": 0.7 * cosine + 0.3 * overlap["jaccard"],
            })

    result = pd.DataFrame(rows)
    if result.empty:
        st.info("Похожие школы по заданным условиям не найдены.")
        return

    if similarity_mode == "profile":
        view = result.sort_values("Косинусная близость", ascending=False).head(int(top_n))[["Школа", "Косинусная близость", "Количество статей", "Общие сильные блоки", "Отличающиеся блоки"]]
    elif similarity_mode == "keywords":
        view = result.sort_values(["Общих ключевых слов", "Jaccard", "Количество статей"], ascending=[False, False, False]).head(int(top_n))[["Школа", "Общих ключевых слов", "Jaccard", "Пересекающиеся ключевые слова", "Количество статей"]]
    else:
        view = result.sort_values("Итоговая близость", ascending=False).head(int(top_n))[["Школа", "Итоговая близость", "Косинусная близость", "Jaccard", "Общих ключевых слов", "Количество статей"]]
    st.dataframe(view, hide_index=True, use_container_width=True)

    share_params_button(
        {
            "tab": "articles_comparison",
            "articles_mode": "similar_schools",
            "aa_source_school": source_school,
            "aa_scope": scope,
            "aa_similarity_mode": similarity_mode,
            "aa_min_articles": int(min_articles),
            "aa_top_n": int(top_n),
            "aa_threshold": float(threshold),
        },
        key="aa_similar_share",
    )
