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
        добавляет колонку «Автореферат» (URL) и «_abstract_label» (текст),
        применяет порядок и русские названия.
    build_tree_export_df(subset) -> tuple[pd.DataFrame, pd.DataFrame]
        Формирует два DataFrame для экспорта:
        - xlsx_df: для Excel (колонка «Автореферат» = формула HYPERLINK)
        - csv_df:  для CSV (колонка «Автореферат» = плоская ссылка)
"""

from __future__ import annotations

import io
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
    # вычисляемая колонка
    "abstract":                "Автореферат",
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
# ---------------------------------------------------------------------------

TREE_TABLE_COLUMNS: list[str] = [
    # вычисляемая — добавляется в build_tree_display_df
    "abstract",
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
# Логика формирования ссылки и метки автореферата
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
        'https://rusneb.ru/...'
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

    Используется совместно с make_abstract_link: в st.dataframe()
    LinkColumn отображает URL-колонку («Автореферат»), а рядом стоит
    текстовая колонка «_abstract_label», скрытая визуально через
    column_config в school_trees_tab.py.

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


# ---------------------------------------------------------------------------
# Формирование отображаемого DataFrame для таблицы деревьев
# ---------------------------------------------------------------------------

def _build_ordered_df(subset: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """
    Внутренняя функция: вычисляет abstract/abstract_label и
    упорядочивает колонки согласно TREE_TABLE_COLUMNS.
    Возвращает (df_ordered, ordered_cols_list).
    """
    df = subset.copy().reset_index(drop=True)
    code_col = "Code" if "Code" in df.columns else None
    name_col = "candidate_name" if "candidate_name" in df.columns else None

    if code_col and name_col:
        df["abstract"] = df.apply(
            lambda row: make_abstract_link(row.get(code_col, ""), row.get(name_col, "")),
            axis=1,
        )
        df["_abstract_label"] = df[code_col].apply(make_abstract_label)
    else:
        df["abstract"] = ""
        df["_abstract_label"] = ""

    ordered_cols: list[str] = []
    for col in TREE_TABLE_COLUMNS:
        if col == "abstract":
            if "abstract" in df.columns:
                ordered_cols.append("abstract")
        elif col in df.columns:
            ordered_cols.append(col)

    return df, ordered_cols


def build_tree_display_df(subset: pd.DataFrame) -> pd.DataFrame:
    """
    Формирует DataFrame для отображения в st.dataframe() на вкладке
    «Построение деревьев».

    Что делает:
    1. Вычисляет колонку «abstract» (URL) через make_abstract_link.
    2. Добавляет служебную колонку «_abstract_label» («Скачать»/«Читать»/«»)
       через make_abstract_label. В UI эта колонка скрывается через
       column_config (hidden=True), но Streamlit использует её как
       display_text для LinkColumn «Автореферат».
    3. Отбирает и упорядочивает колонки согласно TREE_TABLE_COLUMNS.
    4. Переименовывает в русские названия.

    Args:
        subset: DataFrame с исходными колонками (из lineage в graph.py).

    Returns:
        DataFrame с русскими названиями колонок и служебной колонкой
        «_abstract_label» в конце.

    Note:
        Для правильной отрисовки используйте в st.dataframe():

            col_label = "Автореферат"
            st.dataframe(
                display_df,
                column_config={
                    col_label: st.column_config.LinkColumn(
                        label=col_label,
                        display_text="_abstract_label",  # имя колонки с меткой
                    ),
                    "_abstract_label": st.column_config.Column(disabled=True),
                },
                use_container_width=True,
            )

        См. _render_tree_table() в school_trees_tab.py для примера полной настройки.
    """
    if subset.empty:
        final_cols = [COLUMN_LABELS.get(c, c) for c in TREE_TABLE_COLUMNS if c in COLUMN_LABELS]
        return pd.DataFrame(columns=final_cols + ["_abstract_label"])

    df, ordered_cols = _build_ordered_df(subset)
    df_out = df[ordered_cols + ["_abstract_label"]]
    rename_map = {col: COLUMN_LABELS.get(col, col) for col in ordered_cols}
    return df_out.rename(columns=rename_map)


def build_tree_export_df(subset: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Формирует два DataFrame для экспорта (скачивания) таблицы диссертаций.

    Отличие от build_tree_display_df:
    - xlsx_df: колонка «Автореферат» содержит формулу Excel
      =HYPERLINK("url","Метка") для кликабельных ссылок.
    - csv_df:  колонка «Автореферат» содержит плоскую ссылку (URL-строку)
      для формата, не поддерживающего HTML.

    Оба DataFrame содержат русские названия колонок из COLUMN_LABELS
    и следуют порядку TREE_TABLE_COLUMNS (без служебных полей).

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
    if subset.empty:
        final_cols = [COLUMN_LABELS.get(c, c) for c in TREE_TABLE_COLUMNS if c in COLUMN_LABELS]
        empty = pd.DataFrame(columns=final_cols)
        return empty, empty.copy()

    df, ordered_cols = _build_ordered_df(subset)

    # Для экспорта не нужна служебная колонка _abstract_label
    df_base = df[ordered_cols].copy()
    rename_map = {col: COLUMN_LABELS.get(col, col) for col in ordered_cols}
    df_base = df_base.rename(columns=rename_map)

    abstract_ru = COLUMN_LABELS.get("abstract", "Автореферат")

    # --- xlsx_df: заменяем URL на формулу Excel HYPERLINK
    xlsx_df = df_base.copy()
    if abstract_ru in xlsx_df.columns:
        label_series = df["_abstract_label"]  # 'Скачать'/'Читать'/''
        xlsx_df[abstract_ru] = [
            f'=HYPERLINK("{url}","{lbl}")' if url and lbl else ""
            for url, lbl in zip(xlsx_df[abstract_ru], label_series)
        ]

    # --- csv_df: оставляем плоский URL как есть
    csv_df = df_base.copy()

    return xlsx_df, csv_df
