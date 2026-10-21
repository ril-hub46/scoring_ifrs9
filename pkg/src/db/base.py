from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Couches de données (architecture médaillon) + schéma technique de suivi
RAW = "raw"          # données telles que reçues de la source
STAGING = "staging"  # données nettoyées, imputées, prêtes pour la modélisation
MART = "mart"        # résultats métier lus par l'API et le front
OPS = "ops"          # traçabilité des exécutions (ETL, entraînements)
SCHEMAS = (RAW, STAGING, MART, OPS)

# Noms de contraintes déterministes : indispensable pour qu'Alembic puisse les modifier/supprimer
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
