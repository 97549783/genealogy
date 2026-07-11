"""
core/ui/table_display.py — утилиты для отображения таблиц диссертаций в UI.

Модуль предоставляет переиспользуемые функции и константы, которые можно
применять на любых вкладках, где нужно показать список диссертаций
(деревья, поиск, анализ школ и т.д.).

Публичный API:
    COLUMN_ALIASES          — dict: исходное имя колонки → алиас без точек
    COLUMN_LABELS           — dict: исходное/алиасное имя → русское название
    TREE_TABLE_COLUMNS      — list: упорядоченный список исходных колонок
                              для таблицы на вкладке «Построение деревьев»
    make_abstract_links_html(code, name) -> str
        Возвращает HTML-фрагмент с одной или двумя ссылками (Читать / Скачать)
        через пробел, либо пустую строку.
    make_abstract_read_url(code) -> str
        URL для онлайн-просмотра (viewer.rusneb.ru) — для числовых кодов
        и NLR-кодов.
    build_tree_display_df(subset) -> pd.DataFrame
        Формирует DataFrame для рендера HTML-таблицы:
        добавляет колонку «abstract_html» с HTML-ссылками.
    build_tree_st_dataframe_df(subset) -> tuple[pd.DataFrame, dict]
        Формирует DataFrame с плоскими колонками для st.dataframe:
        - колонки «Автореферат» и «PDF-файл» — LinkColumn
        - возвращает также column_config
    build_tree_export_df(subset) -> tuple[pd.DataFrame, pd.DataFrame]
        Формирует два DataFrame для экспорта:
        - xlsx_df: для Excel (колонка «Автореферат» = формула HYPERLINK)
        - csv_df:  для CSV (колонка «Автореферат» = URL для viewer)
"""

from __future__ import annotations

import hashlib
import io
import re
from urllib.parse import quote

import pandas as pd


# ---------------------------------------------------------------------------
# Алиасы колонок: точки → нижние подчёркивания
# ---------------------------------------------------------------------------

COLUMN_ALIASES: dict[str, str] = {
    "degree.degree_level":  "degree_degree_level",
    "degree.science_field": "degree_science_field",
    "specialties_1.code":   "specialties_1_code",
    "specialties_1.name":   "specialties_1_name",
    "specialties_2.code":   "specialties_2_code",
    "specialties_2.name":   "specialties_2_name",
    "supervisors_1.name":   "supervisors_1_name",
    "supervisors_1.degree": "supervisors_1_degree",
    "supervisors_1.title":  "supervisors_1_rank",
    "supervisors_2.name":   "supervisors_2_name",
    "supervisors_2.degree": "supervisors_2_degree",
    "supervisors_2.title":  "supervisors_2_rank",
    "opponents_1.name":     "opponents_1_name",
    "opponents_1.degree":   "opponents_1_degree",
    "opponents_1.title":    "opponents_1_rank",
    "opponents_2.name":     "opponents_2_name",
    "opponents_2.degree":   "opponents_2_degree",
    "opponents_2.title":    "opponents_2_rank",
    "opponents_3.name":     "opponents_3_name",
    "opponents_3.degree":   "opponents_3_degree",
    "opponents_3.title":    "opponents_3_rank",
}

_ALIAS_TO_ORIGINAL: dict[str, str] = {v: k for k, v in COLUMN_ALIASES.items()}


def _resolve(col: str) -> str:
    return _ALIAS_TO_ORIGINAL.get(col, col)


# ---------------------------------------------------------------------------
# Русские названия колонок
# ---------------------------------------------------------------------------

