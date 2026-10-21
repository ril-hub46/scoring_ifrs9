"""Contrats d'échange de l'API (validés automatiquement par FastAPI et documentés dans /docs)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src import features

Term = Literal[tuple(features.TERM_VALUES)]
Grade = Literal[tuple(features.GRADES)]
EmpLength = Literal[tuple(features.EMP_LENGTHS)]
HomeOwnership = Literal[tuple(features.HOME_OWNERSHIPS)]
Dataset = Literal["train", "test"]
LoanStatus = Literal[tuple(features.TARGET_MAPPING)]


class LoanFeatures(BaseModel):
    """Caractéristiques d'un prêt utilisées par le modèle PD."""
    term: Term
    int_rate: float = Field(ge=0, le=100, description="Taux d'intérêt annuel (%)")
    installment: float = Field(gt=0, description="Mensualité")
    grade: Grade
    emp_length: EmpLength
    home_ownership: HomeOwnership
    annual_inc: float = Field(ge=0, description="Revenu annuel")
    dti: float = Field(ge=0, description="Taux d'endettement (%)")
    tot_cur_bal: float = Field(ge=0, description="Solde total de tous les comptes")
    open_acc_6m: float = Field(ge=0, description="Crédits ouverts sur 6 mois")
    total_bal_il: float = Field(ge=0, description="Solde des prêts à tempérament")
    inq_fi: float = Field(ge=0, description="Demandes de crédit sur 6 mois")
    mort_acc: float = Field(ge=0, description="Nombre de prêts immobiliers")
    num_sats: float = Field(ge=0, description="Nombre de crédits sans incident")


class ScoreRequest(LoanFeatures):
    ead: float | None = Field(
        None, ge=0, description="Exposition en cas de défaut. Si absente : capital à l'octroi, "
        "reconstruit depuis la mensualité, le taux et la durée.",
    )
    lgd: float | None = Field(None, ge=0, le=1, description="Si absente : hypothèse par défaut (0,45).")


class ScoreResponse(BaseModel):
    model_run_id: int
    stage: int
    pd: float
    lgd: float
    ead: float
    ead_source: Literal["provided", "computed"]
    ecl: float


class EclOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    stage: int
    pd: float
    lgd: float
    ead: float
    ecl: float


class LoanOut(BaseModel):
    """Prêt du portefeuille (staging). Pas de contraintes de bornes : ce sont des données
    historiques déjà contrôlées par la base, à restituer telles quelles."""
    model_config = ConfigDict(from_attributes=True)
    loan_id: int
    dataset: Dataset
    loan_status: LoanStatus
    term: str
    int_rate: float
    installment: float
    grade: str
    emp_length: str
    home_ownership: str
    annual_inc: float
    dti: float
    tot_cur_bal: float
    open_acc_6m: float
    total_bal_il: float
    inq_fi: float
    mort_acc: float
    num_sats: float
    total_pymnt: float | None
    recoveries: float | None
    result: EclOut | None = Field(None, description="Résultat ECL du modèle actif (null si non scoré)")


class LoanPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[LoanOut]


class SegmentStats(BaseModel):
    n_loans: int
    observed_default_rate: float | None
    mean_pd: float | None
    total_ead: float
    total_ecl: float
    coverage_ratio: float | None = Field(description="ECL / EAD")


class GradeStats(SegmentStats):
    grade: Grade


class PortfolioSummary(BaseModel):
    model_run_id: int
    dataset: Dataset | None
    overall: SegmentStats
    by_grade: list[GradeStats]


class ModelRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    model_type: str
    algorithm: str
    params: dict | None
    metrics: dict | None
    artifact_path: str
    is_active: bool
    trained_at: datetime


class EtlRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    step: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    rows_in: int | None
    rows_out: int | None
    params: dict | None
    error: str | None


class ReferenceData(BaseModel):
    """Valeurs autorisées pour les listes déroulantes du front."""
    terms: list[str]
    grades: list[str]
    emp_lengths: list[str]
    home_ownerships: list[str]
    default_lgd: float


class Health(BaseModel):
    status: Literal["ok"]
    database: Literal["ok"]
