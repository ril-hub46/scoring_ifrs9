import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.deps import ActiveModel, get_active_model, get_db
from app.main import app
from src import features
from src.etl.transform import split_data
from src.modeling.train import train_pd_model

LOAN = {
    "term": " 36 months", "int_rate": 12.0, "installment": 332.1431, "grade": "C",
    "emp_length": "5 years", "home_ownership": "RENT", "annual_inc": 60_000, "dti": 15.0,
    "tot_cur_bal": 150_000, "open_acc_6m": 0, "total_bal_il": 50_000, "inq_fi": 0,
    "mort_acc": 1, "num_sats": 8,
}


@pytest.fixture
def client_with_model(loans):
    """Client dont le modèle actif est entraîné à la volée : pas besoin de base."""
    train, test = split_data(loans, features.TARGET, test_size=0.25, random_state=0)
    model = ActiveModel(run_id=42, pipeline=train_pd_model(train, test).model)
    app.dependency_overrides[get_active_model] = lambda: model
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def client_db(loaded_db):
    """Client branché sur la base de test alimentée par le pipeline complet."""
    factory = sessionmaker(bind=loaded_db)

    def get_test_db():
        with factory() as session, session.begin():
            yield session

    app.dependency_overrides[get_db] = get_test_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_score_computes_ecl_from_pd_lgd_and_given_ead(client_with_model):
    response = client_with_model.post("/score", json=LOAN | {"ead": 25_000, "lgd": 0.5})

    assert response.status_code == 200
    body = response.json()
    assert body["model_run_id"] == 42 and body["stage"] == 1
    assert 0 < body["pd"] < 1
    assert body["ead_source"] == "provided"
    assert body["ecl"] == pytest.approx(body["pd"] * 0.5 * 25_000)


def test_score_reconstructs_ead_and_uses_default_lgd(client_with_model):
    body = client_with_model.post("/score", json=LOAN).json()

    assert body["ead_source"] == "computed"
    assert body["ead"] == pytest.approx(10_000, abs=0.01)
    assert body["lgd"] == 0.45


@pytest.mark.parametrize("change", [{"grade": "Z"}, {"lgd": 1.5}, {"installment": 0}, {"term": "36 months"}])
def test_score_rejects_invalid_input(client_with_model, change):
    assert client_with_model.post("/score", json=LOAN | change).status_code == 422


def test_reference_lists_allowed_values():
    body = TestClient(app).get("/reference").json()

    assert body["grades"] == features.GRADES
    assert body["terms"] == features.TERM_VALUES


@pytest.mark.db
def test_health(client_db):
    assert client_db.get("/health").json() == {"status": "ok", "database": "ok"}


@pytest.mark.db
def test_score_uses_active_model_from_database(client_db):
    body = client_db.post("/score", json=LOAN).json()

    runs = client_db.get("/model-runs").json()
    assert body["model_run_id"] == next(r["id"] for r in runs if r["is_active"])


@pytest.mark.db
def test_loans_pagination_filters_and_results(client_db, loans):
    page = client_db.get("/loans", params={"grade": "A", "limit": 5, "offset": 0}).json()

    assert page["total"] == (loans["grade"] == "A").sum()
    assert len(page["items"]) == 5
    assert all(item["grade"] == "A" and item["result"] is not None for item in page["items"])

    loan = client_db.get(f"/loans/{page['items'][0]['loan_id']}").json()
    assert loan == page["items"][0]
    assert client_db.get("/loans/999999").status_code == 404


@pytest.mark.db
def test_portfolio_summary_totals_match_grades(client_db, loans):
    summary = client_db.get("/portfolio/summary").json()

    overall, by_grade = summary["overall"], summary["by_grade"]
    assert overall["n_loans"] == len(loans)
    assert sum(g["n_loans"] for g in by_grade) == len(loans)
    assert sum(g["total_ecl"] for g in by_grade) == pytest.approx(overall["total_ecl"])
    assert overall["coverage_ratio"] == pytest.approx(overall["total_ecl"] / overall["total_ead"])

    test_only = client_db.get("/portfolio/summary", params={"dataset": "test"}).json()
    assert test_only["overall"]["n_loans"] < overall["n_loans"]


@pytest.mark.db
def test_runs_history(client_db):
    model_runs = client_db.get("/model-runs").json()
    etl_runs = client_db.get("/etl-runs").json()

    assert len(model_runs) == 1 and model_runs[0]["is_active"]
    assert {r["step"] for r in etl_runs} == {"ingest_raw", "build_staging", "score_portfolio"}
