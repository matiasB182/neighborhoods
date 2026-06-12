"""
Palanca: Promoción.

Subtipos:
  - descuento       → % de descuento sobre el precio (ej: -0.30 = 30% OFF)
  - precio_fijo     → precio absoluto (ej: 15000 Gs), se convierte a % cambio
  - 2x1             → uplift medido sobre campañas 2x1 históricas similares
  - producto_gratis → uplift medido sobre campañas producto_gratis históricas similares

Canal (opcional): automac / delivery / app / restaurante
  → aplica el efecto solo a sucursales que tienen ese canal

CÁLCULO (descuento / precio_fijo):
  forecast_promo     = forecast_mensual / días_del_mes × días_de_la_promo
  impacto_volumen    = cambio_pct × elasticidad
  unidades_simuladas = forecast_promo × (1 + impacto_volumen)
  ingreso_simulado   = unidades_simuladas × (precio_base × (1 + cambio_pct))

  precio_fijo: cambio_pct = (precio_fijo - precio_promedio_histórico) / precio_promedio_histórico

CÁLCULO (2x1 / producto_gratis):
  forecast_promo     = forecast_mensual / días_del_mes × días_de_la_promo
  unidades_simuladas = forecast_promo × (1 + uplift)

  uplift CON fechas en la tabla de promos:
    uplift = (ventas_reales_durante_promo - forecast_ese_período) / forecast_ese_período
    promediado sobre todas las promos históricas similares con fechas disponibles

  uplift SIN fechas (situación actual):
    2x1:             uplift = +40% supuesto conservador
    producto_gratis: uplift = +10% supuesto conservador
    (pendiente: cargar fechas en col D/E del Excel Códigos-Promo y re-correr ETL)
"""

import logging
import calendar
from datetime import date
import pandas as pd
from core.elasticidades import get_elasticidad
from core.loader import (
    load_precio_clasificacion2, load_atributos_restaurantes,
    resolver_clasificacion_2,
)

log = logging.getLogger(__name__)

CANAL_A_COLUMNA = {
    "automac":     "tiene_automac",
    "delivery":    "tiene_delivery",
    "app":         "tiene_kiosco_digital",
    "restaurante": "tiene_mostrador",
}

UPLIFT_2X1_DEFAULT             = 0.40
UPLIFT_PRODUCTO_GRATIS_DEFAULT = 0.10


def _dias_promo(fecha_desde: str, fecha_hasta: str) -> int:
    return (date.fromisoformat(fecha_hasta) - date.fromisoformat(fecha_desde)).days + 1


def _forecast_promo(forecast_mensual: float, periodo: str, fecha_desde: str, fecha_hasta: str) -> float:
    """
    Escala el forecast mensual a los días de la promo.
    forecast_diario = forecast_mensual / días_del_mes
    forecast_promo  = forecast_diario  * días_de_la_promo
    """
    anio, mes = int(periodo[:4]), int(periodo[5:7])
    dias_mes  = calendar.monthrange(anio, mes)[1]
    dias      = _dias_promo(fecha_desde, fecha_hasta)
    return forecast_mensual * dias / dias_mes


def _sucursales_con_canal(canal: str) -> set:
    """Retorna el conjunto de api_id de sucursales que tienen el canal."""
    col = CANAL_A_COLUMNA.get(canal.lower())
    if not col:
        log.warning("Canal '%s' no reconocido. Opciones: %s", canal, list(CANAL_A_COLUMNA.keys()))
        return set()
    atributos = load_atributos_restaurantes()
    if atributos.empty:
        return set()
    return set(atributos[atributos[col] == True]["api_id"].astype(str).tolist())


def _cambio_pct_para_precio_fijo(clasificacion_2: str, precio_fijo: float,
                                  periodo_desde: str, periodo_hasta: str) -> float:
    """Calcula el % de cambio entre el precio actual y el precio fijo de la promo."""
    precios = load_precio_clasificacion2(clasificacion_2, periodo_desde, periodo_hasta)
    if precios.empty or precios["precio_promedio_ponderado"].isna().all():
        log.warning("Sin precio histórico para '%s'. Usando cambio_pct=0.", clasificacion_2)
        return 0.0
    precio_actual = precios["precio_promedio_ponderado"].mean()
    return (precio_fijo - precio_actual) / precio_actual


