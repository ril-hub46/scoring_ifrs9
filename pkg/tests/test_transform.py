import numpy as np
import pandas as pd
import pytest

from src import features
from src.etl.transform import impute_deterministic, impute_knn_hotdeck, split_data


def _knn(train, test, random_state=44):
    return impute_knn_hotdeck(
        train,
        test,
        target_vars=features.KNN_TARGET_VARS,
        numeric_features=features.KNN_AUX_NUM,
        ordinal_features=features.KNN_AUX_ORD,
        ordinal_categories=[features.GRADES],
        nominal_features=features.KNN_AUX_NOM,
        k_neighbors=5,
        random_state=random_state,
    )


def _prepared(loans_with_na):
    train, test = split_data(loans_with_na, features.TARGET, test_size=0.25, random_state=0)
    return impute_deterministic(train, test, variables=features.DET_IMPUTE_VARS)


def test_split_is_stratified_and_disjoint(loans):
    train, test = split_data(loans, features.TARGET, test_size=0.25, random_state=0)

    assert len(train) + len(test) == len(loans)
    assert train.index.intersection(test.index).empty
    rate = lambda df: (df[features.TARGET] == "Charged Off").mean()
    assert rate(train) == pytest.approx(rate(test), abs=0.02)


def test_split_rejects_unknown_target(loans):
    with pytest.raises(ValueError, match="stratification"):
        split_data(loans, "unknown", test_size=0.2, random_state=0)


def test_impute_deterministic_fills_low_na_columns_with_train_mean(loans_with_na):
    train, test = split_data(loans_with_na, features.TARGET, test_size=0.25, random_state=0)
    train_imp, test_imp = impute_deterministic(train, test, variables=features.DET_IMPUTE_VARS)

    assert train_imp[["annual_inc", "dti"]].notna().all().all()
    assert test_imp[["annual_inc", "dti"]].notna().all().all()
    # Le test est imputé avec la moyenne apprise sur le train (pas de fuite)
    filled = test["dti"].isna()
    assert np.allclose(test_imp.loc[filled, "dti"], train["dti"].mean())
    # Les variables trop manquantes (> 10 %) sont laissées au k-NN
    assert train_imp[features.KNN_TARGET_VARS].isna().any().all()
    # Les entrées ne sont pas modifiées
    assert train["dti"].isna().any()


def test_knn_hotdeck_fills_only_missing_values_from_train_donors(loans_with_na):
    train, test = _prepared(loans_with_na)
    train_imp, test_imp = _knn(train, test)

    for original, imputed in ((train, train_imp), (test, test_imp)):
        assert imputed[features.KNN_TARGET_VARS].notna().all().all()
        known = original[features.KNN_TARGET_VARS].notna()
        pd.testing.assert_frame_equal(
            imputed[features.KNN_TARGET_VARS].where(known), original[features.KNN_TARGET_VARS]
        )

    # Chaque ligne du test complétée reprend le bloc de valeurs d'un donneur complet du train
    donors = train[train[features.KNN_TARGET_VARS].notna().all(axis=1)][features.KNN_TARGET_VARS]
    donor_blocks = set(map(tuple, donors.to_numpy()))
    fully_missing = test[features.KNN_TARGET_VARS].isna().all(axis=1)
    for row in test_imp.loc[fully_missing, features.KNN_TARGET_VARS].to_numpy():
        assert tuple(row) in donor_blocks


def test_knn_hotdeck_is_reproducible(loans_with_na):
    train, test = _prepared(loans_with_na)

    first = _knn(train, test, random_state=7)
    second = _knn(train, test, random_state=7)

    pd.testing.assert_frame_equal(first[0], second[0])
    pd.testing.assert_frame_equal(first[1], second[1])


def test_knn_hotdeck_does_not_touch_global_random_state(loans_with_na):
    train, test = _prepared(loans_with_na)
    np.random.seed(123)
    expected = np.random.rand()

    np.random.seed(123)
    _knn(train, test)

    assert np.random.rand() == expected
