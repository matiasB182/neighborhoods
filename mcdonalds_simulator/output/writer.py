"""Guarda el resultado del escenario en Redshift y en CSV."""

import json
import logging
from pathlib import Path
import pandas as pd
from psycopg2.extras import execute_values
from core.db import get_connection, execute, TABLE_RESULTADOS

log = logging.getLogger(__name__)

DDL_RESULTADOS = """
    CREATE TABLE IF NOT EXISTS {TABLE_RESULTADOS} (
        escenario_nombre    VARCHAR(300)  NOT NULL,
        clasificacion_2     VARCHAR(200),
        sucursal            INT,
        periodo             VARCHAR(7),
        forecast_base       NUMERIC(14,2),
        forecast_simulado   NUMERIC(14,2),
        delta_abs           NUMERIC(14,2),
        delta_pct           NUMERIC(8,4),
        ingreso_base        NUMERIC(18,2),
        ingreso_simulado    NUMERIC(18,2),
        palancas_json       VARCHAR(2000),
        creado_en           TIMESTAMP DEFAULT SYSDATE
    ) DISTSTYLE ALL SORTKEY (escenario_nombre, periodo);
"""


def guardar(df: pd.DataFrame, escenario_nombre: str, palancas: list):
    """Persiste en Redshift y retorna el path del CSV generado."""
    _crear_tabla_si_no_existe()

    col_sim = "unidades_simuladas" if "unidades_simuladas" in df.columns else "forecast"
    palancas_json = json.dumps(palancas, ensure_ascii=False)[:2000]

    rows = []
    for _, row in df.iterrows():
        base = float(row["forecast"])
        sim  = float(row[col_sim])
        delta_abs = sim - base
        delta_pct = delta_abs / base if base != 0 else 0
        ing_base  = float(row["ingreso_base"]) if "ingreso_base" in row and pd.notna(row["ingreso_base"]) else None
        ing_sim   = float(row["ingreso_simulado"]) if "ingreso_simulado" in row and pd.notna(row["ingreso_simulado"]) else None

        rows.append((
            escenario_nombre,
            row["clasificacion_2"],
            int(row["sucursal"]),
            row["periodo"],
            round(base, 2),
            round(sim, 2),
            round(delta_abs, 2),
            round(delta_pct, 4),
            round(ing_base, 2) if ing_base else None,
            round(ing_sim, 2) if ing_sim else None,
            palancas_json,
        ))

    with get_connection() as conn:
        with conn.cursor() as cur:
            execute_values(
                cur,
                f"""INSERT INTO {TABLE_RESULTADOS}
                    (escenario_nombre, clasificacion_2, sucursal, periodo,
                     forecast_base, forecast_simulado, delta_abs, delta_pct,
                     ingreso_base, ingreso_simulado, palancas_json)
                    VALUES %s""",
                rows,
            )
        conn.commit()
    log.info("Escenario '%s' guardado en Redshift (%d filas).", escenario_nombre, len(rows))

    csv_path = _guardar_csv(df, escenario_nombre, col_sim)
    return csv_path


def _crear_tabla_si_no_existe():
    execute(DDL_RESULTADOS)


def _guardar_csv(df: pd.DataFrame, escenario_nombre: str, col_sim: str) -> Path:
    output_dir = Path("output/resultados")
    output_dir.mkdir(parents=True, exist_ok=True)

    nombre_archivo = escenario_nombre.replace(" ", "_").replace("/", "-")[:80]
    path = output_dir / f"{nombre_archivo}.csv"

    cols_export = ["clasificacion_2", "sucursal", "periodo", "forecast", col_sim]
    if "ingreso_base" in df.columns:
        cols_export += ["ingreso_base", "ingreso_simulado"]
    cols_export = [c for c in cols_export if c in df.columns]

    export = df[cols_export].copy()
    export.rename(columns={col_sim: "forecast_simulado"}, inplace=True)
    export["delta_pct"] = (
        (export["forecast_simulado"] - export["forecast"]) / export["forecast"] * 100
    ).round(2)

    export.to_csv(path, index=False, encoding="utf-8-sig")
    log.info("CSV guardado en: %s", path)
    return path
