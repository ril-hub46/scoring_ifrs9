from pathlib import Path

import pandas as pd

from src import features

LEGACY_ID_COLUMN = "Unnamed: 0"  # index du CSV d'origine, conservé dans les anciens parquets


def load_raw_data(path: Path) -> pd.DataFrame:
    """Charge le fichier source des prêts et vérifie sa structure."""
    if not path.exists():
        raise FileNotFoundError(
            f"Fichier source introuvable : {path}. "
            "Le reconstruire avec `uv run scoring-ifrs9 rebuild-source`."
        )
    df = pd.read_csv(path, keep_default_na=False, na_values=[""])

    expected = [features.LOAN_ID] + features.SOURCE_COLUMNS
    missing = [c for c in expected if c not in df.columns]
    if missing:
        raise ValueError(f"Colonnes manquantes dans {path} : {missing}")
    if not df[features.LOAN_ID].is_unique:
        raise ValueError(f"{features.LOAN_ID} n'est pas unique dans {path}")
    return df[expected]


def rebuild_source_from_parquets(train_path: Path, test_path: Path, output_path: Path) -> int:
    """Reconstruit le fichier source à partir des anciens jeux train/test imputés.

    Le fichier brut d'origine (data_final.csv) a été perdu. Ces données sont déjà imputées :
    elles ne contiennent plus de valeurs manquantes, mais ont la même structure que la source.
    """
    df = pd.concat([pd.read_parquet(train_path), pd.read_parquet(test_path)])
    df = df.rename(columns={LEGACY_ID_COLUMN: features.LOAN_ID})
    df = df[[features.LOAN_ID] + features.SOURCE_COLUMNS].sort_values(features.LOAN_ID)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    return len(df)
