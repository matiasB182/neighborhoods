"""
Queries a Redshift. Centraliza todo acceso a datos del simulador.

Joins clave:
  fact_ventas.producto      → dim_articulo_venta.codigo
  dim_articulo_venta        → clasificacion_2_sheet, codigo_sheet
  fact_ventas.tienda        → dim_restaurantes.api_id_integer
  dim_restaurantes.api_id_integer → forecast.sucursal / apertura_restaurantes.api_id
"""

import logging
import pandas as pd
from core.db import (
    query_df,
    TABLE_FORECAST, TABLE_FACT_VENTAS, TABLE_DIM_ARTICULO, TABLE_DIM_RESTAURANTES,
    TABLE_PRECIO_PRODUCTOS, TABLE_PROMOCIONES, TABLE_LANZAMIENTOS,
    TABLE_APERTURA_RESTAURANTES, TABLE_COMPETENCIA,
)

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Forecast baseline
# ─────────────────────────────────────────────────────────────────────────────

def _score_fuzzy(query: str, candidato: str) -> float:
    """
    Mide qué tan bien el texto query coincide con el candidato.
    Retorna un score: más alto = mejor match.
    Bonifica si el query completo o sus palabras aparecen como substring.
    """
    from difflib import SequenceMatcher
    q = query.lower().strip()
    c = candidato.lower().strip()
    # Máxima confianza: query completo está contenido en el candidato
    if q in c:
        return 100.0
    palabras_query     = [p for p in q.split() if len(p) > 1]
    palabras_candidato = [p for p in c.split() if len(p) > 1]
    if not palabras_query or not palabras_candidato:
        return SequenceMatcher(None, q, c).ratio()
    # Bonus por palabras del query que aparecen como substring en el candidato
    substring_bonus = sum(1.0 for pq in palabras_query if pq in c) / len(palabras_query) * 2.0
    # Score fuzzy palabra a palabra, normalizado entre 0 y 1
    word_scores = [
        max(SequenceMatcher(None, pq, pc).ratio() for pc in palabras_candidato)
        for pq in palabras_query
    ]
    word_ratio = sum(word_scores) / len(word_scores)
    return word_ratio + substring_bonus


def resolver_clasificacion_2(texto: str) -> list[str]:
    """
    Busca la clasificacion_2 más parecida al texto dado.
    Estrategia:
      1. Match AND exacto (substring) → si hay 1 resultado, perfecto.
      2. Si hay 0 o >1, trae todos los candidatos vía OR y aplica
         scoring fuzzy palabra a palabra con difflib para tolerar typos.
    Siempre retorna solo 1 elemento — el mejor match.
    """
    palabras = [p for p in texto.strip().split() if len(p) > 2]
    if not palabras:
        return []

    # Intento 1: AND estricto
    conditions_and = " AND ".join([f"LOWER(clasificacion_2_sheet) LIKE LOWER(%(p{i})s)"
                                    for i in range(len(palabras))])
    params = {f"p{i}": f"%{p}%" for i, p in enumerate(palabras)}

    sql_and = f"""
        SELECT DISTINCT clasificacion_2_sheet AS clasificacion_2
        FROM {TABLE_FORECAST}
        WHERE {conditions_and}
        ORDER BY 1
    """
    df = query_df(sql_and, params)
    if len(df) == 1:
        return df["clasificacion_2"].tolist()

    # Traer todos los candidatos y rankear con fuzzy scoring
    sql_all = f"""
        SELECT DISTINCT clasificacion_2_sheet AS clasificacion_2
        FROM {TABLE_FORECAST}
        WHERE clasificacion_2_sheet IS NOT NULL
        ORDER BY 1
    """
    df_all = query_df(sql_all)
    if df_all.empty:
        return []

    candidatos = df_all["clasificacion_2"].tolist()
    texto_lower = texto.lower()
    scored = sorted(candidatos, key=lambda c: -_score_fuzzy(texto_lower, c))

    mejor_score = _score_fuzzy(texto_lower, scored[0])
    # Umbral mínimo: si el mejor match tiene score bajo, ningún candidato es válido
    UMBRAL_MINIMO = 1.5
    if mejor_score < UMBRAL_MINIMO:
        log.error(
            "No se encontró clasificacion_2 para '%s' — el mejor match fue '%s' (score %.2f < %.1f). "
            "Verificá que exista en el forecast o corregí el nombre.",
            texto, scored[0], mejor_score, UMBRAL_MINIMO
        )
        return []

    log.info("clasificacion_2 resuelta: '%s' → '%s' (score fuzzy: %.2f)", texto, scored[0], mejor_score)
    return [scored[0]]


