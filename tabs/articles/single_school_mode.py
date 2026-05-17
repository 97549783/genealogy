"""Режим анализа статей одной научной школы."""

from __future__ import annotations

import re
from typing import Dict, Optional, Set

import pandas as pd
import streamlit as st

from core.db.articles import load_article_authors, load_article_keywords, load_articles_data
from core.ui.links import share_params_button
from .author_matching import canon_article_author_name, compute_selectable_people, get_school_member_initials, resolve_article_author_to_lineage_root
from .blocks import get_available_block_columns, load_article_analysis_block_groups
from .charts import create_block_scores_chart, create_yearly_articles_chart
from .data import build_articles_dataset_for_school
from .metrics import compute_block_score_summary, normalize_keyword
from .query_params import parse_bool_param, parse_float_param, query_params_signature, should_hydrate_query
from .results_table import prepare_articles_results_table


def _keywords_from_metadata(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in df.iterrows():
        for keyword in re.split(r"[;]", str(row.get("Keywords", "") or "")):
            value = keyword.strip()
            if value:
                rows.append({"Article_id": row.get("Article_id"), "Keyword": value})
    return pd.DataFrame(rows)


def _dataset_article_ids(dataset: pd.DataFrame) -> Set[str]:
    """Возвращает нормализованные идентификаторы статей из набора анализа."""
    if dataset is None or dataset.empty or "Article_id" not in dataset.columns:
        return set()
    return {str(value).strip() for value in dataset["Article_id"].dropna().astype(str) if str(value).strip()}


def _school_article_authors(
    dataset: pd.DataFrame,
    article_authors: pd.DataFrame,
    member_initials: Set[str],
) -> pd.DataFrame:
    """Фильтрует `article_authors` до авторов выбранной школы и статей датасета."""
    if not member_initials or article_authors is None or article_authors.empty:
        return pd.DataFrame()
    if "Article_id" not in article_authors.columns or "Name" not in article_authors.columns:
        return pd.DataFrame()
    article_ids = _dataset_article_ids(dataset)
    if not article_ids:
        return pd.DataFrame()
    sub_authors = article_authors.copy()
    sub_authors["_article_id"] = sub_authors["Article_id"].astype(str).str.strip()
    sub_authors["_canon"] = sub_authors["Name"].apply(canon_article_author_name)
    return sub_authors[sub_authors["_article_id"].isin(article_ids) & sub_authors["_canon"].isin(member_initials)].copy()


def compute_found_school_author_initials(
    dataset: pd.DataFrame,
    article_authors: pd.DataFrame,
    member_initials: Set[str],
) -> Set[str]:
    """Возвращает участников школы, найденных в `article_authors` для статей датасета."""
    school_authors = _school_article_authors(dataset, article_authors, member_initials)
    if school_authors.empty or "_canon" not in school_authors.columns:
        return set()
    return {str(value).strip() for value in school_authors["_canon"].dropna().astype(str) if str(value).strip()}


def compute_yearly_school_author_counts(dataset: pd.DataFrame, school_article_authors: pd.DataFrame) -> pd.DataFrame:
    """Считает годовую динамику статей и авторов школы по данным `article_authors`."""
    columns = ["Год", "Количество статей", "Количество авторов школы"]
    if dataset is None or dataset.empty or "Year" not in dataset.columns:
        return pd.DataFrame(columns=columns)
    rows = []
    prepared = dataset.copy()
    prepared["_article_id"] = prepared["Article_id"].astype(str).str.strip() if "Article_id" in prepared.columns else ""
    prepared = prepared.assign(_year=pd.to_numeric(prepared["Year"], errors="coerce")).dropna(subset=["_year"])
    for year, group in prepared.groupby("_year"):
        article_ids = {str(value).strip() for value in group["_article_id"].dropna().astype(str) if str(value).strip()}
        school_authors = set()
        if school_article_authors is not None and not school_article_authors.empty and "_article_id" in school_article_authors.columns:
            year_authors = school_article_authors[school_article_authors["_article_id"].isin(article_ids)]
            school_authors = {str(value).strip() for value in year_authors.get("_canon", pd.Series(dtype=object)).dropna().astype(str) if str(value).strip()}
        rows.append({"Год": int(year), "Количество статей": len(group), "Количество авторов школы": len(school_authors)})
    return pd.DataFrame(rows).sort_values("Год") if rows else pd.DataFrame(columns=columns)


def _render_results_table(df: pd.DataFrame) -> None:
    display_df = prepare_articles_results_table(df)
    st.dataframe(
        display_df,
        column_config={
            "Сайт журнала": st.column_config.LinkColumn("Сайт журнала", display_text="Читать"),
            "PDF": st.column_config.LinkColumn("PDF", display_text="PDF"),
            "Elibrary": st.column_config.LinkColumn("Elibrary", display_text="Библиометрия"),
        },
        hide_index=True,
        use_container_width=True,
    )


def render_single_school_mode(
    df_lineage: pd.DataFrame,
    idx_lineage: Dict[str, Set[int]],
    classifier_labels: Optional[Dict[str, str]] = None,
    df_articles: pd.DataFrame | None = None,
) -> None:
    """Отрисовывает режим анализа одной школы."""
    st.markdown("### Выбор научной школы")
    options, options_meta = compute_selectable_people(df_lineage, include_without_descendants=True)
    if not options:
        st.warning("Не удалось найти школы или авторов, связанных со статьями.")
        return

    signature = query_params_signature(["articles_mode", "aa_journals", "aa_school", "aa_scope", "aa_threshold", "aa_show_all_blocks"])
    if should_hydrate_query("aa_single_query_signature", signature):
        query_school = str(st.query_params.get("aa_school", "")).strip()
        st.session_state["aa_single_school"] = query_school if query_school in options else None
        scope_q = str(st.query_params.get("aa_scope", "direct")).strip()
        st.session_state["aa_single_scope"] = scope_q if scope_q in {"direct", "all"} else "direct"
        st.session_state["aa_single_threshold"] = max(0.0, min(10.0, parse_float_param(st.query_params.get("aa_threshold", 3.0), 3.0)))
        st.session_state["aa_single_show_all_blocks"] = parse_bool_param(st.query_params.get("aa_show_all_blocks"), False)

    selected_value = st.session_state.get("aa_single_school")
    selected_index = options.index(selected_value) if selected_value in options else None
    selected = st.selectbox(
        "Научная школа",
        options=options,
        index=selected_index,
        placeholder="Выберите научную школу",
        key="aa_single_school",
    )

    if selected is None:
        st.info("Выберите научную школу для анализа.")
        return

    resolution = resolve_article_author_to_lineage_root(selected, df_lineage)
    if resolution.ambiguous_full_names and not resolution.root_name:
        st.warning("Имя автора статьи соответствует нескольким людям в генеалогии. Выберите, чью школу использовать, или оставьте анализ только по этому автору.")
        choices = ["Анализировать только автора", *resolution.ambiguous_full_names]
        choice = st.selectbox("Уточнение автора в генеалогии", choices, key="aa_single_disambiguation")
        disambiguation = dict(st.session_state.get("ac_disambiguation", {}))
        if choice == "Анализировать только автора":
            disambiguation.pop(resolution.canon_key, None)
        else:
            disambiguation[resolution.canon_key] = choice
        st.session_state["ac_disambiguation"] = disambiguation

    scope_value = st.session_state.get("aa_single_scope", "direct")
    scope = st.radio(
        "Охват участников школы:",
        options=["direct", "all"],
        format_func=lambda value: "Только прямые ученики (1-й уровень)" if value == "direct" else "Все поколения школы",
        horizontal=True,
        index=1 if scope_value == "all" else 0,
        key="aa_single_scope",
    )
    threshold = st.number_input("Порог среднего балла", min_value=0.0, max_value=10.0, value=float(st.session_state.get("aa_single_threshold", 3.0)), step=0.1, key="aa_single_threshold")
    show_all = st.checkbox("Показать все тематические блоки", value=bool(st.session_state.get("aa_single_show_all_blocks", False)), key="aa_single_show_all_blocks")

    if df_articles is None:
        df_articles = load_articles_data()
    dataset = build_articles_dataset_for_school(selected, options_meta, df_lineage, idx_lineage, df_articles, scope)
    if dataset.empty:
        st.info("Для выбранной школы статьи не найдены.")
        return

    member_initials = get_school_member_initials(selected, options_meta, df_lineage, idx_lineage, scope)
    article_authors = load_article_authors()
    article_keywords = load_article_keywords()

    school_authors = _school_article_authors(dataset, article_authors, member_initials)
    found_member_initials = compute_found_school_author_initials(dataset, article_authors, member_initials)
    doi_count = int(dataset.get("DOI", pd.Series(dtype=object)).fillna("").astype(str).str.strip().ne("").sum())
    years = pd.to_numeric(dataset.get("Year"), errors="coerce").dropna()
    period = f"{int(years.min())}–{int(years.max())}" if not years.empty else "—"
    if not article_keywords.empty:
        kw_source = article_keywords[article_keywords["Article_id"].astype(str).isin(dataset["Article_id"].astype(str))]
    else:
        kw_source = _keywords_from_metadata(dataset)
    unique_keywords = {normalize_keyword(v) for v in kw_source.get("Keyword", pd.Series(dtype=object)) if normalize_keyword(v)}

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Статей найдено", len(dataset))
    c2.metric("Авторов школы в статьях", len(found_member_initials))
    c3.metric("Уникальных ключевых слов", len(unique_keywords))
    c4.metric("Период публикаций", period)
    c5.metric("Статей с DOI", doi_count)

    st.markdown("### Авторы школы, найденные в статьях")
    author_rows = []
    if not school_authors.empty:
        for name, group in school_authors.groupby("Name", dropna=True):
            article_ids = {str(value).strip() for value in group["_article_id"].dropna().astype(str) if str(value).strip()}
            years_for_author = pd.to_numeric(dataset[dataset["Article_id"].astype(str).str.strip().isin(article_ids)]["Year"], errors="coerce").dropna()
            author_rows.append({
                "Автор": name,
                "Количество статей": len(article_ids),
                "Годы публикаций": ", ".join(str(int(v)) for v in sorted(years_for_author.unique())),
                "Аффилиация": "; ".join(sorted({str(v) for v in group.get("Affiliation", pd.Series(dtype=object)).dropna() if str(v).strip()})),
                "Город": "; ".join(sorted({str(v) for v in group.get("City", pd.Series(dtype=object)).dropna() if str(v).strip()})),
            })
    st.dataframe(pd.DataFrame(author_rows), hide_index=True, use_container_width=True)

    st.markdown("### Результаты")
    _render_results_table(dataset)

    st.markdown("### Ключевые слова статей школы")
    if kw_source.empty:
        st.info("Ключевые слова для выбранных статей не найдены.")
    else:
        kw_counts = kw_source.assign(_kw=kw_source["Keyword"].apply(normalize_keyword))
        kw_counts = kw_counts[kw_counts["_kw"] != ""].groupby("_kw")["Article_id"].nunique().reset_index()
        kw_counts = kw_counts.rename(columns={"_kw": "Ключевое слово", "Article_id": "Количество статей"}).sort_values("Количество статей", ascending=False)
        st.dataframe(kw_counts, hide_index=True, use_container_width=True)

    st.markdown("### Тематический профиль школы по статьям")
    blocks = get_available_block_columns(dataset, classifier_labels=classifier_labels)
    block_scores = compute_block_score_summary(dataset, blocks, threshold=float(threshold), show_all=show_all)
    if block_scores.empty:
        st.info("Нет тематических блоков выше выбранного порога.")
    else:
        st.dataframe(block_scores, hide_index=True, use_container_width=True)
        st.pyplot(create_block_scores_chart(block_scores))
    block_groups = load_article_analysis_block_groups()
    configured_codes = [str(code) for group in block_groups.values() for code in group.get("codes", [])]
    unavailable_codes = [code for code in configured_codes if code not in dataset.columns]
    unsigned_codes = [code for code in configured_codes if classifier_labels is not None and code in dataset.columns and not str(classifier_labels.get(code, "")).strip()]
    with st.expander("Диагностика классификатора", expanded=False):
        st.write(f"Недоступных выбранных кодов в таблице articles_scores_inf_edu: {len(unavailable_codes)}")
        st.write(f"Кодов без подписи в классификаторе: {len(unsigned_codes)}")

    st.markdown("### Динамика по годам")
    yearly_df = compute_yearly_school_author_counts(dataset, school_authors)
    st.dataframe(yearly_df, hide_index=True, use_container_width=True)
    st.pyplot(create_yearly_articles_chart(yearly_df))

    share_params_button(
        {
            "tab": "articles_comparison",
            "articles_mode": "single_school",
            "aa_journals": st.session_state.get("aa_selected_journals", ["all"]),
            "aa_school": selected,
            "aa_scope": scope,
            "aa_threshold": float(threshold),
            "aa_show_all_blocks": bool(show_all),
        },
        key="aa_single_share",
    )