COLUMN_LABELS: dict[str, str] = {
    # вычисляемая колонка — одна HTML-колонка «Автореферат»
    "abstract_html":           "Автореферат",
    # основные поля
    "candidate_name":          "Автор диссертации",
    "title":                   "Название диссертации",
    "year":                    "Год защиты",
    "degree.degree_level":     "Учёная степень",
    "degree.science_field":    "Отрасль науки",
    "specialties_1.code":      "Шифр специальности",
    "specialties_1.name":      "Специальность",
    "specialties_2.code":      "Шифр специальности 2",
    "specialties_2.name":      "Специальность 2",
    "supervisors_1.name":      "Научный руководитель",
    "supervisors_1.degree":    "Степень руководителя",
    "supervisors_1.title":     "Звание руководителя",
    "supervisors_2.name":      "Науч. руководитель 2",
    "supervisors_2.degree":    "Степень руководителя 2",
    "supervisors_2.title":     "Звание руководителя 2",
    "institution_prepared":    "Организация выполнения",
    "defense_location":        "Место защиты",
    "city":                    "Город защиты",
    "defense_council":         "Диссертационный совет",
    "leading_organization":    "Ведущая организация",
    "opponents_1.name":        "Оппонент 1",
    "opponents_1.degree":      "Степень оппонента 1",
    "opponents_1.title":       "Звание оппонента 1",
    "opponents_2.name":        "Оппонент 2",
    "opponents_2.degree":      "Степень оппонента 2",
    "opponents_2.title":       "Звание оппонента 2",
    "opponents_3.name":        "Оппонент 3",
    "opponents_3.degree":      "Степень оппонента 3",
    "opponents_3.title":       "Звание оппонента 3",
}

for _orig, _alias in COLUMN_ALIASES.items():
    if _orig in COLUMN_LABELS:
        COLUMN_LABELS[_alias] = COLUMN_LABELS[_orig]


# ---------------------------------------------------------------------------
# Порядок колонок для таблицы «Построение деревьев»
# ---------------------------------------------------------------------------

TREE_TABLE_COLUMNS: list[str] = [
    "abstract_html",
    "candidate_name",
    "title",
    "year",
    "degree.degree_level",
    "degree.science_field",
    "specialties_1.code",
    "specialties_1.name",
    "specialties_2.code",
    "specialties_2.name",
    "supervisors_1.name",
    "supervisors_1.degree",
    "supervisors_1.title",
    "supervisors_2.name",
    "supervisors_2.degree",
    "supervisors_2.title",
    "institution_prepared",
    "defense_location",
    "city",
    "defense_council",
    "leading_organization",
    "opponents_1.name",
    "opponents_1.degree",
    "opponents_1.title",
    "opponents_2.name",
    "opponents_2.degree",
    "opponents_2.title",
    "opponents_3.name",
    "opponents_3.degree",
    "opponents_3.title",
]

_DATA_COLUMNS: list[str] = [c for c in TREE_TABLE_COLUMNS if c != "abstract_html"]

# Имена плоских колонок для ссылок в st.dataframe.
_COL_READ = "Автореферат"
_COL_DOWNLOAD = "PDF-файл"

DEFAULT_PAGE_SIZE = 200
PAGE_SIZE_OPTIONS = (100, 200, 500)


# ---------------------------------------------------------------------------
# Логика формирования ссылок автореферата
# ---------------------------------------------------------------------------

_URL_DOWNLOAD = (
    "https://rusneb.ru/local/tools/exalead/getFiles.php"
    "?book_id={code}&name={encoded_name}&doc_type=pdf"
)
_URL_READ = "https://viewer.rusneb.ru/ru/{code}?page=1"
_RE_NUMERIC = re.compile(r'^[0-9_]+$')


def make_abstract_read_url(code: str) -> str:
    """
    Возвращает URL для онлайн-просмотра автореферата (viewer.rusneb.ru)
    для числовых кодов (только цифры и '_') и NLR-кодов.
    В остальных случаях — пустая строка.
    """
    code = str(code).strip()
    if not code:
        return ""
    if _RE_NUMERIC.match(code) or "NLR" in code:
        return _URL_READ.format(code=code)
    return ""


def make_abstract_download_url_numeric(code: str, name: str) -> str:
    """
    Возвращает URL для скачивания PDF автореферата.
    Только для числовых кодов (только цифры и '_').
    """
    code = str(code).strip()
    if code and _RE_NUMERIC.match(code):
        file_name = f"Автореферат. {str(name).strip()}"
        encoded_name = quote(file_name, safe="")
        return _URL_DOWNLOAD.format(code=code, encoded_name=encoded_name)
    return ""


