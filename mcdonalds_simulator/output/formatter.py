"""Genera el resumen en consola que GENIA lee para responder al usuario."""

import pandas as pd


def resumen_consola(df: pd.DataFrame, escenario_nombre: str, palancas: list) -> str:
    if df.empty:
        return "Sin datos para el escenario solicitado."

    col_sim      = "unidades_simuladas" if "unidades_simuladas" in df.columns else "forecast"
    total_base   = df["forecast"].sum()
    total_sim    = df[col_sim].sum()
    delta_abs    = total_sim - total_base
    delta_pct    = delta_abs / total_base * 100 if total_base > 0 else 0
    n_sucursales = df["sucursal"].nunique()
    periodos     = sorted(df["periodo"].unique())
    n_periodos   = len(periodos)
    periodo_str  = f"{periodos[0]} → {periodos[-1]}" if n_periodos > 1 else periodos[0]
    clf2_str     = ", ".join(df["clasificacion_2"].unique()[:3])
    palanca_tipo = palancas[0].get("tipo", "?").upper() if palancas else "?"

    linea  = "═" * 65
    linea2 = "─" * 65

    lines = []
    lines.append(linea)
    lines.append(f"  SIMULADOR MCD — {escenario_nombre}")
    lines.append(linea)
    lines.append(f"  Período:              {periodo_str}")
    lines.append(f"  Categoría:            {clf2_str}")
    lines.append(f"  Sucursales afectadas: {n_sucursales}")
    lines.append(f"  Palanca:              {palanca_tipo}")
    lines.append(linea2)

    # ── Bloque de optimización ─────────────────────────────────────────────
    if "optimizacion_objetivo" in df.columns:
        objetivo      = df["optimizacion_objetivo"].iloc[0]
        cambio_optimo = float(df["optimizacion_cambio_optimo"].iloc[0])
        rango         = df["optimizacion_rango"].iloc[0]

        objetivos_label = {
            "max_ingreso":  "Maximizar ingreso total",
            "max_unidades": "Maximizar unidades vendidas",
            "breakeven":    "Máxima suba sin perder ingreso",
        }
        lines.append(f"\n  OPTIMIZACIÓN DE PRECIO")
        lines.append(f"  Objetivo:             {objetivos_label.get(objetivo, objetivo)}")
        lines.append(f"  Rango explorado:      {rango}")
        lines.append(f"  → Cambio óptimo encontrado: {cambio_optimo:+.1%}")
        lines.append("")

    # ── Resultados principales ─────────────────────────────────────────────
    lines.append(f"  RESULTADOS")
    lines.append(f"  Unidades base/mes:    {total_base / n_periodos:>12,.0f}")
    lines.append(f"  Unidades simul./mes:  {total_sim  / n_periodos:>12,.0f}")
    lines.append(f"  Delta unidades:       {delta_abs  / n_periodos:>+12,.0f}  ({delta_pct:+.1f}%)")

    # Ingresos
    if "ingreso_base" in df.columns and df["ingreso_base"].notna().any():
        ing_base = df["ingreso_base"].sum()
        ing_sim  = df["ingreso_simulado"].sum() if "ingreso_simulado" in df.columns else None
        if ing_sim is not None:
            ing_delta     = ing_sim - ing_base
            ing_delta_pct = ing_delta / ing_base * 100 if ing_base > 0 else 0
            lines.append("")
            lines.append(f"  Ingreso base/mes:     {ing_base / n_periodos:>12,.0f} Gs")
            lines.append(f"  Ingreso simul./mes:   {ing_sim  / n_periodos:>12,.0f} Gs")
            lines.append(f"  Delta ingreso:        {ing_delta / n_periodos:>+12,.0f} Gs  ({ing_delta_pct:+.1f}%)")

    lines.append(linea2)

    # ── Justificación ──────────────────────────────────────────────────────
    lines.append(f"\n  POR QUÉ ESTE RESULTADO")
    lines.append("")

    justificacion = _construir_justificacion(df, palancas, delta_pct,
                                              total_base, total_sim, n_periodos)
    for linea_just in justificacion:
        lines.append(f"  {linea_just}")

    lines.append("")
    lines.append(linea)

    return "\n".join(lines)


