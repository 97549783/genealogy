# streamlit_app.py
# -------------------------------------------------------------
# Точка входа приложения: конфигурация, заголовок, вкладки.
# Вся бизнес-логика вынесена в utils/ и *_tab.py.
# -------------------------------------------------------------

from __future__ import annotations

import os
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd
import streamlit as st

# ---------------------- Утилиты (utils/) ----------------------------------
from utils.db import load_data, AUTHOR_COLUMN, SUPERVISOR_COLUMNS, FEEDBACK_FILE
from utils.graph import build_index, TREE_OPTIONS
from utils.ui import (
    feedback_button,
    show_instruction,
)
from utils.table_display import render_dissertations_widget
from utils.urls import share_params_button

# ---------------------- Вкладки ------------------------------------------
from school_trees_tab import render_school_trees_tab
from profiles_tab import render_profiles_tab
from opponents_intersection_tab import render_opponents_intersection_tab
from school_search_tab import render_school_search_tab
from school_analysis_tab import render_school_analysis_tab
from school_comparison_tab import render_school_comparison_tab
# from school_comparison_new_tab import render_school_comparison_new_tab
from articles_comparison_tab import render_articles_comparison_tab

# ---------------------- Тематический классификатор -----------------------
# (остаётся здесь, т.к. используется в нескольких вкладках напрямую и
#  не связан ни с БД, ни с графами — это данные предметной области)
ClassifierItem = Tuple[str, str, bool]

