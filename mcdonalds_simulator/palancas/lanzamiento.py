"""
Palanca: Lanzamiento de producto nuevo.

Lógica:
  1. Si hay un proxy_lanzamiento → usa su patrón histórico exacto.
  2. Si no → promedia el patrón de todos los lanzamientos históricos
     de la misma clasificacion_2.
  3. Si tampoco hay → promedia todos los lanzamientos de cualquier categoría.
  4. Si nada → usa el patrón default conservador.

  El patrón es el uplift por mes relativo al lanzamiento:
  {0: +18%, 1: +12%, 2: +7%, ...}
"""

import logging
import pandas as pd
from core.loader import load_lanzamientos_por_clasificacion, load_tipo_sheet, load_tipo_sheet_por_lanzamiento, resolver_clasificacion_2
from core.db import (
    query_df,
    TABLE_FACT_VENTAS, TABLE_DIM_ARTICULO, TABLE_LANZAMIENTOS,
)

log = logging.getLogger(__name__)

PATRON_DEFAULT = {0: 0.18, 1: 0.12, 2: 0.07, 3: 0.04, 4: 0.02, 5: 0.01}


def _patron_desde_proxy(proxy: str, clasificacion_2: str) -> dict | None:
    sql = f"""
        WITH codigos_lanz AS (
            SELECT CAST(l.codigo AS VARCHAR) AS codigo
            FROM {TABLE_LANZAMIENTOS} l
            WHERE l.lanzamiento = %(proxy)s
        ),
        primer_mes AS (
            SELECT MIN(TO_CHAR(fv.fecha, 'YYYY-MM')) AS periodo_lanzamiento
            FROM {TABLE_FACT_VENTAS} fv
            WHERE CAST(fv.producto AS VARCHAR) IN (SELECT codigo FROM codigos_lanz)
        ),
        ventas_clf2 AS (
            SELECT
                TO_CHAR(fv.fecha, 'YYYY-MM') AS periodo,
                SUM(fv.cantidad)              AS unidades
            FROM {TABLE_FACT_VENTAS} fv
            JOIN {TABLE_DIM_ARTICULO} dav
                ON CAST(fv.producto AS VARCHAR) = CAST(dav.codigo AS VARCHAR)
            WHERE dav.clasificacion_2_sheet = %(clf2)s
            GROUP BY 1
        ),
        baseline AS (
            SELECT AVG(unidades) AS base FROM ventas_clf2
        )
        SELECT
            DATEDIFF('month',
                TO_DATE(pm.periodo_lanzamiento, 'YYYY-MM'),
                TO_DATE(vc.periodo, 'YYYY-MM')
            )                                           AS mes_relativo,
            (vc.unidades - b.base) / NULLIF(b.base, 0) AS uplift_pct
        FROM primer_mes pm
        CROSS JOIN ventas_clf2 vc
        CROSS JOIN baseline b
        WHERE DATEDIFF('month',
                TO_DATE(pm.periodo_lanzamiento, 'YYYY-MM'),
                TO_DATE(vc.periodo, 'YYYY-MM')
              ) BETWEEN 0 AND 5
        ORDER BY mes_relativo
    """
    try:
        df = query_df(sql, {"proxy": proxy, "clf2": clasificacion_2})
        if not df.empty:
            return df.groupby("mes_relativo")["uplift_pct"].mean().to_dict()
    except Exception as e:
        log.warning("Error buscando proxy '%s': %s", proxy, e)
    return None


def _patron_promedio_general(tipo_sheet: str | None = None) -> tuple[dict, str]:
    """
    Promedia el patrón de todos los lanzamientos históricos.
    Si se pasa tipo_sheet, restringe a lanzamientos del mismo tipo.
    """
    tipo_filter = "AND dav.tipo_sheet = %(tipo)s" if tipo_sheet else ""
    params = {"tipo": tipo_sheet} if tipo_sheet else {}

    sql = f"""
        WITH lanzamientos_tipo AS (
            SELECT DISTINCT l.lanzamiento
            FROM {TABLE_LANZAMIENTOS} l
            JOIN {TABLE_DIM_ARTICULO} dav
                ON CAST(l.codigo AS VARCHAR) = CAST(dav.codigo AS VARCHAR)
            WHERE 1=1 {tipo_filter}
        ),
        primer_mes AS (
            SELECT
                l.lanzamiento,
                MIN(TO_CHAR(fv.fecha, 'YYYY-MM')) AS periodo_lanzamiento
            FROM {TABLE_FACT_VENTAS} fv
            JOIN {TABLE_LANZAMIENTOS} l
                ON CAST(fv.producto AS VARCHAR) = CAST(l.codigo AS VARCHAR)
            WHERE l.lanzamiento IN (SELECT lanzamiento FROM lanzamientos_tipo)
            GROUP BY l.lanzamiento
        ),
        ventas_por_lanz AS (
            SELECT
                pm.lanzamiento,
                TO_CHAR(fv.fecha, 'YYYY-MM')  AS periodo,
                SUM(fv.cantidad)               AS unidades
            FROM {TABLE_FACT_VENTAS} fv
            JOIN {TABLE_LANZAMIENTOS} l
                ON CAST(fv.producto AS VARCHAR) = CAST(l.codigo AS VARCHAR)
            JOIN primer_mes pm ON l.lanzamiento = pm.lanzamiento
            GROUP BY pm.lanzamiento, 2
        ),
        baseline_por_lanz AS (
            SELECT lanzamiento, AVG(unidades) AS base FROM ventas_por_lanz GROUP BY 1
        )
        SELECT
            DATEDIFF('month',
                TO_DATE(pm.periodo_lanzamiento, 'YYYY-MM'),
                TO_DATE(vl.periodo, 'YYYY-MM')
            )                                              AS mes_relativo,
            AVG((vl.unidades - bl.base) / NULLIF(bl.base, 0)) AS uplift_pct
        FROM ventas_por_lanz vl
        JOIN primer_mes pm        ON vl.lanzamiento = pm.lanzamiento
        JOIN baseline_por_lanz bl ON vl.lanzamiento = bl.lanzamiento
        WHERE DATEDIFF('month',
                TO_DATE(pm.periodo_lanzamiento, 'YYYY-MM'),
                TO_DATE(vl.periodo, 'YYYY-MM')
              ) BETWEEN 0 AND 5
        GROUP BY 1
        ORDER BY 1
    """
    try:
        df = query_df(sql, params)
        if not df.empty:
            patron = df.set_index("mes_relativo")["uplift_pct"].to_dict()
            scope = f"tipo '{tipo_sheet}'" if tipo_sheet else "general"
            log.warning("Usando patrón promedio de lanzamientos (%s). Confianza: baja.", scope)
            return patron, "baja"
    except Exception as e:
        log.warning("Error calculando patrón general: %s", e)
    log.warning("Sin histórico de lanzamientos. Usando patrón default.")
    return PATRON_DEFAULT, "supuesto"


