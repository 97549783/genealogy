import streamlit as st
import streamlit.components.v1 as components

# The URL you want to redirect to
target_url = "https://academic-genealogy.academyrh.info/"

# This executes inside a protected iframe but can still trigger a top-level redirect
components.html(
    f"""
    <script>
        window.parent.location.href = "{target_url}";
    </script>
    """,
    height=0,
)

# Using a meta tag for automatic redirection
#st.markdown(
#    f'<meta http-equiv="refresh" content="0; url={target_url}">',
#    unsafe_allow_html=True
#)

# Optional: Add a fallback link in case JavaScript is disabled
st.write(f"Перенаправление на {target_url}...")
st.write(f"Если перенаправление не произошло, то [нажмите сюда]({target_url}).")
