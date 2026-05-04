from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from core.lineage.graph import lineage, rows_for

from .entropy_mode import render_entropy_specificity_tab
from .search import get_feature_columns, load_basic_scores
from .topics_mode import render_search_by_topics


def render_profiles_tab(
    df: pd.DataFrame,
    idx: Dict[str, set],
    thematic_classifier: List[Tuple[str, str, bool]],
        supervisor_columns: Optional[List[str]] = None,
) -> None:
    if supervisor_columns is None:
        supervisor_columns = ["supervisors_1.name", "supervisors_2.name"]

    classifier_dict = {code: title for code, title, _ in thematic_classifier}

    st.markdown("---")
    st.markdown("## 🔍 Режим поиска")

    search_mode = st.radio(
        "Выберите режим:",
        options=["По конкретным темам", "По мере общности/специфичности"],
        horizontal=True,
        key="profile_search_mode_selector",
        help=(
            "**По конкретным темам** — классический поиск по выбранным пунктам классификатора.\n\n"
            "**По мере общности/специфичности** — поиск узкоспециализированных или "
            "междисциплинарных работ в научной школе на основе энтропии."
        ),
    )

    st.markdown("---")

    if search_mode == "По конкретным темам":
        try:
            scores_df = load_basic_scores()
            all_feature_columns = get_feature_columns(scores_df)
            st.success(
                f"✅ Загружено {len(scores_df)} профилей, "
                f"{len(all_feature_columns)} признаков классификатора"
            )
        except FileNotFoundError as e:
            st.error(f"❌ Не удалось загрузить SQLite-базу: {e}")
            st.info("Проверьте, что файл genealogy.db доступен или задана переменная SQLITE_DB_PATH.")
            return
        except Exception as e:
            st.error(f"❌ Ошибка загрузки данных: {e}")
            import traceback
            st.code(traceback.format_exc())
            return
        render_search_by_topics(
            df=df,
            scores_df=scores_df,
            thematic_classifier=thematic_classifier,
            classifier_dict=classifier_dict,
        )
    else:
        render_entropy_specificity_tab(
            df=df,
            idx=idx,
            lineage_func=lineage,
            rows_for_func=rows_for,
            classifier_labels=classifier_dict,
            thematic_classifier=thematic_classifier,
            supervisor_columns=supervisor_columns,
        )
