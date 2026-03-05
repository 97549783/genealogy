import streamlit as st

# The URL you want to redirect to
target_url = "https://academic-genealogy.academyrh.info/"

# Using a meta tag for automatic redirection
st.markdown(
    f'<meta http-equiv="refresh" content="0; url={target_url}">',
    unsafe_allow_html=True
)

# Optional: Add a fallback link in case JavaScript is disabled
st.write(f"Перенаправление на {target_url}...")
st.write(f"Если перенаправление не произошло, то [нажмите сюда]({target_url}).")
