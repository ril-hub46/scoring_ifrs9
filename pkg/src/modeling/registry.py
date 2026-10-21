"""Registre des modèles : artefacts sur disque, métadonnées dans mart.model_runs."""
from pathlib import Path

import joblib
from sqlalchemy import select
from sqlalchemy.orm import Session
from sklearn.pipeline import Pipeline

from src.db.models import ModelRun


def save_model(model: Pipeline, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path)


def load_model(path: Path) -> Pipeline:
    if not path.exists():
        raise FileNotFoundError(f"Modèle introuvable : {path}")
    return joblib.load(path)


def get_active_model_run(session: Session, model_type: str = "pd") -> ModelRun | None:
    return session.scalar(
        select(ModelRun).where(ModelRun.model_type == model_type, ModelRun.is_active)
    )
