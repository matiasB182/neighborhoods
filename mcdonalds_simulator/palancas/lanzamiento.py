"""
Palanca: Lanzamiento de producto nuevo (con o sin histórico propio).

Lógica:
  1. Si hay un proxy_lanzamiento específico → usa su patrón histórico exacto.
  2. Si no → busca todos los lanzamientos históricos de la misma clasificacion_2
     y promedia su patrón de adopción (uplift mes 0, 1, 2, 3, 4, 5).
  3. Si tampoco hay → usa el patrón promedio de todos los lanzamientos disponibles.
  4. Aplica ese patrón a cada periodo del forecast a partir de periodo_desde.
"""

import logging
import numpy as np
import pandas as pd
from core.loader import load_lanzamientos_por_clasificacion
from core.db import query_df, SCHEMA

log = logging.getLogger(__name__)

# Patrón fallback si no hay absolutamente ningún histórico de lanzamientos
PATRON_DEFAULT = {0: 0.18, 1: 0.12, 2: 0.07, 3: 0.04, 4: 0.02, 5: 0.01}


def _patron_promedio(clasificacion_2: str, proxy: str | None) -> tuple[dict, str]:
    """
    Retorna el patrón de uplift por mes relativo y el nivel de confianza.
    patron = {0: uplift_mes0, 1: uplift_mes1, ...}
    """
    if proxy:
        # Usar el lanzamiento proxy específico
        sql = f"""
            WITH codigos_lanz AS (
                SELECT l.codigo
                FROM {SCHEMA}.lanzamientos l
                WHERE l.lanzamiento = %(proxy)s
            ),
            primer_mes AS (
                SELECT MIN(TO_CHAR(fv.fecha, 'YYYY-MM')) AS periodo_lanzamiento
                FROM stg.fact_ventas fv
                WHERE fv.producto IN (SELECT codigo FROM codigos_lanz)
            ),
            ventas_clf2 AS (
                SELECT
                    TO_CHAR(fv.fecha, 'YYYY-MM') AS periodo,
                    SUM(fv.cantidad)              AS unidades
                FROM stg.fact_ventas fv
                JOIN stg.dim_articulo_venta dav ON fv.producto = dav.codigo
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
                )                                       AS mes_relativo,
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
        df = query_df(sql, {"proxy": proxy, "clf2": clasificacion_2})
        if not df.empty:
            patron = df.groupby("mes_relativo")["uplift_pct"].mean().to_dict()
            return patron, "alta"

    # Promedio de todos los lanzamientos históricos de la clasificacion_2
    df = load_lanzamientos_por_clasificacion(clasificacion_2)
    if not df.empty:
        patron = df.groupby("mes_relativo")["uplift_pct"].mean().to_dict()
        n = df["lanzamiento"].nunique()
        confianza = "alta" if n >= 3 else "media"
        log.info("Usando %d lanzamiento(s) histórico(s) de '%s' como proxy.", n, clasificacion_2)
        return patron, confianza

    # Fallback: promedio de todos los lanzamientos de cualquier categoría
    sql_general = f"""
        WITH todos_lanzamientos AS (
            SELECT DISTINCT lanzamiento
            FROM {SCHEMA}.lanzamientos
        ),
        primer_mes AS (
            SELECT
                tl.lanzamiento,
                MIN(TO_CHAR(fv.fecha, 'YYYY-MM')) AS periodo_lanzamiento
            FROM stg.fact_ventas fv
            JOIN {SCHEMA}.lanzamientos l ON fv.producto = l.codigo
            JOIN todos_lanzamientos tl ON l.lanzamiento = tl.lanzamiento
            GROUP BY tl.lanzamiento
        ),
        ventas_por_lanz AS (
            SELECT
                pm.lanzamiento,
                TO_CHAR(fv.fecha, 'YYYY-MM')  AS periodo,
                SUM(fv.cantidad)               AS unidades
            FROM stg.fact_ventas fv
            JOIN {SCHEMA}.lanzamientos l ON fv.producto = l.codigo
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
            )                                          AS mes_relativo,
            AVG((vl.unidades - bl.base) / NULLIF(bl.base, 0)) AS uplift_pct
        FROM ventas_por_lanz vl
        JOIN primer_mes pm      ON vl.lanzamiento = pm.lanzamiento
        JOIN baseline_por_lanz bl ON vl.lanzamiento = bl.lanzamiento
        WHERE DATEDIFF('month',
                TO_DATE(pm.periodo_lanzamiento, 'YYYY-MM'),
                TO_DATE(vl.periodo, 'YYYY-MM')
              ) BETWEEN 0 AND 5
        GROUP BY 1
        ORDER BY 1
    """
    df_gen = query_df(sql_general)
    if not df_gen.empty:
        patron = df_gen.set_index("mes_relativo")["uplift_pct"].to_dict()
        log.warning("Sin proxy para '%s'. Usando patrón promedio general. Confianza: BAJA.", clasificacion_2)
        return patron, "baja"

    log.warning("Sin histórico de lanzamientos. Usando patrón default.")
    return PATRON_DEFAULT, "supuesto"


def aplicar(df: pd.DataFrame, params: dict, periodo_desde: str, **kwargs) -> pd.DataFrame:
    """
    df: forecast con columna 'unidades_simuladas' (o 'forecast')
    params: {
        clasificacion_2: str,   # categoría afectada
        nombre_referencia: str, # solo descriptivo
        proxy_lanzamiento: str | None
    }
    """
    clasificacion_2 = params.get("clasificacion_2")
    proxy = params.get("proxy_lanzamiento")

    patron, confianza = _patron_promedio(clasificacion_2, proxy)

    df = df.copy()
    col_base = "unidades_simuladas" if "unidades_simuladas" in df.columns else "forecast"

    # Ordenar periodos del escenario para calcular el mes relativo
    periodos_sorted = sorted(df["periodo"].unique())
    periodo_inicio = min(periodos_sorted)

    def _mes_relativo(periodo: str) -> int:
        y1, m1 = int(periodo_inicio[:4]), int(periodo_inicio[5:7])
        y2, m2 = int(periodo[:4]), int(periodo[5:7])
        return (y2 - y1) * 12 + (m2 - m1)

    def _uplift_para_periodo(periodo: str) -> float:
        mr = _mes_relativo(periodo)
        return patron.get(mr, 0.0)

    uplift_map = {p: _uplift_para_periodo(p) for p in periodos_sorted}
    df["lanzamiento_uplift"] = df["periodo"].map(uplift_map).fillna(0.0)
    df["unidades_simuladas"] = df[col_base] * (1 + df["lanzamiento_uplift"])
    df["lanzamiento_confianza"] = confianza

    ref = params.get("nombre_referencia", clasificacion_2)
    log.info("Lanzamiento '%s': patrón aplicado [%s]. Uplift mes 0: %.1f%%",
             ref, confianza, patron.get(0, 0) * 100)

    return df