def make_abstract_links_html(code: str, name: str) -> str:
    """
    Возвращает HTML-фрагмент со ссылками на автореферат для HTML-таблицы.
    """
    code = str(code).strip()
    if not code:
        return ""
    read_url = _URL_READ.format(code=code)
    if _RE_NUMERIC.match(code):
        file_name = f"Автореферат. {str(name).strip()}"
        encoded_name = quote(file_name, safe="")
        dl_url = _URL_DOWNLOAD.format(code=code, encoded_name=encoded_name)
        return (
            f'<a href="{read_url}" target="_blank">Читать</a>'
            f' <a href="{dl_url}" target="_blank">Скачать</a>'
        )
    if "NLR" in code:
        return f'<a href="{read_url}" target="_blank">Читать</a>'
    return ""


# Обратная совместимость
def make_abstract_link(code: str, name: str) -> str:
    return make_abstract_links_html(code, name)


def make_abstract_label(code: str) -> str:
    code = str(code).strip()
    if not code:
        return ""
    if _RE_NUMERIC.match(code):
        return "Скачать"
    if "NLR" in code:
        return "Читать"
    return ""


def make_abstract_download_url(code: str, name: str) -> str:
    return make_abstract_download_url_numeric(code, name)


def make_abstract_read_url_nlr_only(code: str) -> str:
    code = str(code).strip()
    if code and "NLR" in code:
        return _URL_READ.format(code=code)
    return ""


# ---------------------------------------------------------------------------
# Формирование отображаемого DataFrame (для HTML-рендера)
# ---------------------------------------------------------------------------

