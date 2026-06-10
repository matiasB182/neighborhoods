"""
Calcula y cachea elasticidades precio-demanda por clasificacion_2 y año.

Lógica:
  1. Para cada producto individual (codigo), calculamos la elasticidad:
     cuando subió/bajó el precio de ESE producto, ¿cuánto cambiaron
     las unidades de ESE producto en ese mismo mes?
  2. Promediamos las elasticidades de todos los productos que pertenecen
     a la misma clasificacion_2 y año.

  Al simular, se busca la elasticidad del año del periodo simulado.
  Si no hay datos para ese año, se usa el promedio histórico de la categoría.
  Si tampoco existe, se usa el DEFAULT.
"""

import logging
from core.db import (
    query_df, execute,
    TABLE_PRECIO_PRODUCTOS, TABLE_FACT_VENTAS, TABLE_DIM_ARTICULO,
    TABLE_ELASTICIDADES,
)

log = logging.getLogger(__name__)

ELASTICIDAD_DEFAULT    = -0.5
MIN_CAMBIOS_REQUERIDOS = 2


def calcular_y_guardar():
    """
    Calcula elasticidades por clasificacion_2 + año y las guarda en TABLE_ELASTICIDADES.
    Correr una vez al año o cuando lleguen datos nuevos.
    """
    log.info("Calculando elasticidades históricas por producto → categoría + año...")

    # Recrear tabla para aplicar nuevas columnas si ya existía con estructura vieja
    execute(f"DROP TABLE IF EXISTS {TABLE_ELASTICIDADES};")
    execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_ELASTICIDADES} (
            clasificacion_2     VARCHAR(200) NOT NULL,
            elasticidad_precio  FLOAT        NOT NULL,
            n_productos         INT          NOT NULL,
            n_cambios           INT          NOT NULL,
            precio_desde        FLOAT        NOT NULL,
            precio_hasta        FLOAT        NOT NULL,
            confianza           VARCHAR(10)  NOT NULL,
            fecha_calculo       TIMESTAMP    DEFAULT SYSDATE
        ) DISTSTYLE ALL;
    """)

    # Calcula elasticidad a nivel producto individual, luego agrega por clasificacion_2 + año
    sql_calc = f"""
        WITH precios_con_lag AS (
            SELECT
                CAST(pp.codigo AS VARCHAR)                          AS codigo,
                pp.anio,
                pp.mes,
                pp.precio                                           AS precio_actual,
                LAG(pp.precio) OVER (
                    PARTITION BY pp.codigo
                    ORDER BY pp.anio, pp.mes
                )                                                   AS precio_anterior
            FROM {TABLE_PRECIO_PRODUCTOS} pp
            WHERE pp.precio IS NOT NULL
        ),
        cambios_precio AS (
            SELECT
                codigo,
                anio,
                TO_CHAR(TO_DATE(anio::VARCHAR || '-' || LPAD(mes::VARCHAR,2,'0'), 'YYYY-MM'), 'YYYY-MM') AS periodo,
                precio_actual,
                precio_anterior,
                (precio_actual - precio_anterior) / NULLIF(precio_anterior, 0) AS cambio_pct_precio
            FROM precios_con_lag
            WHERE precio_anterior IS NOT NULL
              AND precio_anterior != precio_actual
        ),
        ventas_por_producto AS (
            SELECT
                CAST(fv.producto AS VARCHAR)                        AS codigo,
                TO_CHAR(fv.fecha, 'YYYY-MM')                       AS periodo,
                SUM(fv.cantidad)                                    AS unidades
            FROM {TABLE_FACT_VENTAS} fv
            GROUP BY 1, 2
        ),
        ventas_con_lag AS (
            SELECT
                codigo,
                periodo,
                unidades,
                LAG(unidades) OVER (
                    PARTITION BY codigo
                    ORDER BY periodo
                ) AS unidades_anterior
            FROM ventas_por_producto
        ),
        cambios_cantidad AS (
            SELECT
                codigo,
                periodo,
                (unidades - unidades_anterior)::FLOAT / NULLIF(unidades_anterior, 0) AS cambio_pct_cantidad
            FROM ventas_con_lag
            WHERE unidades_anterior IS NOT NULL
              AND unidades_anterior != unidades
        ),
        elasticidades_por_producto AS (
            SELECT
                cp.codigo,
                cp.anio,
                cp.precio_actual,
                cp.precio_anterior,
                cc.cambio_pct_cantidad / NULLIF(cp.cambio_pct_precio, 0) AS elasticidad
            FROM cambios_precio cp
            JOIN cambios_cantidad cc
                ON cp.codigo  = cc.codigo
                AND cp.periodo = cc.periodo
            WHERE ABS(cp.cambio_pct_precio) > 0.001
              AND ABS(cc.cambio_pct_cantidad / NULLIF(cp.cambio_pct_precio, 0)) < 10
        ),
        con_clasificacion AS (
            SELECT
                dav.clasificacion_2_sheet   AS clasificacion_2,
                ep.anio,
                ep.elasticidad,
                ep.codigo,
                ep.precio_actual,
                ep.precio_anterior
            FROM elasticidades_por_producto ep
            JOIN {TABLE_DIM_ARTICULO} dav
                ON CAST(dav.codigo AS VARCHAR) = ep.codigo
            WHERE dav.clasificacion_2_sheet IS NOT NULL
        )
        SELECT
            clasificacion_2,
            AVG(elasticidad)                AS elasticidad_precio,
            COUNT(DISTINCT codigo)          AS n_productos,
            COUNT(*)                        AS n_cambios,
            MIN(precio_anterior)            AS precio_desde,
            MAX(precio_actual)              AS precio_hasta
        FROM con_clasificacion
        GROUP BY clasificacion_2
        ORDER BY clasificacion_2
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
        rows.append((
            row["clasificacion_2"],
            float(row["elasticidad_precio"]),
            int(row["n_productos"]),
            n,
            float(row["precio_desde"]),
            float(row["precio_hasta"]),
            confianza,
        ))

    from psycopg2.extras import execute_values
    from core.db import get_connection
    with get_connection() as conn:
        with conn.cursor() as cur:
            execute_values(
                cur,
                f"""INSERT INTO {TABLE_ELASTICIDADES}
                    (clasificacion_2, elasticidad_precio, n_productos,
                     n_cambios, precio_desde, precio_hasta, confianza)
                    VALUES %s""",
                rows,
            )
        conn.commit()

    log.info("Elasticidades calculadas: %d filas (categoría × año).", len(rows))


def get_elasticidad(clasificacion_2: str) -> tuple[float, str]:
    """Retorna (elasticidad, confianza). Default si la tabla no existe o no hay datos."""
    try:
        df = query_df(
            f"""SELECT elasticidad_precio, confianza
                FROM {TABLE_ELASTICIDADES}
                WHERE clasificacion_2 = %(clf2)s
                LIMIT 1""",
            {"clf2": clasificacion_2},
        )
        if not df.empty:
            return float(df.iloc[0]["elasticidad_precio"]), str(df.iloc[0]["confianza"])
    except Exception:
        log.debug("Tabla de elasticidades no encontrada, usando default.")

    return ELASTICIDAD_DEFAULT, "supuesto"
