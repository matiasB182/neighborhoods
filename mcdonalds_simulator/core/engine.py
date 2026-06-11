"""
Motor principal del simulador.

Busca la primera palanca con activo: true en el YAML, carga el forecast
usando los parámetros de esa palanca, y la ejecuta.
"""

import logging
import pandas as pd
from core.loader import load_forecast, resolver_clasificacion_2

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
    Ejecuta el escenario definido en el YAML.
    Busca la primera palanca con activo: true y la ejecuta.
    Retorna (df_resultado, escenario_nombre).
    """
    nombre   = config.get("escenario", {}).get("nombre", "Sin nombre")
    palancas = config.get("palancas", [])

    # Buscar la palanca activa
    palanca = next((p for p in palancas if p.get("activo", False)), None)
    if palanca is None:
        log.error("Ninguna palanca tiene activo: true en el YAML.")
        return pd.DataFrame(), nombre

    tipo = palanca.get("tipo", "").lower()
    if tipo not in PALANCAS_DISPONIBLES:
        log.error("Tipo de palanca '%s' no reconocido. Opciones: %s",
                  tipo, list(PALANCAS_DISPONIBLES.keys()))
        return pd.DataFrame(), nombre

    # Leer parámetros de la palanca activa
    clf2_texto = palanca.get("clasificacion_2")
    sucursal   = palanca.get("sucursal")

    # Todas las palancas aceptan fecha_desde/fecha_hasta (YYYY-MM-DD).
    # Si se pasa fecha exacta, se extrae el período (YYYY-MM) de ella.
    # Si se pasa periodo_desde/periodo_hasta (YYYY-MM), se usa directamente.
    if "fecha_desde" in palanca and palanca["fecha_desde"]:
        fecha_desde   = str(palanca["fecha_desde"])
        fecha_hasta   = str(palanca.get("fecha_hasta") or fecha_desde)
        periodo_desde = fecha_desde[:7]
        periodo_hasta = fecha_hasta[:7]
    else:
        periodo_desde = str(palanca["periodo_desde"])
        periodo_hasta = str(palanca["periodo_hasta"])
        fecha_desde   = periodo_desde + "-01"
        fecha_hasta   = periodo_hasta + "-01"

    # Resolver clasificacion_2 por similitud
    clf2_exactos = None
    if clf2_texto:
        matches = resolver_clasificacion_2(clf2_texto)
        if not matches:
            log.error("No se encontró ninguna clasificacion_2 que coincida con '%s'.", clf2_texto)
            return pd.DataFrame(), nombre
        clf2_exactos = matches

    log.info("Cargando forecast baseline...")
    df = load_forecast(clf2_exactos, sucursal, periodo_desde, periodo_hasta)

    if df.empty:
        log.error("Sin datos de forecast para los filtros indicados.")
        log.error("  clasificacion_2 : %s", clf2_texto or "(todas)")
        log.error("  sucursal        : %s", sucursal or "(todas)")
        log.error("  periodo         : %s → %s", periodo_desde, periodo_hasta)
        return df, nombre

    log.info("Forecast cargado: %d filas (%d clasificaciones, %d sucursales, %d periodos)",
             len(df),
             df["clasificacion_2"].nunique(),
             df["sucursal"].nunique(),
             df["periodo"].nunique())

    # Ejecutar la palanca
    modulo = _importar_palanca(tipo)
    log.info("Aplicando palanca: %s...", tipo.upper())
    df = modulo.aplicar(
        df,
        params=palanca,
        periodo_desde=periodo_desde,
        periodo_hasta=periodo_hasta,
    )

    if "unidades_simuladas" not in df.columns:
        df["unidades_simuladas"] = df["forecast"]

    return df, nombre


def _importar_palanca(tipo: str):
    import importlib
    return importlib.import_module(PALANCAS_DISPONIBLES[tipo])
