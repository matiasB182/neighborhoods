"""
Palanca: Apertura de un competidor cerca de una sucursal.

Lógica:
  1. Busca sucursales que YA tienen competidores a distancia similar (grupo tratado).
  2. Si se especifica zona, restringe la búsqueda a sucursales del mismo
     barrio / distrito / dpto — más representativas que todo el país.
  3. Compara sus ventas vs sucursales sin competidor cercano.
  4. Si no hay histórico suficiente, usa un coeficiente por banda de distancia.

Parámetro zona (opcional):
  barrio    → compara dentro del mismo barrio
  distrito  → compara dentro del mismo distrito
  dpto      → compara dentro del mismo departamento
  null      → compara contra todo el país (comportamiento original)

CÁLCULO:
  similares      = sucursales con competidor a distancia_km ± 0.3km (de la tabla competencia)
  avg_con_comp   = promedio de ventas históricas de esas sucursales
  avg_sin_comp   = promedio de ventas históricas de sucursales sin competidor cercano
  efecto         = (avg_con_comp - avg_sin_comp) / avg_sin_comp  [siempre ≤ 0]

  unidades_simuladas[sucursal_afectada] = forecast × (1 + efecto)
  unidades_simuladas[resto]             = forecast (sin cambio)

  Fallback si no hay sucursales comparables:
    efecto por banda de distancia (supuesto de industria):
    < 300m → -15%, 300-600m → -10%, 600m-1km → -6%, 1-2km → -3%, > 2km → -1%
"""

import logging
import pandas as pd
from core.loader import load_competencia, load_ventas_historicas, load_zonas_restaurantes, load_tipo_sheet

log = logging.getLogger(__name__)

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


def _calcular_efecto_historico(sucursal_id: str, distancia_km: float,
                                clasificacion_2: str | None,
                                zona: str | None) -> tuple[float, str, str]:
    """
    Busca sucursales con competidor a distancia similar y mide el impacto.
    Si se pasa zona, restringe a sucursales de la misma zona que la sucursal objetivo.
    Retorna (efecto_pct, confianza, descripcion_zona).
    """
    comp = load_competencia()
    if comp.empty:
        fallback = _efecto_por_banda(distancia_km)
        log.warning("Sin tabla de competencia. Usando fallback por banda: %.1f%%", fallback * 100)
        return fallback, "supuesto", "sin datos"

    # Sucursales con competidor en banda de distancia similar (±0.3km)
    margen = 0.3
    similares = comp[
        (comp["distancia_km"] >= distancia_km - margen) &
        (comp["distancia_km"] <= distancia_km + margen) &
        (comp["sucursal"].astype(str) != str(sucursal_id))
    ]["sucursal"].astype(str).unique().tolist()

    desc_zona = "todo el país"

    # Filtrar por zona si se especificó
    if zona and similares:
        col_zona = {"barrio": "barrio", "distrito": "distrito", "dpto": "dpto"}.get(zona.lower())
        if col_zona:
            zonas = load_zonas_restaurantes()
            if not zonas.empty:
                zona_sucursal = zonas[zonas["sucursal"] == str(sucursal_id)][col_zona]
                if not zona_sucursal.empty:
                    valor_zona = zona_sucursal.iloc[0]
                    sucursales_zona = set(zonas[zonas[col_zona] == valor_zona]["sucursal"].tolist())
                    similares_zona  = [s for s in similares if s in sucursales_zona]
                    if similares_zona:
                        similares  = similares_zona
                        desc_zona  = f"{zona} '{valor_zona}'"
                        log.info("Comparando dentro de %s: %d sucursales similares.", desc_zona, len(similares))
                    else:
                        log.warning("Sin sucursales comparables en %s '%s'. Usando todo el país.",
                                    zona, valor_zona)

    if not similares:
        fallback = _efecto_por_banda(distancia_km)
        log.warning("Sin sucursales comparables a %.1fkm. Usando fallback: %.1f%%",
                    distancia_km, fallback * 100)
        return fallback, "baja", desc_zona

    ventas = load_ventas_historicas(clasificacion_2)
    if ventas.empty:
        return _efecto_por_banda(distancia_km), "supuesto", desc_zona

    avg_con_comp = ventas[ventas["sucursal"].isin(similares)]["unidades"].mean()
    avg_sin_comp = ventas[~ventas["sucursal"].isin(similares)]["unidades"].mean()

    if avg_sin_comp <= 0:
        return _efecto_por_banda(distancia_km), "supuesto", desc_zona

    efecto    = (avg_con_comp - avg_sin_comp) / avg_sin_comp
    efecto    = min(efecto, 0)  # competencia solo puede bajar ventas
    confianza = "media" if len(similares) >= 2 else "baja"

    log.info("Competencia a %.1fkm en %s: efecto %.1f%% [%s]",
             distancia_km, desc_zona, efecto * 100, confianza)
    return efecto, confianza, desc_zona


def aplicar(df: pd.DataFrame, params: dict, **kwargs) -> pd.DataFrame:
    """
    params:
      sucursal: int        # api_id_integer de la sucursal afectada
      distancia_km: float  # distancia estimada del competidor en km
      zona: str|None       # barrio | distrito | dpto | null = todo el país
    """
    sucursal_id  = str(params["sucursal"])
    distancia_km = float(params["distancia_km"])
    zona         = params.get("zona")

    clf2_lista = df["clasificacion_2"].unique().tolist()
    clf2 = clf2_lista[0] if len(clf2_lista) == 1 else None
    tipo_sheet = load_tipo_sheet(clf2) if clf2 else None

    efecto, confianza, desc_zona = _calcular_efecto_historico(
        sucursal_id, distancia_km, clf2, zona)

    df = df.copy()
    col_base = "unidades_simuladas" if "unidades_simuladas" in df.columns else "forecast"

    mascara = df["sucursal"].astype(str) == sucursal_id
    df.loc[mascara,  "unidades_simuladas"] = df.loc[mascara,  col_base] * (1 + efecto)
    df.loc[~mascara, "unidades_simuladas"] = df.loc[~mascara, col_base]

    df["competencia_efecto"]      = efecto
    df["competencia_confianza"]   = confianza
    df["competencia_zona"]        = desc_zona
    df["competencia_tipo_sheet"]  = tipo_sheet or ""
    return df
