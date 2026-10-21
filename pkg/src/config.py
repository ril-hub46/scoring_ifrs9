"""Paramètres d'exécution, surchargeables par variables d'environnement (préfixe SCORING_)
ou par un fichier .env à la racine du dossier de lancement.

Exemple : SCORING_DATA_DIR=/mnt/data  SCORING_RANDOM_STATE=7
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SCORING_", env_file=".env", extra="ignore")

    data_dir: Path = Path("data")

    # Valeurs par défaut alignées sur docker-compose.yml (Postgres exposé sur localhost:5432)
    database_url: str = "postgresql+psycopg://scoring:scoring@localhost:5432/scoring"

    # Split train/test
    test_size: float = 0.2
    random_state: int = 44

    # Imputation k-NN hot-deck
    k_neighbors: int = 10

    # Hypothèse de LGD tant qu'il n'y a pas de modèle LGD (standard prêt non garanti)
    default_lgd: float = 0.45

    # Origines autorisées à appeler l'API depuis un navigateur (front React plus tard)
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:8501"]

    @property
    def raw_data_path(self) -> Path:
        """Fichier source des prêts, chargé dans raw.loans."""
        return self.data_dir / "raw" / "data_final.csv"

    @property
    def models_dir(self) -> Path:
        """Artefacts des modèles entraînés (un fichier par ligne de mart.model_runs)."""
        return self.data_dir / "models"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def train_path(self) -> Path:
        """Ancien jeu train imputé, utilisé uniquement pour reconstruire la source."""
        return self.processed_dir / "train_imp.parquet"

    @property
    def test_path(self) -> Path:
        """Ancien jeu test imputé, utilisé uniquement pour reconstruire la source."""
        return self.processed_dir / "test_imp.parquet"


@lru_cache
def get_settings() -> Settings:
    return Settings()
