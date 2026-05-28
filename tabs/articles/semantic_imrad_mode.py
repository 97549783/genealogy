"""Режим Streamlit для семантического поиска по IMRAD-зонам."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.db.imrad import load_article_imrad_units, load_imrad_diagnostics, load_imrad_embedding_options, load_imrad_quotes, load_imrad_text_index
from .imrad_search import filter_imrad_index, load_embedding_matrix, resolve_matrix_path, search_similar_units


def _label_article(row: pd.Series) -> str:
    return f"[{row.get('Article_id','')}] {row.get('Title','')} — {row.get('Authors','')} — {row.get('Year','')}"


def _source_unit_label(row: pd.Series) -> str:
    return f"{row.get('unit_id','')} | {row.get('imrad_block','')} / {row.get('imrad_subblock','')} | {row.get('rhetorical_zone_type','')} | уверенность={row.get('confidence','')}"


def render_semantic_imrad_search_mode(df_articles: pd.DataFrame) -> None:
    st.markdown("### Семантический поиск по зонам")
    with st.expander("Диагностика IMRAD-данных", expanded=False):
        counts = load_imrad_diagnostics().get("счётчики", {})
        st.write(f"Количество строк в article_imrad_units: {counts.get('article_imrad_units')}")
        st.write(f"Количество строк в article_imrad_unit_texts: {counts.get('article_imrad_unit_texts')}")
        st.write(f"Количество строк в article_imrad_embeddings: {counts.get('article_imrad_embeddings')}")
        options_df = load_imrad_embedding_options()
        if options_df.empty:
            st.warning("Таблицы эмбеддингов IMRAD недоступны или пусты.")
        else:
            shown = options_df.rename(columns={"matrix_file_id": "ID файла матрицы", "embedding_model_id": "ID модели", "language": "Язык", "text_role": "Роль текста", "file_path": "Путь к файлу", "matrix_shape": "Форма матрицы", "dtype": "Тип", "normalized": "Нормализована", "provider": "Провайдер", "model_name": "Модель", "model_version": "Версия", "distance_metric": "Метрика", "dimensions": "Размерность"})
            st.dataframe(shown, use_container_width=True)
            for _, r in options_df.iterrows():
                p = str(r.get("file_path", "") or "")
                rp = resolve_matrix_path(p) if p else None
                st.write(f"Файл: {p}; существует: {bool(rp and rp.exists())}; форма из БД: {r.get('matrix_shape')}")

    tab_units, tab_similar, tab_query = st.tabs(["Зоны выбранной статьи", "Поиск похожих зон", "Поиск по запросам"])
    with tab_units:
        labels = {str(r.Article_id): _label_article(r) for _, r in df_articles.iterrows()}
        article_id = st.selectbox("Выберите статью", options=list(labels.keys()), format_func=lambda x: labels[x])
        row = df_articles[df_articles["Article_id"].astype(str) == str(article_id)].iloc[0]
        fields = {"Название": "Title", "Авторы": "Authors", "Год": "Year", "Журнал": "Journal", "DOI": "DOI", "Сайт журнала": "Article_URL", "PDF": "Article_PDF", "Аннотация": "Abstract", "Ключевые слова": "Keywords"}
        for k, v in fields.items(): st.write(f"**{k}:** {row.get(v, '')}")
        units = load_article_imrad_units(str(article_id), language="en", text_role="compact_en")
        if units.empty:
            st.info("Для выбранной статьи IMRAD-данные не найдены.")
        else:
            quotes = load_imrad_quotes(units["unit_id"].astype(str).unique().tolist())
            for (b, s), g in units.groupby(["imrad_block", "imrad_subblock"], dropna=False):
                with st.expander(f"Блок IMRAD: {b} / Подблок: {s}"):
                    for _, u in g.iterrows():
                        st.markdown(f"**Единица:** {u.get('unit_id','')} | уверенность={u.get('confidence','')} | слабая зона={u.get('is_weak','')} | выведенная зона={u.get('is_inferred','')}")
                        st.write(f"Текст: {u.get('text', '')}")
                        st.write(f"Ключевые слова: {u.get('keywords_json','')}")
                        st.write(f"Ключевые утверждения: {u.get('key_assertions_json','')}")
                        st.write(f"Извлечённые данные: {u.get('extracted_json','')}")
                        st.write(f"Источник зон: {u.get('source_zone_ids_json','')}")
                        st.write(f"Файл-источник: {u.get('source_file','')}")
                        q = quotes[quotes["unit_id"].astype(str) == str(u.get("unit_id", ""))] if not quotes.empty else pd.DataFrame()
                        if not q.empty:
                            st.dataframe(q[["quote_text", "section_guess", "page_guess", "importance"]].rename(columns={"quote_text":"Цитата","section_guess":"Раздел","page_guess":"Страница","importance":"Важность"}), use_container_width=True)

    with tab_similar:
        options_df = load_imrad_embedding_options().reset_index(drop=True)
        if options_df.empty:
            st.warning("Нет доступных опций эмбеддингов для поиска похожих зон.")
            return
        opt_idx = st.selectbox("Слой эмбеддингов", options=options_df.index.tolist(), format_func=lambda i: f"{options_df.loc[i,'language']} / {options_df.loc[i,'text_role']} / {options_df.loc[i,'model_name']}")
        opt = options_df.loc[opt_idx]
        idx_df = load_imrad_text_index(opt["language"], opt["text_role"], str(opt["embedding_model_id"]), str(opt["matrix_file_id"]))
        if idx_df.empty:
            st.warning("Индекс IMRAD для выбранной опции пуст.")
            return
        try:
            matrix = load_embedding_matrix(resolve_matrix_path(str(opt.get("file_path") or "")))
        except FileNotFoundError as exc:
            st.error(str(exc)); return
        article_labels = {str(r.Article_id): _label_article(r) for _, r in df_articles.iterrows()}
        source_article_id = st.selectbox("Исходная статья", options=list(article_labels.keys()), format_func=lambda x: article_labels[x])
        sources = idx_df[idx_df["article_id"].astype(str) == str(source_article_id)].copy()
        if sources.empty:
            st.warning("Для выбранной статьи нет IMRAD-зон в текущем слое."); return
        source_options = sources["unit_id"].astype(str).tolist()
        label_map = {str(r["unit_id"]): _source_unit_label(r) for _, r in sources.iterrows()}
        source_unit_id = st.selectbox("Исходная зона", options=source_options, format_func=lambda x: label_map.get(str(x), str(x)))
        unit_levels = sorted([x for x in idx_df["unit_level"].dropna().astype(str).unique().tolist() if x])
        blocks = sorted([x for x in idx_df["imrad_block"].dropna().astype(str).unique().tolist() if x])
        subblocks = sorted([x for x in idx_df["imrad_subblock"].dropna().astype(str).unique().tolist() if x])
        selected_levels = st.multiselect("Целевые уровни единиц", options=unit_levels)
        selected_blocks = st.multiselect("Целевые блоки IMRAD", options=blocks)
        selected_subblocks = st.multiselect("Целевые подблоки", options=subblocks)
        exclude_current = st.checkbox("Исключить текущую статью", value=False)
        include_weak = st.checkbox("Включать слабые зоны", value=True)
        include_inferred = st.checkbox("Включать выведенные зоны", value=True)
        min_conf = st.number_input("Минимальная уверенность", min_value=0.0, max_value=1.0, value=0.0, step=0.05)
        top_n = st.slider("Количество результатов (Top-N)", 1, 100, 20)
        src_row = int(sources[sources["unit_id"].astype(str) == str(source_unit_id)].iloc[0]["matrix_row"])
        target = filter_imrad_index(idx_df, unit_levels=selected_levels or None, imrad_blocks=selected_blocks or None, imrad_subblocks=selected_subblocks or None, include_weak=include_weak, include_inferred=include_inferred, min_confidence=min_conf, exclude_article_id=str(source_article_id) if exclude_current else None)
        target = target[target["unit_id"].astype(str) != str(source_unit_id)]
        if target.empty:
            st.warning("После применения фильтров целевые зоны не найдены."); return
        result = search_similar_units(src_row, matrix, idx_df, target, top_n)
        merged = result.merge(df_articles, left_on="article_id", right_on="Article_id", how="left")
        table = merged[["rank","similarity","Title","Authors","Year","Journal","unit_level","imrad_block","imrad_subblock","rhetorical_zone_type","text","keywords_json","confidence","is_weak","is_inferred","Article_URL","Article_PDF"]].rename(columns={"rank":"Ранг","similarity":"Сходство","Title":"Название статьи","Authors":"Авторы","Year":"Год","Journal":"Журнал","unit_level":"Уровень единицы","imrad_block":"Блок IMRAD","imrad_subblock":"Подблок","rhetorical_zone_type":"Риторическая зона","text":"Текст","keywords_json":"Ключевые слова","confidence":"Уверенность","is_weak":"Слабая зона","is_inferred":"Выведенная зона","Article_URL":"Ссылка на статью","Article_PDF":"Ссылка на PDF"})
        st.dataframe(table, use_container_width=True)
        for _, r in merged.iterrows():
            with st.expander(f"#{int(r['rank'])} | {r.get('Title','')} | сходство={float(r.get('similarity',0)):.4f}"):
                st.write(f"**Авторы:** {r.get('Authors','')}  ")
                st.write(f"**Год:** {r.get('Year','')}  ")
                st.write(f"**Журнал:** {r.get('Journal','')}  ")
                st.write(f"**Зона:** {r.get('unit_level','')} / {r.get('imrad_block','')} / {r.get('imrad_subblock','')} / {r.get('rhetorical_zone_type','')}")
                st.write(f"**Текст зоны:** {r.get('text','')}")
                st.write(f"**Ключевые слова:** {r.get('keywords_json','')}")
                st.write(f"**Уверенность:** {r.get('confidence','')} | **Слабая:** {r.get('is_weak','')} | **Выведенная:** {r.get('is_inferred','')}")
                st.write(f"**Сайт статьи:** {r.get('Article_URL','')}  ")
                st.write(f"**PDF:** {r.get('Article_PDF','')}  ")

    with tab_query:
        st.warning("Поиск по запросам недоступен: runtime-энкодер запросов не установлен в текущей среде.")
