# web/streamlit_app.py — point d'entrée : uv run streamlit run web/streamlit_app.py

import streamlit as st

st.set_page_config(page_title="Scoring IFRS 9", page_icon="🏦", layout="wide")

navigation = st.navigation([
    st.Page("views/simulator.py", title="Simulateur ECL", icon="🧮", default=True),
    st.Page("views/portfolio.py", title="Portefeuille", icon="📊"),
    st.Page("views/runs.py", title="Modèles & ETL", icon="🗂️"),
])
navigation.run()
