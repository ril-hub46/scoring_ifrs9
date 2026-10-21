import pytest

from src import features
from src.etl.transform import split_data
from src.ifrs9.ecl import compute_ecl, predict_pd
from src.modeling.train import train_pd_model


def test_compute_ecl_is_pd_times_lgd_times_ead():
    result = compute_ecl(pd_value=0.1, lgd=0.45, ead=25_000)

    assert result.ecl == pytest.approx(1_125)


@pytest.mark.parametrize(
    ("pd_value", "lgd", "ead"),
    [(-0.1, 0.45, 1000), (1.1, 0.45, 1000), (0.1, 1.5, 1000), (0.1, 0.45, -1)],
)
def test_compute_ecl_rejects_invalid_inputs(pd_value, lgd, ead):
    with pytest.raises(ValueError):
        compute_ecl(pd_value=pd_value, lgd=lgd, ead=ead)


def test_predict_pd_returns_probabilities_aligned_on_loans(loans):
    train, test = split_data(loans, features.TARGET, test_size=0.25, random_state=0)
    model = train_pd_model(train, test).model

    pds = predict_pd(model, test)

    assert pds.index.equals(test.index)
    assert pds.between(0, 1).all()
