"""
Palanca: Escenario climático (invierno más frío/lluvioso, verano más caluroso, etc.).

Lógica:
  Cada clasificacion_2 tiene una sensibilidad distinta al clima.
  Productos fríos (McFlurry, helados) bajan con frío/lluvia.
  Productos calientes (café, combos) pueden subir levemente.
  La variacion_pct del YAML es el desvío respecto al clima promedio histórico.
  El efecto final = variacion_pct × coeficiente_clima[clasificacion_2].
"""

import logging
import pandas as pd

log = logging.getLogger(__name__)

# Coeficiente de sensibilidad climática por categoría.
# Positivo = esa categoría CRECE cuando el clima es "más extremo" (frío/lluvia).
# Negativo = esa categoría CAE cuando el clima es "más extremo".
# Magnitud: por cada 1% de desvío climático, cuánto % cambian las unidades.
COEFICIENTES_CLIMA = {
    "mcflurry":        -0.40,
    "helados":         -0.40,
    "sundae":          -0.35,
    "mccafe":           0.20,
    "cafe":             0.20,
    "combos big mac":  -0.05,
    "combos":          -0.05,
    "nuggets":         -0.03,
    "papas":           -0.02,
    "_default":        -0.05,
}


def _coeficiente_para(clasificacion_2: str) -> float:
    clf2_lower = clasificacion_2.lower()
    for key, coef in COEFICIENTES_CLIMA.items():
        if key in clf2_lower:
            return coef
    return COEFICIENTES_CLIMA["_default"]


def aplicar(df: pd.DataFrame, params: dict, **kwargs) -> pd.DataFrame:
    """
    df: forecast con columna 'unidades_simuladas' (o 'forecast')
    params: {
        variacion_pct: float  # -0.20 = invierno 20% más frío/lluvioso que el promedio
    }
    """
    variacion_pct = float(params["variacion_pct"])

    df = df.copy()
    col_base = "unidades_simuladas" if "unidades_simuladas" in df.columns else "forecast"

    for clf2 in df["clasificacion_2"].unique():
        coef   = _coeficiente_para(clf2)
        efecto = variacion_pct * coef
        mascara = df["clasificacion_2"] == clf2
        df.loc[mascara, "unidades_simuladas"] = df.loc[mascara, col_base] * (1 + efecto)
        log.info("Clima: '%s' → coeficiente %.2f × variación %.1f%% = efecto %.1f%%",
                 clf2, coef, variacion_pct * 100, efecto * 100)

    df["clima_variacion_pct"] = variacion_pct
    df["clima_confianza"]     = "supuesto"
    return df