def _build_ordered_df(subset: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    df = subset.copy().reset_index(drop=True)
    code_col = "Code" if "Code" in df.columns else None
    name_col = "candidate_name" if "candidate_name" in df.columns else None

    if code_col and name_col:
        df["abstract_html"] = df.apply(
            lambda row: make_abstract_links_html(
                row.get(code_col, ""), row.get(name_col, "")
            ),
            axis=1,
        )
    else:
        df["abstract_html"] = ""

    ordered_cols: list[str] = []
    for col in TREE_TABLE_COLUMNS:
        if col == "abstract_html":
            if col in df.columns:
                ordered_cols.append(col)
        elif col in df.columns:
            ordered_cols.append(col)

    return df, ordered_cols


def build_tree_display_df(subset: pd.DataFrame) -> pd.DataFrame:
    if subset.empty:
        final_cols = [COLUMN_LABELS.get(c, c) for c in TREE_TABLE_COLUMNS]
        return pd.DataFrame(columns=final_cols)

    df, ordered_cols = _build_ordered_df(subset)
    df_out = df[ordered_cols]
    rename_map = {col: COLUMN_LABELS.get(col, col) for col in ordered_cols}
    return df_out.rename(columns=rename_map)


def build_tree_st_dataframe_df(
    subset: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    """
    Формирует DataFrame с плоскими строковыми колонками для st.dataframe.

    Колонки для ссылок:
      - «Автореферат» — LinkColumn, URL viewer.rusneb.ru
      - «PDF-файл»    — LinkColumn, URL rusneb.ru PDF

    Правила заполнения:
      - Числовой код: обе ссылки
      - NLR-код: только «Автореферат»
      - Иначе: пустые строки

    ВАЖНО: НЕ используется pd.MultiIndex и НЕ используется group=
    в column_config — эти опции не поддерживаются в текущей версии Streamlit.

    Returns:
        (df_flat, column_config): DataFrame со строковыми ключами +
        dict с column_config для st.dataframe.
    """
    import streamlit as st

    col_cfg: dict = {
        _COL_READ: st.column_config.LinkColumn(
            "Автореферат",
            display_text="Читать",
            help="Открыть автореферат в онлайн-просмотрщике",
        ),
        _COL_DOWNLOAD: st.column_config.LinkColumn(
            "PDF-файл",
            display_text="Скачать",
            help="Скачать PDF автореферата",
        ),
    }

    if subset.empty:
        cols = [_COL_READ, _COL_DOWNLOAD]
        for col in _DATA_COLUMNS:
            ru = COLUMN_LABELS.get(col, col)
            cols.append(ru)
        return pd.DataFrame(columns=cols), col_cfg

    df = subset.copy().reset_index(drop=True)
    code_col = "Code" if "Code" in df.columns else None
    name_col = "candidate_name" if "candidate_name" in df.columns else None

    def _read_url(code: str) -> str:
        code = str(code).strip()
        if not code:
            return ""
        if _RE_NUMERIC.match(code) or "NLR" in code:
            return _URL_READ.format(code=code)
        return ""

    if code_col and name_col:
        read_urls = df.apply(lambda r: _read_url(str(r.get(code_col, ""))), axis=1)
        dl_urls = df.apply(
            lambda r: make_abstract_download_url_numeric(
                str(r.get(code_col, "")), str(r.get(name_col, ""))
            ),
            axis=1,
        )
    else:
        read_urls = pd.Series([""] * len(df))
        dl_urls = pd.Series([""] * len(df))

    out: dict[str, list] = {
        _COL_READ: read_urls.tolist(),
        _COL_DOWNLOAD: dl_urls.tolist(),
    }
    for col in _DATA_COLUMNS:
        if col not in df.columns:
            continue
        ru = COLUMN_LABELS.get(col, col)
        out[ru] = df[col].fillna("").astype(str).tolist()

    return pd.DataFrame(out), col_cfg


def build_tree_export_df(subset: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Формирует два DataFrame для экспорта.
    Колонка «Автореферат»:
    - xlsx: =HYPERLINK(url) — viewer-ссылка для числовых и NLR-кодов
    - csv:  URL viewer-ссылки
    """
    abstract_ru = "Автореферат"

    if subset.empty:
        export_cols = []
        for c in TREE_TABLE_COLUMNS:
            if c == "abstract_html":
                export_cols.append(abstract_ru)
            else:
                export_cols.append(COLUMN_LABELS.get(c, c))
        empty = pd.DataFrame(columns=export_cols)
        return empty, empty.copy()

    df, ordered_cols = _build_ordered_df(subset)

    rows_xlsx: list[dict] = []
    rows_csv: list[dict] = []

    for _, row in df.iterrows():
        xlsx_row: dict = {}
        csv_row: dict = {}
        for col in ordered_cols:
            if col == "abstract_html":
                code = str(row.get("Code", "")).strip()
                read_url = make_abstract_read_url(code)
                if read_url:
                    xlsx_row[abstract_ru] = f'=HYPERLINK("{read_url}","Читать")'
                    csv_row[abstract_ru] = read_url
                else:
                    xlsx_row[abstract_ru] = ""
                    csv_row[abstract_ru] = ""
            else:
                ru_name = COLUMN_LABELS.get(col, col)
                val = row.get(col, "")
                xlsx_row[ru_name] = val
                csv_row[ru_name] = val
        rows_xlsx.append(xlsx_row)
        rows_csv.append(csv_row)

    return pd.DataFrame(rows_xlsx), pd.DataFrame(rows_csv)



def paginate_dataframe(
    df: pd.DataFrame,
    page_number: int,
    page_size: int,
) -> tuple[pd.DataFrame, int, int]:
    """Returns page DataFrame, normalized page number, and total page count."""
    page_size = int(page_size) if int(page_size) > 0 else DEFAULT_PAGE_SIZE
    total = len(df)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page_number = min(max(int(page_number or 1), 1), total_pages)
    start = (page_number - 1) * page_size
    end = start + page_size
    return df.iloc[start:end], page_number, total_pages


def build_dissertation_result_signature(subset: pd.DataFrame) -> str:
    h = hashlib.blake2b(digest_size=16)
    h.update(str(len(subset)).encode())
    h.update("\0".join(map(str, subset.columns)).encode("utf-8", "surrogatepass"))
    if "Code" in subset.columns:
        values = subset["Code"].astype(str)
    else:
        values = subset.index.astype(str)
    for value in values:
        h.update(b"\0")
        h.update(str(value).encode("utf-8", "surrogatepass"))
    return h.hexdigest()


def build_dissertations_csv_bytes(subset: pd.DataFrame) -> bytes:
    _, csv_df = build_tree_export_df(subset)
    return csv_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")


def build_dissertations_xlsx_bytes(subset: pd.DataFrame) -> bytes:
    xlsx_df, _ = build_tree_export_df(subset)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        xlsx_df.to_excel(writer, index=False, sheet_name="Диссертации")
    return buf.getvalue()

def render_dissertations_widget(
    subset: pd.DataFrame,
    key: str,
    title: str = "Результаты",
    expanded: bool = False,
    file_name_prefix: str | None = None,
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
    result_signature: str | None = None,
) -> None:
    """Универсальный UI-виджет таблицы диссертаций + ленивый экспорт.

    Phase 1 pagination reduces display transformation and WebSocket transfer,
    but broad searches may still materialize the complete source DataFrame.
    Server-side result handles and SQL LIMIT/keyset pagination are deferred.
    """
    import streamlit as st

    file_base = file_name_prefix or key
    total = len(subset)
    label = f"📋 {title} ({total})"

    with st.expander(label, expanded=expanded):
        if subset.empty:
            st.info("Данные отсутствуют.")
            return

        result_signature = result_signature or build_dissertation_result_signature(subset)
        export_state_key = f"prepared_export_{key}"
        state = st.session_state.get(export_state_key)
        if not isinstance(state, dict) or state.get("signature") != result_signature:
            state = {"signature": result_signature, "xlsx": None, "csv": None}
            st.session_state[export_state_key] = state

        selected_page_size = int(page_size)
        if total > page_size:
            selected_page_size = st.selectbox(
                "Строк на странице",
                PAGE_SIZE_OPTIONS,
                index=PAGE_SIZE_OPTIONS.index(page_size) if page_size in PAGE_SIZE_OPTIONS else 1,
                key=f"page_size_{key}",
            )
            requested_page = st.number_input(
                "Страница",
                min_value=1,
                value=int(st.session_state.get(f"page_number_{key}", 1)),
                step=1,
                key=f"page_number_{key}",
            )
        else:
            requested_page = 1

        page_df, current_page, total_pages = paginate_dataframe(subset, int(requested_page), selected_page_size)
        if total > selected_page_size:
            st.session_state[f"page_number_{key}"] = current_page
        start_row = (current_page - 1) * selected_page_size + 1
        end_row = min(start_row + len(page_df) - 1, total)
        st.caption(f"Показаны строки {start_row}–{end_row} из {total}")

        df_st, col_cfg = build_tree_st_dataframe_df(page_df)
        st.dataframe(
            df_st,
            column_config=col_cfg,
            use_container_width=True,
            hide_index=True,
            key=f"df_table_{key}",
        )

        col_xlsx, col_csv = st.columns(2)
        with col_xlsx:
            if st.button("Подготовить Excel", key=f"prepare_xlsx_{key}", use_container_width=True):
                try:
                    with st.spinner("Подготовка Excel…"):
                        state["xlsx"] = build_dissertations_xlsx_bytes(subset)
                    st.session_state[export_state_key] = state
                except Exception as exc:
                    state["xlsx"] = None
                    st.error(f"Ошибка создания Excel: {exc}")
            if state.get("xlsx") is not None:
                st.download_button(
                    label="📊 Скачать Excel",
                    data=state["xlsx"],
                    file_name=f"{file_base}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"dl_xlsx_{key}",
                    use_container_width=True,
                )
        with col_csv:
            if st.button("Подготовить CSV", key=f"prepare_csv_{key}", use_container_width=True):
                try:
                    with st.spinner("Подготовка CSV…"):
                        state["csv"] = build_dissertations_csv_bytes(subset)
                    st.session_state[export_state_key] = state
                except Exception as exc:
                    state["csv"] = None
                    st.error(f"Ошибка создания CSV: {exc}")
            if state.get("csv") is not None:
                st.download_button(
                    label="📄 Скачать CSV",
                    data=state["csv"],
                    file_name=f"{file_base}.csv",
                    mime="text/csv",
                    key=f"dl_csv_{key}",
                    use_container_width=True,
                )
