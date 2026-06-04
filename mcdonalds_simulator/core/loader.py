"""
Queries a Redshift. Centraliza todo acceso a datos del simulador.

Joins clave:
  fact_ventas.producto      → dim_articulo_venta.codigo
  dim_articulo_venta        → clasificacion_2_sheet, codigo_sheet
  fact_ventas.tienda        → dim_restaurantes.api_id_integer
  dim_restaurantes.api_id_integer → forecast.sucursal / apertura_restaurantes.api_id
"""

import pandas as pd
from core.db import (
    query_df,
    TABLE_FORECAST, TABLE_FACT_VENTAS, TABLE_DIM_ARTICULO, TABLE_DIM_RESTAURANTES,
    TABLE_PRECIO_PRODUCTOS, TABLE_PROMOCIONES, TABLE_LANZAMIENTOS,
    TABLE_APERTURA_RESTAURANTES, TABLE_COMPETENCIA,
)


# ─────────────────────────────────────────────────────────────────────────────
# Forecast baseline
# ─────────────────────────────────────────────────────────────────────────────

def load_forecast(clasificacion_2: str | None, sucursal: int | None,
                  periodo_desde: str, periodo_hasta: str) -> pd.DataFrame:
    conditions = ["periodo >= %(desde)s", "periodo <= %(hasta)s"]
    params = {"desde": periodo_desde, "hasta": periodo_hasta}

    if clasificacion_2:
        conditions.append("clasificacion_2 = %(clf2)s")
        params["clf2"] = clasificacion_2
    if sucursal is not None:
        conditions.append("sucursal = %(suc)s")
        params["suc"] = sucursal

    where = " AND ".join(conditions)
    sql = f"""
        SELECT
            clasificacion_2,
            sucursal,
            periodo,
            COALESCE(forecast, unidades) AS forecast
        FROM {TABLE_FORECAST}
        WHERE {where}
        ORDER BY clasificacion_2, sucursal, periodo
    """
    return query_df(sql, params)


# ─────────────────────────────────────────────────────────────────────────────
# Precio promedio ponderado por clasificacion_2 y periodo
# ─────────────────────────────────────────────────────────────────────────────

def load_precio_clasificacion2(clasificacion_2: str | None,
                                periodo_desde: str, periodo_hasta: str) -> pd.DataFrame:
    clf_filter = "AND dav.clasificacion_2_sheet = %(clf2)s" if clasificacion_2 else ""
    params = {"desde": periodo_desde[:4] + "-01-01", "hasta": periodo_hasta[:4] + "-12-31",
              "periodo_desde": periodo_desde, "periodo_hasta": periodo_hasta}
    if clasificacion_2:
        params["clf2"] = clasificacion_2

    sql = f"""
        WITH ventas_precio AS (
            SELECT
                dav.clasificacion_2_sheet                           AS clasificacion_2,
                TO_CHAR(fv.fecha, 'YYYY-MM')                        AS periodo,
                pp.precio                                            AS precio_unitario,
                SUM(fv.cantidad)                                     AS unidades
            FROM {TABLE_FACT_VENTAS} fv
            JOIN {TABLE_DIM_ARTICULO} dav
                ON fv.producto = dav.codigo
            JOIN {TABLE_PRECIO_PRODUCTOS} pp
                ON dav.codigo_sheet = pp.codigo
                AND pp.anio = EXTRACT(YEAR FROM fv.fecha)::INT
                AND pp.mes  = EXTRACT(MONTH FROM fv.fecha)::INT
            WHERE fv.fecha BETWEEN %(desde)s AND %(hasta)s
              AND dav.clasificacion_2_sheet IS NOT NULL
              {clf_filter}
            GROUP BY 1, 2, 3
        )
        SELECT
            clasificacion_2,
            periodo,
            SUM(precio_unitario * unidades) / NULLIF(SUM(unidades), 0) AS precio_promedio_ponderado
        FROM ventas_precio
        WHERE periodo >= %(periodo_desde)s AND periodo <= %(periodo_hasta)s
        GROUP BY 1, 2
        ORDER BY 1, 2
    """
    return query_df(sql, params)


# ─────────────────────────────────────────────────────────────────────────────
# Ventas históricas agregadas por clasificacion_2 + sucursal + periodo
# ─────────────────────────────────────────────────────────────────────────────

def load_ventas_historicas(clasificacion_2: str | None = None) -> pd.DataFrame:
    clf_filter = "AND dav.clasificacion_2_sheet = %(clf2)s" if clasificacion_2 else ""
    params = {}
    if clasificacion_2:
        params["clf2"] = clasificacion_2

    sql = f"""
        SELECT
            dav.clasificacion_2_sheet                               AS clasificacion_2,
            dr.api_id_integer                                       AS sucursal,
            TO_CHAR(fv.fecha, 'YYYY-MM')                            AS periodo,
            SUM(fv.cantidad)                                        AS unidades,
            SUM(fv.precio_final_producto * fv.cantidad)
                / NULLIF(SUM(fv.cantidad), 0)                       AS precio_promedio
        FROM {TABLE_FACT_VENTAS} fv
        JOIN {TABLE_DIM_ARTICULO} dav
            ON fv.producto = dav.codigo
        JOIN {TABLE_DIM_RESTAURANTES} dr
            ON fv.tienda = dr.api_id_integer
        WHERE dav.clasificacion_2_sheet IS NOT NULL
          {clf_filter}
        GROUP BY 1, 2, 3
        ORDER BY 1, 2, 3
    """
    return query_df(sql, params)


