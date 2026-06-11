"""
Palanca: Agregar un canal estructural a una sucursal (Automac, Delivery, etc.).

Lógica:
  1. Identifica sucursales que YA tienen el canal (grupo tratado).
  2. Identifica sucursales SIN el canal (grupo control).
  3. Si se especifica zona, restringe la comparación a sucursales del mismo
     barrio / distrito / dpto — más representativas que todo el país.
  4. Calcula la diferencia porcentual de ventas entre ambos grupos.
  5. Aplica ese efecto a las sucursales del escenario.

Parámetro zona (opcional):
  barrio    → compara dentro del mismo barrio
  distrito  → compara dentro del mismo distrito
  dpto      → compara dentro del mismo departamento
  null      → compara contra todo el país (comportamiento original)

CÁLCULO:
  avg_con_canal  = promedio de ventas históricas de sucursales CON el canal
  avg_sin_canal  = promedio de ventas históricas de sucursales SIN el canal
  efecto         = (avg_con_canal - avg_sin_canal) / avg_sin_canal

  unidades_simuladas = forecast × (1 + efecto)

  Limitación: es una comparación cross-sectional, no causal. Las sucursales
  con Automac pueden tener más ventas por otros factores (ubicación, tamaño).
  La zona ayuda a reducir ese sesgo comparando sucursales más similares entre sí.
"""

import logging
import pandas as pd
from core.loader import load_atributos_restaurantes, load_ventas_historicas, load_zonas_restaurantes, load_tipo_sheet

log = logging.getLogger(__name__)

CANALES = {
    "mostrador":      "tiene_mostrador",
    "automac":        "tiene_automac",
    "delivery":       "tiene_delivery",
    "kiosco_digital": "tiene_kiosco_digital",
    "centro_postres": "tiene_centro_postres",
}

EFECTO_MINIMO = 0.05
ZONA_A_COLUMNA = {
    "barrio":    "barrio",
    "distrito":  "distrito",
    "dpto":      "dpto",
}


def _calcular_efecto_canal(canal: str, clasificacion_2: str | None,
                            sucursal: str | None, zona: str | None) -> tuple[float, str, str]:
    """
    Compara ventas de sucursales con vs sin el canal.
    Si se pasa zona, restringe la comparación a sucursales de la misma zona
    que la sucursal objetivo.
    Retorna (efecto_pct, confianza, descripcion_zona).
    """
    col_flag = CANALES.get(canal)
    if not col_flag:
        log.error("Canal '%s' no reconocido. Opciones: %s", canal, list(CANALES.keys()))
        return 0.0, "supuesto", "sin zona"

    atributos = load_atributos_restaurantes()
    if atributos.empty:
        return EFECTO_MINIMO, "supuesto", "sin zona"

    # Filtrar por zona si se especificó
    desc_zona = "todo el país"
    if zona and sucursal:
        col_zona = ZONA_A_COLUMNA.get(zona.lower())
        if col_zona:
            zonas = load_zonas_restaurantes()
            if not zonas.empty:
                zona_sucursal = zonas[zonas["sucursal"] == str(sucursal)][col_zona]
                if not zona_sucursal.empty:
                    valor_zona = zona_sucursal.iloc[0]
                    sucursales_zona = set(zonas[zonas[col_zona] == valor_zona]["sucursal"].tolist())
                    atributos = atributos[atributos["api_id"].astype(str).isin(sucursales_zona)]
                    desc_zona = f"{zona} '{valor_zona}'"
                    log.info("Comparando dentro de %s: %d sucursales.", desc_zona, len(atributos))

    con_canal = set(atributos[atributos[col_flag] == True]["api_id"].astype(str).tolist())
    sin_canal = set(atributos[atributos[col_flag] == False]["api_id"].astype(str).tolist())

    if not con_canal or not sin_canal:
        log.warning("No hay suficientes sucursales en %s para comparar '%s'. Usando todo el país.",
                    desc_zona, canal)
        # Fallback a todo el país
        atributos_todos = load_atributos_restaurantes()
        con_canal = set(atributos_todos[atributos_todos[col_flag] == True]["api_id"].astype(str).tolist())
        sin_canal = set(atributos_todos[atributos_todos[col_flag] == False]["api_id"].astype(str).tolist())
        desc_zona = "todo el país (fallback: sin zona con suficientes datos)"

    ventas = load_ventas_historicas(clasificacion_2)
    if ventas.empty:
        return EFECTO_MINIMO, "supuesto", desc_zona

    avg_con = ventas[ventas["sucursal"].isin(con_canal)]["unidades"].mean()
    avg_sin = ventas[ventas["sucursal"].isin(sin_canal)]["unidades"].mean()

    if avg_sin <= 0:
        return EFECTO_MINIMO, "supuesto", desc_zona

    efecto    = (avg_con - avg_sin) / avg_sin
    n_con     = len(con_canal)
    n_sin     = len(sin_canal)
    confianza = "alta" if min(n_con, n_sin) >= 5 else "media" if min(n_con, n_sin) >= 2 else "baja"

    log.info("Canal '%s' en %s: efecto %.1f%% (n_con=%d, n_sin=%d) [%s]",
             canal, desc_zona, efecto * 100, n_con, n_sin, confianza)
    return efecto, confianza, desc_zona


def aplicar(df: pd.DataFrame, params: dict, **kwargs) -> pd.DataFrame:
    """
    params:
      canal: str          # automac | delivery | app | restaurante | centro_postres
      sucursal: str|None  # api_id_integer | null = todas
      zona: str|None      # barrio | distrito | dpto | null = todo el país
    """
    canal    = params["canal"]
    sucursal = str(params["sucursal"]) if params.get("sucursal") else None
    zona     = params.get("zona")

    clf2_lista = df["clasificacion_2"].unique().tolist()
    clf2 = clf2_lista[0] if len(clf2_lista) == 1 else None
    tipo_sheet = load_tipo_sheet(clf2) if clf2 else None

    efecto, confianza, desc_zona = _calcular_efecto_canal(canal, clf2, sucursal, zona)

    df = df.copy()
    col_base = "unidades_simuladas" if "unidades_simuladas" in df.columns else "forecast"

    mascara = pd.Series(True, index=df.index)
    if sucursal is not None:
        mascara = df["sucursal"].astype(str) == sucursal

    df.loc[mascara,  "unidades_simuladas"] = df.loc[mascara,  col_base] * (1 + efecto)
    df.loc[~mascara, "unidades_simuladas"] = df.loc[~mascara, col_base]

    df["estructural_canal"]      = canal
    df["estructural_efecto"]     = efecto
    df["estructural_confianza"]  = confianza
    df["estructural_zona"]       = desc_zona
    df["estructural_tipo_sheet"] = tipo_sheet or ""
    return df
