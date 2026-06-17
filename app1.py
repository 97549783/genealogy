
import streamlit as st
# Импортируем функцию из папки test1111 и файла test1111.py
from test1111.test1111 import show_page

st.title("Главное приложение")

# Вызываем функцию для отображения текста
show_page()
