"""
Palanca: Promoción.

Subtipos:
  - descuento      → % de descuento sobre el precio (ej: -0.30 = 30% OFF)
  - 2x1            → equivale a descuento del 50% en precio efectivo
  - precio_fijo    → precio absoluto (ej: 15000 Gs), se convierte a % cambio
  - producto_gratis → uplift en unidades sin cambio de precio

Canal (opcional): automac / delivery / app / restaurante
  → aplica el efecto solo a sucursales que tienen ese canal

Lógica de descuento/2x1/precio_fijo:
  Usa la misma elasticidad que la palanca de precio para calcular el impacto
  en unidades, y calcula ingresos con el precio promocional.
"""

import logging
import pandas as pd
from core.elasticidades import get_elasticidad
from core.loader import (
    load_precio_clasificacion2, load_atributos_restaurantes,
    resolver_clasificacion_2,
)

log = logging.getLogger(__name__)

CANAL_A_COLUMNA = {
    "automac":     "tiene_automac",
    "delivery":    "tiene_delivery",
    "app":         "tiene_kiosco_digital",
    "restaurante": "tiene_mostrador",
}

UPLIFT_PRODUCTO_GRATIS_DEFAULT = 0.10


def _sucursales_con_canal(canal: str) -> set:
    """Retorna el conjunto de api_id de sucursales que tienen el canal."""
    col = CANAL_A_COLUMNA.get(canal.lower())
    if not col:
        log.warning("Canal '%s' no reconocido. Opciones: %s", canal, list(CANAL_A_COLUMNA.keys()))
        return set()
    atributos = load_atributos_restaurantes()
    if atributos.empty:
        return set()
    return set(atributos[atributos[col] == True]["api_id"].astype(str).tolist())


def _cambio_pct_para_precio_fijo(clasificacion_2: str, precio_fijo: float,
                                  periodo_desde: str, periodo_hasta: str) -> float:
    """Calcula el % de cambio entre el precio actual y el precio fijo de la promo."""
    precios = load_precio_clasificacion2(clasificacion_2, periodo_desde, periodo_hasta)
    if precios.empty or precios["precio_promedio_ponderado"].isna().all():
        log.warning("Sin precio histórico para '%s'. Usando cambio_pct=0.", clasificacion_2)
        return 0.0
    precio_actual = precios["precio_promedio_ponderado"].mean()
    return (precio_fijo - precio_actual) / precio_actual


def _uplift_producto_gratis(clasificacion_2: str) -> tuple[float, str]:
    """
    Busca en el histórico promos de 'producto gratis' para esa clasificacion_2.
    Si no hay, usa el default conservador.
    """
    from core.db import query_df, TABLE_FACT_VENTAS, TABLE_DIM_ARTICULO, TABLE_PROMOCIONES
    sql = f"""
        WITH codigos_promo AS (
            SELECT DISTINCT p.codigo
            FROM {TABLE_PROMOCIONES} p
            JOIN {TABLE_DIM_ARTICULO} dav
                ON CAST(p.codigo AS VARCHAR) = CAST(dav.codigo AS VARCHAR)
            WHERE dav.clasificacion_2_sheet = %(clf2)s
        ),
        ventas_promo AS (
            SELECT
                TO_CHAR(fv.fecha, 'YYYY-MM') AS periodo,
                SUM(fv.cantidad)              AS unidades
            FROM {TABLE_FACT_VENTAS} fv
            WHERE CAST(fv.producto AS VARCHAR) IN (SELECT CAST(codigo AS VARCHAR) FROM codigos_promo)
            GROUP BY 1
        ),
        ventas_total AS (
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
            SELECT AVG(unidades) AS base FROM ventas_total
            WHERE periodo NOT IN (SELECT periodo FROM ventas_promo)
        )
        SELECT
            (AVG(vt.unidades) - b.base) / NULLIF(b.base, 0) AS uplift
        FROM ventas_total vt, baseline b
        WHERE vt.periodo IN (SELECT periodo FROM ventas_promo)
    """
    try:
        df = query_df(sql, {"clf2": clasificacion_2})
        if not df.empty and df.iloc[0]["uplift"] is not None:
            return float(df.iloc[0]["uplift"]), "histórico"
    except Exception:
        pass
    log.warning("Sin histórico de producto gratis para '%s'. Usando default +%.0f%%.",
                clasificacion_2, UPLIFT_PRODUCTO_GRATIS_DEFAULT * 100)
    return UPLIFT_PRODUCTO_GRATIS_DEFAULT, "supuesto"


