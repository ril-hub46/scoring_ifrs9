import streamlit as st

import api_client
from api_client import ApiError

st.title("🏦 Simulateur ECL (IFRS 9)")

try:
    ref = api_client.reference()
except ApiError as e:
    st.error(str(e))
    st.stop()

col_inputs, col_results = st.columns(2)

with col_inputs:
    st.header("Paramètres du client et du prêt")

    # A. Exposition et perte
    st.subheader("Exposition (EAD) et perte (LGD)")
    ead_mode = st.radio(
        "EAD", ["Saisir le montant", "Calculer depuis la mensualité"], horizontal=True,
        help="Sans montant saisi, l'API reconstruit le capital à l'octroi depuis la mensualité, le taux et la durée.",
    )
    ead_input = None
    if ead_mode == "Saisir le montant":
        ead_input = st.number_input("Capital restant dû (€)", 0.0, 1_000_000.0, 25_000.0, step=100.0)
    lgd = st.slider("LGD (Loss Given Default)", 0.0, 1.0, ref["default_lgd"], step=0.01,
                    help="Part de l'exposition perdue en cas de défaut. 45 % = standard prêt non garanti.")

    st.divider()

    # B. Caractéristiques principales (PD)
    st.subheader("Caractéristiques principales (PD)")
    c1, c2 = st.columns(2)
    with c1:
        annual_inc = st.number_input("Revenu annuel (€)", 1000, 5_000_000, 60_000, step=1000)
        dti = st.number_input("Taux d'endettement (%)", 0.0, 100.0, 15.0, step=0.1)
        term = st.selectbox("Durée du prêt", ref["terms"], format_func=str.strip)
    with c2:
        installment = st.number_input("Mensualité (€)", 1.0, 5000.0, 450.0, step=10.0)
        grade = st.selectbox("Notation (grade) du prêt", ref["grades"])
        int_rate = st.number_input("Taux d'intérêt (%)", 0.0, 30.0, 12.5, step=0.1)

    # C. Caractéristiques secondaires
    st.divider()
    with st.expander("Paramètres avancés (emprunteur et comportement)"):
        c3, c4 = st.columns(2)
        with c3:
            st.markdown("Profil emprunteur")
            emp_length = st.selectbox("Ancienneté professionnelle", ref["emp_lengths"], index=5)
            home_ownership = st.selectbox(
                "Situation immobilière", ref["home_ownerships"], index=ref["home_ownerships"].index("MORTGAGE"),
                help="MORTGAGE = propriétaire avec hypothèque, RENT = locataire, OWN = propriétaire",
            )
            mort_acc = st.number_input("Nombre de prêts immobiliers", 0, 20, 1, step=1)
        with c4:
            st.markdown("Comportement de crédit")
            tot_cur_bal = st.number_input("Solde total tous comptes (€)", 0, 1_000_000, 150_000, step=1000)
            open_acc_6m = st.number_input("Nouveaux crédits (6 derniers mois)", 0, 10, 0, step=1)
            total_bal_il = st.number_input("Solde des prêts à tempérament (€)", 0, 500_000, 50_000, step=100)
            inq_fi = st.number_input("Demandes de crédit (6 derniers mois)", 0, 10, 0, step=1)
            num_sats = st.number_input("Nombre de crédits sans incident", 0, 50, 8, step=1)

with col_results:
    st.header("Résultats de la simulation")

    if st.button("Calculer le risque (ECL)", type="primary", use_container_width=True):
        payload = {
            "term": term, "int_rate": int_rate, "installment": installment, "grade": grade,
            "emp_length": emp_length, "home_ownership": home_ownership, "annual_inc": annual_inc,
            "dti": dti, "tot_cur_bal": tot_cur_bal, "open_acc_6m": open_acc_6m,
            "total_bal_il": total_bal_il, "inq_fi": inq_fi, "mort_acc": mort_acc, "num_sats": num_sats,
            "ead": ead_input, "lgd": lgd,
        }
        try:
            result = api_client.score(payload)
        except ApiError as e:
            st.error(str(e))
            st.stop()

        st.subheader("Ventilation du risque")
        r1, r2, r3 = st.columns(3)
        r1.metric("Probabilité de défaut (PD)", f"{result['pd']:.2%}")
        r2.metric(
            "Exposition (EAD)", f"€ {result['ead']:,.0f}",
            help="Capital à l'octroi reconstruit par l'API" if result["ead_source"] == "computed" else None,
        )
        r3.metric("Perte (LGD)", f"{result['lgd']:.0%}")

        st.divider()
        st.metric(
            "Provision ECL (Expected Credit Loss)", f"€ {result['ecl']:,.2f}",
            help=f"ECL = PD × LGD × EAD = {result['pd']:.2%} × {result['lgd']:.2f} × {result['ead']:,.0f}",
        )
        st.progress(result["pd"], text=f"Niveau de risque (PD) : {result['pd']:.2%}")
        st.caption(f"Modèle PD n° {result['model_run_id']} — stade IFRS 9 : {result['stage']}")
