"""Секретная административная страница приложения."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.db import FEEDBACK_FILE

_ADMIN_SECRET = "nb39fdv94beraaagv2evdc9ewr3fokv"


def maybe_render_admin_page_and_stop() -> None:
    """Отрисовывает таблицу обратной связи и завершает выполнение при секретном ключе."""
    if st.query_params.get("secret") != _ADMIN_SECRET:
        return

    st.title("📋 Обратная связь")
    if FEEDBACK_FILE.exists():
        fb_df = pd.read_csv(FEEDBACK_FILE)
        st.caption(f"Всего записей: {len(fb_df)}")
        st.table(fb_df)
    else:
        st.info("Файл feedback.csv пока не существует — нет ни одного сообщения.")
    st.stop()
