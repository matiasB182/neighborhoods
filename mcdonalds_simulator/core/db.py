"""Conexión a Redshift y helpers de query."""

import os
import pandas as pd
import psycopg2
from dotenv import load_dotenv

load_dotenv()

SCHEMA = os.environ.get("REDSHIFT_SCHEMA", "mcd")

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
    with get_connection() as conn:
        return pd.read_sql(sql, conn, params=params)


def execute(sql: str, params=None):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()
