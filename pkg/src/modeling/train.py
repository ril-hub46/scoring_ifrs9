from dataclasses import dataclass

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder, StandardScaler

from src import features


@dataclass(frozen=True)
class Metrics:
    accuracy: float
    roc_auc: float


@dataclass(frozen=True)
class TrainingResult:
    model: Pipeline
    validation: Metrics
    test: Metrics


def build_pd_pipeline() -> Pipeline:
    """Pipeline PD : standardisation des numériques, encodage ordinal des catégorielles, régression logistique."""
    preprocessor = ColumnTransformer(transformers=[
        ("num", Pipeline(steps=[("scaler", StandardScaler())]), features.NUM_FEATURES),
        ("cat", Pipeline(steps=[("ord_enc", OrdinalEncoder(categories=features.CAT_ORDER))]), features.CAT_FEATURES),
    ])
    return Pipeline(steps=[
        ("preprocessor", preprocessor),
        ("classifier", LogisticRegression(max_iter=1000, solver="lbfgs")),
    ])


def split_xy(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Sépare features et cible, la cible étant encodée en 0 (remboursé) / 1 (défaut)."""
    return df[features.MODEL_FEATURES], df[features.TARGET].map(features.TARGET_MAPPING)


def evaluate(model: Pipeline, X: pd.DataFrame, y: pd.Series) -> Metrics:
    proba = model.predict_proba(X)[:, 1]
    return Metrics(
        accuracy=float(accuracy_score(y, (proba >= 0.5).astype(int))),
        roc_auc=float(roc_auc_score(y, proba)),
    )


def train_pd_model(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    validation_size: float = 0.2,
    random_state: int = 42,
) -> TrainingResult:
    """Entraîne le modèle PD sur une partie du train, l'évalue sur la validation puis sur le test."""
    X, y = split_xy(train_df)
    X_train, X_valid, y_train, y_valid = train_test_split(
        X, y, test_size=validation_size, random_state=random_state
    )

    model = build_pd_pipeline().fit(X_train, y_train)

    X_test, y_test = split_xy(test_df)
    return TrainingResult(
        model=model,
        validation=evaluate(model, X_valid, y_valid),
        test=evaluate(model, X_test, y_test),
    )
