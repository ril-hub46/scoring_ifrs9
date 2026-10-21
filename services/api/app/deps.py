from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sklearn.pipeline import Pipeline
from sqlalchemy.orm import Session

from src.config import Settings, get_settings
from src.db.session import session_scope
from src.modeling.registry import get_active_model_run, load_model


def get_db() -> Iterator[Session]:
    with session_scope() as session:
        yield session


@dataclass(frozen=True)
class ActiveModel:
    run_id: int
    pipeline: Pipeline


@lru_cache(maxsize=4)
def _load_cached(artifact_path: str) -> Pipeline:
    # Un artefact n'est jamais modifié après l'entraînement : on peut le garder en mémoire
    return load_model(Path(artifact_path))


def get_active_model(db: Annotated[Session, Depends(get_db)]) -> ActiveModel:
    run = get_active_model_run(db, "pd")
    if run is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Aucun modèle PD actif : lancer `scoring-ifrs9 train`.",
        )
    try:
        return ActiveModel(run_id=run.id, pipeline=_load_cached(run.artifact_path))
    except FileNotFoundError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


def get_active_model_id(db: Annotated[Session, Depends(get_db)]) -> int | None:
    """Id du modèle actif, sans charger l'artefact (pour les lectures du portefeuille)."""
    run = get_active_model_run(db, "pd")
    return run.id if run else None


DbSession = Annotated[Session, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
ActiveModelDep = Annotated[ActiveModel, Depends(get_active_model)]
ActiveModelIdDep = Annotated[int | None, Depends(get_active_model_id)]
