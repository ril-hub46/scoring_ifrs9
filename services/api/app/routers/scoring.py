import pandas as pd
from fastapi import APIRouter

from app.deps import ActiveModelDep, SettingsDep
from app.schemas import LoanFeatures, ScoreRequest, ScoreResponse
from src.ifrs9.ead import ead_at_origination
from src.ifrs9.ecl import STAGE_AT_ORIGINATION, compute_ecl, predict_pd

router = APIRouter(tags=["scoring"])


@router.post("/score", response_model=ScoreResponse)
def score(request: ScoreRequest, model: ActiveModelDep, settings: SettingsDep) -> ScoreResponse:
    """Calcule la PD d'un prêt avec le modèle actif, puis son ECL = PD × LGD × EAD."""
    loan = pd.DataFrame([request.model_dump(include=set(LoanFeatures.model_fields))])
    pd_value = float(predict_pd(model.pipeline, loan).iloc[0])

    ead = request.ead if request.ead is not None else float(ead_at_origination(loan).iloc[0])
    lgd = request.lgd if request.lgd is not None else settings.default_lgd
    result = compute_ecl(pd_value=pd_value, lgd=lgd, ead=ead)

    return ScoreResponse(
        model_run_id=model.run_id,
        stage=STAGE_AT_ORIGINATION,
        pd=result.pd,
        lgd=result.lgd,
        ead=result.ead,
        ead_source="provided" if request.ead is not None else "computed",
        ecl=result.ecl,
    )
