from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy import Engine, func, update

from src.db.models import EtlRun
from src.db.session import session_scope


@dataclass
class RunStats:
    id: int
    rows_in: int | None = None
    rows_out: int | None = None


@contextmanager
def tracked_run(engine: Engine, step: str, params: dict | None = None) -> Iterator[RunStats]:
    """Trace une étape dans ops.etl_runs : 'running' au début, puis 'success' ou 'failed'.

    Le statut est écrit dans des transactions séparées de celle des données, pour qu'un échec
    reste visible dans ops.etl_runs même si l'écriture des données est annulée.
    """
    with session_scope(engine) as session:
        run = EtlRun(step=step, params=params)
        session.add(run)
        session.flush()
        stats = RunStats(id=run.id)

    def finish(status: str, error: str | None = None) -> None:
        with session_scope(engine) as session:
            session.execute(
                update(EtlRun).where(EtlRun.id == stats.id).values(
                    status=status, finished_at=func.now(), error=error,
                    rows_in=stats.rows_in, rows_out=stats.rows_out,
                )
            )

    try:
        yield stats
    except Exception as exc:
        finish("failed", f"{type(exc).__name__}: {exc}")
        raise
    finish("success")