def _inferir_tipo_promo(campania: str) -> str:
    c = campania.lower()
    if "2x1" in c:
        return "2x1"
    if any(x in c for x in ["gratis", "regalo", "te llevás", "llevás"]):
        return "producto_gratis"
    if any(x in c for x in ["gs.", " mil", "miles"]):
        return "precio_fijo"
    if any(x in c for x in ["% off", "% de desc", "off "]):
        return "descuento_pct"
    return "otro"


def _campanias_similares(clasificacion_2: str, subtipo: str) -> list[str]:
    """
    Retorna campañas históricas del mismo tipo de promo.
    Estrategia:
      1. Mismo tipo_sheet + mismo subtipo  → ideal
      2. Cualquier tipo_sheet + mismo subtipo → fallback si no hay en la categoría
    Nunca mezcla tipos de promo distintos.
    """
    from core.db import query_df, TABLE_DIM_ARTICULO, TABLE_PROMOCIONES
    from core.loader import load_tipo_sheet

    tipo_sheet = load_tipo_sheet(clasificacion_2)

    # Paso 1: misma categoría
    if tipo_sheet:
        sql = f"""
            SELECT DISTINCT p.campania
            FROM {TABLE_PROMOCIONES} p
            JOIN {TABLE_DIM_ARTICULO} dav
                ON CAST(p.codigo AS VARCHAR) = CAST(dav.codigo AS VARCHAR)
            WHERE dav.tipo_sheet = %(tipo)s
            ORDER BY 1
        """
        try:
            df = query_df(sql, {"tipo": tipo_sheet})
            todas = df["campania"].tolist() if not df.empty else []
            filtradas = [c for c in todas if _inferir_tipo_promo(c) == subtipo]
            if filtradas:
                log.info("Campañas similares (%s, %s): %d encontradas.", subtipo, tipo_sheet, len(filtradas))
                return filtradas
        except Exception:
            pass

    # Paso 2: buscar el mismo tipo de promo en toda la tabla
    sql_all = f"""
        SELECT DISTINCT campania
        FROM {TABLE_PROMOCIONES}
        ORDER BY 1
    """
    try:
        df_all = query_df(sql_all)
        if df_all.empty:
            return []
        todas = df_all["campania"].tolist()
        filtradas = [c for c in todas if _inferir_tipo_promo(c) == subtipo]
        if filtradas:
            log.info("Campañas similares (%s, cualquier categoría): %d encontradas.", subtipo, len(filtradas))
            return filtradas
    except Exception:
        pass

    return []


def _datos_campania(campania: str) -> tuple[list[int], list[str]]:
    """
    Retorna (codigos, clf2s) para una campaña:
    - codigos: product IDs para filtrar fact_ventas directamente
    - clf2s: clasificacion_2_sheet para filtrar el forecast
    """
    from core.db import query_df, TABLE_PROMOCIONES, TABLE_DIM_ARTICULO
    sql = f"""
        SELECT DISTINCT p.codigo, dav.clasificacion_2_sheet
        FROM {TABLE_PROMOCIONES} p
        LEFT JOIN {TABLE_DIM_ARTICULO} dav
            ON CAST(p.codigo AS VARCHAR) = CAST(dav.codigo AS VARCHAR)
        WHERE p.campania = %(camp)s
    """
    df = query_df(sql, {"camp": campania})
    if df.empty:
        return [], []
    codigos = df["codigo"].dropna().astype(int).tolist()
    clf2s   = df["clasificacion_2_sheet"].dropna().unique().tolist()
    return codigos, clf2s


