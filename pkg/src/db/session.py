from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.config import get_settings


@lru_cache
def get_engine(database_url: str | None = None) -> Engine:
    return create_engine(database_url or get_settings().database_url, pool_pre_ping=True)


@contextmanager
def session_scope(engine: Engine | None = None) -> Iterator[Session]:
    """Session transactionnelle : commit si tout se passe bien, rollback sinon."""
    factory = sessionmaker(bind=engine or get_engine(), expire_on_commit=False)
    with factory() as session, session.begin():
        yield session
