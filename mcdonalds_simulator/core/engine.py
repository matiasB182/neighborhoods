"""
Motor principal del simulador.

Orquesta las palancas en orden, pasando el resultado de cada una
como input de la siguiente (acumulativo).
"""

import logging
import pandas as pd
from core.loader import load_forecast

log = logging.getLogger(__name__)

PALANCAS_DISPONIBLES = {
    "precio":       "palancas.precio",
    "promocion":    "palancas.promocion",
    "lanzamiento":  "palancas.lanzamiento",
    "estructural":  "palancas.estructural",
    "competencia":  "palancas.competencia",
    "clima":        "palancas.clima",
}


def correr_escenario(config: dict) -> tuple[pd.DataFrame, str]:
    """
    Ejecuta el escenario completo definido en el YAML cargado como dict.
    Retorna (df_resultado, escenario_nombre).
    """
    escenario  = config.get("escenario", {})
    nombre     = escenario.get("nombre", "Sin nombre")
    filtros    = config.get("filtros", {})
    palancas   = config.get("palancas", [])

    clf2        = filtros.get("clasificacion_2")
    sucursal    = filtros.get("sucursal")
    periodo_desde = filtros["periodo_desde"]
    periodo_hasta = filtros["periodo_hasta"]

    log.info("Cargando forecast baseline...")
    df = load_forecast(clf2, sucursal, periodo_desde, periodo_hasta)

    if df.empty:
        log.error("Sin datos de forecast para los filtros indicados.")
        return df, nombre

    log.info("Forecast cargado: %d filas (%d clasificaciones, %d sucursales, %d periodos)",
             len(df),
             df["clasificacion_2"].nunique(),
             df["sucursal"].nunique(),
             df["periodo"].nunique())

    for i, palanca in enumerate(palancas):
        tipo = palanca.get("tipo", "").lower()
        if tipo not in PALANCAS_DISPONIBLES:
            log.warning("Palanca '%s' no reconocida, se omite.", tipo)
            continue

        modulo = _importar_palanca(tipo)
        log.info("Aplicando palanca %d/%d: %s...", i + 1, len(palancas), tipo.upper())

        df = modulo.aplicar(
            df,
            params=palanca,
            periodo_desde=periodo_desde,
            periodo_hasta=periodo_hasta,
        )

    # Si ninguna palanca generó unidades_simuladas, las igualamos al forecast base
    if "unidades_simuladas" not in df.columns:
        df["unidades_simuladas"] = df["forecast"]

    return df, nombre


def _importar_palanca(tipo: str):
    import importlib
    return importlib.import_module(PALANCAS_DISPONIBLES[tipo])
