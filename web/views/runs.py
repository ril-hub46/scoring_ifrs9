import pandas as pd
import streamlit as st

import api_client
from api_client import ApiError

st.title("🗂️ Modèles & ETL")

try:
    model_runs = api_client.model_runs()
    etl_runs = api_client.etl_runs()
except ApiError as e:
    st.error(str(e))
    st.stop()

st.subheader("Modèles entraînés")
if not model_runs:
    st.info("Aucun modèle : lancer `scoring-ifrs9 train`.")
else:
    st.dataframe(
        pd.DataFrame([
            {
                "id": run["id"],
                "actif": run["is_active"],
                "type": run["model_type"].upper(),
                "algorithme": run["algorithm"],
                "auc_validation": run["metrics"]["validation"]["roc_auc"],
                "auc_test": run["metrics"]["test"]["roc_auc"],
                "n_train": run["metrics"]["n_train"],
                "entraîné le": pd.to_datetime(run["trained_at"]),
            }
            for run in model_runs
        ]),
        column_config={
            "actif": st.column_config.CheckboxColumn("Actif"),
            "auc_validation": st.column_config.NumberColumn("AUC validation", format="%.4f"),
            "auc_test": st.column_config.NumberColumn("AUC test", format="%.4f"),
            "n_train": st.column_config.NumberColumn("Prêts d'entraînement", format="localized"),
            "entraîné le": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm"),
        },
        hide_index=True, use_container_width=True,
    )

st.subheader("Exécutions de l'ETL")
STATUS_LABELS = {"success": "✅ succès", "failed": "❌ échec", "running": "⏳ en cours"}
if not etl_runs:
    st.info("Aucune exécution : lancer `scoring-ifrs9 run-all`.")
else:
    df = pd.DataFrame(etl_runs)
    df["started_at"] = pd.to_datetime(df["started_at"])
    df["durée (s)"] = (pd.to_datetime(df["finished_at"]) - df["started_at"]).dt.total_seconds()
    df["status"] = df["status"].map(STATUS_LABELS)
    st.dataframe(
        df[["id", "step", "status", "started_at", "durée (s)", "rows_in", "rows_out", "error"]],
        column_config={
            "step": "Étape", "status": "Statut", "error": "Erreur",
            "started_at": st.column_config.DatetimeColumn("Début", format="DD/MM/YYYY HH:mm:ss"),
            "durée (s)": st.column_config.NumberColumn(format="%.1f"),
            "rows_in": st.column_config.NumberColumn("Lignes lues", format="localized"),
            "rows_out": st.column_config.NumberColumn("Lignes écrites", format="localized"),
        },
        hide_index=True, use_container_width=True,
    )
