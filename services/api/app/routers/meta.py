from fastapi import APIRouter
from sqlalchemy import text

from app.deps import DbSession, SettingsDep
from app.schemas import Health, ReferenceData
from src import features

router = APIRouter(tags=["meta"])


@router.get("/health", response_model=Health)
def health(db: DbSession) -> Health:
    db.execute(text("SELECT 1"))
    return Health(status="ok", database="ok")


@router.get("/reference", response_model=ReferenceData)
def reference(settings: SettingsDep) -> ReferenceData:
    return ReferenceData(
        terms=features.TERM_VALUES,
        grades=features.GRADES,
        emp_lengths=features.EMP_LENGTHS,
        home_ownerships=features.HOME_OWNERSHIPS,
        default_lgd=settings.default_lgd,
    )
