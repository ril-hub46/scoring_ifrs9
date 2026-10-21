"""Tests d'intégration PostgreSQL : schémas et contraintes (voir conftest.py pour la base de test)."""
import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from src.db.base import SCHEMAS
from src.db.models import EtlRun, ModelRun, RawLoan, StagingLoan
from src.db.session import session_scope

pytestmark = pytest.mark.db


@pytest.fixture
def engine(clean_db):
    return clean_db


def _staging_loan(loan_id: int, run_id: int, **overrides) -> StagingLoan:
    values = dict(
        loan_id=loan_id, dataset="train", term=" 36 months", int_rate=10.0, installment=300.0,
        grade="B", emp_length="5 years", home_ownership="RENT", annual_inc=50_000.0,
        loan_status="Fully Paid", dti=15.0, tot_cur_bal=10_000.0, open_acc_6m=1.0,
        total_bal_il=5_000.0, inq_fi=0.0, mort_acc=0.0, num_sats=5.0, etl_run_id=run_id,
    )
    return StagingLoan(**values | overrides)


def _seed_raw(engine, loan_id: int = 1) -> int:
    with session_scope(engine) as s:
        run = EtlRun(step="test")
        s.add(run)
        s.flush()
        s.add(RawLoan(loan_id=loan_id, etl_run_id=run.id))
        return run.id


def test_all_layers_and_tables_exist(engine):
    insp = inspect(engine)
    assert set(SCHEMAS) <= set(insp.get_schema_names())
    assert set(insp.get_table_names(schema="raw")) == {"loans"}
    assert set(insp.get_table_names(schema="staging")) == {"loans"}
    assert set(insp.get_table_names(schema="mart")) == {"model_runs", "pd_scores", "ecl_results"}
    assert {"etl_runs", "alembic_version"} <= set(insp.get_table_names(schema="ops"))


def test_raw_accepts_incomplete_rows_and_staging_accepts_clean_rows(engine):
    run_id = _seed_raw(engine)

    with session_scope(engine) as s:
        s.add(_staging_loan(1, run_id))

    with session_scope(engine) as s:
        assert s.get(StagingLoan, 1).grade == "B"
        assert s.get(RawLoan, 1).grade is None


@pytest.mark.parametrize(
    "overrides",
    [{"grade": "Z"}, {"loan_status": "Current"}, {"dataset": "valid"}, {"int_rate": -1.0}, {"dti": None}],
)
def test_staging_rejects_invalid_rows(engine, overrides):
    run_id = _seed_raw(engine)

    with pytest.raises(IntegrityError), session_scope(engine) as s:
        s.add(_staging_loan(1, run_id, **overrides))


def test_staging_requires_matching_raw_loan(engine):
    run_id = _seed_raw(engine, loan_id=1)

    with pytest.raises(IntegrityError), session_scope(engine) as s:
        s.add(_staging_loan(999, run_id))


def test_only_one_active_model_per_type(engine):
    def model(active: bool) -> ModelRun:
        return ModelRun(model_type="pd", algorithm="logreg", artifact_path="x.pkl", is_active=active)

    with session_scope(engine) as s:
        s.add_all([model(True), model(False), model(False)])

    with pytest.raises(IntegrityError), session_scope(engine) as s:
        s.add(model(True))
