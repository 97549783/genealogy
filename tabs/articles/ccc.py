import streamlit as st

st.title("Пример вывода текста")
st.write("Это обычный текст через st.write.")
st.text("Это текст через st.text — без автоформатирования.")
st.markdown("**Это жирный текст** и *это курсив* через st.markdown.")
st.caption("Это подпись, например, к графику.")
