from __future__ import annotations

import io
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from core.classifier import (
    PROFILE_MIN_SCORE,
    PROFILE_SELECTION_LIMIT,
    PROFILE_SELECTION_SESSION_KEY,
)
from core.classifier.helpers import classifier_format
from core.ui.links import share_params_button

from .search import (
    build_export_df,
    classifier_label,
    format_results_for_display,
    get_feature_columns,
    merge_with_dissertation_info,
    search_by_codes,
    validate_code_selection,
)
from .state import hydrate_topics_query_params, trigger_rerun

INSTRUCTION_BY_TOPICS = """
## 📊 Поиск по конкретным темам

На этой вкладке реализован содержательный поиск диссертаций по конкретным темам. 
Он основан не на совпадении слов в заголовке, а на анализе всего текста автореферата 
диссертационной работы. Поиск осуществляется с использованием иерархического 
классификатора, содержащего различные критерии, отражающие объект, процесс и 
результат диссертационного исследования.

---

### 🎯 Выбор тематики

В выпадающем списке **"Элемент классификатора"** выберите интересующую тему, метод 
или педагогическую технологию (например, "Начальное общее образование", "Информатика", 
"Интерактивные цифровые ресурсы", "Инклюзия"). Нажмите кнопку **"Добавить в подборку"**.

---

### 🔧 Логика поиска

- Можно добавить в подборку от одного до пяти пунктов классификатора
- Система отберет только те диссертации, у которых оценка присутствия **каждого** 
  выбранного пункта (темы) составляет не менее установленного порога (по умолчанию 4 балла 
  по 10-балльной шкале)
- Порог отсечения можно настроить в параметрах поиска

Для запуска алгоритма нажмите кнопку **"🔍 Найти диссертации"**.

---

### 📈 Результаты

Вы получите список работ, наиболее полно раскрывающих выбранные темы:

- **Ранжирование по сумме баллов**: сверху списка находятся диссертации, в которых 
  искомые темы проработаны максимально глубоко
- **Фильтр по таблице**: поле "🔍 Фильтр" позволяет найти работу по автору или слову 
  в названии внутри полученной выборки
- **Экспорт результатов**: итоговую таблицу с баллами и метаданными можно выгрузить 
  в форматах CSV или Excel

Чем выше балл, тем в большей степени тематика диссертации соответствует тем 
содержательным критериям, по которым осуществлялся поиск.

---

### 💡 Советы по использованию

- Начните с 1-2 ключевых тем для более широкого охвата
- Добавляйте дополнительные темы для более точного поиска
- Снизьте порог отсечения (например, до 3 баллов), если результатов слишком мало
- Используйте фильтр для поиска по конкретной организации или году
"""


def show_instruction_dialog() -> None:
    @st.dialog("📖 Инструкция", width="large")
    def _show() -> None:
        st.markdown(INSTRUCTION_BY_TOPICS)

    _show()


