"""
Palanca: Agregar un canal estructural a una sucursal (Automac, Kiosco Digital, etc.).

Lógica:
  1. Identifica sucursales que YA tienen el canal solicitado (grupo tratado).
  2. Identifica sucursales similares sin el canal (grupo control).
  3. Calcula la diferencia porcentual sostenida de unidades entre ambos grupos.
  4. Aplica ese efecto a las sucursales del filtro del escenario.
"""

import logging
import pandas as pd
from core.loader import load_atributos_restaurantes, load_ventas_historicas

log = logging.getLogger(__name__)

CANALES = {
    "mostrador":      "tiene_mostrador",
    "automac":        "tiene_automac",
    "delivery":       "tiene_delivery",
    "kiosco_digital": "tiene_kiosco_digital",
    "centro_postres": "tiene_centro_postres",
}

# Efecto mínimo razonable si hay muy pocas observaciones
EFECTO_MINIMO = 0.05


def _calcular_efecto_canal(canal: str,
                            clasificacion_2: str | None = None) -> tuple[float, str]:
    """
    Compara ventas promedio de sucursales con vs sin el canal.
    Retorna (efecto_pct, confianza).
    """
    col_flag = CANALES.get(canal)
    if not col_flag:
        log.error("Canal '%s' no reconocido. Opciones: %s", canal, list(CANALES.keys()))
        return 0.0, "supuesto"

    atributos = load_atributos_restaurantes()
    if atributos.empty:
        return EFECTO_MINIMO, "supuesto"

    con_canal    = set(atributos[atributos[col_flag] == True]["api_id"].tolist())
    sin_canal    = set(atributos[atributos[col_flag] == False]["api_id"].tolist())

    if not con_canal or not sin_canal:
        log.warning("No hay suficientes sucursales para comparar el efecto de '%s'.", canal)
        return EFECTO_MINIMO, "supuesto"

    ventas = load_ventas_historicas(clasificacion_2)
    if ventas.empty:
        return EFECTO_MINIMO, "supuesto"

    avg_con    = ventas[ventas["sucursal"].isin(con_canal)]["unidades"].mean()
    avg_sin    = ventas[ventas["sucursal"].isin(sin_canal)]["unidades"].mean()

    if avg_sin <= 0:
        return EFECTO_MINIMO, "supuesto"

    efecto = (avg_con - avg_sin) / avg_sin
    n_con  = len(con_canal)
    n_sin  = len(sin_canal)
    confianza = "alta" if min(n_con, n_sin) >= 5 else "media" if min(n_con, n_sin) >= 2 else "baja"

    log.info("Canal '%s': efecto estimado %.1f%% (n_con=%d, n_sin=%d) [%s]",
             canal, efecto * 100, n_con, n_sin, confianza)
    return efecto, confianza


def aplicar(df: pd.DataFrame, params: dict, **kwargs) -> pd.DataFrame:
    """
    df: forecast con columna 'unidades_simuladas' (o 'forecast')
    params: {
        canal: str,         # nombre del canal a agregar
        sucursal: int | None  # None = aplica a todas las del escenario
    }
    """
    canal     = params["canal"]
    sucursal  = params.get("sucursal")

    # Tomamos la clasificacion_2 del df para afinar el cálculo
    clf2_lista = df["clasificacion_2"].unique().tolist()
    clf2 = clf2_lista[0] if len(clf2_lista) == 1 else None

    efecto, confianza = _calcular_efecto_canal(canal, clf2)

    df = df.copy()
    col_base = "unidades_simuladas" if "unidades_simuladas" in df.columns else "forecast"

    mascara = pd.Series(True, index=df.index)
    if sucursal is not None:
        mascara = df["sucursal"] == sucursal

    df.loc[mascara, "unidades_simuladas"] = df.loc[mascara, col_base] * (1 + efecto)
    df.loc[~mascara, "unidades_simuladas"] = df.loc[~mascara, col_base]

    df["estructural_canal"]      = canal
    df["estructural_efecto"]     = efecto
    df["estructural_confianza"]  = confianza
    return df
