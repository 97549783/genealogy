import streamlit as st

st.title("Тестовое приложение")
st.write("Привет! Streamlit работает отлично.")

name = st.text_input("Как вас зовут?")
if name:
    st.success(f"Приятно познакомиться, {name}!")
