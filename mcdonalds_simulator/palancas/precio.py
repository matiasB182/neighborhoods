"""
Palanca: Cambio de precio.

Lógica:
  1. Obtiene la elasticidad histórica de la clasificacion_2 afectada.
  2. Calcula el impacto en unidades: Δunidades = cambio_pct_precio × elasticidad
  3. Calcula el ingreso base y simulado para mostrar si el movimiento es favorable.
"""

import pandas as pd
from core.elasticidades import get_elasticidad
from core.loader import load_precio_clasificacion2


def aplicar(df: pd.DataFrame, params: dict, periodo_desde: str, periodo_hasta: str) -> pd.DataFrame:
    """
    df: forecast con columnas [clasificacion_2, sucursal, periodo, forecast]
    params: { cambio_pct: float }
    Agrega columnas: unidades_simuladas, precio_base, precio_simulado,
                     ingreso_base, ingreso_simulado, elasticidad_usada, confianza_elasticidad
    """
    cambio_pct = float(params["cambio_pct"])

    # Precio promedio ponderado por clasificacion_2 y periodo
    clf2_unicas = df["clasificacion_2"].unique().tolist()
    precios_list = []
    for clf2 in clf2_unicas:
        p = load_precio_clasificacion2(clf2, periodo_desde, periodo_hasta)
        precios_list.append(p)
    precios = pd.concat(precios_list, ignore_index=True) if precios_list else pd.DataFrame()

    df = df.copy()

    if not precios.empty:
        df = df.merge(precios[["clasificacion_2", "periodo", "precio_promedio_ponderado"]],
                      on=["clasificacion_2", "periodo"], how="left")
        df.rename(columns={"precio_promedio_ponderado": "precio_base"}, inplace=True)
    else:
        df["precio_base"] = None

    # Elasticidad por clasificacion_2, usando el año del periodo simulado
    anio_simulado = int(periodo_desde[:4])
    elasticidades_cache = {}
    confianza_cache = {}
    for clf2 in clf2_unicas:
        e, c = get_elasticidad(clf2, anio=anio_simulado)
        elasticidades_cache[clf2] = e
        confianza_cache[clf2] = c

    df["elasticidad_usada"] = df["clasificacion_2"].map(elasticidades_cache)
    df["confianza_elasticidad"] = df["clasificacion_2"].map(confianza_cache)

    impacto_volumen = cambio_pct * df["elasticidad_usada"]
    df["unidades_simuladas"] = df["forecast"] * (1 + impacto_volumen)

    # Ingresos
    df["precio_simulado"] = df["precio_base"] * (1 + cambio_pct) if "precio_base" in df else None
    df["ingreso_base"] = df["forecast"] * df["precio_base"]
    df["ingreso_simulado"] = df["unidades_simuladas"] * df["precio_simulado"]

    return df