THEMATIC_CLASSIFIER: List[ClassifierItem] = [
    ("1.1", "Среда и предметная область", True),
    ("1.1.1", "Уровень формального образования", True),
    ("1.1.1.1", "Дошкольное образование", False),
    ("1.1.1.2", "Школьное образование", False),
    ("1.1.1.2.1", "Начальное общее образование", False),
    ("1.1.1.2.2", "Основное общее образование", False),
    ("1.1.1.2.3", "Среднее общее образование", False),
    ("1.1.1.3", "Среднее профессиональное образование (СПО)", False),
    ("1.1.1.4", "Высшее образование", False),
    ("1.1.1.4.1", "Высшее образование – Бакалавриат", False),
    ("1.1.1.4.2", "Высшее образование – Специалитет", False),
    ("1.1.1.4.3", "Высшее образование – Магистратура", False),
    ("1.1.1.5", "Подготовка кадров высшей квалификации", False),
    ("1.1.1.5.1", "Подготовка кадров высшей квалификации – Аспирантура", False),
    ("1.1.1.5.2", "Подготовка кадров высшей квалификации – Ординатура", False),
    ("1.1.1.6", "Дополнительное профессиональное образование", False),
    ("1.1.1.6.1", "Дополнительное профессиональное образование – Повышение квалификации", False),
    ("1.1.1.6.2", "Дополнительное профессиональное образование – Профессиональная переподготовка", False),
    ("1.1.1.7", "Дополнительное образование детей и взрослых", False),
    ("1.1.1.8", "Профессиональное обучение", False),
    ("1.1.2", "Предметный цикл / Область знания", True),
    ("1.1.2.1", "Математические и естественнонаучные дисциплины", False),
    ("1.1.2.1.1", "Математика", False),
    ("1.1.2.1.2", "Информатика", False),
    ("1.1.2.1.3", "Физика", False),
    ("1.1.2.1.4", "Химия", False),
    ("1.1.2.1.5", "Биология", False),
    ("1.1.2.1.6", "Другие естественнонаучные дисциплины", False),
    ("1.1.2.2", "Гуманитарные и социальные дисциплины", False),
    ("1.1.2.2.1", "Филология", False),
    ("1.1.2.2.1.1", "Языки", False),
    ("1.1.2.2.1.1.1", "Русский язык", False),
    ("1.1.2.2.1.1.2", "Язык народов России", False),
    ("1.1.2.2.1.1.3", "Иностранный язык", False),
    ("1.1.2.2.1.1.3.1", "Английский язык", False),
    ("1.1.2.2.1.1.3.2", "Немецкий язык", False),
    ("1.1.2.2.1.1.3.3", "Французский язык", False),
    ("1.1.2.2.1.1.3.4", "Иной иностранный язык", False),
    ("1.1.2.2.1.2", "Литература", False),
    ("1.1.2.2.2", "История", False),
    ("1.1.2.2.3", "Обществознание, социология", False),
    ("1.1.2.2.4", "Социально-экономическая география", False),
    ("1.1.2.2.5", "Экономика", False),
    ("1.1.2.2.6", "Право", False),
    ("1.1.2.2.7", "Другие гуманитарные и общественные дисциплины", False),
    ("1.1.2.3", "Изобразительное и музыкальное искусство", False),
    ("1.1.2.4", "Технология", False),
    ("1.1.2.5", "Физическая культура и спорт", False),
    ("1.1.2.6", "Инженерно-техническое направление", False),
    ("1.1.2.7", "Психолого-педагогическое направление", False),
    ("1.1.2.8", "Междисциплинарные и надпредметные области", False),
    ("1.2", "Субъект образования (когорта)", True),
    ("1.2.1", "Социально-профессиональная группа", True),
    ("1.2.1.1", "Обучающиеся общеобразовательных организаций", False),
    ("1.2.1.2", "Студенты колледжей и техникумов (СПО)", False),
    ("1.2.1.3", "Студенты вузов (ВО)", False),
    ("1.2.1.4", "Действующие специалисты (в системе ДПО)", False),
    ("1.2.1.5", "Педагогические и научные кадры (как объект развития)", False),
    ("1.2.1.6", "Военнослужащие / сотрудники силовых структур", False),
    ("1.2.1.7", "Спортсмены", False),
    ("1.2.2", "Специфические образовательные потребности", True),
    ("1.2.2.1", "Обучающиеся с ОВЗ и/или инвалидностью", False),
    ("1.2.2.2", "Одаренные и высокомотивированные обучающиеся", False),
    ("1.2.2.3", "Обучающиеся из групп социального риска", False),
    ("1.2.2.4", "Инофоны / образовательные мигранты", False),
    ("2.1", "Тип и масштаб разрабатываемого решения", True),
    ("2.1.1", "Уровень абстракции", True),
    ("2.1.1.1", "Теоретико-методологическая концепция", False),
    ("2.1.1.2", "Структурно-функциональная модель", False),
    ("2.1.1.3", "Организационно-педагогическая система", False),
    ("2.1.1.4", "Педагогическая технология", False),
    ("2.1.1.5", "Частная методика преподавания", False),
    ("2.1.1.6", "Комплекс педагогических условий", False),
    ("2.1.1.7", "Образовательная/воспитательная программа", False),
    ("2.1.2", "Доминирующая педагогическая парадигма", True),
    ("2.1.2.1", "Знаниевая (традиционная)", False),
    ("2.1.2.2", "Компетентностная", False),
    ("2.1.2.3", "Системно-деятельностная", False),
    ("2.1.2.4", "Личностно-ориентированная / Гуманистическая", False),
    ("2.1.2.5", "Аксиологическая (ценностная)", False),
    ("2.1.2.6", "Контекстная / Проблемная", False),
    ("2.2", "Технологии и методы педагогического воздействия", True),
    ("2.2.1", "Ведущая форма организации деятельности", True),
    ("2.2.1.1", "Репродуктивная учебная деятельность", False),
    ("2.2.1.2", "Проектная деятельность", False),
    ("2.2.1.3", "Исследовательская деятельность", False),
    ("2.2.1.4", "Игровая деятельность (дидактическая, деловая, ролевая)", False),
    ("2.2.1.5", "Дискуссионные формы (дискуссия, дебаты)", False),
    ("2.2.1.6", "Художественно-творческая деятельность", False),
    ("2.2.1.7", "Спортивно-тренировочная деятельность", False),
    ("2.2.2", "Используемые средства обучения", True),
    ("2.2.2.1", "Текстовые и печатные средства (учебник, рабочая тетрадь)", False),
    ("2.2.2.2", "Аудиовизуальные средства (видео, презентации)", False),
    ("2.2.2.3", "Интерактивные цифровые ресурсы (тренажеры, симуляторы, ЭОР)", False),
    ("2.2.2.4", "Средства виртуальной и дополненной реальности (VR/AR)", False),
    ("2.2.2.5", "Платформенные решения (LMS, онлайн-курсы)", False),
    ("2.2.2.6", "Средства геймификации", False),
    ("2.2.3", "Доминирующий тип педагогического взаимодействия", True),
    ("2.2.3.1", "Прямое управление (инструктаж, объяснение)", False),
    ("2.2.3.2", "Фасилитация / Модерация", False),
    ("2.2.3.3", "Тьюторское сопровождение / Наставничество", False),
    ("2.2.3.4", "Консультирование", False),
    ("3.1", "Когнитивная сфера", True),
    ("3.1.1", "Предметные знания и представления", False),
    ("3.1.2", "Методологические знания", False),
    ("3.1.3", "Критическое мышление", False),
    ("3.1.4", "Креативное (творческое) мышление", False),
    ("3.1.5", "Системное / Проектное мышление", False),
    ("3.1.6", "Научное / Профессиональное мировоззрение", False),
    ("3.2", "Деятельностно-практическая сфера", True),
    ("3.2.1", "Предметные умения и навыки (Hard Skills)", False),
    ("3.2.2", "Универсальные навыки (Soft Skills)", False),
    ("3.2.2.1", "Коммуникативные навыки", False),
    ("3.2.2.2", "Навыки кооперации и работы в команде", False),
    ("3.2.2.3", "Навыки самоорганизации и тайм-менеджмента", False),
    ("3.2.2.4", "Навыки решения проблем (problem-solving)", False),
    ("3.2.3", "Профессиональные компетенции", False),
    ("3.2.4", "Метапредметные / Ключевые компетенции", False),
    ("3.2.5", "Социальная компетентность", False),
    ("3.3", "Личностно-ценностная сфера", True),
    ("3.3.1", "Мотивация (учебная, профессиональная)", False),
    ("3.3.2", "Ценностные ориентации", False),
    ("3.3.3", "Волевая саморегуляция", False),
    ("3.3.4", "Рефлексивные способности", False),
    ("3.3.5", "Интегративные личностные конструкты", True),
    ("3.3.5.1", "Готовность (к деятельности, самообразованию и др.)", False),
    ("3.3.5.2", "Субъектность / Субъектная позиция", False),
    ("3.3.5.3", "Идентичность (профессиональная, гражданская)", False),
    ("3.3.5.4", "Патриотизм / Гражданственность", False),
    ("3.3.6", "Формируемый тип культуры личности", True),
    ("3.3.6.1", "Информационная культура", False),
    ("3.3.6.2", "Правовая культура", False),
    ("3.3.6.3", "Экологическая культура", False),
    ("3.3.6.4", "Физическая культура", False),
    ("3.3.6.5", "Профессиональная культура", False),
    ("3.3.6.6", "Культура безопасности жизнедеятельности", False),
]

