"""
utils/table_display.py — утилиты для отображения таблиц диссертаций в UI.

Модуль предоставляет переиспользуемые функции и константы, которые можно
применять на любых вкладках, где нужно показать список диссертаций
(деревья, поиск, анализ школ и т.д.).

Публичный API:
    COLUMN_ALIASES          — dict: исходное имя колонки → алиас без точек
                              (нужен при переходе на SQLite, где точки в именах
                              колонок недопустимы)
    COLUMN_LABELS           — dict: исходное/алиасное имя → русское название
    TREE_TABLE_COLUMNS      — list: упорядоченный список исходных колонок
                              для таблицы на вкладке «Построение деревьев»
    make_abstract_link(code, name) -> str
        Возвращает URL автореферата (или пустую строку) по коду диссертации.
    make_abstract_label(code) -> str
        Возвращает текстовую метку ссылки: «Скачать», «Читать» или «».
    build_tree_display_df(subset) -> pd.DataFrame
        Формирует DataFrame для отображения в st.dataframe():
        добавляет две колонки — «Скачать» (URL для PDF) и «Читать» (URL для
        онлайн-просмотра). Пустые значения скрываются Streamlit автоматически.
    build_tree_export_df(subset) -> tuple[pd.DataFrame, pd.DataFrame]
        Формирует два DataFrame для экспорта:
        - xlsx_df: для Excel (колонка «Автореферат» = формула HYPERLINK)
        - csv_df:  для CSV (колонка «Автореферат» = плоская ссылка)
"""

from __future__ import annotations

import re
from urllib.parse import quote

import pandas as pd


# ---------------------------------------------------------------------------
# Алиасы колонок: точки → нижние подчёркивания
# Нужны для совместимости с SQLite, где точки в именах колонок запрещены.
# При переходе на SQLite достаточно переименовать колонки один раз при загрузке
# и везде использовать алиасы.
# ---------------------------------------------------------------------------

