"""Fixtures partagées par les tests du package (pkg/tests) et de l'API (services/api/tests).

Les tests marqués `db` utilisent PostgreSQL et sont ignorés sauf si SCORING_TEST_DATABASE_URL
pointe vers une base de test VIDE et jetable (migrations appliquées, tables vidées après chaque test) :
    SCORING_TEST_DATABASE_URL=postgresql+psycopg://scoring:scoring@localhost:5432/scoring_test
"""
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from src import features
from src.config import Settings

ROOT = Path(__file__).resolve().parent
TEST_DATABASE_URL = os.environ.get("SCORING_TEST_DATABASE_URL")


def pytest_configure(config):
    config.addinivalue_line("markers", "db: nécessite SCORING_TEST_DATABASE_URL (PostgreSQL)")


def pytest_collection_modifyitems(config, items):
    if TEST_DATABASE_URL:
        return
    skip = pytest.mark.skip(reason="SCORING_TEST_DATABASE_URL non défini")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def loans() -> pd.DataFrame:
    """Petit portefeuille synthétique au format de la source, défaut corrélé au grade."""
    rng = np.random.default_rng(0)
    n = 400
    grade_idx = rng.integers(0, len(features.GRADES), size=n)
    default = rng.random(n) < 0.05 + 0.08 * grade_idx
    return pd.DataFrame({
        "loan_id": np.arange(1000, 1000 + n),
        "term": rng.choice(features.TERM_VALUES, size=n),
        "int_rate": 6 + 3 * grade_idx + rng.normal(0, 1, n),
        "installment": rng.uniform(50, 1500, n),
        "grade": np.array(features.GRADES)[grade_idx],
        "emp_length": rng.choice(features.EMP_LENGTHS, size=n),
        "home_ownership": rng.choice(["OWN", "MORTGAGE", "RENT"], size=n),
        "annual_inc": rng.uniform(20_000, 200_000, n),
        "loan_status": np.where(default, "Charged Off", "Fully Paid"),
        "dti": rng.uniform(0, 40, n),
        "tot_cur_bal": rng.uniform(0, 500_000, n),
        "open_acc_6m": rng.integers(0, 5, n).astype(float),
        "total_bal_il": rng.uniform(0, 100_000, n),
        "inq_fi": rng.integers(0, 6, n).astype(float),
        "mort_acc": rng.integers(0, 4, n).astype(float),
        "num_sats": rng.integers(1, 30, n).astype(float),
        "out_prncp": 0.0,
        "total_pymnt": rng.uniform(1_000, 30_000, n),
        "recoveries": np.where(default, rng.uniform(0, 2_000, n), 0.0),
    })


@pytest.fixture
def loans_with_na(loans: pd.DataFrame) -> pd.DataFrame:
    """Même portefeuille avec des trous : peu sur annual_inc/dti, beaucoup sur les variables k-NN."""
    rng = np.random.default_rng(1)
    df = loans.copy()
    df.loc[rng.random(len(df)) < 0.03, "annual_inc"] = np.nan
    df.loc[rng.random(len(df)) < 0.05, "dti"] = np.nan
    for col in features.KNN_TARGET_VARS:
        df.loc[rng.random(len(df)) < 0.3, col] = np.nan
    return df


@pytest.fixture(scope="session")
def db_engine():
    if not TEST_DATABASE_URL:
        pytest.skip("SCORING_TEST_DATABASE_URL non défini")
    os.environ["SCORING_DATABASE_URL"] = TEST_DATABASE_URL  # lu par migrations/env.py
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    engine = create_engine(TEST_DATABASE_URL)
    yield engine
    engine.dispose()


@pytest.fixture
def clean_db(db_engine):
    """Base migrée, vidée après le test."""
    yield db_engine
    with db_engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE mart.ecl_results, mart.pd_scores, mart.model_runs, "
            "staging.loans, raw.loans, ops.etl_runs RESTART IDENTITY CASCADE"
        ))


@pytest.fixture
def db_settings(tmp_path, loans_with_na) -> Settings:
    """Paramètres pointant vers la base de test et un fichier source synthétique (avec trous)."""
    settings = Settings(data_dir=tmp_path, database_url=TEST_DATABASE_URL or "")
    settings.raw_data_path.parent.mkdir(parents=True)
    loans_with_na.to_csv(settings.raw_data_path, index=False)
    return settings


@pytest.fixture
def loaded_db(clean_db, db_settings):
    """Base alimentée par tout le pipeline : raw -> staging -> modèle actif -> mart."""
    from src.etl.pipeline import build_staging, ingest_raw, score_portfolio
    from src.modeling.pipeline import train_and_register

    ingest_raw(clean_db, db_settings)
    build_staging(clean_db, db_settings)
    train_and_register(clean_db, db_settings)
    score_portfolio(clean_db, db_settings)
    return clean_db
