"""Requêtes de lecture utilisées par l'API (portefeuille, prêts, historique des exécutions)."""
from sqlalchemy import Select, and_, case, func, select
from sqlalchemy.orm import Session

from src.db.models import EclResult, EtlRun, ModelRun, StagingLoan

_is_default = case((StagingLoan.loan_status == "Charged Off", 1), else_=0)

_SEGMENT_COLUMNS = (
    func.count().label("n_loans"),
    func.avg(_is_default).label("observed_default_rate"),
    func.avg(EclResult.pd).label("mean_pd"),
    func.coalesce(func.sum(EclResult.ead), 0).label("total_ead"),
    func.coalesce(func.sum(EclResult.ecl), 0).label("total_ecl"),
)


def _loans_with_results(model_run_id: int | None) -> Select:
    """Prêts de staging avec leur résultat ECL pour le modèle donné (vide si pas encore scorés)."""
    return select(StagingLoan, EclResult).outerjoin(
        EclResult,
        and_(EclResult.loan_id == StagingLoan.loan_id, EclResult.model_run_id == model_run_id),
    )


def list_loans(
    session: Session,
    model_run_id: int | None,
    *,
    dataset: str | None = None,
    grade: str | None = None,
    loan_status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[tuple[StagingLoan, EclResult | None]]]:
    filters = [
        column == value
        for column, value in (
            (StagingLoan.dataset, dataset),
            (StagingLoan.grade, grade),
            (StagingLoan.loan_status, loan_status),
        )
        if value is not None
    ]
    total = session.scalar(select(func.count()).select_from(StagingLoan).where(*filters))
    rows = session.execute(
        _loans_with_results(model_run_id).where(*filters)
        .order_by(StagingLoan.loan_id).limit(limit).offset(offset)
    ).all()
    return total, rows


def get_loan(
    session: Session, loan_id: int, model_run_id: int | None
) -> tuple[StagingLoan, EclResult | None] | None:
    return session.execute(
        _loans_with_results(model_run_id).where(StagingLoan.loan_id == loan_id)
    ).one_or_none()


def portfolio_summary(session: Session, model_run_id: int, dataset: str | None = None) -> dict:
    """Agrégats du portefeuille scoré : global et par grade."""
    base = select(*_SEGMENT_COLUMNS).select_from(StagingLoan).join(
        EclResult,
        and_(EclResult.loan_id == StagingLoan.loan_id, EclResult.model_run_id == model_run_id),
    )
    if dataset is not None:
        base = base.where(StagingLoan.dataset == dataset)

    overall = session.execute(base).mappings().one()
    by_grade = session.execute(
        base.add_columns(StagingLoan.grade).group_by(StagingLoan.grade).order_by(StagingLoan.grade)
    ).mappings().all()
    return {"overall": dict(overall), "by_grade": [dict(row) for row in by_grade]}


def list_model_runs(session: Session, model_type: str | None = None) -> list[ModelRun]:
    query = select(ModelRun).order_by(ModelRun.id.desc())
    if model_type is not None:
        query = query.where(ModelRun.model_type == model_type)
    return list(session.scalars(query))


def list_etl_runs(session: Session, limit: int = 50) -> list[EtlRun]:
    return list(session.scalars(select(EtlRun).order_by(EtlRun.id.desc()).limit(limit)))