def _construir_justificacion(df: pd.DataFrame, palancas: list,
                              delta_pct: float, total_base: float,
                              total_sim: float, n_periodos: int) -> list[str]:
    """
    Construye el bloque de justificación narrativa según la palanca aplicada.
    """
    if not palancas:
        return ["Sin información de palancas para justificar."]

    palanca = palancas[0]
    tipo    = palanca.get("tipo", "").lower()
    lines   = []

    # ── PRECIO ────────────────────────────────────────────────────────────
    if tipo == "precio":
        modo = palanca.get("modo", "simular")

        if "elasticidad_usada" in df.columns:
            e = float(df["elasticidad_usada"].iloc[0])
            c = str(df["confianza_elasticidad"].iloc[0]) if "confianza_elasticidad" in df.columns else "?"
            n_cambios = ""

            # Explicar qué es la elasticidad en palabras simples
            if e < 0:
                direccion = "cada vez que el precio sube 1%, las ventas caen"
                magnitud  = f"{abs(e):.2f}%"
            else:
                direccion = "cada vez que el precio sube 1%, las ventas también suben"
                magnitud  = f"{abs(e):.2f}% (elasticidad positiva, inusual)"

            lines.append(f"Elasticidad histórica de esta categoría: {e:.2f} (confianza: {c})")
            lines.append(f"Esto significa que {direccion} {magnitud}.")
            lines.append("")

            _explicar_confianza(lines, c, e)

        if modo == "simular":
            cambio_pct = float(palanca.get("cambio_pct", 0))
            impacto_vol = cambio_pct * (float(df["elasticidad_usada"].iloc[0])
                                        if "elasticidad_usada" in df.columns else 0)
            lines.append(f"Se simuló un cambio de precio de {cambio_pct:+.1%}.")
            lines.append(f"Aplicando la elasticidad, el impacto estimado en volumen es {impacto_vol:+.1%}.")

            if "ingreso_base" in df.columns and "ingreso_simulado" in df.columns:
                ing_base = df["ingreso_base"].sum()
                ing_sim  = df["ingreso_simulado"].sum()
                ing_delta_pct = (ing_sim - ing_base) / ing_base * 100 if ing_base > 0 else 0
                if ing_delta_pct > 0:
                    lines.append(f"Aunque se venden menos unidades, el precio más alto")
                    lines.append(f"compensa la caída: el ingreso sube {ing_delta_pct:+.1f}%.")
                elif ing_delta_pct < 0:
                    lines.append(f"La caída en volumen supera la ganancia del precio mayor:")
                    lines.append(f"el ingreso cae {ing_delta_pct:.1f}%.")
                    e_val = float(df["elasticidad_usada"].iloc[0]) if "elasticidad_usada" in df.columns else 0
                    if e_val < 0:
                        p_eq = abs(-1 / e_val - 1) * 100
                        lines.append(f"El punto de equilibrio es una suba máxima de {p_eq:.1f}%.")

        elif modo == "optimizar":
            objetivo      = palanca.get("objetivo", "max_ingreso")
            cambio_optimo = float(df["optimizacion_cambio_optimo"].iloc[0]) if "optimizacion_cambio_optimo" in df.columns else 0
            rango_desde   = float(palanca.get("rango_desde", -0.30))
            rango_hasta   = float(palanca.get("rango_hasta",  0.30))
            pasos         = int((rango_hasta - rango_desde) / 0.01) + 1

            lines.append(f"Se evaluaron {pasos} escenarios de precio entre {rango_desde:+.0%} y {rango_hasta:+.0%},")
            lines.append(f"en pasos de 1%, para encontrar el punto óptimo.")
            lines.append("")

            if objetivo == "max_ingreso":
                lines.append(f"Objetivo: maximizar el ingreso total.")
                lines.append(f"El punto óptimo es {cambio_optimo:+.1%} porque a partir de ahí")
                lines.append(f"la caída en volumen empieza a superar la ganancia del precio mayor.")
            elif objetivo == "max_unidades":
                lines.append(f"Objetivo: maximizar las unidades vendidas.")
                lines.append(f"El punto óptimo es {cambio_optimo:+.1%} — bajar más el precio")
                lines.append(f"genera retornos decrecientes en volumen.")
            elif objetivo == "breakeven":
                lines.append(f"Objetivo: encontrar la máxima suba sin perder ingreso.")
                lines.append(f"Hasta {cambio_optimo:+.1%} de suba, el mayor precio compensa")
                lines.append(f"la caída en volumen y el ingreso se mantiene igual o mayor.")

    # ── PROMOCIÓN ─────────────────────────────────────────────────────────
    elif tipo == "promocion":
        subtipo = palanca.get("subtipo", "descuento")
        canal   = palanca.get("canal")
        clf2    = palanca.get("clasificacion_2", "")

        if subtipo in ("descuento", "2x1", "precio_fijo"):
            cambio = -0.50 if subtipo == "2x1" else float(palanca.get("cambio_pct", 0))
            if subtipo == "precio_fijo":
                lines.append(f"Se fijó un precio promocional.")
            elif subtipo == "2x1":
                lines.append(f"Un 2x1 equivale a un 50% de descuento en el precio efectivo.")
            else:
                lines.append(f"Se aplicó un descuento de {cambio:.0%} sobre el precio actual.")

            if "elasticidad_usada" in df.columns:
                e = float(df["elasticidad_usada"].iloc[0])
                c = str(df["confianza_elasticidad"].iloc[0]) if "confianza_elasticidad" in df.columns else "?"
                impacto_vol = cambio * e
                lines.append(f"Con elasticidad {e:.2f}, ese descuento genera un aumento")
                lines.append(f"estimado de {impacto_vol:+.1%} en unidades vendidas.")
                lines.append("")
                _explicar_confianza(lines, c, e)

        elif subtipo == "producto_gratis":
            uplift    = float(df["promo_uplift"].iloc[0]) if "promo_uplift" in df.columns else 0
            conf      = str(df["promo_confianza"].iloc[0]) if "promo_confianza" in df.columns else "?"
            campanias = str(df["promo_campanias"].iloc[0]) if "promo_campanias" in df.columns else ""
            lines.append(f"El uplift estimado de regalar un producto es {uplift:+.1%}.")
            if conf == "histórico":
                lines.append(f"Este número viene de promos similares registradas en el histórico.")
            else:
                lines.append(f"No hay fechas de promoción en la tabla, así que no se puede medir")
                lines.append(f"el impacto real. Se usó un supuesto conservador de +10%.")
            if campanias:
                lines.append(f"")
                lines.append(f"Campañas históricas encontradas para esta categoría:")
                for c in campanias.split(", "):
                    lines.append(f"  · {c}")

        if canal:
            n_suc = df["sucursal"].nunique()
            lines.append(f"El efecto aplica solo a las {n_suc} sucursales con canal '{canal}'.")

    # ── LANZAMIENTO ───────────────────────────────────────────────────────
    elif tipo == "lanzamiento":
        conf = str(df["lanzamiento_confianza"].iloc[0]) if "lanzamiento_confianza" in df.columns else "?"
        uplift_mes0 = float(df["lanzamiento_uplift"].max()) if "lanzamiento_uplift" in df.columns else 0
        lines.append(f"Se aplicó el patrón histórico de lanzamientos anteriores de esta categoría.")
        lines.append(f"El uplift estimado en el primer mes es {uplift_mes0:+.1%},")
        lines.append(f"decayendo gradualmente en los meses siguientes.")
        lines.append("")
        _explicar_confianza(lines, conf, None)

    # ── ESTRUCTURAL ───────────────────────────────────────────────────────
    elif tipo == "estructural":
        canal  = palanca.get("canal", "")
        efecto = float(df["estructural_efecto"].iloc[0]) if "estructural_efecto" in df.columns else 0
        conf   = str(df["estructural_confianza"].iloc[0]) if "estructural_confianza" in df.columns else "?"
        lines.append(f"Se estimó el impacto de agregar el canal '{canal}'.")
        lines.append(f"El efecto se calculó comparando las ventas históricas de sucursales")
        lines.append(f"que ya tienen '{canal}' contra las que no lo tienen.")
        lines.append(f"La diferencia promedio observada es {efecto:+.1%}.")
        lines.append("")
        _explicar_confianza(lines, conf, None)

    # ── COMPETENCIA ───────────────────────────────────────────────────────
    elif tipo == "competencia":
        dist   = float(palanca.get("distancia_km", 0))
        efecto = float(df["competencia_efecto"].iloc[0]) if "competencia_efecto" in df.columns else 0
        conf   = str(df["competencia_confianza"].iloc[0]) if "competencia_confianza" in df.columns else "?"
        lines.append(f"Se simuló la apertura de un competidor a {dist} km.")
        lines.append(f"A esa distancia, el impacto estimado en ventas es {efecto:+.1%}.")
        lines.append(f"Este número se basa en el comportamiento histórico de sucursales")
        lines.append(f"que ya tienen competidores a distancias similares.")
        lines.append("")
        _explicar_confianza(lines, conf, None)

    # ── CLIMA ─────────────────────────────────────────────────────────────
    elif tipo == "clima":
        var = float(palanca.get("variacion_pct", 0))
        tipo_clima = "más frío/lluvioso" if var < 0 else "más caluroso"
        lines.append(f"Se simuló un clima {tipo_clima} de {abs(var):.0%} respecto al promedio histórico.")
        lines.append(f"Cada categoría tiene una sensibilidad distinta al clima:")
        lines.append(f"helados y postres caen con frío, el café sube levemente.")
        lines.append(f"Los coeficientes son supuestos basados en comportamiento estacional típico.")

    if not lines:
        lines.append("Sin justificación disponible para esta palanca.")

    return lines


def _explicar_confianza(lines: list, confianza: str, elasticidad) -> None:
    """Agrega una línea explicando qué tan confiable es el número."""
    if confianza == "alta":
        lines.append(f"Confianza ALTA: el número está respaldado por suficientes")
        lines.append(f"eventos históricos para ser estadísticamente representativo.")
    elif confianza == "media":
        lines.append(f"Confianza MEDIA: hay pocos eventos históricos para esta categoría.")
        lines.append(f"El número es orientativo — tomarlo como referencia, no como certeza.")
    elif confianza in ("baja", "supuesto"):
        lines.append(f"Confianza BAJA: no hay suficiente historial para esta categoría.")
        lines.append(f"Se usó un supuesto de industria. El resultado es indicativo.")
    elif confianza == "promedio histórico":
        lines.append(f"Se usó el promedio histórico de todos los años disponibles")
        lines.append(f"porque no hay datos específicos para el período simulado.")
