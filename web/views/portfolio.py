import altair as alt
import pandas as pd
import streamlit as st

import api_client
from api_client import ApiError

# Couleurs catégorielles (palette de référence validée daltonisme : slots 1 et 2)
BLUE, ORANGE = "#2a78d6", "#eb6834"

st.title("📊 Portefeuille")

# Filtres sur une seule ligne, au-dessus des graphiques
dataset_label = st.segmented_control(
    "Jeu de données", ["Tous", "Train", "Test"], default="Tous",
    help="Le jeu test n'a pas servi à entraîner le modèle : c'est là que la calibration se juge.",
)
dataset = None if dataset_label in (None, "Tous") else dataset_label.lower()

try:
    summary = api_client.portfolio_summary(dataset)
except ApiError as e:
    st.error(str(e))
    st.stop()

overall = summary["overall"]
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Prêts", f"{overall['n_loans']:,}".replace(",", " "))
k2.metric("Taux de défaut observé", f"{overall['observed_default_rate']:.2%}")
k3.metric("PD moyenne", f"{overall['mean_pd']:.2%}")
k4.metric("EAD totale", f"€ {overall['total_ead'] / 1e9:,.2f} Md")
k5.metric("ECL totale", f"€ {overall['total_ecl'] / 1e6:,.1f} M",
          help=f"Taux de couverture ECL / EAD : {overall['coverage_ratio']:.2%}")
st.caption(f"Modèle PD actif n° {summary['model_run_id']} — ECL à l'octroi (stade 1), LGD fixe.")

by_grade = pd.DataFrame(summary["by_grade"])
if by_grade.empty:
    st.info("Aucun prêt scoré : lancer `scoring-ifrs9 score`.")
    st.stop()

left, right = st.columns(2)

with left:
    st.subheader("Calibration par grade")
    st.caption("Un modèle bien calibré prédit en moyenne le taux de défaut observé.")
    calib = by_grade.melt(
        id_vars="grade", value_vars=["mean_pd", "observed_default_rate"], var_name="mesure", value_name="taux"
    )
    calib["mesure"] = calib["mesure"].map({"mean_pd": "PD moyenne prédite", "observed_default_rate": "Défaut observé"})
    chart = (
        alt.Chart(calib)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("grade:N", title="Grade", axis=alt.Axis(labelAngle=0)),
            xOffset=alt.XOffset("mesure:N", sort=["PD moyenne prédite", "Défaut observé"]),
            y=alt.Y("taux:Q", title=None, axis=alt.Axis(format="%", gridOpacity=0.4)),
            color=alt.Color(
                "mesure:N",
                scale=alt.Scale(domain=["PD moyenne prédite", "Défaut observé"], range=[BLUE, ORANGE]),
                legend=alt.Legend(title=None, orient="top"),
            ),
            tooltip=[
                alt.Tooltip("grade:N", title="Grade"),
                alt.Tooltip("mesure:N", title="Mesure"),
                alt.Tooltip("taux:Q", title="Taux", format=".2%"),
            ],
        )
        .properties(height=320)
        .configure_view(stroke=None)
    )
    st.altair_chart(chart, use_container_width=True)

with right:
    st.subheader("ECL par grade")
    st.caption("Montant de provision attendu (€).")
    chart = (
        alt.Chart(by_grade)
        .mark_bar(color=BLUE, cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("grade:N", title="Grade", axis=alt.Axis(labelAngle=0)),
            y=alt.Y("total_ecl:Q", title=None, axis=alt.Axis(format="~s", gridOpacity=0.4)),
            tooltip=[
                alt.Tooltip("grade:N", title="Grade"),
                alt.Tooltip("total_ecl:Q", title="ECL (€)", format=",.0f"),
                alt.Tooltip("coverage_ratio:Q", title="Couverture ECL/EAD", format=".2%"),
                alt.Tooltip("n_loans:Q", title="Prêts", format=","),
            ],
        )
        .properties(height=320)
        .configure_view(stroke=None)
    )
    st.altair_chart(chart, use_container_width=True)

with st.expander("Tableau par grade"):
    st.dataframe(
        by_grade[["grade", "n_loans", "observed_default_rate", "mean_pd", "total_ead", "total_ecl", "coverage_ratio"]],
        column_config={
            "grade": "Grade",
            "n_loans": st.column_config.NumberColumn("Prêts", format="localized"),
            "observed_default_rate": st.column_config.NumberColumn("Défaut observé", format="percent"),
            "mean_pd": st.column_config.NumberColumn("PD moyenne", format="percent"),
            "total_ead": st.column_config.NumberColumn("EAD (€)", format="localized"),
            "total_ecl": st.column_config.NumberColumn("ECL (€)", format="localized"),
            "coverage_ratio": st.column_config.NumberColumn("Couverture", format="percent"),
        },
        hide_index=True, use_container_width=True,
    )

st.divider()
st.subheader("Explorer les prêts")

f1, f2, f3 = st.columns(3)
grade = f1.selectbox("Grade", ["Tous", "A", "B", "C", "D", "E", "F", "G"])
status = f2.selectbox("Statut", ["Tous", "Fully Paid", "Charged Off"])
page_size = 50
page = f3.number_input("Page", min_value=1, value=1, step=1)

try:
    loans = api_client.loans(
        dataset=dataset,
        grade=None if grade == "Tous" else grade,
        loan_status=None if status == "Tous" else status,
        limit=page_size,
        offset=(page - 1) * page_size,
    )
except ApiError as e:
    st.error(str(e))
    st.stop()

rows = [
    {
        "loan_id": loan["loan_id"], "grade": loan["grade"], "term": loan["term"].strip(),
        "int_rate": loan["int_rate"], "annual_inc": loan["annual_inc"], "statut": loan["loan_status"],
        "pd": (loan["result"] or {}).get("pd"), "ead": (loan["result"] or {}).get("ead"),
        "ecl": (loan["result"] or {}).get("ecl"),
    }
    for loan in loans["items"]
]
st.caption(f"{loans['total']:,} prêts — page {page} sur {max(1, -(-loans['total'] // page_size))}".replace(",", " "))
st.dataframe(
    pd.DataFrame(rows),
    column_config={
        "loan_id": st.column_config.NumberColumn("Id", format="%d"),
        "grade": "Grade", "term": "Durée", "statut": "Statut",
        "int_rate": st.column_config.NumberColumn("Taux (%)", format="%.2f"),
        "annual_inc": st.column_config.NumberColumn("Revenu (€)", format="localized"),
        "pd": st.column_config.ProgressColumn("PD", format="percent", min_value=0, max_value=1),
        "ead": st.column_config.NumberColumn("EAD (€)", format="localized"),
        "ecl": st.column_config.NumberColumn("ECL (€)", format="localized"),
    },
    hide_index=True, use_container_width=True,
)
