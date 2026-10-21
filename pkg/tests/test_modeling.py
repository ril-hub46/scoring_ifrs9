import pandas as pd

from src import features
from src.etl.transform import split_data
from src.modeling.registry import load_model, save_model
from src.modeling.train import train_pd_model


def test_train_pd_model_learns_and_leaves_inputs_untouched(loans):
    train, test = split_data(loans, features.TARGET, test_size=0.25, random_state=0)
    train_before, test_before = train.copy(), test.copy()

    result = train_pd_model(train, test)

    # Le défaut dépend du grade dans les données synthétiques : le modèle doit le capter
    assert result.validation.roc_auc > 0.6
    assert result.test.roc_auc > 0.6
    assert 0 <= result.test.accuracy <= 1
    pd.testing.assert_frame_equal(train, train_before)
    pd.testing.assert_frame_equal(test, test_before)


def test_model_roundtrip(loans, tmp_path):
    train, test = split_data(loans, features.TARGET, test_size=0.25, random_state=0)
    model = train_pd_model(train, test).model
    path = tmp_path / "models" / "pd.pkl"

    save_model(model, path)
    reloaded = load_model(path)

    X = test[features.MODEL_FEATURES]
    assert (reloaded.predict_proba(X) == model.predict_proba(X)).all()