COLUMN_ALIASES: dict[str, str] = {
    # степень и отрасль
    "degree.degree_level":  "degree_degree_level",
    "degree.science_field": "degree_science_field",
    # специальности
    "specialties_1.code":   "specialties_1_code",
    "specialties_1.name":   "specialties_1_name",
    "specialties_2.code":   "specialties_2_code",
    "specialties_2.name":   "specialties_2_name",
    # научные руководители
    "supervisors_1.name":   "supervisors_1_name",
    "supervisors_1.degree": "supervisors_1_degree",
    "supervisors_1.title":  "supervisors_1_rank",   # title → rank
    "supervisors_2.name":   "supervisors_2_name",
    "supervisors_2.degree": "supervisors_2_degree",
    "supervisors_2.title":  "supervisors_2_rank",   # title → rank
    # оппоненты
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

# Обратный словарь: алиас → исходное имя
_ALIAS_TO_ORIGINAL: dict[str, str] = {v: k for k, v in COLUMN_ALIASES.items()}


def _resolve(col: str) -> str:
    """Возвращает исходное имя колонки, принимая как исходное, так и алиасное."""
    return _ALIAS_TO_ORIGINAL.get(col, col)


# ---------------------------------------------------------------------------
# Русские названия колонок
# Ключи — исходные имена с точками (canonical form).
# ---------------------------------------------------------------------------

COLUMN_LABELS: dict[str, str] = {
    # вычисляемые колонки автореферата (раздельные)
    "abstract_download":       "Скачать",
    "abstract_read":           "Читать",
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
    # руководители
    "supervisors_1.name":      "Научный руководитель",
    "supervisors_1.degree":    "Степень руководителя",
    "supervisors_1.title":     "Звание руководителя",
    "supervisors_2.name":      "Науч. руководитель 2",
    "supervisors_2.degree":    "Степень руководителя 2",
    "supervisors_2.title":     "Звание руководителя 2",
    # место защиты / организации
    "institution_prepared":    "Организация выполнения",
    "defense_location":        "Место защиты",
    "city":                    "Город защиты",
    "defense_council":         "Диссертационный совет",
    "leading_organization":    "Ведущая организация",
    # оппоненты
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

# Добавляем алиасные варианты в COLUMN_LABELS, чтобы поиск работал по обоим именам
for _orig, _alias in COLUMN_ALIASES.items():
    if _orig in COLUMN_LABELS:
        COLUMN_LABELS[_alias] = COLUMN_LABELS[_orig]


# ---------------------------------------------------------------------------
# Порядок колонок для таблицы «Построение деревьев»
# Первыми идут две раздельные колонки автореферата, затем все остальные.
# ---------------------------------------------------------------------------

TREE_TABLE_COLUMNS: list[str] = [
    # вычисляемые колонки: «Скачать» (PDF) и «Читать» (онлайн)
    "abstract_download",
    "abstract_read",
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


# ---------------------------------------------------------------------------
# Логика формирования ссылок автореферата
# ---------------------------------------------------------------------------

_URL_DOWNLOAD = (
    "https://rusneb.ru/local/tools/exalead/getFiles.php"
    "?book_id={code}&name={encoded_name}&doc_type=pdf"
)
_URL_READ = "https://viewer.rusneb.ru/ru/{code}?page=1"
_RE_NUMERIC = re.compile(r'^[0-9_]+$')


def make_abstract_link(code: str, name: str) -> str:
    """
    Возвращает URL автореферата диссертации в зависимости от формата кода.

    Правила:
    - Если code состоит только из цифр и нижних подчёркиваний
      (например, «000199_000009_003279301») — ссылка на скачивание PDF.
      Пробелы в ФИО кодируются через urllib.parse.quote.
    - Если code содержит подстроку «NLR» — ссылка для онлайн-просмотра.
    - В остальных случаях возвращается пустая строка.

    Args:
        code: Код диссертации из колонки «Code».
        name: ФИО автора — используется как имя файла PDF.

    Returns:
        Строка-URL или пустая строка «».

    Examples:
        >>> make_abstract_link("000199_000009_003279301", "Иванов Иван Иванович")
        'https://rusneb.ru/local/tools/exalead/getFiles.php?book_id=000199_000009_003279301&name=%D0%90%D0%B2%D1%82%D0%BE%D1%80%D0%B5%D1%84%D0%B5%D1%80%D0%B0%D1%82.+%D0%98%D0%B2%D0%B0%D0%BD%D0%BE%D0%B2+%D0%98%D0%B2%D0%B0%D0%BD+%D0%98%D0%B2%D0%B0%D0%BD%D0%BE%D0%B2%D0%B8%D1%87&doc_type=pdf'
        >>> make_abstract_link("000200_000018_RU_NLR_bibl_574554", "Петров Пётр")
        'https://viewer.rusneb.ru/ru/000200_000018_RU_NLR_bibl_574554?page=1'
        >>> make_abstract_link("", "Кто-то")
        ''
    """
    code = str(code).strip()
    if not code:
        return ""
    if _RE_NUMERIC.match(code):
        file_name = f"Автореферат. {str(name).strip()}"
        encoded_name = quote(file_name, safe="")
        return _URL_DOWNLOAD.format(code=code, encoded_name=encoded_name)
    if "NLR" in code:
        return _URL_READ.format(code=code)
    return ""


def make_abstract_label(code: str) -> str:
    """
    Возвращает текстовую метку ссылки на автореферат:
    «Скачать», «Читать» или пустая строка.

    Используется совместно с make_abstract_link.

    Args:
        code: Код диссертации.

    Returns:
        'Скачать' — если только цифры/подчёркивания
        'Читать'   — если содержит NLR
        ''         — в остальных случаях
    """
    code = str(code).strip()
    if not code:
        return ""
    if _RE_NUMERIC.match(code):
        return "Скачать"
    if "NLR" in code:
        return "Читать"
    return ""


def make_abstract_download_url(code: str, name: str) -> str:
    """
    Возвращает URL для скачивания PDF-автореферата, если code состоит
    только из цифр и нижних подчёркиваний. Иначе — пустую строку.

    Это отдельная функция для использования в колонке «Скачать»
    при разделённом отображении (две LinkColumn вместо одной).

    Args:
        code: Код диссертации.
        name: ФИО автора.

    Returns:
        URL-строка или ''.
    """
    code = str(code).strip()
    if code and _RE_NUMERIC.match(code):
        file_name = f"Автореферат. {str(name).strip()}"
        encoded_name = quote(file_name, safe="")
        return _URL_DOWNLOAD.format(code=code, encoded_name=encoded_name)
    return ""


def make_abstract_read_url(code: str) -> str:
    """
    Возвращает URL для онлайн-просмотра автореферата, если code содержит
    подстроку «NLR». Иначе — пустую строку.

    Это отдельная функция для использования в колонке «Читать»
    при разделённом отображении (две LinkColumn вместо одной).

    Args:
        code: Код диссертации.

    Returns:
        URL-строка или ''.
    """
    code = str(code).strip()
    if code and "NLR" in code:
        return _URL_READ.format(code=code)
    return ""


# ---------------------------------------------------------------------------
# Формирование отображаемого DataFrame для таблицы деревьев
# ---------------------------------------------------------------------------

def _build_ordered_df(subset: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """
    Внутренняя функция: вычисляет abstract_download / abstract_read
    и упорядочивает колонки согласно TREE_TABLE_COLUMNS.
    Возвращает (df_extended, ordered_cols_list).

    Примечание о дизайне:
        Вместо единой колонки «Автореферат» используются две раздельные
        LinkColumn — «Скачать» (только PDF) и «Читать» (только NLR).
        Это позволяет Streamlit правильно отображать разные метки ссылок,
        т.к. display_text в LinkColumn принимает regex-паттерн для URL,
        а не имя другой колонки DataFrame.
    """
    df = subset.copy().reset_index(drop=True)
    code_col = "Code" if "Code" in df.columns else None
    name_col = "candidate_name" if "candidate_name" in df.columns else None

    if code_col and name_col:
        df["abstract_download"] = df.apply(
            lambda row: make_abstract_download_url(
                row.get(code_col, ""), row.get(name_col, "")
            ),
            axis=1,
        )
        df["abstract_read"] = df[code_col].apply(make_abstract_read_url)
    else:
        df["abstract_download"] = ""
        df["abstract_read"] = ""

    ordered_cols: list[str] = []
    for col in TREE_TABLE_COLUMNS:
        if col in ("abstract_download", "abstract_read"):
            if col in df.columns:
                ordered_cols.append(col)
        elif col in df.columns:
            ordered_cols.append(col)

    return df, ordered_cols


def build_tree_display_df(subset: pd.DataFrame) -> pd.DataFrame:
    """
    Формирует DataFrame для отображения в st.dataframe() на вкладке
    «Построение деревьев».

    Что делает:
    1. Вычисляет колонку «abstract_download» (URL PDF) через
       make_abstract_download_url — заполняется только для кодов из цифр/_.
    2. Вычисляет колонку «abstract_read» (URL NLR) через
       make_abstract_read_url — заполняется только для кодов с «NLR».
    3. Отбирает и упорядочивает колонки согласно TREE_TABLE_COLUMNS.
    4. Переименовывает в русские названия («Скачать» / «Читать» / ...).

    Почему две колонки, а не одна:
        Streamlit LinkColumn.display_text принимает regex-паттерн для URL,
        а не имя другой колонки. Разделив ссылки на две колонки, мы получаем
        нативную поддержку: «Скачать» показывается только там, где есть PDF,
        «Читать» — только там, где есть NLR. Пустые ячейки Streamlit
        не отображает как ссылки.

    Args:
        subset: DataFrame с исходными колонками (из lineage в graph.py).

    Returns:
        DataFrame с русскими названиями колонок. Первые две колонки —
        «Скачать» (LinkColumn) и «Читать» (LinkColumn).

    Note:
        Для правильной отрисовки используйте в st.dataframe():

            st.dataframe(
                display_df,
                column_config={
                    "Скачать": st.column_config.LinkColumn(
                        label="Скачать",
                        display_text="Скачать",
                    ),
                    "Читать": st.column_config.LinkColumn(
                        label="Читать",
                        display_text="Читать",
                    ),
                },
                use_container_width=True,
            )

        См. _render_tree_table() в school_trees_tab.py для примера.
    """
    if subset.empty:
        final_cols = [COLUMN_LABELS.get(c, c) for c in TREE_TABLE_COLUMNS]
        return pd.DataFrame(columns=final_cols)

    df, ordered_cols = _build_ordered_df(subset)
    df_out = df[ordered_cols]
    rename_map = {col: COLUMN_LABELS.get(col, col) for col in ordered_cols}
    return df_out.rename(columns=rename_map)


def build_tree_export_df(subset: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Формирует два DataFrame для экспорта (скачивания) таблицы диссертаций.

    Колонка «Автореферат»:
    - xlsx_df: формула Excel =HYPERLINK("url","Скачать") или =HYPERLINK("url","Читать")
               для кликабельных ссылок. Если у диссертации нет ни одной ссылки — пусто.
    - csv_df:  плоская ссылка (URL-строка) — из abstract_download или abstract_read.
               Если нет ни одной — пусто.

    Оба DataFrame содержат русские названия колонок из COLUMN_LABELS
    и следуют порядку TREE_TABLE_COLUMNS (кроме abstract_download/abstract_read,
    которые объединяются в одну колонку «Автореферат»).

    Args:
        subset: DataFrame с исходными колонками (из lineage в graph.py).

    Returns:
        (xlsx_df, csv_df) — кортеж из двух DataFrame.

    Usage:
        xlsx_df, csv_df = build_tree_export_df(subset)

        # Excel с гиперссылками
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            xlsx_df.to_excel(writer, index=False)
        xlsx_bytes = buf.getvalue()

        # CSV с плоскими URL
        csv_bytes = csv_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    """
    abstract_ru = "Автореферат"

    if subset.empty:
        # Порядок для экспорта: abstract_download/read заменяются на одну колонку
        export_cols = []
        for c in TREE_TABLE_COLUMNS:
            if c == "abstract_download":
                export_cols.append(abstract_ru)
            elif c == "abstract_read":
                pass  # пропускаем — уже добавлена как «Автореферат»
            else:
                export_cols.append(COLUMN_LABELS.get(c, c))
        empty = pd.DataFrame(columns=export_cols)
        return empty, empty.copy()

    df, ordered_cols = _build_ordered_df(subset)

    # Строим базовый df для экспорта: abstract_download + abstract_read → «Автореферат»
    rows_xlsx: list[dict] = []
    rows_csv: list[dict] = []

    for _, row in df.iterrows():
        xlsx_row: dict = {}
        csv_row: dict = {}
        seen_abstract = False
        for col in ordered_cols:
            if col == "abstract_download":
                if not seen_abstract:
                    dl_url = row.get("abstract_download", "")
                    rd_url = row.get("abstract_read", "")
                    if dl_url:
                        xlsx_row[abstract_ru] = f'=HYPERLINK("{dl_url}","Скачать")'
                        csv_row[abstract_ru] = dl_url
                    elif rd_url:
                        xlsx_row[abstract_ru] = f'=HYPERLINK("{rd_url}","Читать")'
                        csv_row[abstract_ru] = rd_url
                    else:
                        xlsx_row[abstract_ru] = ""
                        csv_row[abstract_ru] = ""
                    seen_abstract = True
            elif col == "abstract_read":
                pass  # уже обработано выше
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