def _uplift_con_fechas(campanias: list[str], clasificacion_2: str,
                       tipo_sheet: str | None) -> tuple[float, str] | None:
    """
    Dado un listado de campañas similares, busca las que tienen fechas en la DB
    y calcula el uplift real: ventas reales / forecast diario - 1, medido sobre
    la categoría promovida en cada campaña (no necesariamente el target).
    Retorna (uplift_promedio, confianza) o None si no hay fechas.
    """
    from core.loader import load_fechas_campania
    from core.db import query_df, TABLE_FACT_VENTAS, TABLE_DIM_ARTICULO, TABLE_FORECAST

    fechas_df = load_fechas_campania(clasificacion_2, tipo_sheet, campanas=campanias)
    if fechas_df.empty:
        return None

    uplifts = []
    for _, row in fechas_df.iterrows():
        fd = str(row["fecha_desde"])[:10]
        fh = str(row["fecha_hasta"])[:10] if row["fecha_hasta"] else fd
        pm_desde = fd[:7]
        pm_hasta = fh[:7]
        campania = row["campania"]

        # Los codigos de la campaña identifican qué clasificaciones medir
        _, clf2s_camp = _datos_campania(campania)
        if not clf2s_camp:
            continue

        ph_clf2 = ", ".join([f"%(clf2_{i})s" for i in range(len(clf2s_camp))])
        params_clf2 = {f"clf2_{i}": v for i, v in enumerate(clf2s_camp)}

        # Ventas reales: todos los PLUs de esas clasificaciones (no solo los códigos del CSV)
        sql_ventas = f"""
            SELECT SUM(fv.cantidad) AS unidades_reales
            FROM {TABLE_FACT_VENTAS} fv
            JOIN {TABLE_DIM_ARTICULO} dav
                ON CAST(fv.producto AS VARCHAR) = CAST(dav.codigo AS VARCHAR)
            WHERE dav.clasificacion_2_sheet IN ({ph_clf2})
              AND fv.fecha BETWEEN %(fd)s AND %(fh)s
        """
        df_v = query_df(sql_ventas, {**params_clf2, "fd": fd, "fh": fh})
        unidades_reales = float(df_v["unidades_reales"].iloc[0] or 0)
        if unidades_reales == 0:
            continue

        # Forecast para esas mismas clasificaciones
        params_fc = {**params_clf2, "pm_desde": pm_desde, "pm_hasta": pm_hasta}
        sql_fc = f"""
            SELECT SUM(COALESCE(forecast, unidades)) AS forecast_total,
                   COUNT(DISTINCT periodo) AS n_periodos
            FROM {TABLE_FORECAST}
            WHERE clasificacion_2_sheet IN ({ph_clf2})
              AND periodo BETWEEN %(pm_desde)s AND %(pm_hasta)s
        """
        df_fc = query_df(sql_fc, params_fc)
        fc_total = float(df_fc["forecast_total"].iloc[0] or 0)
        n_meses  = int(df_fc["n_periodos"].iloc[0] or 1)

        if fc_total == 0:
            continue

        # Forecast diario × días de campaña
        import calendar as cal
        from datetime import date
        fd_d = date.fromisoformat(fd)
        fh_d = date.fromisoformat(fh)
        n_dias = (fh_d - fd_d).days + 1
        dias_mes = cal.monthrange(fd_d.year, fd_d.month)[1]
        fc_diario = fc_total / n_meses / dias_mes
        fc_periodo = fc_diario * n_dias

        if fc_periodo == 0:
            continue

        uplift = (unidades_reales - fc_periodo) / fc_periodo
        uplifts.append(uplift)
        log.info("Campaña '%s' (%s → %s) [%d clf2s]: uplift medido %+.1f%%",
                 campania, fd, fh, len(clf2s_camp), uplift * 100)

    if not uplifts:
        return None

    promedio  = sum(uplifts) / len(uplifts)
    confianza = "alta" if len(uplifts) >= 3 else "media" if len(uplifts) >= 1 else "baja"
    log.info("Uplift histórico promedio: %+.1f%% (%d campañas, confianza: %s)",
             promedio * 100, len(uplifts), confianza)
    return promedio, confianza


def _uplift_2x1(clasificacion_2: str,
                fecha_desde_sim: str, fecha_hasta_sim: str) -> tuple[float, str, list[str]]:
    """
    1. Si hay campañas 2x1 históricas CON fechas → uplift medido vs forecast.
    2. Sin fechas → supuesto +40%.
    Retorna (uplift, confianza, campañas).
    """
    from core.loader import load_tipo_sheet
    tipo_sheet = load_tipo_sheet(clasificacion_2)
    campanias  = _campanias_similares(clasificacion_2, "2x1")

    resultado = _uplift_con_fechas(campanias, clasificacion_2, tipo_sheet)
    if resultado:
        uplift, confianza = resultado
        return uplift, confianza, campanias

    log.warning("Sin fechas de campañas 2x1 históricas — usando supuesto +%.0f%% sobre forecast diario.",
                UPLIFT_2X1_DEFAULT * 100)
    return UPLIFT_2X1_DEFAULT, "supuesto", campanias


