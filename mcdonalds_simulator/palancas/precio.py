"""
Palanca: Cambio de precio.

Modos:
  - simular   → aplica un cambio_pct fijo y muestra el resultado
  - optimizar → explora un rango de cambios y encuentra el óptimo según el objetivo

Objetivos de optimización:
  - max_ingreso  → % de cambio que maximiza el ingreso total
  - max_unidades → % de cambio que maximiza las unidades vendidas (siempre baja el precio)
  - breakeven    → % máximo de suba sin perder ingreso respecto al baseline
"""

import logging
import numpy as np
import pandas as pd
from core.elasticidades import get_elasticidad
from core.loader import load_precio_clasificacion2

log = logging.getLogger(__name__)


def _aplicar_cambio(df: pd.DataFrame, cambio_pct: float,
                    elasticidades: dict, precio_base_col: bool) -> pd.DataFrame:
    """Aplica un cambio_pct al df y retorna el df con unidades e ingresos simulados."""
    df = df.copy()
    impacto = cambio_pct * df["clasificacion_2"].map(elasticidades)
    df["unidades_simuladas"] = df["forecast"] * (1 + impacto)
    if precio_base_col:
        df["precio_simulado"]  = df["precio_base"] * (1 + cambio_pct)
        df["ingreso_base"]     = df["forecast"] * df["precio_base"]
        df["ingreso_simulado"] = df["unidades_simuladas"] * df["precio_simulado"]
    return df


def aplicar(df: pd.DataFrame, params: dict, periodo_desde: str, periodo_hasta: str) -> pd.DataFrame:
    """
    params:
      modo: simular | optimizar  (default: simular)

      # Modo simular:
      cambio_pct: float          # positivo = sube | negativo = baja

      # Modo optimizar:
      objetivo: max_ingreso | max_unidades | breakeven
      rango_desde: float         # límite inferior del rango a explorar (ej: -0.30)
      rango_hasta: float         # límite superior del rango a explorar (ej: 0.30)
    """
    modo = params.get("modo", "simular").lower()

    # Cargar precios base
    clf2_unicas = df["clasificacion_2"].unique().tolist()
    precios_list = [load_precio_clasificacion2(c, periodo_desde, periodo_hasta) for c in clf2_unicas]
    precios = pd.concat(precios_list, ignore_index=True) if precios_list else pd.DataFrame()

    df = df.copy()
    if not precios.empty:
        df = df.merge(precios[["clasificacion_2", "periodo", "precio_promedio_ponderado"]],
                      on=["clasificacion_2", "periodo"], how="left")
        df.rename(columns={"precio_promedio_ponderado": "precio_base"}, inplace=True)
        tiene_precios = True
    else:
        df["precio_base"] = None
        tiene_precios = False

    # Cargar elasticidades
    elasticidades = {}
    confianzas = {}
    for clf2 in clf2_unicas:
        e, c = get_elasticidad(clf2)
        elasticidades[clf2] = e
        confianzas[clf2] = c
    df["elasticidad_usada"]    = df["clasificacion_2"].map(elasticidades)
    df["confianza_elasticidad"] = df["clasificacion_2"].map(confianzas)

    if modo == "simular":
        cambio_pct = float(params["cambio_pct"])
        df = _aplicar_cambio(df, cambio_pct, elasticidades, tiene_precios)
        log.info("Precio %+.1f%% → impacto volumen estimado: %+.1f%%",
                 cambio_pct * 100,
                 (cambio_pct * list(elasticidades.values())[0]) * 100)

    elif modo == "optimizar":
        objetivo     = params.get("objetivo", "max_ingreso").lower()
        rango_desde  = float(params.get("rango_desde", -0.30))
        rango_hasta  = float(params.get("rango_hasta",  0.30))

        # Explorar el rango en pasos de 1%
        pasos = np.arange(rango_desde, rango_hasta + 0.001, 0.01)

        ingreso_base_total   = (df["forecast"] * df["precio_base"]).sum() if tiene_precios else 0
        unidades_base_total  = df["forecast"].sum()

        mejor_cambio  = 0.0
        mejor_valor   = ingreso_base_total if objetivo != "max_unidades" else unidades_base_total

        resultados = []
        for paso in pasos:
            df_paso = _aplicar_cambio(df, paso, elasticidades, tiene_precios)
            unidades = df_paso["unidades_simuladas"].sum()
            ingreso  = df_paso["ingreso_simulado"].sum() if tiene_precios else 0
            resultados.append({"cambio_pct": paso, "unidades": unidades, "ingreso": ingreso})

        resultados_df = pd.DataFrame(resultados)

        if objetivo == "max_ingreso":
            idx = resultados_df["ingreso"].idxmax()
            mejor_cambio = resultados_df.loc[idx, "cambio_pct"]
            mejor_valor  = resultados_df.loc[idx, "ingreso"]
            log.info("Optimización max_ingreso: punto óptimo %+.1f%% (ingreso: %+.1f%% vs base)",
                     mejor_cambio * 100,
                     (mejor_valor - ingreso_base_total) / ingreso_base_total * 100)

        elif objetivo == "max_unidades":
            idx = resultados_df["unidades"].idxmax()
            mejor_cambio = resultados_df.loc[idx, "cambio_pct"]
            mejor_valor  = resultados_df.loc[idx, "unidades"]
            log.info("Optimización max_unidades: punto óptimo %+.1f%% (unidades: %+.1f%% vs base)",
                     mejor_cambio * 100,
                     (mejor_valor - unidades_base_total) / unidades_base_total * 100)

        elif objetivo == "breakeven":
            # Máxima suba donde el ingreso no baja respecto al baseline
            subas = resultados_df[resultados_df["cambio_pct"] >= 0]
            viables = subas[subas["ingreso"] >= ingreso_base_total]
            if not viables.empty:
                mejor_cambio = viables["cambio_pct"].max()
                log.info("Optimización breakeven: podés subir hasta %+.1f%% sin perder ingreso",
                         mejor_cambio * 100)
            else:
                mejor_cambio = 0.0
                log.warning("Optimización breakeven: cualquier suba reduce el ingreso.")

        # Aplicar el cambio óptimo al df final
        df = _aplicar_cambio(df, mejor_cambio, elasticidades, tiene_precios)

        # Guardar metadata de optimización para el formatter
        df["optimizacion_objetivo"] = objetivo
        df["optimizacion_cambio_optimo"] = mejor_cambio
        df["optimizacion_rango"] = f"{rango_desde:+.0%} → {rango_hasta:+.0%}"

    else:
        log.error("Modo '%s' no reconocido. Usar: simular | optimizar", modo)

    return df
