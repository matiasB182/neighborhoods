"""Genera el resumen en consola que GENIA lee para responder al usuario."""

import pandas as pd


def resumen_consola(df: pd.DataFrame, escenario_nombre: str, palancas: list) -> str:
    if df.empty:
        return "Sin datos para el escenario solicitado."

    col_sim = "unidades_simuladas" if "unidades_simuladas" in df.columns else "forecast"

    total_base = df["forecast"].sum()
    total_sim  = df[col_sim].sum()
    delta_abs  = total_sim - total_base
    delta_pct  = delta_abs / total_base * 100 if total_base > 0 else 0

    n_sucursales = df["sucursal"].nunique()
    periodos     = sorted(df["periodo"].unique())
    periodo_str  = f"{periodos[0]} → {periodos[-1]}" if len(periodos) > 1 else periodos[0]

    # Ingresos (si están disponibles)
    ingreso_lines = ""
    if "ingreso_base" in df.columns and df["ingreso_base"].notna().any():
        ing_base = df["ingreso_base"].sum()
        ing_sim  = df["ingreso_simulado"].sum() if "ingreso_simulado" in df.columns else None
        if ing_sim is not None:
            ing_delta     = ing_sim - ing_base
            ing_delta_pct = ing_delta / ing_base * 100 if ing_base > 0 else 0
            ing_base_fmt  = f"{ing_base:,.0f} Gs"
            ing_sim_fmt   = f"{ing_sim:,.0f} Gs"
            ing_delta_fmt = f"{ing_delta:+,.0f} Gs ({ing_delta_pct:+.1f}%)"
            ingreso_lines = (
                f"  Ingreso base/mes:    {ing_base_fmt}\n"
                f"  Ingreso simulado/mes:{ing_sim_fmt}\n"
                f"  Delta ingreso:       {ing_delta_fmt}\n"
            )

    # Elasticidad (si aplica palanca precio)
    elast_line = ""
    if "elasticidad_usada" in df.columns:
        e = df["elasticidad_usada"].iloc[0]
        c = df.get("confianza_elasticidad", pd.Series(["?"])).iloc[0]
        elast_line = f"\n  Elasticidad usada: {e:.2f}  |  Confianza: {c}"

    # Advertencia de ingreso
    advertencia = ""
    if "ingreso_base" in df.columns and "ingreso_simulado" in df.columns:
        if df["ingreso_simulado"].sum() < df["ingreso_base"].sum():
            # Calcular punto de equilibrio para palanca precio
            if "elasticidad_usada" in df.columns:
                e = df["elasticidad_usada"].iloc[0]
                if e < 0:
                    # Precio óptimo: maximiza precio*(1+p)*(1+e*p) → derivada = 0
                    # Simplificado: punto donde Δingreso = 0 → p_eq = -1/e - 1 ≈ -(1+e)/e
                    p_eq = -1 / e - 1
                    advertencia = (
                        f"\n  ⚠ El ingreso cae a pesar de la suba de precio.\n"
                        f"    Punto de equilibrio: ≤{p_eq*100:.1f}% de suba para no perder ingreso."
                    )

    # Palancas aplicadas
    palanca_names = [p.get("tipo", "?").upper() for p in palancas]
    palancas_str  = ", ".join(palanca_names)

    linea = "═" * 60
    output = f"""
{linea}
  SIMULADOR MCD — {escenario_nombre}
{linea}
  Período:             {periodo_str}
  Clasificación:       {", ".join(df["clasificacion_2"].unique()[:3])}
  Sucursales afectadas:{n_sucursales}
  Palancas aplicadas:  {palancas_str}

  Unidades base/mes:   {total_base / len(periodos):,.0f}
  Unidades simul./mes: {total_sim / len(periodos):,.0f}
  Delta unidades:      {delta_abs / len(periodos):+,.0f} ({delta_pct:+.1f}%)
{ingreso_lines}{elast_line}{advertencia}
{linea}"""

    return output.strip()
