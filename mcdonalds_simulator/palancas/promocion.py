"""
Palanca: Activar o desactivar una campaña promocional.

Lógica:
  1. Identifica qué clasificacion_2 afecta la campaña (via dim_articulo_venta).
  2. Busca en el histórico de ventas los periodos donde esa campaña estuvo activa.
  3. Calcula el uplift promedio que generó sobre la clasificacion_2.
  4. Aplica ese uplift (o lo resta si la acción es 'quitar').
  5. Si no hay histórico de la campaña, usa el promedio de campañas similares.
"""

import logging
import pandas as pd
from core.loader import load_periodos_campania, load_campania_clasificaciones, load_ventas_historicas
from core.db import query_df, SCHEMA

log = logging.getLogger(__name__)


def _calcular_uplift_campania(campania: str) -> tuple[float, str]:
    """
    Calcula el uplift promedio que generó una campaña sobre su clasificacion_2.
    Retorna (uplift_pct, nivel_confianza).
    """
    clfs = load_campania_clasificaciones(campania)
    if not clfs:
        log.warning("Campaña '%s' no encontrada o sin clasificacion_2 asociada.", campania)
        return _uplift_promedio_general(), "supuesto"

    # Ventas históricas de las clf2 afectadas
    ventas_list = [load_ventas_historicas(clf2) for clf2 in clfs]
    ventas = pd.concat(ventas_list, ignore_index=True)

    if ventas.empty:
        return _uplift_promedio_general(), "supuesto"

    # Periodos activos de la campaña
    periodos_promo = load_periodos_campania(campania)
    periodos_activos = set(periodos_promo["periodo"].unique()) if not periodos_promo.empty else set()

    if not periodos_activos:
        return _uplift_promedio_general(), "supuesto"

    ventas["en_promo"] = ventas["periodo"].isin(periodos_activos)
    baseline = ventas[~ventas["en_promo"]]["unidades"].mean()
    con_promo = ventas[ventas["en_promo"]]["unidades"].mean()

    if baseline <= 0:
        return _uplift_promedio_general(), "supuesto"

    uplift = (con_promo - baseline) / baseline
    n = len(periodos_activos)
    confianza = "alta" if n >= 3 else "media" if n >= 1 else "supuesto"
    return uplift, confianza


def _uplift_promedio_general() -> float:
    """Uplift promedio de todas las campañas históricas como fallback."""
    sql = f"""
        WITH codigos_promo AS (
            SELECT DISTINCT codigo FROM {SCHEMA}.promociones
        ),
        ventas_con_promo AS (
            SELECT
                TO_CHAR(fv.fecha, 'YYYY-MM') AS periodo,
                SUM(fv.cantidad)              AS unidades,
                1                             AS en_promo
            FROM stg.fact_ventas fv
            WHERE fv.producto IN (SELECT codigo FROM codigos_promo)
            GROUP BY 1
        ),
        baseline AS (
            SELECT AVG(unidades) AS base FROM ventas_con_promo
        )
        SELECT
            (AVG(vp.unidades) - b.base) / NULLIF(b.base, 0) AS uplift_promedio
        FROM ventas_con_promo vp, baseline b
    """
    try:
        df = query_df(sql)
        if not df.empty and df.iloc[0]["uplift_promedio"] is not None:
            return float(df.iloc[0]["uplift_promedio"])
    except Exception:
        pass
    return 0.12  # default conservador: +12% si no hay datos


def aplicar(df: pd.DataFrame, params: dict, **kwargs) -> pd.DataFrame:
    """
    df: forecast con columna 'unidades_simuladas' (o 'forecast' si es la primera palanca)
    params: { campania: str, accion: 'agregar' | 'quitar' }
    """
    campania = params["campania"]
    accion = params.get("accion", "agregar").lower()

    uplift, confianza = _calcular_uplift_campania(campania)

    if accion == "quitar":
        uplift = -uplift

    df = df.copy()
    col_base = "unidades_simuladas" if "unidades_simuladas" in df.columns else "forecast"
    df["unidades_simuladas"] = df[col_base] * (1 + uplift)

    log.info("Promoción '%s' (%s): uplift %.1f%% [%s]", campania, accion, uplift * 100, confianza)

    df["promo_uplift"] = uplift
    df["promo_confianza"] = confianza
    return df
