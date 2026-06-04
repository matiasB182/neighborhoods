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

    # Resolver clasificacion_2 por similitud si viene texto libre
    clf2_exactos = None  # lista de nombres exactos resueltos
    if clf2:
        from core.loader import resolver_clasificacion_2
        matches = resolver_clasificacion_2(clf2)
        if len(matches) == 0:
            log.error("No se encontró ninguna clasificacion_2 que coincida con '%s'.", clf2)
            log.error("Ejecutá: python run.py --listar para ver valores disponibles.")
            return pd.DataFrame(), nombre
        elif len(matches) == 1:
            clf2_exactos = matches
            log.info("clasificacion_2 resuelta → '%s'", matches[0])
        else:
            clf2_exactos = matches
            log.warning("Se encontraron %d clasificaciones que coinciden con '%s':", len(matches), clf2)
            for m in matches:
                log.warning("  - %s", m)
            log.warning("Se simulará con TODAS. Especificá el nombre exacto en el YAML para filtrar una sola.")

    df = load_forecast(clf2_exactos, sucursal, periodo_desde, periodo_hasta)

    if df.empty:
        log.error("Sin datos de forecast para los filtros indicados.")
        log.error("  clasificacion_2 : %s", clf2 or "(todas)")
        log.error("  sucursal        : %s", sucursal or "(todas)")
        log.error("  periodo         : %s → %s", periodo_desde, periodo_hasta)
        log.error("Ejecutá: python run.py --listar para ver valores disponibles.")
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
