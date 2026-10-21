from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from src.config import Settings
from src.db import models  # noqa: F401  (enregistre les tables dans Base.metadata)
from src.db.base import OPS, SCHEMAS, Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_name(name, type_, parent_names):
    # On ne compare que nos schémas (ignore public et les schémas système)
    if type_ == "schema":
        return name in SCHEMAS
    return True


def _configure(**kwargs) -> None:
    context.configure(
        target_metadata=target_metadata,
        include_schemas=True,
        include_name=include_name,
        version_table_schema=OPS,
        compare_type=True,
        **kwargs,
    )


def run_migrations_offline() -> None:
    """Génère le SQL sans se connecter (uv run alembic upgrade head --sql)."""
    _configure(url=Settings().database_url, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(Settings().database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        # La table de version vit dans ops : le schéma doit exister avant la 1re migration
        connection.exec_driver_sql(f"CREATE SCHEMA IF NOT EXISTS {OPS}")
        connection.commit()
        _configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