def _patron_promedio(clasificacion_2: str, proxy: str | None) -> tuple[dict, str, str | None]:
    """Retorna (patron, confianza, tipo_sheet_usado)."""
    tipo_sheet = load_tipo_sheet(clasificacion_2)

    if proxy:
        patron = _patron_desde_proxy(proxy, clasificacion_2)
        if patron:
            tipo_proxy = load_tipo_sheet_por_lanzamiento(proxy)
            log.info("Proxy '%s' (tipo: %s) usado como referencia.", proxy, tipo_proxy or "?")
            return patron, "alta", tipo_sheet

    df = load_lanzamientos_por_clasificacion(clasificacion_2)
    if not df.empty:
        patron = df.groupby("mes_relativo")["uplift_pct"].mean().to_dict()
        n = df["lanzamiento"].nunique()
        confianza = "alta" if n >= 3 else "media"
        log.info("Usando %d lanzamiento(s) histórico(s) de '%s'.", n, clasificacion_2)
        return patron, confianza, tipo_sheet

    # Fallback: patrón general del mismo tipo_sheet
    if tipo_sheet:
        patron, confianza = _patron_promedio_general(tipo_sheet)
        if patron != PATRON_DEFAULT:
            return patron, confianza, tipo_sheet

    patron, confianza = _patron_promedio_general()
    return patron, confianza, tipo_sheet


def aplicar(df: pd.DataFrame, params: dict, periodo_desde: str, **kwargs) -> pd.DataFrame:
    """
    params:
      clasificacion_2: str     (texto libre, se resuelve por similitud)
      nombre_referencia: str   (descriptivo, para el log)
      proxy_lanzamiento: str   (opcional, nombre de un lanzamiento histórico)
    """
    clf2_texto = params.get("clasificacion_2", "")
    matches = resolver_clasificacion_2(clf2_texto)
    if not matches:
        log.error("No se encontró clasificacion_2 para '%s'. Se omite la palanca.", clf2_texto)
        return df
    clasificacion_2 = matches[0]
    log.info("Lanzamiento '%s' → clasificacion_2 resuelta: '%s'", clf2_texto, clasificacion_2)

    proxy = params.get("proxy_lanzamiento")
    patron, confianza, tipo_sheet = _patron_promedio(clasificacion_2, proxy)

    df = df.copy()
    col_base = "unidades_simuladas" if "unidades_simuladas" in df.columns else "forecast"

    periodos_sorted = sorted(df["periodo"].unique())
    periodo_inicio = min(periodos_sorted)

    def _mes_relativo(periodo: str) -> int:
        y1, m1 = int(periodo_inicio[:4]), int(periodo_inicio[5:7])
        y2, m2 = int(periodo[:4]), int(periodo[5:7])
        return (y2 - y1) * 12 + (m2 - m1)

    uplift_map = {p: patron.get(_mes_relativo(p), 0.0) for p in periodos_sorted}
    df["lanzamiento_uplift"]    = df["periodo"].map(uplift_map).fillna(0.0)
    df["unidades_simuladas"]    = df[col_base] * (1 + df["lanzamiento_uplift"])
    df["lanzamiento_confianza"] = confianza
    df["lanzamiento_tipo"]      = tipo_sheet or ""

    ref = params.get("nombre_referencia", clasificacion_2)
    log.info("Lanzamiento '%s': uplift mes 0 = %.1f%% [%s]",
             ref, patron.get(0, 0) * 100, confianza)
    return df