CLASSIFIER_BY_CODE: Dict[str, ClassifierItem] = {
    code: (code, title, disabled) for code, title, disabled in THEMATIC_CLASSIFIER
}

PROFILE_SELECTION_SESSION_KEY = "profile_selected_codes"
PROFILE_SELECTION_LIMIT = 5
PROFILE_MIN_SCORE = 4.0


def classifier_depth(code: str) -> int:
    return code.count(".") if code else 0


def classifier_format(option: Optional[ClassifierItem]) -> str:
    if option is None:
        return "— выберите пункт —"
    code, title, disabled = option
    indent = "\u2003" * classifier_depth(code)
    label = f"{code} {title}"
    if disabled:
        label += " (нельзя выбрать)"
    return f"{indent}{label}"


def classifier_label(code: str) -> str:
    item = CLASSIFIER_BY_CODE.get(code)
    if not item:
        return code
    _, title, _ = item
    return f"{code} · {title}"


# ---------------------- Оформление страницы -------------------------------
st.set_page_config(page_title="Академические родословные", layout="wide")

st.markdown("""
<meta name="google" content="notranslate">
<style>
  iframe { width: 100%; }
</style>
""", unsafe_allow_html=True)

# ---------------------- Секретная страница администратора -----------------
# Доступна только по URL: ?secret=nb39fdv94beraaagv2evdc9ewr3fokv
# Отображает содержимое feedback.csv без кнопки скачивания.
_ADMIN_SECRET = "nb39fdv94beraaagv2evdc9ewr3fokv"

if st.query_params.get("secret") == _ADMIN_SECRET:
    st.title("📋 Обратная связь")
    if FEEDBACK_FILE.exists():
        fb_df = pd.read_csv(FEEDBACK_FILE)
        st.caption(f"Всего записей: {len(fb_df)}")
        st.table(fb_df)
    else:
        st.info("Файл feedback.csv пока не существует — нет ни одного сообщения.")
    st.stop()

# ---------------------- Шапка --------------------------------------------
header_left, header_right = st.columns([0.78, 0.22])
with header_left:
    st.title("📚 Академическая генеалогия")
    st.caption(
        "Платформа для построения деревьев научного руководства, поиска и сравнения "
        "диссертаций по содержательным и формальным критериям. В настоящий момент "
        "основу базы данных составляют авторефераты диссертационных исследований "
        "по педагогическим наукам с 1995 года."
    )
with header_right:
    feedback_button()


# ---------------------- Загрузка данных ----------------------------------
try:
    df = load_data()
