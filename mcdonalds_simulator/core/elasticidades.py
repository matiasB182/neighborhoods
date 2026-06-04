"""
Calcula y cachea elasticidades precio-demanda por clasificacion_2 y año.

Lógica:
  Para cada clasificacion_2 + año, buscamos los meses donde hubo un cambio
  de precio y medimos el cambio proporcional en unidades vendidas.
  La elasticidad es el promedio de esos ratios dentro del año.

  Al simular, se busca la elasticidad del año más reciente disponible.
  Si no hay datos suficientes para ese año, se usa el promedio histórico
  de la categoría. Si tampoco existe, se usa el DEFAULT.
"""

import logging
import pandas as pd
from core.db import (
    query_df, execute,
    TABLE_PRECIO_PRODUCTOS, TABLE_FACT_VENTAS, TABLE_DIM_ARTICULO,
    TABLE_ELASTICIDADES,
)

log = logging.getLogger(__name__)

ELASTICIDAD_DEFAULT    = -0.5
MIN_CAMBIOS_REQUERIDOS = 2  # mínimo por año (menos datos que antes al segmentar)


def calcular_y_guardar():
    """
    Calcula elasticidades por clasificacion_2 + año y las guarda en TABLE_ELASTICIDADES.
    Pensado para correr una vez al año o cuando lleguen datos nuevos.
    """
    log.info("Calculando elasticidades históricas por categoría + año...")

    sql_crear = f"""
        CREATE TABLE IF NOT EXISTS {TABLE_ELASTICIDADES} (
            clasificacion_2     VARCHAR(200) NOT NULL,
            anio                INT          NOT NULL,
            elasticidad_precio  FLOAT        NOT NULL,
            n_cambios           INT          NOT NULL,
            confianza           VARCHAR(10)  NOT NULL,
            fecha_calculo       TIMESTAMP    DEFAULT SYSDATE
        ) DISTSTYLE ALL;
    """
    execute(sql_crear)

    sql_calc = f"""
        WITH precios_con_cambio AS (
            SELECT
                dav.clasificacion_2_sheet                           AS clasificacion_2,
                pp.anio,
                pp.mes,
                pp.precio                                           AS precio_actual,
                LAG(pp.precio) OVER (
                    PARTITION BY dav.clasificacion_2_sheet, pp.codigo
                    ORDER BY pp.anio, pp.mes
                )                                                   AS precio_anterior
            FROM {TABLE_PRECIO_PRODUCTOS} pp
            JOIN {TABLE_DIM_ARTICULO} dav
                ON CAST(pp.codigo AS VARCHAR) = CAST(dav.codigo_sheet AS VARCHAR)
            WHERE pp.precio IS NOT NULL
              AND dav.clasificacion_2_sheet IS NOT NULL
        ),
        cambios_precio AS (
            SELECT
                clasificacion_2,
                anio,
                TO_CHAR(TO_DATE(anio::VARCHAR || '-' || LPAD(mes::VARCHAR,2,'0'), 'YYYY-MM'), 'YYYY-MM') AS periodo,
                (precio_actual - precio_anterior) / NULLIF(precio_anterior, 0) AS cambio_pct_precio
            FROM precios_con_cambio
            WHERE precio_anterior IS NOT NULL
              AND precio_anterior != precio_actual
        ),
        ventas_periodo AS (
            SELECT
                dav.clasificacion_2_sheet                           AS clasificacion_2,
                EXTRACT(YEAR FROM fv.fecha)::INT                    AS anio,
                TO_CHAR(fv.fecha, 'YYYY-MM')                        AS periodo,
                SUM(fv.cantidad)                                     AS unidades
            FROM {TABLE_FACT_VENTAS} fv
            JOIN {TABLE_DIM_ARTICULO} dav
                ON CAST(fv.producto AS VARCHAR) = CAST(dav.codigo AS VARCHAR)
            WHERE dav.clasificacion_2_sheet IS NOT NULL
            GROUP BY 1, 2, 3
        ),
        ventas_con_lag AS (
            SELECT
                clasificacion_2,
                anio,
                periodo,
                unidades,
                LAG(unidades) OVER (
                    PARTITION BY clasificacion_2
                    ORDER BY periodo
                ) AS unidades_anterior
            FROM ventas_periodo
        ),
        cambios_cantidad AS (
            SELECT
                clasificacion_2,
                anio,
                periodo,
                (unidades - unidades_anterior) / NULLIF(unidades_anterior, 0) AS cambio_pct_cantidad
            FROM ventas_con_lag
            WHERE unidades_anterior IS NOT NULL AND unidades_anterior != unidades
        ),
        elasticidades_brutas AS (
            SELECT
                cp.clasificacion_2,
                cp.anio,
                cc.cambio_pct_cantidad / NULLIF(cp.cambio_pct_precio, 0) AS elasticidad
            FROM cambios_precio cp
            JOIN cambios_cantidad cc
                ON cp.clasificacion_2 = cc.clasificacion_2
                AND cp.periodo        = cc.periodo
            WHERE ABS(cp.cambio_pct_precio) > 0.001
              AND ABS(cc.cambio_pct_cantidad / NULLIF(cp.cambio_pct_precio, 0)) < 10
        )
        SELECT
            clasificacion_2,
            anio,
            AVG(elasticidad)    AS elasticidad_precio,
            COUNT(*)            AS n_cambios
        FROM elasticidades_brutas
        GROUP BY clasificacion_2, anio
        ORDER BY clasificacion_2, anio
    """
    df = query_df(sql_calc)

    if df.empty:
        log.warning("No se encontraron cambios de precio históricos.")
        return

    execute(f"TRUNCATE TABLE {TABLE_ELASTICIDADES};")

    rows = []
    for _, row in df.iterrows():
        n = int(row["n_cambios"])
        confianza = "alta" if n >= MIN_CAMBIOS_REQUERIDOS else "media"
        rows.append((row["clasificacion_2"], int(row["anio"]), float(row["elasticidad_precio"]), n, confianza))

    from psycopg2.extras import execute_values
    from core.db import get_connection
    with get_connection() as conn:
        with conn.cursor() as cur:
            execute_values(
                cur,
                f"""INSERT INTO {TABLE_ELASTICIDADES}
                    (clasificacion_2, anio, elasticidad_precio, n_cambios, confianza)
                    VALUES %s""",
                rows,
            )
        conn.commit()

    log.info("Elasticidades calculadas: %d filas (categoría × año).", len(rows))