def render_search_by_topics(
    df: pd.DataFrame,
    scores_df: pd.DataFrame,
    thematic_classifier: List[Tuple[str, str, bool]],
    classifier_dict: Dict[str, str],
) -> None:
    hydrate_topics_query_params(classifier_dict)

    if st.button("📖 Инструкция", key="instruction_profiles_topics"):
        show_instruction_dialog()

    st.subheader("🔍 Поиск по конкретным темам")
    st.write(
        f"Выберите до {PROFILE_SELECTION_LIMIT} пунктов классификатора. "
        f"Поиск найдет диссертации, где каждая выбранная тема оценена не менее "
        f"чем на {PROFILE_MIN_SCORE} баллов (по 10-балльной шкале)."
    )

    if PROFILE_SELECTION_SESSION_KEY not in st.session_state:
        st.session_state[PROFILE_SELECTION_SESSION_KEY] = []

    selected_codes: List[str] = list(st.session_state.get(PROFILE_SELECTION_SESSION_KEY, []))

    with st.container():
        st.markdown("### 📋 Выбор тематики")
        options: List[Optional[Tuple[str, str, bool]]] = [None] + thematic_classifier
        choice = st.selectbox(
            "Элемент классификатора",
            options=options,
            format_func=classifier_format,
            key="profile_classifier_choice",
        )

        add_reason: Optional[str] = None
        add_code: Optional[str] = None
        if choice is not None:
            add_code = choice[0]
            if choice[2]:
                add_reason = "Этот пункт нельзя выбрать. Пожалуйста, выберите более конкретный."
            elif add_code in selected_codes:
                add_reason = "Этот пункт уже добавлен в подборку."
            elif len(selected_codes) >= PROFILE_SELECTION_LIMIT:
                add_reason = (
                    f"Достигнут лимит: можно выбрать максимум {PROFILE_SELECTION_LIMIT} пунктов."
                )

        add_disabled = add_code is None or add_reason is not None
        add_clicked = st.button(
            "➕ Добавить в подборку",
            disabled=add_disabled,
            key="profile_add_button",
        )
        if add_clicked and add_code is not None:
            st.session_state[PROFILE_SELECTION_SESSION_KEY] = selected_codes + [add_code]
            trigger_rerun()

        if add_reason and choice is not None:
            st.caption(add_reason)

    st.markdown("---")
    st.markdown("### 🎯 Выбранные темы")

    if selected_codes:
        st.caption(f"Поиск найдет диссертации с баллом ≥ {PROFILE_MIN_SCORE} по каждой теме.")
        for code in list(selected_codes):
            cols = st.columns([0.85, 0.15])
            with cols[0]:
                st.markdown(f"**{classifier_label(code, classifier_dict)}**")
            with cols[1]:
                if st.button("❌", key=f"profile_remove_{code}", use_container_width=True):
                    st.session_state[PROFILE_SELECTION_SESSION_KEY] = [
                        c for c in selected_codes if c != code
                    ]
                    trigger_rerun()

        col_clear, _ = st.columns([0.2, 0.8])
        with col_clear:
            if st.button("🗑️ Очистить все", key="profile_clear_selection"):
                st.session_state[PROFILE_SELECTION_SESSION_KEY] = []
                trigger_rerun()
    else:
        st.info("Темы не выбраны. Выберите хотя бы один пункт классификатора выше.")

    st.markdown("---")
    st.markdown("### ⚙️ Параметры поиска")

    min_score = st.slider(
        "Минимальный балл для каждой темы",
        min_value=1.0,
        max_value=10.0,
        value=PROFILE_MIN_SCORE,
        step=0.5,
        key="profile_min_score",
        help="Диссертации с баллом ниже этого порога по любой из выбранных тем будут исключены",
    )

    st.markdown("---")
    run_search_click = st.button(
        "🔍 Найти диссертации",
        type="primary",
        disabled=not selected_codes,
        key="profile_run_search",
    )
    if run_search_click:
        st.session_state["profile_search_active"] = True

    if st.session_state.get("profile_search_active") and selected_codes:
        with st.spinner("Поиск диссертаций..."):
            try:
                all_feature_columns = get_feature_columns(scores_df)
                valid, error_message = validate_code_selection(selected_codes, all_feature_columns)
                if not valid:
                    st.error(f"❌ {error_message}")
                    return

                search_results = search_by_codes(scores_df, selected_codes, min_score)
                if search_results.empty:
                    st.info(
                        "🔍 По выбранным критериям диссертации не найдены. "
                        "Попробуйте снизить порог оценки или изменить выбранные темы."
                    )
                    return

                results = merge_with_dissertation_info(search_results, df, selected_codes)
                display_df, _, results_full = format_results_for_display(
                    results=results,
                    selected_codes=selected_codes,
                    classifier_labels=classifier_dict,
                )
                st.session_state["profile_results"] = display_df
                st.session_state["profile_results_full"] = results_full
            except Exception as exc:
                st.error(f"❌ Ошибка при поиске: {exc}")
                import traceback

                st.code(traceback.format_exc())
                return

        display_df = st.session_state.get("profile_results")
        results_full = st.session_state.get("profile_results_full")
        if display_df is not None and not display_df.empty:
            st.markdown("---")
            st.markdown("## 📊 Результаты поиска")
            st.success(f"✅ Найдено диссертаций: {len(display_df)}")
            share_params_button(
                {"tab": "profiles", "codes": selected_codes, "min_score": min_score},
                key="profiles_share_results",
            )

            st.markdown("### 🔍 Фильтр по таблице")
            fcol1, _ = st.columns([0.6, 0.4])
            with fcol1:
                search_query = st.text_input(
                    "Поиск в результатах:",
                    placeholder="Например, фамилия автора, слово из названия, организация...",
                    help="Введите текст для поиска в таблице результатов. Поиск работает по всем полям.",
                    key="profile_result_filter",
                )

            if search_query:
                mask = display_df.astype(str).apply(
                    lambda x: x.str.contains(search_query, case=False, na=False).any(), axis=1
                )
                filtered_df = display_df[mask]
                filtered_full = results_full.loc[filtered_df.index] if results_full is not None else None
            else:
                filtered_df = display_df
                filtered_full = results_full

            if len(filtered_df) != len(display_df):
                st.success(f"Показано {len(filtered_df)} из {len(display_df)} диссертаций.")
            else:
                st.success(f"Показано {len(display_df)} диссертаций.")

            column_config = {}
            if "Скачать" in filtered_df.columns:
                column_config["Скачать"] = st.column_config.LinkColumn(
                    label="Скачать", display_text="Автореферат"
                )
            st.dataframe(filtered_df, use_container_width=True, column_config=column_config)

            st.markdown("### 📥 Скачать результаты")
            selection_slug = "_".join(selected_codes[:3]) or "profiles"
            col_dl1, col_dl2 = st.columns(2)

            with col_dl1:
                try:
                    csv_export = build_export_df(
                        results=filtered_full,
                        display_df=filtered_df,
                        for_excel=False,
                    )
                except Exception:
                    csv_export = filtered_df
                csv_data = csv_export.to_csv(index=False, encoding="utf-8-sig")
                st.download_button(
                    label="📄 Скачать CSV",
                    data=csv_data.encode("utf-8-sig"),
                    file_name=f"профили_{selection_slug}.csv",
                    mime="text/csv",
                    key="profile_download_csv",
                    use_container_width=True,
                )

            with col_dl2:
                try:
                    xlsx_export = build_export_df(
                        results=filtered_full,
                        display_df=filtered_df,
                        for_excel=True,
                    )
                    buf_xlsx = io.BytesIO()
                    with pd.ExcelWriter(buf_xlsx, engine="openpyxl") as writer:
                        xlsx_export.to_excel(writer, index=False, sheet_name="Результаты")
                    st.download_button(
                        label="📊 Скачать Excel",
                        data=buf_xlsx.getvalue(),
                        file_name=f"профили_{selection_slug}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="profile_download_xlsx",
                        use_container_width=True,
                    )
                except Exception as e:
                    st.error(f"Ошибка создания Excel: {e}")