except Exception as e:
    st.error(f"Ошибка при загрузке данных: {e}")
    st.stop()

missing = [c for c in [AUTHOR_COLUMN, *SUPERVISOR_COLUMNS] if c not in df.columns]
if missing:
    st.error("Отсутствуют нужные колонки: " + ", ".join(f"`{c}`" for c in missing))
    st.stop()

idx = build_index(df, SUPERVISOR_COLUMNS)

all_supervisor_names: Set[str] = set()
for col in SUPERVISOR_COLUMNS:
    all_supervisor_names.update({v for v in df[col].dropna().astype(str).unique() if v})

shared_roots = st.query_params.get_all("root")
valid_shared_roots = [r for r in shared_roots if r in all_supervisor_names]

if not st.session_state.get("diss_search_query_hydrated", False):
    criteria_q = [
        c for c in st.query_params.get_all("diss_criterion")
        if c in {
            "title", "candidate_name", "supervisors", "opponents",
            "institution_prepared", "leading_organization", "defense_location",
            "city", "year", "specialties",
        }
    ]
    if criteria_q:
        st.session_state["dissertation_search_criteria"] = criteria_q
        for criterion in criteria_q:
            q_val = str(st.query_params.get(f"diss_{criterion}", "")).strip()
            if q_val:
                st.session_state[f"diss_search_{criterion}"] = q_val
        st.session_state["diss_search_should_run"] = True
    st.session_state["diss_search_query_hydrated"] = True


# ---------------------- Вкладки ------------------------------------------
(
    tab_lineages,
    tab_dissertations,
    tab_profiles,
    tab_school_search,
    tab_intersection,
    tab_school_analysis,
    #tab_schoolcomparison,
    #tab_articles_comparison,
) = st.tabs([
    "Построение деревьев",
    "Поиск информации о диссертациях",
    "Поиск по тематическим профилям",
    "Поиск научных школ",
    "Взаимосвязи научных школ",
    "Анализ научной школы",
    #"Сравнение научных школ",
    #"Сравнение по статьям",
])

# ---------- Вкладка: Построение деревьев ---------------------------------
with tab_lineages:
    render_school_trees_tab(
        df=df,
        idx=idx,
        all_supervisor_names=all_supervisor_names,
        shared_roots=valid_shared_roots,
    )

