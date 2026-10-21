"""Transferts en masse DataFrame <-> PostgreSQL via COPY (bien plus rapide que des INSERT)."""
import io

import pandas as pd
from sqlalchemy import Connection

CHUNK_ROWS = 200_000


def copy_from_dataframe(conn: Connection, table: str, df: pd.DataFrame) -> int:
    """Insère `df` dans `table` (colonnes = colonnes du DataFrame). Les NaN deviennent NULL."""
    columns = ", ".join(df.columns)
    with conn.connection.driver_connection.cursor() as cur:
        with cur.copy(f"COPY {table} ({columns}) FROM STDIN WITH (FORMAT csv)") as copy:
            for start in range(0, len(df), CHUNK_ROWS):
                copy.write(df.iloc[start:start + CHUNK_ROWS].to_csv(index=False, header=False))
    return len(df)


def read_query(conn: Connection, sql: str) -> pd.DataFrame:
    """Exécute une requête SELECT (sans paramètres) et renvoie le résultat en DataFrame."""
    buffer = io.BytesIO()
    with conn.connection.driver_connection.cursor() as cur:
        with cur.copy(f"COPY ({sql}) TO STDOUT WITH (FORMAT csv, HEADER)") as copy:
            for chunk in copy:
                buffer.write(chunk)
    buffer.seek(0)
    # Seule une cellule vide signifie NULL (sinon "NA" ou "None" seraient lus comme manquants)
    return pd.read_csv(buffer, keep_default_na=False, na_values=[""])