def _uplift_producto_gratis(clasificacion_2: str,
                             fecha_desde_sim: str, fecha_hasta_sim: str) -> tuple[float, str, list[str]]:
    """
    1. Si hay promos históricas CON fechas → uplift medido:
       (ventas_reales_promo - forecast_período) / forecast_período
    2. Sin fechas → supuesto +10% sobre el forecast_promo (forecast diario × días).
    Retorna (uplift, confianza, campañas).
    """
    from core.loader import load_tipo_sheet
    tipo_sheet = load_tipo_sheet(clasificacion_2)
    campanias  = _campanias_similares(clasificacion_2, "producto_gratis")

    resultado = _uplift_con_fechas(campanias, clasificacion_2, tipo_sheet)
    if resultado:
        uplift, confianza = resultado
        return uplift, confianza, campanias

    log.warning("Sin fechas de promo históricas — usando supuesto +%.0f%% sobre forecast diario.",
                UPLIFT_PRODUCTO_GRATIS_DEFAULT * 100)
    return UPLIFT_PRODUCTO_GRATIS_DEFAULT, "supuesto", campanias


def aplicar(df: pd.DataFrame, params: dict, periodo_desde: str, periodo_hasta: str) -> pd.DataFrame:
    """
    params:
      subtipo: descuento | 2x1 | precio_fijo | producto_gratis
      clasificacion_2: str   (texto libre, se resuelve por similitud)
      fecha_desde: str       (YYYY-MM-DD — inicio de la promo)
      fecha_hasta: str       (YYYY-MM-DD — fin de la promo)
      cambio_pct: float      (solo subtipo: descuento)
      precio: float          (solo subtipo: precio_fijo)
      producto_gratis: str   (solo subtipo: producto_gratis, descriptivo)
      canal: str             (opcional: automac / delivery / app / restaurante)
    """
    subtipo     = params.get("subtipo", "descuento").lower()
    canal       = params.get("canal")
    fecha_desde = str(params["fecha_desde"])
    fecha_hasta = str(params.get("fecha_hasta") or fecha_desde)

    # Resolver clasificacion_2 por similitud
    clf2_texto = params.get("clasificacion_2", "")
    matches = resolver_clasificacion_2(clf2_texto)
    if not matches:
        log.error("No se encontró clasificacion_2 para '%s'. Se omite la palanca.", clf2_texto)
        return df
    clasificacion_2 = matches[0]
    log.info("Promoción '%s' → clasificacion_2 resuelta: '%s'", clf2_texto, clasificacion_2)

    # Sucursales afectadas por canal
    sucursales_canal = _sucursales_con_canal(canal) if canal else None

    df = df.copy()
    col_base = "unidades_simuladas" if "unidades_simuladas" in df.columns else "forecast"
    mascara_clf2 = df["clasificacion_2"] == clasificacion_2

    if sucursales_canal is not None:
        mascara_canal = df["sucursal"].astype(str).isin(sucursales_canal)
        mascara = mascara_clf2 & mascara_canal
        log.info("Canal '%s': %d sucursales afectadas.", canal, mascara_canal.sum())
    else:
        mascara = mascara_clf2

    # ── Subtipos que usan elasticidad ──────────────────────────────────────
    if subtipo in ("descuento", "precio_fijo"):

        if subtipo == "precio_fijo":
            precio_fijo = float(params["precio"])
            cambio_pct = _cambio_pct_para_precio_fijo(
                clasificacion_2, precio_fijo, periodo_desde, periodo_hasta)
        else:
            cambio_pct = float(params["cambio_pct"])

        elasticidad, confianza = get_elasticidad(clasificacion_2)
        impacto_volumen = cambio_pct * elasticidad

        # Precio base para calcular ingresos
        precios = load_precio_clasificacion2(clasificacion_2, periodo_desde, periodo_hasta)
        if not precios.empty:
            df = df.merge(precios[["clasificacion_2", "periodo", "precio_promedio_ponderado"]],
                          on=["clasificacion_2", "periodo"], how="left")
            df.rename(columns={"precio_promedio_ponderado": "precio_base"}, inplace=True)
        else:
            df["precio_base"] = None

        # Forecast base escalado a los días de la promo
        df["forecast_promo"] = df.apply(
            lambda r: _forecast_promo(r[col_base], r["periodo"], fecha_desde, fecha_hasta), axis=1)

        df.loc[mascara, "unidades_simuladas"]  = df.loc[mascara,  "forecast_promo"] * (1 + impacto_volumen)
        df.loc[~mascara, "unidades_simuladas"] = df.loc[~mascara, "forecast_promo"]

        df["precio_simulado"] = df.get("precio_base", pd.Series(dtype=float)) * (1 + cambio_pct)
        df["ingreso_base"]     = df["forecast_promo"] * df.get("precio_base", pd.Series(dtype=float))
        df["ingreso_simulado"] = df["unidades_simuladas"] * df["precio_simulado"]

        df["promo_subtipo"]     = subtipo
        df["promo_cambio_pct"]  = cambio_pct
        df["promo_elasticidad"] = elasticidad
        df["promo_confianza"]   = confianza
        df["promo_canal"]       = canal or "todos"
        df["promo_fecha_desde"] = fecha_desde
        df["promo_fecha_hasta"] = fecha_hasta
        df["promo_dias"]        = _dias_promo(fecha_desde, fecha_hasta)

        log.info("Promo '%s' (%s): %d días, precio %+.1f%% → volumen %+.1f%% [elasticidad %.2f, %s]",
                 clasificacion_2, subtipo, _dias_promo(fecha_desde, fecha_hasta),
                 cambio_pct * 100, impacto_volumen * 100, elasticidad, confianza)

    # ── 2x1: uplift medido sobre campañas históricas ───────────────────────
    elif subtipo == "2x1":
        uplift, confianza, campanias = _uplift_2x1(clasificacion_2, fecha_desde, fecha_hasta)

        df["forecast_promo"] = df.apply(
            lambda r: _forecast_promo(r[col_base], r["periodo"], fecha_desde, fecha_hasta), axis=1)

        df.loc[mascara,  "unidades_simuladas"] = df.loc[mascara,  "forecast_promo"] * (1 + uplift)
        df.loc[~mascara, "unidades_simuladas"] = df.loc[~mascara, "forecast_promo"]

        df["promo_subtipo"]     = subtipo
        df["promo_uplift"]      = uplift
        df["promo_confianza"]   = confianza
        df["promo_canal"]       = canal or "todos"
        df["promo_campanias"]   = "|||".join(campanias) if campanias else ""
        df["promo_fecha_desde"] = fecha_desde
        df["promo_fecha_hasta"] = fecha_hasta
        df["promo_dias"]        = _dias_promo(fecha_desde, fecha_hasta)
        log.info("Promo '%s' 2x1: %d días, uplift %.1f%% [%s] — %d campañas similares",
                 clasificacion_2, _dias_promo(fecha_desde, fecha_hasta),
                 uplift * 100, confianza, len(campanias))

    # ── Producto gratis: uplift en unidades, precio sin cambio ─────────────
    elif subtipo == "producto_gratis":
        uplift, confianza, campanias = _uplift_producto_gratis(clasificacion_2, fecha_desde, fecha_hasta)

        df["forecast_promo"] = df.apply(
            lambda r: _forecast_promo(r[col_base], r["periodo"], fecha_desde, fecha_hasta), axis=1)

        df.loc[mascara, "unidades_simuladas"]  = df.loc[mascara,  "forecast_promo"] * (1 + uplift)
        df.loc[~mascara, "unidades_simuladas"] = df.loc[~mascara, "forecast_promo"]

        df["promo_subtipo"]     = subtipo
        df["promo_uplift"]      = uplift
        df["promo_confianza"]   = confianza
        df["promo_canal"]       = canal or "todos"
        df["promo_campanias"]   = "|||".join(campanias) if campanias else ""
        df["promo_fecha_desde"] = fecha_desde
        df["promo_fecha_hasta"] = fecha_hasta
        df["promo_dias"]        = _dias_promo(fecha_desde, fecha_hasta)
        desc = params.get("producto_gratis", "")
        log.info("Promo '%s' producto gratis (%s): %d días, uplift %.1f%% [%s]",
                 clasificacion_2, desc, _dias_promo(fecha_desde, fecha_hasta),
                 uplift * 100, confianza)

    else:
        log.error("Subtipo de promoción '%s' no reconocido.", subtipo)

    return df
