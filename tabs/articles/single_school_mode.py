"""Режим анализа статей одной научной школы."""

from __future__ import annotations

import re
from typing import Dict, Optional, Set

import pandas as pd
import streamlit as st

from core.db.articles import load_article_authors, load_article_keywords, load_articles_data
from .author_matching import canon_initials, compute_selectable_people, fio_to_short, get_school_member_initials
from .blocks import get_available_block_columns, load_article_analysis_block_groups
from .charts import create_block_scores_chart, create_yearly_articles_chart
from .data import build_articles_dataset_for_school
from .metrics import compute_block_score_summary, normalize_keyword
from .query_params import parse_float_param
from .results_table import prepare_articles_results_table


def _keywords_from_metadata(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in df.iterrows():
        for keyword in re.split(r"[;]", str(row.get("Keywords", "") or "")):
            value = keyword.strip()
            if value:
                rows.append({"Article_id": row.get("Article_id"), "Keyword": value})
    return pd.DataFrame(rows)


def compute_found_school_author_initials(dataset: pd.DataFrame, member_initials: Set[str]) -> Set[str]:
    """Возвращает участников школы, фактически найденных среди авторов статей."""
    found: Set[str] = set()
    if dataset is None or dataset.empty or "Authors" not in dataset.columns:
        return found
    for raw in dataset["Authors"].fillna("").astype(str):
        for part in raw.split(";"):
            key = canon_initials(part)
            if key in member_initials:
                found.add(key)
    return found


def _render_results_table(df: pd.DataFrame) -> None:
    display_df = prepare_articles_results_table(df)
    st.dataframe(
        display_df,
        column_config={
            "Сайт журнала": st.column_config.LinkColumn("Сайт журнала", display_text="Читать"),
            "Elibrary": st.column_config.LinkColumn("Elibrary", display_text="Библиометрия"),
        },
        hide_index=True,
        use_container_width=True,
    )


def render_single_school_mode(
    df_lineage: pd.DataFrame,
    idx_lineage: Dict[str, Set[int]],
    classifier_labels: Optional[Dict[str, str]] = None,
) -> None:
    """Отрисовывает режим анализа одной школы."""
    st.markdown("### Выбор научной школы")
    df_articles = load_articles_data()
    options, options_meta = compute_selectable_people(df_lineage, include_without_descendants=True)
    hidden_ambiguous = [option for option in options if options_meta.get(option) == "initials_ambiguous"]
    if hidden_ambiguous:
        st.caption("Неоднозначные варианты с совпадающими инициалами временно скрыты, чтобы избежать ошибочного сопоставления авторов.")
    options = [option for option in options if options_meta.get(option) != "initials_ambiguous"]
    options_meta = {option: kind for option, kind in options_meta.items() if option in options}
    if not options:
        st.warning("Не удалось найти школы или авторов, связанных со статьями.")
        return

    query_school = str(st.query_params.get("aa_school", "")).strip()
    default_index = options.index(query_school) if query_school in options else 0
    selected = st.selectbox("Научная школа", options=options, index=default_index, key="aa_single_school")

    scope_q = str(st.query_params.get("aa_scope", "direct")).strip()
    scope_index = 1 if scope_q == "all" else 0
    scope = st.radio(
        "Охват участников школы:",
        options=["direct", "all"],
        format_func=lambda value: "Только прямые ученики (1-й уровень)" if value == "direct" else "Все поколения школы",
        horizontal=True,
        index=scope_index,
        key="aa_single_scope",
    )
    threshold = st.number_input("Порог среднего балла", min_value=0.0, max_value=10.0, value=max(0.0, min(10.0, parse_float_param(st.query_params.get("aa_threshold", 3.0), 3.0))), step=0.1, key="aa_single_threshold")
    show_all = st.checkbox("Показать все тематические блоки", value=False, key="aa_single_show_all_blocks")

    dataset = build_articles_dataset_for_school(selected, options_meta, df_lineage, idx_lineage, df_articles, scope)
    if dataset.empty:
        st.info("Для выбранной школы статьи не найдены.")
        return

    member_initials = get_school_member_initials(selected, options_meta, df_lineage, idx_lineage, scope)
    article_authors = load_article_authors()
    article_keywords = load_article_keywords()

    found_member_initials = compute_found_school_author_initials(dataset, member_initials)
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
    if not article_authors.empty:
        sub_authors = article_authors[article_authors["Article_id"].astype(str).isin(dataset["Article_id"].astype(str))].copy()
        sub_authors["_canon"] = sub_authors["Name"].apply(lambda value: canon_initials(value) if str(value).count(".") else canon_initials(fio_to_short(str(value))))
        sub_authors = sub_authors[sub_authors["_canon"].isin(member_initials)]
        for name, group in sub_authors.groupby("Name", dropna=True):
            article_ids = set(group["Article_id"].astype(str))
            years_for_author = pd.to_numeric(dataset[dataset["Article_id"].astype(str).isin(article_ids)]["Year"], errors="coerce").dropna()
            author_rows.append({
                "Автор": name,
                "Количество статей": len(article_ids),
                "Годы публикаций": ", ".join(str(int(v)) for v in sorted(years_for_author.unique())),
                "Аффилиация": "; ".join(sorted({str(v) for v in group.get("Affiliation", pd.Series(dtype=object)).dropna() if str(v).strip()})),
                "Город": "; ".join(sorted({str(v) for v in group.get("City", pd.Series(dtype=object)).dropna() if str(v).strip()})),
            })
    if not author_rows:
        for key in sorted(found_member_initials):
            count = int(dataset["Authors"].astype(str).apply(lambda raw: key in {canon_initials(part) for part in raw.split(";")}).sum())
            if count:
                author_rows.append({"Автор": key, "Количество статей": count, "Годы публикаций": period, "Аффилиация": "", "Город": ""})
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
    yearly_rows = []
    for year, group in dataset.assign(_year=pd.to_numeric(dataset["Year"], errors="coerce")).dropna(subset=["_year"]).groupby("_year"):
        school_authors = set()
        for raw in group["Authors"].astype(str):
            school_authors.update({canon_initials(part) for part in raw.split(";") if canon_initials(part) in member_initials})
        yearly_rows.append({"Год": int(year), "Количество статей": len(group), "Количество авторов школы": len(school_authors)})
    yearly_df = pd.DataFrame(yearly_rows).sort_values("Год") if yearly_rows else pd.DataFrame(columns=["Год", "Количество статей", "Количество авторов школы"])
    st.dataframe(yearly_df, hide_index=True, use_container_width=True)
    st.pyplot(create_yearly_articles_chart(yearly_df))
