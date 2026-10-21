"""Étapes de l'ETL, chacune tracée dans ops.etl_runs.

    fichier source --ingest_raw--> raw.loans --build_staging--> staging.loans
    staging.loans + modèle PD actif --score_portfolio--> mart.pd_scores, mart.ecl_results

Chaque étape recharge entièrement sa table cible (TRUNCATE puis COPY, dans une transaction) :
en cas d'erreur, la table garde son contenu précédent.
"""
import logging
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine, text

from src import features
from src.config import Settings
from src.db.io import copy_from_dataframe, read_query
from src.db.session import session_scope
from src.etl.extract import load_raw_data
from src.etl.runs import tracked_run
from src.etl.transform import impute_deterministic, impute_knn_hotdeck, split_data
from src.ifrs9.ead import ead_at_origination
from src.ifrs9.ecl import compute_ecl_frame, predict_pd
from src.modeling.registry import get_active_model_run, load_model

logger = logging.getLogger(__name__)

STAGING_COLUMNS = [features.LOAN_ID, "dataset"] + features.SOURCE_COLUMNS


def ingest_raw(engine: Engine, settings: Settings) -> int:
    """Charge le fichier source tel quel dans raw.loans.

    Le TRUNCATE ... CASCADE vide aussi staging et mart, qui dépendent de raw.
    """
    source_path = settings.raw_data_path
    with tracked_run(engine, "ingest_raw", {"source": str(source_path)}) as run:
        source = load_raw_data(source_path)
        run.rows_in = len(source)

        with engine.begin() as conn:
            conn.execute(text("TRUNCATE raw.loans CASCADE"))
            run.rows_out = copy_from_dataframe(conn, "raw.loans", source.assign(etl_run_id=run.id))

    logger.info("raw.loans : %d prêts chargés depuis %s", run.rows_out, source_path)
    return run.rows_out


def prepare_staging(raw: pd.DataFrame, settings: Settings) -> pd.DataFrame:
    """Nettoie et impute les prêts bruts (fonction pure, sans base de données).

    1. Garde les prêts au statut connu (remboursé / en défaut) et aux modalités connues
       (une valeur manquante est acceptée : elle sera imputée).
    2. Split train/test stratifié.
    3. Imputation déterministe puis k-NN hot-deck (apprises sur le train uniquement).
    4. Écarte les lignes où il reste une valeur manquante.
    """
    valid = raw[features.TARGET].isin(features.TARGET_MAPPING)
    for column, allowed in zip(features.CAT_FEATURES, features.CAT_ORDER):
        valid &= raw[column].isin(allowed) | raw[column].isna()
    if (~valid).any():
        logger.warning("%d prêts écartés (statut ou modalité inconnus)", (~valid).sum())
    known = raw[valid]

    train, test = split_data(
        known, target=features.TARGET, test_size=settings.test_size, random_state=settings.random_state
    )
    train, test = impute_deterministic(train, test, variables=features.DET_IMPUTE_VARS)
    train, test = impute_knn_hotdeck(
        train,
        test,
        target_vars=features.KNN_TARGET_VARS,
        numeric_features=features.KNN_AUX_NUM,
        ordinal_features=features.KNN_AUX_ORD,
        ordinal_categories=[features.GRADES],
        nominal_features=features.KNN_AUX_NOM,
        k_neighbors=settings.k_neighbors,
        random_state=settings.random_state,
    )
    staged = pd.concat([train.assign(dataset="train"), test.assign(dataset="test")])

    complete = staged[features.MODEL_FEATURES].notna().all(axis=1)
    if (~complete).any():
        logger.warning("%d prêts écartés (valeurs manquantes après imputation)", (~complete).sum())

    return staged.loc[complete, STAGING_COLUMNS].sort_values(features.LOAN_ID)


def build_staging(engine: Engine, settings: Settings) -> int:
    """raw.loans -> staging.loans (nettoyage, split, imputation)."""
    params = {
        "test_size": settings.test_size,
        "random_state": settings.random_state,
        "k_neighbors": settings.k_neighbors,
    }
    with tracked_run(engine, "build_staging", params) as run:
        with engine.connect() as conn:
            raw = read_query(conn, f"SELECT {features.LOAN_ID}, {', '.join(features.SOURCE_COLUMNS)} FROM raw.loans")
        run.rows_in = len(raw)

        staged = prepare_staging(raw, settings)

        with engine.begin() as conn:
            conn.execute(text("TRUNCATE staging.loans CASCADE"))
            run.rows_out = copy_from_dataframe(conn, "staging.loans", staged.assign(etl_run_id=run.id))

    logger.info("staging.loans : %d prêts (sur %d bruts)", run.rows_out, run.rows_in)
    return run.rows_out


def score_portfolio(engine: Engine, settings: Settings) -> int:
    """Calcule PD, EAD et ECL de tous les prêts de staging avec le modèle PD actif."""
    with session_scope(engine) as session:
        model_run = get_active_model_run(session, "pd")
        if model_run is None:
            raise RuntimeError("Aucun modèle PD actif : lancer d'abord `scoring-ifrs9 train`.")
        model_run_id, artifact_path = model_run.id, Path(model_run.artifact_path)

    lgd = settings.default_lgd
    with tracked_run(engine, "score_portfolio", {"model_run_id": model_run_id, "lgd": lgd}) as run:
        model = load_model(artifact_path)
        with engine.connect() as conn:
            loans = read_query(
                conn, f"SELECT {features.LOAN_ID}, {', '.join(features.MODEL_FEATURES)} FROM staging.loans"
            ).set_index(features.LOAN_ID)
        run.rows_in = len(loans)

        results = compute_ecl_frame(predict_pd(model, loans), lgd, ead_at_origination(loans))
        results = results.assign(model_run_id=model_run_id).reset_index()

        with engine.begin() as conn:
            params = {"run_id": model_run_id}
            conn.execute(text("DELETE FROM mart.ecl_results WHERE model_run_id = :run_id"), params)
            conn.execute(text("DELETE FROM mart.pd_scores WHERE model_run_id = :run_id"), params)
            copy_from_dataframe(conn, "mart.pd_scores", results[[features.LOAN_ID, "model_run_id", "pd"]])
            run.rows_out = copy_from_dataframe(
                conn, "mart.ecl_results",
                results[[features.LOAN_ID, "model_run_id", "stage", "pd", "lgd", "ead", "ecl"]],
            )

    logger.info("mart : %d prêts scorés avec le modèle %d", run.rows_out, model_run_id)
    return run.rows_out
