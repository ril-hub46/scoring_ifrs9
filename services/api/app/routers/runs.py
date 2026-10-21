from fastapi import APIRouter, Query

from app.deps import DbSession
from app.schemas import EtlRunOut, ModelRunOut
from src.db import queries

router = APIRouter(tags=["runs"])


@router.get("/model-runs", response_model=list[ModelRunOut])
def list_model_runs(db: DbSession, model_type: str | None = None) -> list[ModelRunOut]:
    return [ModelRunOut.model_validate(run) for run in queries.list_model_runs(db, model_type)]


@router.get("/etl-runs", response_model=list[EtlRunOut])
def list_etl_runs(db: DbSession, limit: int = Query(50, ge=1, le=500)) -> list[EtlRunOut]:
    return [EtlRunOut.model_validate(run) for run in queries.list_etl_runs(db, limit)]
