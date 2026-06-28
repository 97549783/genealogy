"""Интерфейс вкладки характеристик диссертаций."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.db.dissertation_sections import (
    load_dissertation_section_codes,
    load_dissertation_section_index,
    load_dissertation_section_texts_by_ids,
    load_dissertation_sections_by_code,
    load_dissertation_sections_diagnostics,
    load_vector_metadata,
)
from core.domain.science_fields import filter_df_by_science_fields
from core.ui.filters import hydrate_science_fields_from_query_params, render_science_field_filter, science_field_filter_caption
from core.ui.table_display import make_abstract_download_url_numeric, make_abstract_read_url
from tabs.dissertation_characteristics.labels import DISPLAY_SECTION_KEYS, SEARCHABLE_SECTION_KEYS, SECTION_LABELS_RU
from tabs.dissertation_characteristics.query_search import (
    collect_non_empty_queries,
    encode_user_queries,
    get_query_encoder_device,
    is_query_encoder_available,
    search_dissertation_sections_by_query_vector,
)
from tabs.dissertation_characteristics.search import (
    filter_targets_for_similar_search,
    get_search_batch_size,
    load_current_dissertation_matrix,
    search_similar_dissertation_sections,
)


def _value(row: pd.Series, column: str) -> str:
    value = row.get(column, "") if row is not None else ""
    return "" if pd.isna(value) else str(value)


def _label(row: pd.Series) -> str:
    parts = [_value(row, "candidate_name"), _value(row, "title"), _value(row, "year"), _value(row, "degree.science_field")]
    return " — ".join([p for p in parts if p]) or "Без названия"


def _linked_df(df: pd.DataFrame, section_index: pd.DataFrame) -> pd.DataFrame:
    """Оставляет только записи, связанные с базой разделов."""
    if df is None or df.empty or "Code" not in df.columns or section_index.empty:
        return pd.DataFrame(columns=df.columns if df is not None else [])
    codes = set(section_index["Code"].astype(str))
    return df[df["Code"].astype(str).isin(codes)].copy()


def _search_rows(df: pd.DataFrame, text: str, mode: str) -> pd.DataFrame:
    if df.empty or not text.strip():
        return df
    needle = text.strip().casefold()
    columns = {
        "Только по автору": ["candidate_name"],
        "Только по названию": ["title"],
    }.get(mode, ["candidate_name", "title"])
    mask = pd.Series(False, index=df.index)
    for col in columns:
        if col in df.columns:
            mask |= df[col].astype(str).str.casefold().str.contains(needle, regex=False, na=False)
    return df[mask].copy()


def _submitted_search_key(key_prefix: str) -> str:
    """Возвращает ключ сохранённых параметров поиска диссертации."""
    return f"{key_prefix}_submitted_search"


def _select_dissertation(df: pd.DataFrame, key_prefix: str) -> pd.Series | None:
    mode_key = f"{key_prefix}_mode"
    query_key = f"{key_prefix}_query"
    button_key = f"{key_prefix}_search_button"
    select_key = f"{key_prefix}_select"
    submitted_key = _submitted_search_key(key_prefix)

    mode = st.radio("Искать:", ["По автору или названию", "Только по автору", "Только по названию"], horizontal=True, key=mode_key)
    query = st.text_input(
        "Поиск диссертаций",
        key=query_key,
        placeholder="Введите фрагмент имени автора или названия",
        label_visibility="collapsed",
    )
    if st.button("Поиск", type="primary", key=button_key):
        st.session_state[submitted_key] = {"query": query, "mode": mode}
        st.session_state[select_key] = None

    submitted = st.session_state.get(submitted_key)
    if not submitted:
        st.caption("Введите параметры и нажмите «Поиск».")
        return None

    found = _search_rows(df, str(submitted.get("query", "")), str(submitted.get("mode", "По автору или названию"))).head(300)
    if found.empty:
        st.warning("Подходящие диссертации не найдены.")
        return None
    options = list(found.index)
    selected = st.selectbox(
        "Выберите диссертацию из результатов поиска",
        options=options,
        index=None,
        format_func=lambda i: _label(found.loc[i]),
        key=select_key,
    )
    if selected is None:
        return None
    return found.loc[selected]


def _specialty_value(row: pd.Series) -> str:
    """Возвращает специальность из возможных плоских столбцов основной базы."""
    direct = _value(row, "specialty")
    if direct:
        return direct
    values: list[str] = []
    for idx in range(1, 6):
        code = _value(row, f"specialties_{idx}.code")
        name = _value(row, f"specialties_{idx}.name")
        if code and name:
            values.append(f"{code} — {name}")
        elif code or name:
            values.append(code or name)
    return "; ".join(values)


def _abstract_link_values(code: str, candidate_name: str) -> dict[str, str]:
    """Возвращает ссылки на автореферат без вывода служебного кода."""
    return {
        "read": make_abstract_read_url(code),
        "download": make_abstract_download_url_numeric(code, candidate_name),
    }


def _render_abstract_links(code: str, candidate_name: str) -> None:
    """Показывает ссылки на автореферат без вывода служебного кода."""
    links = _abstract_link_values(code, candidate_name)
    visible_links: list[str] = []
    if links["read"]:
        visible_links.append(f"[Читать]({links['read']})")
    if links["download"]:
        visible_links.append(f"[Скачать]({links['download']})")
    if visible_links:
        st.markdown(f"**Автореферат:** {' · '.join(visible_links)}")


def _show_metadata(row: pd.Series) -> None:
    labels = [("Автор", "candidate_name"), ("Название", "title"), ("Год", "year"), ("Отрасль наук", "degree.science_field")]
    for label, col in labels:
        st.markdown(f"**{label}:** {_value(row, col) or '—'}")
    st.markdown(f"**Специальность:** {_specialty_value(row) or '—'}")
    _render_abstract_links(_value(row, "Code"), _value(row, "candidate_name"))


def _render_sections_view(df: pd.DataFrame) -> None:
    row = _select_dissertation(df, "diss_char_view")
    if row is None:
        return
    _show_metadata(row)
    sections = load_dissertation_sections_by_code(_value(row, "Code"))
    sections = sections[sections["section_key"].isin(DISPLAY_SECTION_KEYS)]
    sections = sections[sections["text"].fillna("").astype(str).str.strip() != ""]
    if sections.empty:
        st.warning("Для выбранной диссертации нет извлечённых разделов.")
        return
    order = {key: i for i, key in enumerate(DISPLAY_SECTION_KEYS)}
    sections = sections.assign(_order=sections["section_key"].map(order)).sort_values(["section_order", "_order"])
    for _, sec in sections.iterrows():
        with st.expander(str(sec["section_label"])):
            st.write(str(sec["text"]))


def _enrich_results(results: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    if results.empty or "Code" not in df.columns:
        return results
    meta = df.drop_duplicates("Code").set_index(df["Code"].astype(str))
    out = results.copy()
    for col in ["candidate_name", "title", "year", "degree.science_field"]:
        out[col] = out["Code"].astype(str).map(meta[col] if col in meta.columns else {})
    if "text" not in out.columns and "text_id" in out.columns:
        texts = load_dissertation_section_texts_by_ids(out["text_id"].tolist())
        if not texts.empty:
            by_id = texts.drop_duplicates("text_id").set_index("text_id")
            out["text"] = out["text_id"].map(by_id["text"])
    return out


def _show_results(results: pd.DataFrame) -> None:
    if results.empty:
        st.warning("Похожие разделы не найдены.")
        return
    for _, row in results.iterrows():
        title = f"{int(row['rank'])}. {row.get('section_label', '')} — сходство {float(row.get('similarity', 0)):.3f}"
        with st.expander(title, expanded=int(row["rank"]) <= 3):
            st.markdown(f"**Автор:** {row.get('candidate_name', '—')}")
            st.markdown(f"**Название:** {row.get('title', '—')}")
            st.markdown(f"**Год:** {row.get('year', '—')}")
            st.markdown(f"**Отрасль наук:** {row.get('degree.science_field', '—')}")
            _render_abstract_links(str(row.get("Code", "")), str(row.get("candidate_name", "")))
            for col in [c for c in results.columns if c.startswith("query_similarity_")]:
                n = col.rsplit("_", 1)[1]
                st.caption(f"Сходство с запросом {n}: {float(row[col]):.3f}; вклад запроса {n}: {float(row.get('query_weight_' + n, 0)):.1f}%")
            st.write(str(row.get("text", "")))


def _matrix_ready() -> tuple[object | None, bool]:
    matrix = load_current_dissertation_matrix()
    if matrix is None or len(matrix.shape) != 2:
        st.warning("Семантический поиск недоступен: матрица векторов не найдена или имеет неверный формат.")
        return None, False
    return matrix, True


def _render_similar_search(df: pd.DataFrame, index_df: pd.DataFrame, metadata: dict[str, str]) -> None:
    row = _select_dissertation(df, "diss_char_similar")
    if row is None:
        return
    code = _value(row, "Code")
    sections = load_dissertation_sections_by_code(code)
    sections = sections[sections["section_key"].isin(SEARCHABLE_SECTION_KEYS)].dropna(subset=["matrix_row"])
    if sections.empty:
        st.warning("У выбранной диссертации нет разделов, доступных для семантического поиска.")
        return
    selected_text_id = st.selectbox("Исходный раздел", sections["text_id"].tolist(), format_func=lambda tid: str(sections.set_index("text_id").loc[tid, "section_label"]), key="diss_char_source_section")
    source = sections[sections["text_id"] == selected_text_id].iloc[0]
    same_type = st.checkbox("Искать только среди разделов того же типа", value=True, key="diss_char_same_type")
    if same_type:
        section_keys = [str(source["section_key"])]
    else:
        section_keys = st.multiselect("Типы разделов для поиска", SEARCHABLE_SECTION_KEYS, default=SEARCHABLE_SECTION_KEYS, format_func=lambda k: SECTION_LABELS_RU.get(k, k), key="diss_char_target_types")
    top_n = st.number_input("Количество результатов", min_value=1, max_value=100, value=10, step=1, key="diss_char_similar_top")
    run_search = st.button("Поиск", type="primary", key="diss_char_similar_search_button")
    if not run_search:
        st.caption("Настройте параметры и нажмите «Поиск».")
        return
    matrix, ready = _matrix_ready()
    if not ready:
        return
    targets = filter_targets_for_similar_search(index_df, code, section_keys)
    normalized = str(metadata.get("normalized", "true")).casefold() in {"1", "true", "yes", "да"}
    results = search_similar_dissertation_sections(int(source["matrix_row"]), matrix, targets, int(top_n), get_search_batch_size(), normalized)
    _show_results(_enrich_results(results, df))


def _render_query_search(df: pd.DataFrame, index_df: pd.DataFrame, metadata: dict[str, str]) -> None:
    values = [st.text_input(f"Запрос {i}", key=f"diss_char_query_{i}") for i in range(1, 4)]
    queries = collect_non_empty_queries(values, max_queries=5)
    section_keys = st.multiselect("Типы разделов для поиска", SEARCHABLE_SECTION_KEYS, default=SEARCHABLE_SECTION_KEYS, format_func=lambda k: SECTION_LABELS_RU.get(k, k), key="diss_char_query_types")
    top_n = st.number_input("Количество результатов", min_value=1, max_value=100, value=10, step=1, key="diss_char_query_top")
    run_search = st.button("Поиск", type="primary", key="diss_char_query_search_button")
    if not run_search:
        st.caption("Введите запрос и нажмите «Поиск».")
        return
    if not queries:
        st.warning("Введите один или несколько запросов.")
        return
    matrix, ready = _matrix_ready()
    if not ready:
        return
    targets = index_df[index_df["section_key"].isin(section_keys)].copy()
    model_name = metadata.get("model_name") or "intfloat/multilingual-e5-base"
    normalized = str(metadata.get("normalized", "true")).casefold() in {"1", "true", "yes", "да"}
    try:
        vectors = encode_user_queries(queries, model_name, normalized, get_query_encoder_device())
        results = search_dissertation_sections_by_query_vector(vectors, matrix, targets, int(top_n), get_search_batch_size(), normalized)
    except Exception:
        st.warning("Не удалось выполнить нейросетевой поиск по запросу.")
        return
    _show_results(_enrich_results(results, df))


def render_dissertation_characteristics_tab(df: pd.DataFrame) -> None:
    """Рисует вкладку просмотра и поиска характеристик диссертаций."""
    st.markdown("## Характеристики диссертаций")
    st.caption("Раздел содержит извлечённые элементы общей характеристики диссертаций: актуальность, цель, объект, предмет, задачи, методы, научную новизну, значимость и другие разделы автореферата.")
    st.markdown("### Фильтр отраслей наук")
    default_fields = hydrate_science_fields_from_query_params()
    science_field_ids = render_science_field_filter(key_prefix="dissertation_characteristics", default_selected_ids=default_fields)
    filtered_df = filter_df_by_science_fields(df, science_field_ids)
    caption = science_field_filter_caption(science_field_ids)
    if science_field_ids:
        caption += f" После фильтрации осталось диссертаций: {len(filtered_df)} из {len(df)}."
    st.caption(caption)

    diagnostics = load_dissertation_sections_diagnostics()
    for warning in diagnostics.get("warnings", [])[:3]:
        st.warning(str(warning))

    allowed_codes = set(filtered_df["Code"].astype(str)) if filtered_df is not None and "Code" in filtered_df.columns else set()
    linked_codes = load_dissertation_section_codes(allowed_codes=allowed_codes)
    linked = _linked_df(filtered_df, linked_codes)
    if linked.empty:
        st.warning("Нет связанных записей между основной базой диссертаций и базой извлечённых разделов.")

    searchable_index = load_dissertation_section_index(allowed_codes=allowed_codes, searchable_only=True, include_text=False)
    metadata = load_vector_metadata() if diagnostics.get("db_exists") else {}
    encoder_available = is_query_encoder_available()
    names = ["Разделы характеристики", "Поиск похожих разделов"] + (["Нейросетевой поиск по разделам"] if encoder_available else [])
    subtabs = st.tabs(names)
    with subtabs[0]:
        _render_sections_view(linked)
    with subtabs[1]:
        _render_similar_search(linked, searchable_index, metadata)
    if encoder_available:
        with subtabs[2]:
            _render_query_search(linked, searchable_index, metadata)
    else:
        st.caption("Нейросетевой поиск по текстовому запросу недоступен: на сервере не установлен энкодер запросов.")
