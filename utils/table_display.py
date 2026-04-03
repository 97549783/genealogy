"""
utils/table_display.py — утилиты для отображения таблиц диссертаций в UI.

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
        Формирует DataFrame с pd.MultiIndex-заголовками для st.dataframe:
        - колонки «Читать» и «Скачать» объединены под верхним уровнем «Автореферат»
        - возвращает также column_config для LinkColumn
    build_tree_export_df(subset) -> tuple[pd.DataFrame, pd.DataFrame]
        Формирует два DataFrame для экспорта:
        - xlsx_df: для Excel (колонка «Автореферат» = формула HYPERLINK)
        - csv_df:  для CSV (колонка «Автореферат» = URL для viewer,
                  если код числовой; иначе NLR viewer-ссылка)
"""

from __future__ import annotations

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
# Первой идёт одна колонка «Автореферат» (HTML), затем все остальные.
# ---------------------------------------------------------------------------

TREE_TABLE_COLUMNS: list[str] = [
    "abstract_html",        # единая колонка: Читать + Скачать
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

# Колонки данных (без abstract_html) — используются в build_tree_st_dataframe_df
_DATA_COLUMNS: list[str] = [c for c in TREE_TABLE_COLUMNS if c != "abstract_html"]


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

    Используется в экспорте (CSV/xlsx) в колонке «Автореферат».

    Args:
        code: Код диссертации.

    Returns:
        URL-строка или ''.

    Examples:
        >>> make_abstract_read_url("000199_000009_003279301")
        'https://viewer.rusneb.ru/ru/000199_000009_003279301?page=1'
        >>> make_abstract_read_url("000200_000018_RU_NLR_bibl_574554")
        'https://viewer.rusneb.ru/ru/000200_000018_RU_NLR_bibl_574554?page=1'
        >>> make_abstract_read_url("")
        ''
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
    В остальных случаях — пустая строка.

    Args:
        code: Код диссертации.
        name: ФИО автора — используется как имя файла PDF.

    Returns:
        URL-строка или ''.
    """
    code = str(code).strip()
    if code and _RE_NUMERIC.match(code):
        file_name = f"Автореферат. {str(name).strip()}"
        encoded_name = quote(file_name, safe="")
        return _URL_DOWNLOAD.format(code=code, encoded_name=encoded_name)
    return ""


def make_abstract_links_html(code: str, name: str) -> str:
    """
    Возвращает HTML-фрагмент со ссылками на автореферат для отображения
    в HTML-таблице (через st.html).

    Правила:
    - Числовой код (только цифры и '_'):
        <a href="viewer.rusneb.ru/...">Читать</a> <a href="rusneb.ru/...">Скачать</a>
    - NLR-код:
        <a href="viewer.rusneb.ru/...">Читать</a>
    - Иначе: пустая строка.

    Args:
        code: Код диссертации из колонки «Code».
        name: ФИО автора — используется как имя файла PDF.

    Returns:
        HTML-строка с тегами <a> или ''.

    Examples:
        >>> make_abstract_links_html("000199_000009_003279301", "Иванов И.И.")
        '<a href="https://viewer.rusneb.ru/ru/000199_000009_003279301?page=1" target="_blank">Читать</a> <a href="https://rusneb.ru/local/tools/exalead/getFiles.php?book_id=000199_000009_003279301&name=...&doc_type=pdf" target="_blank">Скачать</a>'
        >>> make_abstract_links_html("000200_000018_RU_NLR_bibl_574554", "Петров П.")
        '<a href="https://viewer.rusneb.ru/ru/000200_000018_RU_NLR_bibl_574554?page=1" target="_blank">Читать</a>'
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


# Обратная совместимость: старые имена функций, используемые в других модулях
def make_abstract_link(code: str, name: str) -> str:
    """Устаревшая функция. Использует make_abstract_links_html."""
    return make_abstract_links_html(code, name)


def make_abstract_label(code: str) -> str:
    """Устаревшая функция. Возвращает текстовую метку."""
    code = str(code).strip()
    if not code:
        return ""
    if _RE_NUMERIC.match(code):
        return "Скачать"
    if "NLR" in code:
        return "Читать"
    return ""


def make_abstract_download_url(code: str, name: str) -> str:
    """Устаревшая функция. Возвращает URL для скачивания PDF."""
    return make_abstract_download_url_numeric(code, name)


def make_abstract_read_url_nlr_only(code: str) -> str:
    """Устаревшая функция. Возвращает URL только для NLR-кодов."""
    code = str(code).strip()
    if code and "NLR" in code:
        return _URL_READ.format(code=code)
    return ""


# ---------------------------------------------------------------------------
# Формирование отображаемого DataFrame (для HTML-рендера)
# ---------------------------------------------------------------------------

def _build_ordered_df(subset: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """
    Вычисляет колонку abstract_html и упорядочивает колонки
    согласно TREE_TABLE_COLUMNS.
    """
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
    """
    Формирует DataFrame для рендера HTML-таблицы на вкладке
    «Построение деревьев».

    Колонка «abstract_html» содержит HTML-фрагменты со ссылками:
    - Числовой код → «Читать» + «Скачать» (через пробел)
    - NLR-код      → только «Читать»
    - Иначе        → пустая строка

    Используется совместно с render_dissertation_html_table() в
    school_trees_tab.py, которая рендерит DataFrame через st.html.

    Args:
        subset: DataFrame с исходными колонками (из lineage в graph.py).

    Returns:
        DataFrame с русскими названиями колонок. Первая колонка —
        «Автореферат» (HTML-фрагмент со ссылками).
    """
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
    Формирует DataFrame с pd.MultiIndex-заголовками для отображения через
    st.dataframe с LinkColumn.

    Структура заголовков (2 уровня):
    - Верхний уровень «Автореферат» объединяет подколонки «Читать» и «Скачать».
    - Для остальных колонок верхний уровень — пустая строка, нижний —
      русское название колонки.

    Правила заполнения ссылок:
    - Числовой код (только цифры и '_'):
        Читать → https://viewer.rusneb.ru/ru/{code}?page=1
        Скачать → https://rusneb.ru/local/tools/exalead/getFiles.php?...
    - NLR-код:
        Читать → https://viewer.rusneb.ru/ru/{code}?page=1
        Скачать → None (пустая строка)
    - Иначе:
        Читать → None, Скачать → None

    Args:
        subset: DataFrame с исходными колонками (из lineage в graph.py).

    Returns:
        Кортеж (df_multiindex, column_config):
        - df_multiindex: DataFrame с pd.MultiIndex в колонках.
        - column_config: dict для параметра column_config в st.dataframe.
    """
    import streamlit as st  # импорт здесь, чтобы не тянуть в тестах

    if subset.empty:
        # Возвращаем пустой DataFrame с правильной структурой заголовков
        tuples: list[tuple[str, str]] = [
            ("Автореферат", "Читать"),
            ("Автореферат", "Скачать"),
        ]
        for col in _DATA_COLUMNS:
            ru = COLUMN_LABELS.get(col, col)
            tuples.append(("", ru))
        mi = pd.MultiIndex.from_tuples(tuples)
        return pd.DataFrame(columns=mi), {}

    df = subset.copy().reset_index(drop=True)
    code_col = "Code" if "Code" in df.columns else None
    name_col = "candidate_name" if "candidate_name" in df.columns else None

    # --- Вычисляем URL для ссылок ---
    def _read_url(code: str) -> str:
        code = str(code).strip()
        if not code:
            return ""
        if _RE_NUMERIC.match(code) or "NLR" in code:
            return _URL_READ.format(code=code)
        return ""

    def _dl_url(code: str, name: str) -> str:
        return make_abstract_download_url_numeric(code, name)

    if code_col and name_col:
        read_urls = df.apply(
            lambda r: _read_url(r.get(code_col, "")), axis=1
        )
        dl_urls = df.apply(
            lambda r: _dl_url(r.get(code_col, ""), r.get(name_col, "")), axis=1
        )
    else:
        read_urls = pd.Series([""] * len(df))
        dl_urls = pd.Series([""] * len(df))

    # --- Собираем данные колонок в порядке MultiIndex ---
    col_data: dict[tuple[str, str], list] = {}
    col_data[("Автореферат", "Читать")] = read_urls.tolist()
    col_data[("Автореферат", "Скачать")] = dl_urls.tolist()

    for col in _DATA_COLUMNS:
        if col not in df.columns:
            continue
        ru = COLUMN_LABELS.get(col, col)
        col_data[("", ru)] = df[col].fillna("").astype(str).tolist()

    df_out = pd.DataFrame(col_data)
    df_out.columns = pd.MultiIndex.from_tuples(list(col_data.keys()))

    # --- Строим column_config ---
    column_config: dict = {
        ("Автореферат", "Читать"): st.column_config.LinkColumn(
            "Читать",
            display_text="Читать",
            help="Открыть автореферат в онлайн-просмотрщике",
        ),
        ("Автореферат", "Скачать"): st.column_config.LinkColumn(
            "Скачать",
            display_text="Скачать",
            help="Скачать PDF автореферата",
        ),
    }

    return df_out, column_config


def build_tree_export_df(subset: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Формирует два DataFrame для экспорта (скачивания) таблицы диссертаций.

    Колонка «Автореферат»:
    - xlsx_df: формула Excel =HYPERLINK("url","Читать") — viewer-ссылка
               для числовых кодов и NLR-кодов. Если нет ни одной — пусто.
    - csv_df:  плоская viewer-ссылка для числовых кодов и NLR-кодов.
               Если нет ни одной — пусто.

    Изменение vs предыдущей версии:
        Ранее CSV для числовых кодов содержал ссылку на скачивание PDF.
        Теперь — ссылку на viewer (Читать), что удобнее для копирования.

    Args:
        subset: DataFrame с исходными колонками (из lineage в graph.py).

    Returns:
        (xlsx_df, csv_df) — кортеж из двух DataFrame.
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
                # Получаем code напрямую из исходного df
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

    xlsx_df = pd.DataFrame(rows_xlsx)
    csv_df = pd.DataFrame(rows_csv)
    return xlsx_df, csv_df
