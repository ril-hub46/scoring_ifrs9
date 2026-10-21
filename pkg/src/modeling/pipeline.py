import logging
from dataclasses import asdict

from sqlalchemy import Engine, update

from src import features
from src.config import Settings
from src.db.io import read_query
from src.db.models import ModelRun
from src.db.session import session_scope
from src.modeling.registry import save_model
from src.modeling.train import train_pd_model

logger = logging.getLogger(__name__)

JSON_SCALARS = (bool, int, float, str, type(None))


def train_and_register(engine: Engine, settings: Settings) -> int:
    """Entraîne le modèle PD sur staging.loans, sauvegarde l'artefact et l'active dans mart.model_runs.

    L'ancien modèle actif est désactivé dans la même transaction : il y a toujours au plus un
    modèle PD actif, et c'est lui qu'utilisent le scoring du portefeuille et l'API.
    """
    columns = ["dataset", features.TARGET] + features.MODEL_FEATURES
    with engine.connect() as conn:
        loans = read_query(conn, f"SELECT {', '.join(columns)} FROM staging.loans")
    train_df, test_df = loans[loans["dataset"] == "train"], loans[loans["dataset"] == "test"]
    if train_df.empty or test_df.empty:
        raise RuntimeError("staging.loans est vide : lancer d'abord `scoring-ifrs9 staging`.")

    result = train_pd_model(train_df, test_df)
    classifier = result.model.named_steps["classifier"]

    with session_scope(engine) as session:
        session.execute(
            update(ModelRun).where(ModelRun.model_type == "pd", ModelRun.is_active).values(is_active=False)
        )
        run = ModelRun(
            model_type="pd",
            algorithm=type(classifier).__name__,
            params={k: v for k, v in classifier.get_params().items() if isinstance(v, JSON_SCALARS)},
            metrics={
                "validation": asdict(result.validation),
                "test": asdict(result.test),
                "n_train": len(train_df),
                "n_test": len(test_df),
            },
            artifact_path="",
            is_active=True,
        )
        session.add(run)
        session.flush()

        path = settings.models_dir / f"pd_{run.id}.pkl"
        save_model(result.model, path)
        run.artifact_path = path.as_posix()
        run_id = run.id

    logger.info(
        "Modèle PD %d actif — validation AUC=%.4f, test AUC=%.4f (%s)",
        run_id, result.validation.roc_auc, result.test.roc_auc, path,
    )
    return run_id