# ─────────────────────────────────────────────────────────────────────────────
# Periodos activos de una campaña
# ─────────────────────────────────────────────────────────────────────────────

def load_periodos_campania(campania: str) -> pd.DataFrame:
    sql = f"""
        WITH codigos_campania AS (
            SELECT codigo FROM {TABLE_PROMOCIONES} WHERE campania = %(campania)s
        ),
        ventas_promo AS (
            SELECT
                dav.clasificacion_2_sheet       AS clasificacion_2,
                TO_CHAR(fv.fecha, 'YYYY-MM')    AS periodo,
                SUM(fv.cantidad)                AS unidades_promo
            FROM {TABLE_FACT_VENTAS} fv
            JOIN {TABLE_DIM_ARTICULO} dav ON fv.producto = dav.codigo
            WHERE fv.producto IN (SELECT codigo FROM codigos_campania)
              AND dav.clasificacion_2_sheet IS NOT NULL
            GROUP BY 1, 2
        )
        SELECT * FROM ventas_promo ORDER BY clasificacion_2, periodo
    """
    return query_df(sql, {"campania": campania})


def load_campania_clasificaciones(campania: str) -> list[str]:
    sql = f"""
        SELECT DISTINCT dav.clasificacion_2_sheet AS clasificacion_2
        FROM {TABLE_PROMOCIONES} p
        JOIN {TABLE_DIM_ARTICULO} dav ON p.codigo = dav.codigo
        WHERE p.campania = %(campania)s
          AND dav.clasificacion_2_sheet IS NOT NULL
    """
    return query_df(sql, {"campania": campania})["clasificacion_2"].tolist()


# ─────────────────────────────────────────────────────────────────────────────
# Lanzamientos históricos por clasificacion_2
# ─────────────────────────────────────────────────────────────────────────────

def load_lanzamientos_por_clasificacion(clasificacion_2: str) -> pd.DataFrame:
    sql = f"""
        WITH codigos_lanzamiento AS (
            SELECT l.lanzamiento, l.codigo
            FROM {TABLE_LANZAMIENTOS} l
            JOIN {TABLE_DIM_ARTICULO} dav ON l.codigo = dav.codigo
            WHERE dav.clasificacion_2_sheet = %(clf2)s
        ),
        primer_mes AS (
            SELECT
                cl.lanzamiento,
                MIN(TO_CHAR(fv.fecha, 'YYYY-MM')) AS periodo_lanzamiento
            FROM {TABLE_FACT_VENTAS} fv
            JOIN codigos_lanzamiento cl ON fv.producto = cl.codigo
            GROUP BY cl.lanzamiento
        ),
        ventas_clf2 AS (
            SELECT
                TO_CHAR(fv.fecha, 'YYYY-MM')  AS periodo,
                SUM(fv.cantidad)               AS unidades
            FROM {TABLE_FACT_VENTAS} fv
            JOIN {TABLE_DIM_ARTICULO} dav ON fv.producto = dav.codigo
            WHERE dav.clasificacion_2_sheet = %(clf2)s
            GROUP BY 1
        ),
        baseline AS (
            SELECT AVG(unidades) AS unidades_base FROM ventas_clf2
        )
        SELECT
            pm.lanzamiento,
            DATEDIFF('month',
                TO_DATE(pm.periodo_lanzamiento, 'YYYY-MM'),
                TO_DATE(vc.periodo, 'YYYY-MM')
            )                                            AS mes_relativo,
            (vc.unidades - b.unidades_base)
                / NULLIF(b.unidades_base, 0)             AS uplift_pct
        FROM primer_mes pm
        CROSS JOIN ventas_clf2 vc
        CROSS JOIN baseline b
        WHERE DATEDIFF('month',
                TO_DATE(pm.periodo_lanzamiento, 'YYYY-MM'),
                TO_DATE(vc.periodo, 'YYYY-MM')
              ) BETWEEN 0 AND 5
        ORDER BY pm.lanzamiento, mes_relativo
    """
    return query_df(sql, {"clf2": clasificacion_2})


# ─────────────────────────────────────────────────────────────────────────────
# Atributos de restaurantes
# ─────────────────────────────────────────────────────────────────────────────

def load_atributos_restaurantes() -> pd.DataFrame:
    sql = f"""
        SELECT api_id, short_name,
               tiene_mostrador, tiene_automac, tiene_delivery,
               tiene_kiosco_digital, tiene_centro_postres
        FROM {TABLE_APERTURA_RESTAURANTES}
    """
    return query_df(sql)


# ─────────────────────────────────────────────────────────────────────────────
# Competencia por sucursal
# ─────────────────────────────────────────────────────────────────────────────

def load_competencia() -> pd.DataFrame:
    sql = f"""
        SELECT sucursal, competidor, distancia_km
        FROM {TABLE_COMPETENCIA}
        ORDER BY sucursal, distancia_km
    """
    return query_df(sql)
