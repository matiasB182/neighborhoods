"""Conexión a Redshift y helpers de query."""

import os
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

SCHEMA      = os.environ.get("REDSHIFT_SCHEMA", "mcd")
FORECAST_TABLE = os.environ.get("FORECAST_TABLE", "forecast")  # nombre completo o solo tabla

_CONN_PARAMS = dict(
    host=os.environ["REDSHIFT_HOST"],
    port=int(os.environ.get("REDSHIFT_PORT", 5439)),
    dbname=os.environ["REDSHIFT_DB"],
    user=os.environ["REDSHIFT_USER"],
    password=os.environ["REDSHIFT_PASSWORD"],
    connect_timeout=30,
)


def get_connection():
    return psycopg2.connect(**_CONN_PARAMS)


def query_df(sql: str, params=None) -> pd.DataFrame:
    """Ejecuta una query y retorna un DataFrame. Usa cursor nativo para evitar warning de pandas."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
    return pd.DataFrame(rows, columns=cols)


def execute(sql: str, params=None):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()