# ---------- Вкладка: Поиск информации о диссертациях ---------------------
with tab_dissertations:
    if st.button("📖 Инструкция", key="instruction_dissertations"):
        show_instruction("dissertations")

    st.subheader("Поиск информации о диссертациях")
    st.write("На этой вкладке доступен поиск диссертаций по формальным критериям.")

    all_years = sorted(
        [str(y) for y in df["year"].dropna().unique() if str(y).strip()], reverse=True
    )
    all_cities = sorted(
        [str(c) for c in df["city"].dropna().unique() if str(c).strip()]
    )
    all_specialties: Set[str] = set()
    for col in ["specialties_1.code", "specialties_1.name", "specialties_2.code", "specialties_2.name"]:
        if col in df.columns:
            all_specialties.update([str(v).strip() for v in df[col].dropna().unique() if str(v).strip()])
    all_specialties_sorted = sorted(all_specialties)

    available_criteria = {
        "title": "Название диссертации",
        "candidate_name": "ФИО автора",
        "supervisors": "ФИО научного руководителя",
        "opponents": "ФИО оппонента",
        "institution_prepared": "Организация выполнения",
        "leading_organization": "Ведущая организация",
        "defense_location": "Место защиты",
        "city": "Город защиты",
        "year": "Год защиты",
        "specialties": "Специальность",
    }

    st.markdown("### 1. Выбор критериев поиска")
    selected_criteria = st.multiselect(
        "Выберите критерии поиска (максимум 5 одновременно)",
        options=list(available_criteria.keys()),
        format_func=lambda x: available_criteria[x],
        max_selections=5,
        key="dissertation_search_criteria",
    )

    if not selected_criteria:
        st.info("Выберите хотя бы один критерий для поиска.")
    else:
        st.markdown("### 2. Ввод данных")
        search_params: Dict[str, str] = {}

        for criterion in selected_criteria:
            if criterion == "year":
                search_params[criterion] = st.selectbox(
                    available_criteria[criterion],
                    options=["Все"] + all_years,
                    key=f"diss_search_{criterion}",
                )
            elif criterion == "city":
                search_params[criterion] = st.selectbox(
                    available_criteria[criterion],
                    options=["Все"] + all_cities,
                    key=f"diss_search_{criterion}",
                )
            elif criterion == "specialties":
                search_params[criterion] = st.selectbox(
                    available_criteria[criterion],
                    options=["Все"] + all_specialties_sorted,
                    key=f"diss_search_{criterion}",
                )
            else:
                search_params[criterion] = st.text_input(
                    available_criteria[criterion],
                    placeholder=f"Введите {available_criteria[criterion].lower()}...",
                    key=f"diss_search_{criterion}",
                )

        st.markdown("### 3. Результат")

        if st.button("Найти", type="primary", key="dissertation_search_button"):
            st.session_state["diss_search_should_run"] = True

        if st.session_state.get("diss_search_should_run", False):
            result_df = df.copy()
            for criterion, value in search_params.items():
                if not value or value == "Все":
                    continue
                if criterion in [
                    "title", "candidate_name", "institution_prepared",
                    "leading_organization", "defense_location",
                ]:
                    result_df = result_df[
                        result_df[criterion].astype(str).str.contains(value, case=False, na=False)
                    ]
                elif criterion == "supervisors":
                    mask = pd.Series([False] * len(result_df), index=result_df.index)
                    for col in ["supervisors_1.name", "supervisors_2.name"]:
                        if col in result_df.columns:
                            mask |= result_df[col].astype(str).str.contains(value, case=False, na=False)
                    result_df = result_df[mask]
                elif criterion == "opponents":
                    mask = pd.Series([False] * len(result_df), index=result_df.index)
                    for col in ["opponents_1.name", "opponents_2.name", "opponents_3.name"]:
                        if col in result_df.columns:
                            mask |= result_df[col].astype(str).str.contains(value, case=False, na=False)
                    result_df = result_df[mask]
                elif criterion in ["city", "year"]:
                    result_df = result_df[
                        result_df[criterion].astype(str).str.contains(value, case=False, na=False)
                    ]
                elif criterion == "specialties":
                    mask = pd.Series([False] * len(result_df), index=result_df.index)
                    for col in [
                        "specialties_1.code", "specialties_1.name",
                        "specialties_2.code", "specialties_2.name",
                    ]:
                        if col in result_df.columns:
                            mask |= result_df[col].astype(str).str.contains(value, case=False, na=False)
                    result_df = result_df[mask]
            st.session_state["diss_search_result"] = result_df

        if "diss_search_result" in st.session_state:
            result_df = st.session_state["diss_search_result"]
            if result_df.empty:
                st.warning("По заданным критериям ничего не найдено.")
            else:
                st.success(f"Найдено диссертаций: {len(result_df)}")
                share_params_button(
                    {
                        "diss_criterion": selected_criteria,
                        **{
                            f"diss_{criterion}": search_params.get(criterion, "")
                            for criterion in selected_criteria
                        },
                    },
                    key="diss_search_share",
                )
                render_dissertations_widget(
                    subset=result_df,
                    key="поиск_диссертаций",
                    title="Результаты",
                    expanded=False,
                    file_name_prefix="список_диссертаций_поиск",
                )

# ---------- Вкладка: Поиск по тематическим профилям ---------------------
with tab_profiles:
    render_profiles_tab(
        df=df,
        idx=idx,
        thematic_classifier=THEMATIC_CLASSIFIER,
        scores_folder="basic_scores",
        specific_files=None,
    )

# ---------- Вкладка: Поиск научных школ ---------------------------------
with tab_school_search:
    render_school_search_tab(
        df=df,
        idx=idx,
        classifier=THEMATIC_CLASSIFIER,
        scores_folder="basic_scores",
    )

# ---------- Вкладка: Взаимосвязи научных школ ----------------------------
with tab_intersection:
    render_opponents_intersection_tab(
        df=df,
        idx=idx,
    )

# ---------- Вкладка: Анализ научной школы --------------------------------
with tab_school_analysis:
    render_school_analysis_tab(
        df=df,
        idx=idx,
        classifier=THEMATIC_CLASSIFIER,
        scores_folder="basic_scores",
    )

## ---------- Вкладка: Сравнение научных школ ------------------------------
#with tab_schoolcomparison:
#    classifier_labels = {code: title for code, title, _ in THEMATIC_CLASSIFIER}
#    render_school_comparison_tab(
#        df=df,
#        idx=idx,
#        scores_folder="basic_scores",
#        specific_files=None,
#        classifier_labels=classifier_labels,
#    )

## ---------- Вкладка: Сравнение по статьям --------------------------------
#with tab_articles_comparison:
#    render_articles_comparison_tab(
#        df_lineage=df,
#        idx_lineage=idx,
#    )
