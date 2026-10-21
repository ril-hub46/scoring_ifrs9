from dataclasses import dataclass

import pandas as pd
from sklearn.pipeline import Pipeline

from src import features

# L'ECL est calculé à l'octroi : par définition IFRS 9, un prêt qui vient d'être accordé est en stade 1
STAGE_AT_ORIGINATION = 1


@dataclass(frozen=True)
class EclResult:
    pd: float
    lgd: float
    ead: float
    ecl: float


def predict_pd(model: Pipeline, loans: pd.DataFrame) -> pd.Series:
    """Probabilité de défaut (classe 1) de chaque prêt."""
    proba = model.predict_proba(loans[features.MODEL_FEATURES])[:, 1]
    return pd.Series(proba, index=loans.index, name="pd")


def _check_inputs(pd_value, lgd, ead) -> None:
    if not ((0 <= pd_value) & (pd_value <= 1)).all():
        raise ValueError(f"La PD doit être comprise entre 0 et 1 (reçu : {pd_value}).")
    if not 0 <= lgd <= 1:
        raise ValueError(f"La LGD doit être comprise entre 0 et 1 (reçu : {lgd}).")
    if not (ead >= 0).all():
        raise ValueError(f"L'EAD doit être positive (reçu : {ead}).")


def compute_ecl(pd_value: float, lgd: float, ead: float) -> EclResult:
    """Expected Credit Loss : ECL = PD × LGD × EAD."""
    _check_inputs(pd.Series([pd_value]), lgd, pd.Series([ead]))
    return EclResult(pd=pd_value, lgd=lgd, ead=ead, ecl=pd_value * lgd * ead)


def compute_ecl_frame(pds: pd.Series, lgd: float, ead: pd.Series) -> pd.DataFrame:
    """Version vectorisée de compute_ecl pour un portefeuille (Series alignées sur les prêts)."""
    _check_inputs(pds, lgd, ead)
    return pd.DataFrame({
        "stage": STAGE_AT_ORIGINATION,
        "pd": pds,
        "lgd": lgd,
        "ead": ead.round(2),
        "ecl": (pds * lgd * ead).round(2),
    })
