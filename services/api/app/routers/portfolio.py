from fastapi import APIRouter, HTTPException, Query, status

from app.deps import ActiveModelIdDep, DbSession
from app.schemas import Dataset, EclOut, Grade, LoanOut, LoanPage, LoanStatus, PortfolioSummary
from src.db import queries
from src.db.models import EclResult, StagingLoan

router = APIRouter(tags=["portfolio"])


def _loan_out(loan: StagingLoan, result: EclResult | None) -> LoanOut:
    out = LoanOut.model_validate(loan)
    out.result = EclOut.model_validate(result) if result else None
    return out


@router.get("/loans", response_model=LoanPage)
def list_loans(
    db: DbSession,
    model_run_id: ActiveModelIdDep,
    dataset: Dataset | None = None,
    grade: Grade | None = None,
    loan_status: LoanStatus | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> LoanPage:
    total, rows = queries.list_loans(
        db, model_run_id, dataset=dataset, grade=grade, loan_status=loan_status, limit=limit, offset=offset
    )
    return LoanPage(total=total, limit=limit, offset=offset, items=[_loan_out(*row) for row in rows])


@router.get("/loans/{loan_id}", response_model=LoanOut)
def get_loan(loan_id: int, db: DbSession, model_run_id: ActiveModelIdDep) -> LoanOut:
    row = queries.get_loan(db, loan_id, model_run_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Prêt {loan_id} introuvable")
    return _loan_out(*row)


@router.get("/portfolio/summary", response_model=PortfolioSummary)
def portfolio_summary(
    db: DbSession, model_run_id: ActiveModelIdDep, dataset: Dataset | None = None
) -> PortfolioSummary:
    """PD moyenne, taux de défaut observé, EAD et ECL du portefeuille, au global et par grade."""
    if model_run_id is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Aucun modèle PD actif.")

    summary = queries.portfolio_summary(db, model_run_id, dataset)

    def with_coverage(stats: dict) -> dict:
        ead, ecl = float(stats["total_ead"]), float(stats["total_ecl"])
        return stats | {"coverage_ratio": ecl / ead if ead else None}

    return PortfolioSummary(
        model_run_id=model_run_id,
        dataset=dataset,
        overall=with_coverage(summary["overall"]),
        by_grade=[with_coverage(row) for row in summary["by_grade"]],
    )
