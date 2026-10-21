"""Tests de l'ETL : partie pure (prepare_staging) et pipeline complet sur PostgreSQL."""
import numpy as np
import pandas as pd
import pytest
from sqlalchemy import select, text

from src import features
from src.config import Settings
from src.db.models import EtlRun, ModelRun
from src.db.session import session_scope
from src.etl.extract import load_raw_data, rebuild_source_from_parquets
from src.etl.pipeline import build_staging, ingest_raw, prepare_staging, score_portfolio
from src.modeling.pipeline import train_and_register


def test_prepare_staging_imputes_splits_and_drops_unknown_status(loans_with_na):
    raw = loans_with_na.copy()
    raw.loc[raw.index[:5], "loan_status"] = "Current"

    staged = prepare_staging(raw, Settings())

    assert len(staged) == len(raw) - 5
    assert set(staged["dataset"]) == {"train", "test"}
    assert staged[features.MODEL_FEATURES].notna().all().all()
    assert staged[features.LOAN_ID].is_unique
    assert list(staged.columns) == [features.LOAN_ID, "dataset"] + features.SOURCE_COLUMNS


def test_prepare_staging_drops_rows_with_unknown_modalities(loans):
    raw = loans.copy()
    raw.loc[raw.index[0], "grade"] = "Z"

    staged = prepare_staging(raw, Settings())

    assert raw.loc[raw.index[0], "loan_id"] not in staged["loan_id"].values


def test_rebuild_source_renames_legacy_id(tmp_path, loans):
    legacy = loans.rename(columns={"loan_id": "Unnamed: 0"})
    legacy.iloc[:300].to_parquet(tmp_path / "train.parquet")
    legacy.iloc[300:].to_parquet(tmp_path / "test.parquet")
    output = tmp_path / "raw" / "source.csv"

    n = rebuild_source_from_parquets(tmp_path / "train.parquet", tmp_path / "test.parquet", output)

    source = load_raw_data(output)
    assert n == len(loans) == len(source)
    assert source["term"].isin(features.TERM_VALUES).all()  # l'espace initial est conservé
    pd.testing.assert_frame_equal(source, loans[source.columns], check_dtype=False)


def test_load_raw_data_rejects_duplicate_ids(tmp_path, loans):
    path = tmp_path / "source.csv"
    pd.concat([loans, loans.iloc[:1]]).to_csv(path, index=False)

    with pytest.raises(ValueError, match="unique"):
        load_raw_data(path)


@pytest.mark.db
def test_full_pipeline_fills_every_layer(loaded_db, loans_with_na, db_settings):
    with loaded_db.connect() as conn:
        count = lambda table: conn.execute(text(f"SELECT count(*) FROM {table}")).scalar()
        assert count("raw.loans") == len(loans_with_na)
        assert count("staging.loans") == len(loans_with_na)
        assert count("mart.pd_scores") == count("mart.ecl_results") == len(loans_with_na)

        # Raw garde les trous de la source, staging n'en a plus
        assert conn.execute(text("SELECT count(*) FROM raw.loans WHERE inq_fi IS NULL")).scalar() > 0

        # ECL = PD × LGD × EAD (à l'arrondi au centime près)
        gap = conn.execute(text("SELECT max(abs(ecl - pd * lgd * ead)) FROM mart.ecl_results")).scalar()
        assert gap <= 0.01

    with session_scope(loaded_db) as session:
        runs = session.scalars(select(EtlRun).order_by(EtlRun.id)).all()
        assert [r.step for r in runs] == ["ingest_raw", "build_staging", "score_portfolio"]
        assert all(r.status == "success" and r.finished_at is not None for r in runs)

        model = session.scalar(select(ModelRun).where(ModelRun.is_active))
        assert model.metrics["test"]["roc_auc"] > 0.6
        assert (db_settings.data_dir / "models" / f"pd_{model.id}.pkl").exists()


@pytest.mark.db
def test_retraining_switches_active_model_and_rescoring_is_idempotent(loaded_db, db_settings):
    new_id = train_and_register(loaded_db, db_settings)
    score_portfolio(loaded_db, db_settings)
    score_portfolio(loaded_db, db_settings)

    with session_scope(loaded_db) as session:
        active = session.scalars(select(ModelRun.id).where(ModelRun.is_active)).all()
        assert active == [new_id]

    with loaded_db.connect() as conn:
        per_model = dict(conn.execute(
            text("SELECT model_run_id, count(*) FROM mart.ecl_results GROUP BY model_run_id")
        ).all())
    # L'ancien modèle garde ses résultats (historique), le nouveau n'est pas dupliqué
    assert len(per_model) == 2
    assert len(set(per_model.values())) == 1


@pytest.mark.db
def test_failed_step_is_recorded_and_keeps_previous_data(loaded_db, db_settings):
    db_settings.raw_data_path.write_text("pas,le,bon,format\n1,2,3,4\n")

    with pytest.raises(ValueError):
        ingest_raw(loaded_db, db_settings)

    with session_scope(loaded_db) as session:
        last = session.scalar(select(EtlRun).order_by(EtlRun.id.desc()))
        assert last.step == "ingest_raw" and last.status == "failed"
        assert "Colonnes manquantes" in last.error
    with loaded_db.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM staging.loans")).scalar() > 0


@pytest.mark.db
def test_scoring_without_active_model_fails_clearly(clean_db, db_settings):
    ingest_raw(clean_db, db_settings)
    build_staging(clean_db, db_settings)

    with pytest.raises(RuntimeError, match="Aucun modèle PD actif"):
        score_portfolio(clean_db, db_settings)
