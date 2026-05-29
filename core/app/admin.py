"""Секретная административная страница приложения."""

from __future__ import annotations

import streamlit as st

from core.app.feedback import feedback_exists, load_feedback

_ADMIN_SECRET = "nb39fdv94beraaagv2evdc9ewr3fokv"


def maybe_render_admin_page_and_stop() -> None:
    """Отрисовывает таблицу обратной связи и завершает выполнение при секретном ключе."""
    if st.query_params.get("secret") != _ADMIN_SECRET:
        return

    st.title("📋 Обратная связь")
    if feedback_exists():
        fb_df = load_feedback()
        st.caption(f"Всего записей: {len(fb_df)}")
        st.table(fb_df)
    else:
        st.info("Файл feedback.csv пока не существует — нет ни одного сообщения.")
    st.stop()
