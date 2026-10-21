import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.model_selection import train_test_split
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

# Au-delà de ce taux de valeurs manquantes, une variable n'est pas imputée par moyenne/mode
DET_IMPUTE_MAX_NA_PCT = 10


def split_data(
    data: pd.DataFrame, target: str, test_size: float, random_state: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Divise un DataFrame en jeux d'entraînement et de test, stratifiés sur `target`."""
    if target not in data.columns:
        raise ValueError(f"La colonne de stratification '{target}' n'existe pas dans le DataFrame.")

    train_set, test_set = train_test_split(
        data, test_size=test_size, random_state=random_state, stratify=data[target]
    )
    return train_set, test_set


def impute_deterministic(
    train_set: pd.DataFrame, test_set: pd.DataFrame, variables: list[str]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Impute par moyenne (numériques) ou mode (catégorielles) les variables peu manquantes.

    Les valeurs sont apprises sur `train_set` uniquement puis appliquées aux deux jeux.
    `annual_inc` est toujours imputée, quel que soit son taux de valeurs manquantes.
    """
    train_imp = train_set.copy()
    test_imp = test_set.copy()

    na_pct = train_set[variables].isna().mean().mul(100).round(2)
    to_fill = [col for col, pct in na_pct.items() if 0 < pct <= DET_IMPUTE_MAX_NA_PCT]
    if "annual_inc" not in to_fill and "annual_inc" in train_set.columns:
        to_fill.append("annual_inc")

    num_cols = [c for c in to_fill if pd.api.types.is_numeric_dtype(train_set[c])]
    cat_cols = [c for c in to_fill if c not in num_cols]

    for cols, strategy in ((num_cols, "mean"), (cat_cols, "most_frequent")):
        if not cols:
            continue
        imputer = SimpleImputer(strategy=strategy).fit(train_imp[cols])
        train_imp[cols] = imputer.transform(train_imp[cols])
        test_imp[cols] = imputer.transform(test_imp[cols])

    return train_imp, test_imp


def impute_knn_hotdeck(
    train_set: pd.DataFrame,
    test_set: pd.DataFrame,
    target_vars: list[str],
    numeric_features: list[str],
    ordinal_features: list[str],
    ordinal_categories: list[list[str]],
    nominal_features: list[str],
    k_neighbors: int = 10,
    random_state: int = 44,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Impute `target_vars` par hot-deck k-NN stochastique.

    Pour chaque ligne incomplète (« receveur »), on cherche ses k plus proches voisins
    parmi les lignes complètes du train (« donneurs ») et on recopie les valeurs d'un
    voisin tiré au hasard. Pas de fuite de données : l'encodage, les donneurs et le k-NN
    viennent uniquement de `train_set`, et seules les valeurs manquantes sont remplacées.
    """
    rng = np.random.RandomState(random_state)
    train_imp = train_set.copy()
    test_imp = test_set.copy()

    aux_vars = numeric_features + ordinal_features + nominal_features
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), numeric_features),
            ("cat_nom", OneHotEncoder(handle_unknown="ignore"), nominal_features),
            ("cat_ord", OrdinalEncoder(categories=ordinal_categories), ordinal_features),
        ],
        remainder="passthrough",
    ).fit(train_set[aux_vars])

    X_train = preprocessor.transform(train_set[aux_vars])
    X_test = preprocessor.transform(test_set[aux_vars])

    is_donor = train_set[target_vars].notna().all(axis=1).to_numpy()
    donors = train_set[is_donor]
    nn_model = NearestNeighbors(n_neighbors=k_neighbors, metric="euclidean", n_jobs=-1)
    nn_model.fit(X_train[is_donor])

    # L'ordre train puis test est conservé pour garder des tirages reproductibles
    for source, encoded, imputed in ((train_set, X_train, train_imp), (test_set, X_test, test_imp)):
        is_recipient = source[target_vars].isna().any(axis=1).to_numpy()
        if not is_recipient.any():
            continue

        _, neighbor_idx = nn_model.kneighbors(encoded[is_recipient])
        chosen = rng.randint(0, neighbor_idx.shape[1], size=len(neighbor_idx))
        donor_rows = donors.iloc[neighbor_idx[np.arange(len(neighbor_idx)), chosen]]
        donor_rows.index = source.index[is_recipient]

        for var in target_vars:
            imputed[var] = imputed[var].fillna(donor_rows[var])

    return train_imp, test_imp
