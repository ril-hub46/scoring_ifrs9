import numpy as np
import pandas as pd

from src import features


def principal_from_installment(installment, annual_rate_pct, n_months):
    """Capital initial d'un prêt amortissable à mensualités constantes.

    P = M × (1 − (1 + r)^−n) / r, avec r = taux annuel / 12 et n le nombre de mensualités.
    Fonctionne sur des scalaires comme sur des Series.
    """
    installment = np.asarray(installment, dtype=float)
    n = np.asarray(n_months, dtype=float)
    r = np.asarray(annual_rate_pct, dtype=float) / 100 / 12
    with np.errstate(divide="ignore", invalid="ignore"):
        annuity_factor = np.where(r > 0, (1 - (1 + r) ** -n) / r, n)
    return installment * annuity_factor


def ead_at_origination(loans: pd.DataFrame) -> pd.Series:
    """EAD de chaque prêt = capital à l'octroi.

    Les prêts des données sont tous soldés (out_prncp = 0) : on mesure donc l'exposition
    au moment de l'octroi, reconstruite à partir de la mensualité, du taux et de la durée.
    """
    principal = principal_from_installment(
        loans["installment"], loans["int_rate"], loans["term"].map(features.TERM_MONTHS)
    )
    return pd.Series(principal, index=loans.index, name="ead")