def get_elasticidad(clasificacion_2: str, anio: int | None = None) -> tuple[float, str]:
    """
    Retorna (elasticidad, confianza) para una categoría.

    Busca en este orden:
      1. Elasticidad del año solicitado (si se pasa anio)
      2. Promedio histórico de la categoría (todos los años)
      3. DEFAULT si la tabla no existe o no hay datos
    """
    try:
        if anio is not None:
            df = query_df(
                f"""SELECT elasticidad_precio, confianza
                    FROM {TABLE_ELASTICIDADES}
                    WHERE clasificacion_2 = %(clf2)s AND anio = %(anio)s
                    LIMIT 1""",
                {"clf2": clasificacion_2, "anio": anio},
            )
            if not df.empty:
                return float(df.iloc[0]["elasticidad_precio"]), str(df.iloc[0]["confianza"])

        # Fallback: promedio histórico de la categoría
        df = query_df(
            f"""SELECT AVG(elasticidad_precio) AS elasticidad_precio,
                       MAX(confianza)          AS confianza
                FROM {TABLE_ELASTICIDADES}
                WHERE clasificacion_2 = %(clf2)s""",
            {"clf2": clasificacion_2},
        )
        if not df.empty and df.iloc[0]["elasticidad_precio"] is not None:
            return float(df.iloc[0]["elasticidad_precio"]), "promedio histórico"

    except Exception:
        log.debug("Tabla de elasticidades no encontrada, usando default.")

    return ELASTICIDAD_DEFAULT, "supuesto"
