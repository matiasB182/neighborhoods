"""Conexión a Redshift y helpers de query."""

import os
import pandas as pd
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# ── Tablas fuente ────────────────────────────────────────────────
TABLE_FORECAST          = os.environ["TABLE_FORECAST"]
TABLE_FACT_VENTAS       = os.environ["TABLE_FACT_VENTAS"]
TABLE_DIM_ARTICULO      = os.environ["TABLE_DIM_ARTICULO"]
TABLE_DIM_RESTAURANTES  = os.environ["TABLE_DIM_RESTAURANTES"]

# ── Tablas cargadas desde Excel ──────────────────────────────────
TABLE_PRECIO_PRODUCTOS      = os.environ["TABLE_PRECIO_PRODUCTOS"]
TABLE_PROMOCIONES           = os.environ["TABLE_PROMOCIONES"]
TABLE_LANZAMIENTOS          = os.environ["TABLE_LANZAMIENTOS"]
TABLE_APERTURA_RESTAURANTES = os.environ["TABLE_APERTURA_RESTAURANTES"]
TABLE_COMPETENCIA           = os.environ["TABLE_COMPETENCIA"]

# ── Tablas generadas por el simulador ───────────────────────────
TABLE_ELASTICIDADES = os.environ["TABLE_ELASTICIDADES"]
TABLE_RESULTADOS    = os.environ["TABLE_RESULTADOS"]

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


import logging as _logging
_log = _logging.getLogger(__name__)

def query_df(sql: str, params=None) -> pd.DataFrame:
    import psycopg2.extras
    _log.debug("SQL: %s | PARAMS: %s", sql.strip()[:300], params)
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(sql, params)
            except Exception as e:
                _log.error("SQL FALLIDO:\n%s\nPARAMS: %s", sql, params)
                raise
            cols = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
    return pd.DataFrame(rows, columns=cols)


def execute(sql: str, params=None):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()