def aplicar(df: pd.DataFrame, params: dict, periodo_desde: str, periodo_hasta: str) -> pd.DataFrame:
    """
    params:
      subtipo: descuento | 2x1 | precio_fijo | producto_gratis
      clasificacion_2: str (texto libre, se resuelve por similitud)
      cambio_pct: float           (solo subtipo: descuento)
      precio: float               (solo subtipo: precio_fijo)
      producto_gratis: str        (solo subtipo: producto_gratis, descriptivo)
      canal: str                  (opcional: automac / delivery / app / restaurante)
    """
    subtipo = params.get("subtipo", "descuento").lower()
    canal   = params.get("canal")

    # Resolver clasificacion_2 por similitud
    clf2_texto = params.get("clasificacion_2", "")
    matches = resolver_clasificacion_2(clf2_texto)
    if not matches:
        log.error("No se encontró clasificacion_2 para '%s'. Se omite la palanca.", clf2_texto)
        return df
    clasificacion_2 = matches[0]
    log.info("Promoción '%s' → clasificacion_2 resuelta: '%s'", clf2_texto, clasificacion_2)

    # Sucursales afectadas por canal
    sucursales_canal = _sucursales_con_canal(canal) if canal else None

    df = df.copy()
    col_base = "unidades_simuladas" if "unidades_simuladas" in df.columns else "forecast"
    mascara_clf2 = df["clasificacion_2"] == clasificacion_2

    if sucursales_canal is not None:
        mascara_canal = df["sucursal"].astype(str).isin(sucursales_canal)
        mascara = mascara_clf2 & mascara_canal
        log.info("Canal '%s': %d sucursales afectadas.", canal, mascara_canal.sum())
    else:
        mascara = mascara_clf2

    # ── Subtipos que usan elasticidad ──────────────────────────────────────
    if subtipo in ("descuento", "2x1", "precio_fijo"):

        if subtipo == "2x1":
            cambio_pct = -0.50
        elif subtipo == "precio_fijo":
            precio_fijo = float(params["precio"])
            cambio_pct = _cambio_pct_para_precio_fijo(
                clasificacion_2, precio_fijo, periodo_desde, periodo_hasta)
        else:
            cambio_pct = float(params["cambio_pct"])

        elasticidad, confianza = get_elasticidad(clasificacion_2)
        impacto_volumen = cambio_pct * elasticidad

        # Precio base para calcular ingresos
        precios = load_precio_clasificacion2(clasificacion_2, periodo_desde, periodo_hasta)
        if not precios.empty:
            df = df.merge(precios[["clasificacion_2", "periodo", "precio_promedio_ponderado"]],
                          on=["clasificacion_2", "periodo"], how="left")
            df.rename(columns={"precio_promedio_ponderado": "precio_base"}, inplace=True)
        else:
            df["precio_base"] = None

        df.loc[mascara, "unidades_simuladas"] = df.loc[mascara, col_base] * (1 + impacto_volumen)
        df.loc[~mascara, "unidades_simuladas"] = df.loc[~mascara, col_base]

        df["precio_simulado"] = df.get("precio_base", pd.Series(dtype=float)) * (1 + cambio_pct)
        df["ingreso_base"]     = df[col_base] * df.get("precio_base", pd.Series(dtype=float))
        df["ingreso_simulado"] = df["unidades_simuladas"] * df["precio_simulado"]

        df["promo_subtipo"]     = subtipo
        df["promo_cambio_pct"]  = cambio_pct
        df["promo_elasticidad"] = elasticidad
        df["promo_confianza"]   = confianza
        df["promo_canal"]       = canal or "todos"

        log.info("Promo '%s' (%s): precio %+.1f%% → volumen %+.1f%% [elasticidad %.2f, %s]",
                 clasificacion_2, subtipo, cambio_pct * 100, impacto_volumen * 100,
                 elasticidad, confianza)

    # ── Producto gratis: uplift en unidades, precio sin cambio ─────────────
    elif subtipo == "producto_gratis":
        uplift, confianza = _uplift_producto_gratis(clasificacion_2)

        df.loc[mascara, "unidades_simuladas"] = df.loc[mascara, col_base] * (1 + uplift)
        df.loc[~mascara, "unidades_simuladas"] = df.loc[~mascara, col_base]

        df["promo_subtipo"]    = subtipo
        df["promo_uplift"]     = uplift
        df["promo_confianza"]  = confianza
        df["promo_canal"]      = canal or "todos"
        desc = params.get("producto_gratis", "")
        log.info("Promo '%s' producto gratis (%s): uplift %.1f%% [%s]",
                 clasificacion_2, desc, uplift * 100, confianza)

    else:
        log.error("Subtipo de promoción '%s' no reconocido.", subtipo)

    return df
