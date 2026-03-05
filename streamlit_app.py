import streamlit as st

# The URL you want to redirect to
target_url = "https://academic-genealogy.academyrh.info/"

# This code injects JavaScript to redirect the page
st.markdown(
    f"""
    <script>
        window.top.location.href = "{target_url}";
    </script>
    """,
    unsafe_allow_html=True
)

# Optional: Add a fallback link in case JavaScript is disabled
st.write(f"Перенаправление на {target_url}...")
st.write(f"Если перенаправление не произошло, то [нажмите сюда]({target_url}).")
