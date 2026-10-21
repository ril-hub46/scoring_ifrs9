"""Tables PostgreSQL du projet.

Flux : source -> raw.loans -> staging.loans -> mart.pd_scores / mart.ecl_results
Chaque écriture est rattachée à une exécution (ops.etl_runs ou mart.model_runs) pour l'audit.
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import MART, OPS, RAW, STAGING, Base

Money = Numeric(14, 2)


def _in(column: str, values: list[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


# --- ops ---

class EtlRun(Base):
    """Une exécution d'une étape de l'ETL (ingestion, imputation, scoring...)."""
    __tablename__ = "etl_runs"
    __table_args__ = (
        CheckConstraint(_in("status", ["running", "success", "failed"]), name="status"),
        {"schema": OPS},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    step: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), server_default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rows_in: Mapped[int | None] = mapped_column(BigInteger)
    rows_out: Mapped[int | None] = mapped_column(BigInteger)
    params: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)


# --- raw ---

class RawLoan(Base):
    """Prêt tel que reçu de la source : aucune contrainte métier, tout est nullable."""
    __tablename__ = "loans"
    __table_args__ = {"schema": RAW}

    loan_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    term: Mapped[str | None] = mapped_column(String(20))
    int_rate: Mapped[float | None] = mapped_column(Double)
    installment: Mapped[float | None] = mapped_column(Double)
    grade: Mapped[str | None] = mapped_column(String(5))
    emp_length: Mapped[str | None] = mapped_column(String(20))
    home_ownership: Mapped[str | None] = mapped_column(String(20))
    annual_inc: Mapped[float | None] = mapped_column(Double)
    loan_status: Mapped[str | None] = mapped_column(String(50))
    dti: Mapped[float | None] = mapped_column(Double)
    tot_cur_bal: Mapped[float | None] = mapped_column(Double)
    open_acc_6m: Mapped[float | None] = mapped_column(Double)
    total_bal_il: Mapped[float | None] = mapped_column(Double)
    inq_fi: Mapped[float | None] = mapped_column(Double)
    mort_acc: Mapped[float | None] = mapped_column(Double)
    num_sats: Mapped[float | None] = mapped_column(Double)
    out_prncp: Mapped[float | None] = mapped_column(Double)
    total_pymnt: Mapped[float | None] = mapped_column(Double)
    recoveries: Mapped[float | None] = mapped_column(Double)
    etl_run_id: Mapped[int] = mapped_column(ForeignKey(f"{OPS}.etl_runs.id"))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --- staging ---

class StagingLoan(Base):
    """Prêt nettoyé et imputé : plus de valeurs manquantes sur les features, modalités contrôlées."""
    __tablename__ = "loans"
    __table_args__ = (
        CheckConstraint(_in("dataset", ["train", "test"]), name="dataset"),
        CheckConstraint(_in("loan_status", ["Fully Paid", "Charged Off"]), name="loan_status"),
        CheckConstraint(_in("grade", ["A", "B", "C", "D", "E", "F", "G"]), name="grade"),
        CheckConstraint(_in("term", [" 36 months", " 60 months"]), name="term"),
        CheckConstraint("int_rate >= 0 AND annual_inc >= 0", name="positive_amounts"),
        Index("ix_staging_loans_dataset", "dataset"),
        {"schema": STAGING},
    )

    loan_id: Mapped[int] = mapped_column(ForeignKey(f"{RAW}.loans.loan_id"), primary_key=True)
    dataset: Mapped[str] = mapped_column(String(10))
    term: Mapped[str] = mapped_column(String(20))
    int_rate: Mapped[float] = mapped_column(Double)
    installment: Mapped[float] = mapped_column(Double)
    grade: Mapped[str] = mapped_column(String(5))
    emp_length: Mapped[str] = mapped_column(String(20))
    home_ownership: Mapped[str] = mapped_column(String(20))
    annual_inc: Mapped[float] = mapped_column(Double)
    loan_status: Mapped[str] = mapped_column(String(50))
    dti: Mapped[float] = mapped_column(Double)
    tot_cur_bal: Mapped[float] = mapped_column(Double)
    open_acc_6m: Mapped[float] = mapped_column(Double)
    total_bal_il: Mapped[float] = mapped_column(Double)
    inq_fi: Mapped[float] = mapped_column(Double)
    mort_acc: Mapped[float] = mapped_column(Double)
    num_sats: Mapped[float] = mapped_column(Double)
    out_prncp: Mapped[float | None] = mapped_column(Double)
    total_pymnt: Mapped[float | None] = mapped_column(Double)
    recoveries: Mapped[float | None] = mapped_column(Double)
    etl_run_id: Mapped[int] = mapped_column(ForeignKey(f"{OPS}.etl_runs.id"))


# --- mart ---

class ModelRun(Base):
    """Un modèle entraîné : paramètres, métriques et emplacement de l'artefact."""
    __tablename__ = "model_runs"
    __table_args__ = (
        CheckConstraint(_in("model_type", ["pd", "lgd", "ead"]), name="model_type"),
        # Au plus un modèle actif par type
        Index(
            "uq_model_runs_active_per_type", "model_type",
            unique=True, postgresql_where="is_active",
        ),
        {"schema": MART},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_type: Mapped[str] = mapped_column(String(10))
    algorithm: Mapped[str] = mapped_column(String(100))
    params: Mapped[dict | None] = mapped_column(JSONB)
    metrics: Mapped[dict | None] = mapped_column(JSONB)
    artifact_path: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(server_default="false")
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PdScore(Base):
    """PD d'un prêt calculée par un modèle donné."""
    __tablename__ = "pd_scores"
    __table_args__ = (
        CheckConstraint("pd BETWEEN 0 AND 1", name="pd_range"),
        {"schema": MART},
    )

    loan_id: Mapped[int] = mapped_column(ForeignKey(f"{STAGING}.loans.loan_id"), primary_key=True)
    model_run_id: Mapped[int] = mapped_column(ForeignKey(f"{MART}.model_runs.id"), primary_key=True)
    pd: Mapped[float] = mapped_column(Double)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EclResult(Base):
    """ECL d'un prêt : ECL = PD × LGD × EAD, avec le stade IFRS 9 (1, 2 ou 3)."""
    __tablename__ = "ecl_results"
    __table_args__ = (
        CheckConstraint("pd BETWEEN 0 AND 1", name="pd_range"),
        CheckConstraint("lgd BETWEEN 0 AND 1", name="lgd_range"),
        CheckConstraint("ead >= 0 AND ecl >= 0", name="positive_amounts"),
        CheckConstraint("stage IN (1, 2, 3)", name="stage"),
        {"schema": MART},
    )

    loan_id: Mapped[int] = mapped_column(ForeignKey(f"{STAGING}.loans.loan_id"), primary_key=True)
    model_run_id: Mapped[int] = mapped_column(ForeignKey(f"{MART}.model_runs.id"), primary_key=True)
    stage: Mapped[int] = mapped_column(Integer, server_default="1")
    pd: Mapped[float] = mapped_column(Double)
    lgd: Mapped[float] = mapped_column(Double)
    ead: Mapped[Decimal] = mapped_column(Money)
    ecl: Mapped[Decimal] = mapped_column(Money)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
