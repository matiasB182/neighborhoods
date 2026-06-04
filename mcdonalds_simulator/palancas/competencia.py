"""
Palanca: Apertura de un competidor cerca de una sucursal.

Lógica:
  1. Busca en el histórico sucursales que YA tienen competidores a distancia similar.
  2. Compara sus ventas antes/después de la aparición del competidor.
  3. Aplica ese efecto a la sucursal del escenario.
  4. Si no hay histórico, usa un coeficiente por banda de distancia.
"""

import logging
import pandas as pd
from core.loader import load_competencia, load_ventas_historicas

log = logging.getLogger(__name__)

# Efecto por banda de distancia (fallback si no hay histórico)
EFECTO_POR_DISTANCIA = {
    0.3:  -0.15,  # < 300m: impacto fuerte
    0.6:  -0.10,  # 300-600m
    1.0:  -0.06,  # 600m-1km
    2.0:  -0.03,  # 1-2km
    999:  -0.01,  # > 2km: impacto mínimo
}


def _efecto_por_banda(distancia_km: float) -> float:
    for limite, efecto in sorted(EFECTO_POR_DISTANCIA.items()):
        if distancia_km <= limite:
            return efecto
    return -0.01


def _calcular_efecto_historico(sucursal_id: int,
                                distancia_km: float,
                                clasificacion_2: str | None) -> tuple[float, str]:
    """
    Busca sucursales que ya tienen un competidor a distancia similar
    y mide el impacto histórico en sus ventas.
    """
    comp = load_competencia()
    if comp.empty:
        fallback = _efecto_por_banda(distancia_km)
        log.warning("Sin tabla de competencia. Usando fallback por banda: %.1f%%", fallback * 100)
        return fallback, "supuesto"

    # Sucursales con competidor en banda de distancia similar (±0.3km)
    margen = 0.3
    similares = comp[
        (comp["distancia_km"] >= distancia_km - margen) &
        (comp["distancia_km"] <= distancia_km + margen) &
        (comp["sucursal"] != sucursal_id)
    ]["sucursal"].unique().tolist()

    if not similares:
        fallback = _efecto_por_banda(distancia_km)
        log.warning("Sin sucursales comparables a %.1fkm. Usando fallback: %.1f%%",
                    distancia_km, fallback * 100)
        return fallback, "baja"

    ventas = load_ventas_historicas(clasificacion_2)
    if ventas.empty:
        return _efecto_por_banda(distancia_km), "supuesto"

    # Promedio de ventas de esas sucursales vs el resto
    avg_con_comp  = ventas[ventas["sucursal"].isin(similares)]["unidades"].mean()
    avg_sin_comp  = ventas[~ventas["sucursal"].isin(similares)]["unidades"].mean()

    if avg_sin_comp <= 0:
        return _efecto_por_banda(distancia_km), "supuesto"

    efecto = (avg_con_comp - avg_sin_comp) / avg_sin_comp
    efecto = min(efecto, 0)  # competencia solo puede bajar ventas
    confianza = "media" if len(similares) >= 2 else "baja"
    log.info("Competencia a %.1fkm: efecto %.1f%% [%s]", distancia_km, efecto * 100, confianza)
    return efecto, confianza


def aplicar(df: pd.DataFrame, params: dict, **kwargs) -> pd.DataFrame:
    """
    df: forecast con columna 'unidades_simuladas' (o 'forecast')
    params: {
        sucursal: int,       # api_id_integer afectado
        distancia_km: float
    }
    """
    sucursal     = int(params["sucursal"])
    distancia_km = float(params["distancia_km"])

    clf2_lista = df["clasificacion_2"].unique().tolist()
    clf2 = clf2_lista[0] if len(clf2_lista) == 1 else None

    efecto, confianza = _calcular_efecto_historico(sucursal, distancia_km, clf2)

    df = df.copy()
    col_base = "unidades_simuladas" if "unidades_simuladas" in df.columns else "forecast"

    mascara = df["sucursal"] == sucursal
    df.loc[mascara, "unidades_simuladas"]  = df.loc[mascara, col_base] * (1 + efecto)
    df.loc[~mascara, "unidades_simuladas"] = df.loc[~mascara, col_base]

    df["competencia_efecto"]    = efecto
    df["competencia_confianza"] = confianza
    return df