def load_forecast(clasificacion_2: list | None, sucursal: str | None,
                  periodo_desde: str, periodo_hasta: str) -> pd.DataFrame:
    """
    clasificacion_2: lista de nombres exactos (ya resueltos por resolver_clasificacion_2)
                     o None para traer todas.
    """
    conditions = ["periodo >= %(desde)s", "periodo <= %(hasta)s",
                  "CAST(modelo AS VARCHAR) = CAST(mejor_modelo AS VARCHAR)"]
    params = {"desde": periodo_desde, "hasta": periodo_hasta}

    if clasificacion_2:
        placeholders = ", ".join([f"%(clf2_{i})s" for i in range(len(clasificacion_2))])
        conditions.append(f"clasificacion_2_sheet IN ({placeholders})")
        for i, v in enumerate(clasificacion_2):
            params[f"clf2_{i}"] = v
    if sucursal is not None:
        conditions.append("CAST(sucursal AS VARCHAR) = %(suc)s")
        params["suc"] = str(sucursal)

    where = " AND ".join(conditions)
    sql = f"""
        SELECT
            clasificacion_2_sheet     AS clasificacion_2,
            CAST(sucursal AS VARCHAR) AS sucursal,
            periodo,
            COALESCE(forecast, unidades) AS forecast
        FROM {TABLE_FORECAST}
        WHERE {where}
        ORDER BY clasificacion_2_sheet, sucursal, periodo
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
                ON CAST(fv.producto AS VARCHAR) = CAST(dav.codigo AS VARCHAR)
            JOIN {TABLE_PRECIO_PRODUCTOS} pp
                ON CAST(dav.codigo_sheet AS VARCHAR) = CAST(pp.codigo AS VARCHAR)
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
            CAST(dr.api_id_integer AS VARCHAR)                      AS sucursal,
            TO_CHAR(fv.fecha, 'YYYY-MM')                            AS periodo,
            SUM(fv.cantidad)                                        AS unidades,
            SUM(fv.precio_final_producto * fv.cantidad)
                / NULLIF(SUM(fv.cantidad), 0)                       AS precio_promedio
        FROM {TABLE_FACT_VENTAS} fv
        JOIN {TABLE_DIM_ARTICULO} dav
            ON CAST(fv.producto AS VARCHAR) = CAST(dav.codigo AS VARCHAR)
        JOIN {TABLE_DIM_RESTAURANTES} dr
            ON CAST(fv.tienda AS VARCHAR) = CAST(dr.api_id_integer AS VARCHAR)
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


def load_tipo_sheet(clasificacion_2: str) -> str | None:
    """
    Retorna el tipo_sheet dominante para una clasificacion_2 (el que más unidades vendió).
    Maneja el caso N:1 donde una clasificacion_2 aparece en varios tipos.
    """
    sql = f"""
        SELECT dav.tipo_sheet, SUM(fv.cantidad) AS unidades
        FROM {TABLE_FACT_VENTAS} fv
        JOIN {TABLE_DIM_ARTICULO} dav
            ON CAST(fv.producto AS VARCHAR) = CAST(dav.codigo AS VARCHAR)
        WHERE dav.clasificacion_2_sheet = %(clf2)s
          AND dav.tipo_sheet IS NOT NULL
        GROUP BY dav.tipo_sheet
        ORDER BY unidades DESC
        LIMIT 1
    """
    df = query_df(sql, {"clf2": clasificacion_2})
    if df.empty:
        return None
    return str(df.iloc[0]["tipo_sheet"])


def load_tipo_sheet_por_lanzamiento(lanzamiento: str) -> str | None:
    """
    Retorna el tipo_sheet dominante de los productos de un lanzamiento histórico.
    """
    sql = f"""
        SELECT dav.tipo_sheet, SUM(fv.cantidad) AS unidades
        FROM {TABLE_FACT_VENTAS} fv
        JOIN {TABLE_LANZAMIENTOS} l
            ON CAST(fv.producto AS VARCHAR) = CAST(l.codigo AS VARCHAR)
        JOIN {TABLE_DIM_ARTICULO} dav
            ON CAST(fv.producto AS VARCHAR) = CAST(dav.codigo AS VARCHAR)
        WHERE l.lanzamiento = %(lanz)s
          AND dav.tipo_sheet IS NOT NULL
        GROUP BY dav.tipo_sheet
        ORDER BY unidades DESC
        LIMIT 1
    """
    df = query_df(sql, {"lanz": lanzamiento})
    if df.empty:
        return None
    return str(df.iloc[0]["tipo_sheet"])


def load_zonas_restaurantes() -> pd.DataFrame:
    """
    Retorna los atributos de zona de cada sucursal desde dim_restaurantes.
    Columnas: sucursal (VARCHAR), barrio, distrito, dpto
    """
    sql = f"""
        SELECT
            CAST(api_id_integer AS VARCHAR) AS sucursal,
            barlo_desc                      AS barrio,
            distrito_desc                   AS distrito,
            dpto_desc                       AS dpto
        FROM {TABLE_DIM_RESTAURANTES}
        WHERE api_id_integer IS NOT NULL
    """
    return query_df(sql)


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

def load_fechas_campania(clasificacion_2: str, tipo_sheet: str | None) -> pd.DataFrame:
    """
    Retorna campañas con fechas para productos del mismo tipo_sheet (o clasificacion_2).
    Columnas: campania, fecha_desde, fecha_hasta
    Solo devuelve filas donde fecha_desde y fecha_hasta no son null.
    """
    if tipo_sheet:
        sql = f"""
            SELECT DISTINCT p.campania,
                   MIN(p.fecha_desde) AS fecha_desde,
                   MAX(p.fecha_hasta) AS fecha_hasta
            FROM {TABLE_PROMOCIONES} p
            JOIN {TABLE_DIM_ARTICULO} dav
                ON CAST(p.codigo AS VARCHAR) = CAST(dav.codigo AS VARCHAR)
            WHERE dav.tipo_sheet = %(tipo)s
              AND p.fecha_desde IS NOT NULL
              AND p.fecha_hasta IS NOT NULL
            GROUP BY p.campania
            ORDER BY p.campania
        """
        return query_df(sql, {"tipo": tipo_sheet})
    else:
        sql = f"""
            SELECT DISTINCT p.campania,
                   MIN(p.fecha_desde) AS fecha_desde,
                   MAX(p.fecha_hasta) AS fecha_hasta
            FROM {TABLE_PROMOCIONES} p
            JOIN {TABLE_DIM_ARTICULO} dav
                ON CAST(p.codigo AS VARCHAR) = CAST(dav.codigo AS VARCHAR)
            WHERE dav.clasificacion_2_sheet = %(clf2)s
              AND p.fecha_desde IS NOT NULL
              AND p.fecha_hasta IS NOT NULL
            GROUP BY p.campania
            ORDER BY p.campania
        """
        return query_df(sql, {"clf2": clasificacion_2})


def load_competencia() -> pd.DataFrame:
    """
    Retorna competidores por sucursal.
    Hace join por short_name para obtener el api_id_integer de dim_restaurantes.
    Retorna: sucursal (VARCHAR), competidor, radio_km
    """
    sql = f"""
        SELECT
            CAST(dr.api_id_integer AS VARCHAR)  AS sucursal,
            c.competidor,
            c.radio_km
        FROM {TABLE_COMPETENCIA} c
        JOIN {TABLE_DIM_RESTAURANTES} dr
            ON UPPER(TRIM(c.short_name)) = UPPER(TRIM(dr.short_name))
        ORDER BY sucursal, radio_km
    """
    return query_df(sql)
