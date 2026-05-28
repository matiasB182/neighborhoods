"""
Sistema de Recomendaciones Comerciales
=======================================
Genera tres tipos de recomendaciones para el equipo comercial:

  Modelo 1 — Upsell por Vertical:
    Familias de productos que el cliente NO compra pero que aplican
    a su sub-sector (según el Excel de mapeo vertical-familia).

  Modelo 2 — Complementarios:
    Si el cliente compra un equipo, se le recomiendan los accesorios
    e insumos del mismo grupo que todavía no compra.

  Modelo 3 — Recencia de Insumos:
    Insumos que el cliente compraba con regularidad y dejó de comprar,
    detectado cuando la recencia supera su frecuencia habitual.

Configuración:
  - Parámetros del sistema → config.yaml  (modificar acá, no en el código)
  - Credenciales y hosts  → .env          (nunca subir al repositorio)

Uso:
  python generar_recomendaciones.py

  Para cambiar el destino de los resultados, modificar en recomendaciones.yaml:
    ejecucion.destino: ambos      → guarda en Redshift Y crea leads en Odoo
    ejecucion.destino: redshift   → solo guarda en Redshift
    ejecucion.destino: odoo       → solo crea leads en Odoo
"""

import os
import yaml
import numpy as np
import pandas as pd
import xmlrpc.client
from datetime import datetime
from dotenv import load_dotenv
from scipy.sparse import csr_matrix
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import MinMaxScaler

from utils_varios import run_redshift_query
from utils_redshift import cargar_y_mantener_rs, cargar_tabla_rs


# ============================================================
# CARGA DE CONFIGURACIÓN
# ============================================================

load_dotenv()


def cargar_config(ruta="recomendaciones.yaml"):
    """Lee el archivo config.yaml y devuelve todos los parámetros."""
    with open(ruta, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_redshift_params():
    """
    Lee los datos de conexión a Redshift desde el archivo .env.
    Los nombres de variables deben coincidir con los que usa utils_redshift.py:
      RS_HOST, RS_PORT, RS_DATABASE, RS_USERNAME, RS_PASSWORD

    Si falta alguno, lanza un error claro indicando cuál falta.
    """
    params = {
        "host":     os.getenv("RS_HOST"),
        "port":     int(os.getenv("RS_PORT", 5439)),
        "database": os.getenv("RS_DATABASE"),
        "user":     os.getenv("RS_USERNAME"),
        "password": os.getenv("RS_PASSWORD"),
    }
    faltantes = [k for k, v in params.items() if not v]
    if faltantes:
        raise ValueError(f"Faltan variables en .env: {faltantes}")
    return params


def conectar_odoo():
    """
    Conecta a Odoo usando las credenciales del .env.
    Devuelve (uid, models, db, password) para hacer llamadas a la API.
    """
    url      = os.getenv("API_URL", "").rstrip("/").removesuffix("/web")
    db       = os.getenv("API_DB")
    user     = os.getenv("API_USERNAME")
    password = os.getenv("API_PASSWORD")

    if not all([url, db, user, password]):
        raise ValueError("Faltan variables en .env: API_URL, API_DB, API_USERNAME, API_PASSWORD")

    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
    uid    = common.authenticate(db, user, password, {})

    if not uid:
        raise ValueError("Autenticación en Odoo fallida. Verificá las credenciales en .env")

    print(f"    Conexión Odoo OK — UID: {uid}")
    return uid, models, db, password


# ============================================================
# PASO 1 — EXTRACCIÓN DE DATOS
# ============================================================

def extraer_ventas(rs_params, dimension_col, fecha_inicio, fecha_corte):
    """
    Trae todas las ventas del período desde Redshift.

    Incluye el tipo y grupo del producto (necesarios para los modelos
    de complementarios y recencia), además de la columna de dimensión
    configurada (por defecto: familia).
    """
    query = f"""
        SELECT
            v.cliente_id,
            v.factura_nro,
            v.fecha_venta,
            (v.monto_venta - v.costo_venta)        AS margen,
            v.monto_venta,
            v.cantidad_venta,
            UPPER(TRIM(p.tipo))                    AS tipo_producto,
            UPPER(TRIM(p.grupo))                   AS grupo_producto,
            COALESCE(
                UPPER(TRIM(p.{dimension_col})),
                'SIN_{dimension_col.upper()}'
            )                                      AS {dimension_col}
        FROM processed.ventas v
        JOIN processed.productos p ON v.producto_id = p.producto_id
        WHERE v.fecha_venta   >= '{fecha_inicio}'
          AND v.fecha_venta    < '{fecha_corte}'
          AND v.cliente_id    IS NOT NULL
          AND p.{dimension_col} IS NOT NULL
          AND TRIM(p.{dimension_col}) != ''
          AND v.tipo_transaccion = 'V'
          AND v.monto_venta   > 0
    """
    df = run_redshift_query(**rs_params, query=query)

    # Descartar filas con dimensión sin datos válidos
    valores_invalidos = {f"SIN_{dimension_col.upper()}", "SIN DATOS", "FALSE"}
    df = df[~df[dimension_col].isin(valores_invalidos)]

    print(f"    Ventas: {len(df):,} filas | {df['cliente_id'].nunique():,} clientes únicos")
    return df


def extraer_clientes(rs_params):
    """
    Trae los datos básicos de cada cliente: nombre, RUC y vertical (sub-sector).
    El vertical es clave para determinar qué familias le aplican.
    """
    query = """
        SELECT
            cliente_id,
            razon_social,
            ruc,
            COALESCE(UPPER(TRIM(vertical)), '') AS vertical
        FROM processed.clientes
    """
    df = run_redshift_query(**rs_params, query=query)
    print(f"    Clientes: {len(df):,} | Verticales distintas: {df['vertical'].nunique()}")
    return df


def extraer_segmentacion(rs_params):
    """
    Trae el segmento comercial de cada cliente
    (ej: Premium, Recurrente, Ocasional, etc.).
    """
    query = """
        SELECT cliente_id, nombre_segmento
        FROM profiling.segmentacion_clientes
    """
    df = run_redshift_query(**rs_params, query=query)
    print(f"    Segmentación: {len(df):,} registros")
    return df


def cargar_mapeo_vertical_familia(ruta_excel):
    """
    Lee el Excel que define qué familias aplican a cada vertical (sub-sector).

    El Excel tiene celdas combinadas en la columna de vertical, por eso
    se usa forward-fill para completar los valores vacíos.

    Devuelve tres estructuras:
      - familias_permitidas: set de tuplas (vertical, familia) válidas
      - verticales_sin_restriccion: verticales sin familias asignadas
        (pueden recibir cualquier familia)
      - verticales_con_mapeo: verticales que sí tienen restricción definida
    """
    df = pd.read_excel(ruta_excel, engine="openpyxl")
    df.columns = ["vertical", "familia"]

    df["vertical"] = df["vertical"].ffill().str.strip().str.upper()
    df["familia"]  = df["familia"].str.strip().str.upper()

    verticales_sin_restriccion = set(df[df["familia"].isna()]["vertical"].unique())

    df = df.dropna(subset=["familia"])
    familias_permitidas   = set(zip(df["vertical"], df["familia"]))
    verticales_con_mapeo  = set(df["vertical"].unique())

    print(f"    Mapeo cargado: {len(familias_permitidas)} pares (vertical, familia)")
    return familias_permitidas, verticales_sin_restriccion, verticales_con_mapeo


# ============================================================
# PASO 2 — MÉTRICAS POR CLIENTE-DIMENSIÓN
# ============================================================

def calcular_metricas(df_ventas, dimension_col, fecha_corte):
    """
    Calcula indicadores de comportamiento de compra para cada par
    cliente-dimensión (ej: cliente X en familia NETWORKING).

    Métricas generadas:
      recencia                      → días desde la última compra
      frecuencia_compra             → promedio de días entre compras
      margen                        → margen total del período
      cantidad_total                → unidades totales compradas
      margen_promedio               → margen promedio por día con compra
      cantidad_promedio             → unidades promedio por día con compra
      cantidad_facturas_en_categoria→ facturas distintas en esa familia
      promedio_tickets_mes          → facturas por mes en promedio
    """
    df_ventas = df_ventas.copy()
    df_ventas["fecha_venta"]    = pd.to_datetime(df_ventas["fecha_venta"])
    df_ventas["monto_venta"]    = pd.to_numeric(df_ventas["monto_venta"],    errors="coerce").fillna(0)
    df_ventas["margen"]         = pd.to_numeric(df_ventas["margen"],         errors="coerce").fillna(0)
    df_ventas["cantidad_venta"] = pd.to_numeric(df_ventas["cantidad_venta"], errors="coerce").fillna(0)

    fecha_corte_dt = pd.to_datetime(fecha_corte)

    # --- Métricas base ---
    base = df_ventas.groupby(["cliente_id", dimension_col]).agg(
        ultima_compra                 = ("fecha_venta",   "max"),
        primera_compra                = ("fecha_venta",   "min"),
        nro_ventas                    = ("factura_nro",   "nunique"),
        margen                        = ("margen",        "sum"),
        cantidad_total                = ("cantidad_venta","sum"),
        cantidad_facturas_en_categoria= ("factura_nro",   "nunique"),
    ).reset_index()

    # --- Frecuencia: promedio de días entre compras ---
    def avg_days_between(grp):
        fechas = grp["fecha_venta"].sort_values().drop_duplicates()
        if len(fechas) < 2:
            return np.nan
        return fechas.diff().dropna().dt.days.mean()

    freq = (
        df_ventas.groupby(["cliente_id", dimension_col])
        .apply(avg_days_between, include_groups=False)
        .rename("frecuencia_compra")
        .reset_index()
    )

    # --- Margen promedio por día de compra ---
    margen_dia = (
        df_ventas.groupby(["cliente_id", dimension_col, "fecha_venta"])["margen"]
        .sum().reset_index()
        .groupby(["cliente_id", dimension_col])["margen"]
        .mean().rename("margen_promedio").reset_index()
    )

    # --- Cantidad promedio por día de compra ---
    cant_dia = (
        df_ventas.groupby(["cliente_id", dimension_col, "fecha_venta"])["cantidad_venta"]
        .sum().reset_index()
        .groupby(["cliente_id", dimension_col])["cantidad_venta"]
        .mean().rename("cantidad_promedio").reset_index()
    )

    # --- Tickets promedio por mes ---
    meses = base[["cliente_id", dimension_col, "primera_compra", "cantidad_facturas_en_categoria"]].copy()
    meses["meses_vida"] = (
        (fecha_corte_dt.year  - meses["primera_compra"].dt.year)  * 12
        + (fecha_corte_dt.month - meses["primera_compra"].dt.month)
        - (meses["primera_compra"].dt.day > fecha_corte_dt.day).astype(int)
    ).clip(lower=1)
    meses["promedio_tickets_mes"] = meses["cantidad_facturas_en_categoria"] / (meses["meses_vida"] + 1)

    # --- Ensamblar todas las métricas ---
    df = base.copy()
    df["recencia"] = (fecha_corte_dt - df["ultima_compra"]).dt.days
    df = df.merge(freq,   on=["cliente_id", dimension_col], how="left")
    df = df.merge(margen_dia, on=["cliente_id", dimension_col], how="left")
    df = df.merge(cant_dia,   on=["cliente_id", dimension_col], how="left")
    df = df.merge(
        meses[["cliente_id", dimension_col, "promedio_tickets_mes"]],
        on=["cliente_id", dimension_col], how="left"
    )

    # Fallback: si solo hay una compra, usar días desde primera compra como frecuencia
    df["frecuencia_compra"]    = df["frecuencia_compra"].fillna(
        (fecha_corte_dt - df["primera_compra"]).dt.days
    )
    df["margen_promedio"]      = df["margen_promedio"].fillna(0)
    df["cantidad_promedio"]    = df["cantidad_promedio"].fillna(0)
    df["promedio_tickets_mes"] = df["promedio_tickets_mes"].fillna(0)

    print(f"    Métricas: {len(df):,} pares cliente-{dimension_col}")
    return df


# ============================================================
# PASO 3 — RATING POR CLIENTE-DIMENSIÓN
# ============================================================

def calcular_rating(df_metrics, pesos, rating_min, rating_max, columnas_invertir):
    """
    Normaliza cada métrica al rango [0, 1] y calcula un rating ponderado.

    Las columnas en 'columnas_invertir' se invierten antes de ponderar,
    porque para esas métricas un valor MENOR indica mejor comportamiento.
    (Ej: recencia baja = compró hace poco = mejor cliente)

    El rating final se escala al rango definido en config.yaml (ej: 1 a 5).
    """
    total_pesos = sum(pesos.values())
    if abs(total_pesos - 1.0) > 1e-6:
        raise ValueError(f"Los pesos en config.yaml deben sumar 1.0 (suman {total_pesos:.4f})")

    scaler = MinMaxScaler()
    for col in pesos:
        values     = df_metrics[col].values.reshape(-1, 1)
        normalized = scaler.fit_transform(values).flatten()
        df_metrics[f"{col}_norm"] = (1 - normalized) if col in columnas_invertir else normalized

    norm_cols = {f"{col}_norm": w for col, w in pesos.items()}
    df_metrics["rating"]        = sum(df_metrics[c] * w for c, w in norm_cols.items())
    df_metrics["rating_scaled"] = rating_min + df_metrics["rating"] * (rating_max - rating_min)

    print(f"    Rating — Min: {df_metrics['rating_scaled'].min():.2f} | "
          f"Max: {df_metrics['rating_scaled'].max():.2f} | "
          f"Media: {df_metrics['rating_scaled'].mean():.2f}")
    return df_metrics


# ============================================================
# AUXILIAR — FILTRO VERTICAL
# ============================================================

def es_familia_permitida(vertical, familia, familias_permitidas,
                         verticales_sin_restriccion, verticales_con_mapeo):
    """
    Determina si una familia aplica para el vertical del cliente.

    Reglas:
      - Vertical vacío o sin datos → todas las familias aplican
      - Vertical en 'sin restricción' → todas las familias aplican
      - Vertical no está en el mapeo → todas las familias aplican
      - Vertical sí está en el mapeo → solo las familias del Excel aplican
    """
    if not vertical or pd.isna(vertical) or vertical in ("", "FALSE"):
        return True
    if vertical in verticales_sin_restriccion:
        return True
    if vertical not in verticales_con_mapeo:
        return True
    return (vertical, familia) in familias_permitidas


# ============================================================
# MODELO 1 — UPSELL POR VERTICAL
# ============================================================

def generar_upsell(df_metrics, df_ventas, df_clientes, df_segmentacion,
                   dimension_col, cfg_upsell, familias_permitidas,
                   verticales_sin_restriccion, verticales_con_mapeo,
                   rating_min, rating_max, map_family_id_fn):
    """
    Modelo 1 — Upsell por Vertical.

    Para cada cliente:
      1. Obtiene las familias permitidas según su vertical (del Excel).
      2. Resta las familias que ya compra → estas son las candidatas.
      3. Usa similitud coseno con clientes similares para rankear las candidatas.
         (Cuánto compran clientes similares esa familia = qué tan probable es que
          este cliente también la necesite)
      4. Toma el top N y marca como enviado_cliente la mejor si supera el score mínimo.

    El filtro vertical actúa desde el inicio, no como post-filtro,
    evitando así recomendaciones fuera del sector del cliente.
    """
    n_recs        = cfg_upsell["top_recomendaciones"]
    n_similar     = cfg_upsell["clientes_similares"]
    min_sim       = cfg_upsell["similitud_minima"]
    score_min     = cfg_upsell["score_minimo_envio"]

    # Matriz cliente × familia (rating como valor, 0 si no compra)
    matrix = df_metrics.pivot_table(
        index="cliente_id", columns=dimension_col,
        values="rating_scaled", fill_value=0
    )
    sim_matrix = cosine_similarity(csr_matrix(matrix.values))
    np.fill_diagonal(sim_matrix, 0)

    clientes    = matrix.index.tolist()
    dimensiones = matrix.columns.tolist()

    vertical_por_cliente = df_clientes.set_index("cliente_id")["vertical"].to_dict()
    dims_por_cliente     = {
        c: set(matrix.loc[c][matrix.loc[c] > 0].index) for c in clientes
    }

    all_recs = []
    for idx, cliente in enumerate(clientes):
        vertical      = vertical_por_cliente.get(cliente, "")
        dims_compradas = dims_por_cliente[cliente]

        # Candidatas = permitidas por vertical y que el cliente aún no compra
        candidatas = [
            d for d in dimensiones
            if d not in dims_compradas
            and es_familia_permitida(
                vertical, d, familias_permitidas,
                verticales_sin_restriccion, verticales_con_mapeo
            )
        ]
        if not candidatas:
            continue

        # Clientes similares para calcular el score de cada candidata
        sims       = sim_matrix[idx]
        top_similar = sorted(
            [(i, sims[i]) for i in np.where(sims >= min_sim)[0]],
            key=lambda x: x[1], reverse=True
        )[:n_similar]

        for dim in candidatas:
            weighted  = sum(s * matrix.iloc[i][dim] for i, s in top_similar if matrix.iloc[i][dim] > 0)
            total_sim = sum(s for i, s in top_similar if matrix.iloc[i][dim] > 0)

            if total_sim > 0:
                all_recs.append({
                    "cliente_id":  cliente,
                    dimension_col: dim,
                    "score":       weighted / total_sim,
                })

    df = pd.DataFrame(all_recs)
    if df.empty:
        print("    Upsell — Sin recomendaciones generadas")
        return df

    df = df.sort_values(["cliente_id", "score"], ascending=[True, False])
    df["ranking"] = df.groupby("cliente_id").cumcount() + 1
    df = df[df["ranking"] <= n_recs].reset_index(drop=True)

    # Score en escala 0-100 (tope 80 para dejar margen al score de certeza)
    df["score_scaled"] = ((df["score"] - rating_min) / (rating_max - rating_min) * 100).clip(upper=80)

    # Ranking y flag de envío
    df["ranking_filtrado"] = df.groupby("cliente_id").cumcount() + 1
    df["enviado_cliente"]  = (df["ranking_filtrado"] == 1) & (df["score_scaled"] >= score_min)
    df["filtrado_vertical"] = True   # Todas ya pasaron el filtro en origen

    # Enriquecer con datos del cliente
    df = (df
        .merge(df_clientes[["cliente_id", "razon_social", "ruc", "vertical"]], on="cliente_id", how="left")
        .merge(df_segmentacion[["cliente_id", "nombre_segmento"]],             on="cliente_id", how="left")
    )
    df["family_id"]          = df[dimension_col].apply(map_family_id_fn)
    df["fecha_actualizacion"] = pd.Timestamp.now()
    df = df.rename(columns={"vertical": "sub_sector"})

    df = df[[
        "cliente_id", "razon_social", "ruc", "sub_sector",
        "family_id", dimension_col,
        "score", "score_scaled", "ranking", "ranking_filtrado",
        "filtrado_vertical", "enviado_cliente",
        "nombre_segmento", "fecha_actualizacion",
    ]]

    print(f"    Upsell — {len(df):,} recomendaciones | Enviadas al CRM: {df['enviado_cliente'].sum():,}")
    return df


# ============================================================
# MODELO 2 — COMPLEMENTARIOS (EQUIPO → INSUMOS/ACCESORIOS)
# ============================================================

def generar_complementarios(df_ventas, df_clientes, df_segmentacion,
                             dimension_col, cfg_comp, map_family_id_fn):
    """
    Modelo 2 — Productos Complementarios.

    Para cada cliente que compra un EQUIPO:
      1. Identifica el grupo del equipo (ej: "CODIFICACIÓN TTO").
      2. Busca qué tipos complementarios (ACCESORIO, INSUMO, etc.) existen en ese grupo.
      3. Si el cliente NO compra esos tipos en ese grupo → recomendación por grupo.

    La recomendación es a nivel GRUPO porque el vendedor necesita saber exactamente
    qué complementarios ofrecer, no solo la familia genérica.

    Ejemplo:
      Cliente compra EQUIPO en grupo "CODIFICACIÓN TTO"
      → Existen INSUMO y ACCESORIO en ese grupo
      → El cliente no compra INSUMO en ese grupo
      → Lead: "Complementarios - CLIENTE - CODIFICACIÓN TTO"
         Descripción: "Grupo: CODIFICACIÓN TTO | Tipos a ofrecer: INSUMO"
    """
    tipos_equipo = set(t.upper() for t in cfg_comp["tipos_equipo"])
    tipos_comp   = set(t.upper() for t in cfg_comp["tipos_complementario"])

    df = df_ventas.copy()

    # Grupos donde cada cliente compra equipos
    equipos_cliente = (
        df[df["tipo_producto"].isin(tipos_equipo)]
        .groupby("cliente_id")["grupo_producto"]
        .apply(set)
        .to_dict()
    )

    # Para cada grupo: qué tipos complementarios existen en el catálogo
    tipos_comp_por_grupo = (
        df[df["tipo_producto"].isin(tipos_comp)]
        .groupby("grupo_producto")["tipo_producto"]
        .apply(set)
        .to_dict()
    )

    # Para cada grupo: su familia (para el family_id de Odoo)
    familia_por_grupo = (
        df.groupby("grupo_producto")[dimension_col]
        .first()
        .to_dict()
    )

    # Tipos que cada cliente compra por grupo (para detectar qué le falta)
    grupos_tipos_cliente = (
        df.groupby(["cliente_id", "grupo_producto"])["tipo_producto"]
        .apply(set)
        .to_dict()
    )

    all_recs = []
    for cliente, grupos_equipo in equipos_cliente.items():
        for grupo in grupos_equipo:
            tipos_comp_en_grupo = tipos_comp_por_grupo.get(grupo, set())
            if not tipos_comp_en_grupo:
                continue

            # Qué tipos complementarios NO compra el cliente en este grupo
            tipos_cliente_en_grupo = grupos_tipos_cliente.get((cliente, grupo), set())
            tipos_faltantes = tipos_comp_en_grupo - tipos_cliente_en_grupo

            if tipos_faltantes:
                all_recs.append({
                    "cliente_id":        cliente,
                    "grupo_origen":      grupo,
                    dimension_col:       familia_por_grupo.get(grupo, ""),  # para family_id
                    "tipos_disponibles": ", ".join(sorted(tipos_faltantes)),
                })

    if not all_recs:
        print("    Complementarios — Sin recomendaciones generadas")
        return pd.DataFrame()

    df_comp = pd.DataFrame(all_recs)
    df_comp["ranking"] = df_comp.groupby("cliente_id").cumcount() + 1

    # Enriquecer con datos del cliente
    df_comp = (df_comp
        .merge(df_clientes[["cliente_id", "razon_social", "ruc", "vertical"]], on="cliente_id", how="left")
        .merge(df_segmentacion[["cliente_id", "nombre_segmento"]],             on="cliente_id", how="left")
    )
    df_comp["family_id"]           = df_comp[dimension_col].apply(map_family_id_fn)
    df_comp["enviado_cliente"]     = True   # cada grupo es una recomendación específica y accionable
    df_comp["fecha_actualizacion"] = pd.Timestamp.now()
    df_comp = df_comp.rename(columns={"vertical": "sub_sector"})

    df_comp = df_comp[[
        "cliente_id", "razon_social", "ruc", "sub_sector",
        "family_id", dimension_col, "grupo_origen", "tipos_disponibles",
        "ranking", "enviado_cliente",
        "nombre_segmento", "fecha_actualizacion",
    ]]

    print(f"    Complementarios — {len(df_comp):,} recomendaciones | Grupos únicos: {df_comp['grupo_origen'].nunique()}")
    return df_comp


# ============================================================
# MODELO 3 — RECENCIA DE INSUMOS
# ============================================================

def generar_recencia(df_metrics, df_ventas, df_clientes, df_segmentacion,
                     dimension_col, cfg_rec, map_family_id_fn):
    """
    Modelo 3 — Recencia de Insumos.

    Detecta clientes que compraban insumos con regularidad y dejaron de hacerlo.

    Lógica:
      1. Filtra solo pares cliente-familia donde el producto es de tipo INSUMO.
      2. Compara la recencia (días sin comprar) con la frecuencia habitual del cliente.
      3. Si la recencia supera la frecuencia → el cliente está fuera de su patrón.
      4. Genera un score de prioridad considerando:
           - Cuántos días excedió su patrón (más días = más urgente)
           - Cuántas compras previas tenía (más historial = más confiable)
           - Su rating general en esa familia

    Ejemplo:
      Cliente compra ribbons cada 45 días → lleva 120 días sin comprar
      → Recencia (120) > Frecuencia (45) → Oportunidad de recencia generada
    """
    fallback_dias = cfg_rec["dias_fallback"]
    min_ventas    = cfg_rec["min_ventas_envio"]
    tipos_insumo  = set(t.upper() for t in cfg_rec["tipos_producto"])

    # Solo pares cliente-familia donde el cliente compró insumos
    pares_insumo = (
        df_ventas[df_ventas["tipo_producto"].isin(tipos_insumo)]
        [["cliente_id", dimension_col]]
        .drop_duplicates()
    )

    df = df_metrics.merge(pares_insumo, on=["cliente_id", dimension_col], how="inner")

    if df.empty:
        print("    Recencia — Sin datos de insumos para analizar")
        return pd.DataFrame()

    # Umbral: frecuencia habitual del cliente, o fallback si no hay dato
    df["umbral"] = df["frecuencia_compra"].where(df["frecuencia_compra"] > 0, fallback_dias)

    # Solo donde la recencia ya superó el umbral (patrón roto)
    df = df[df["recencia"] > df["umbral"]].copy()
    df["dias_excedido"] = df["recencia"] - df["umbral"]

    if df.empty:
        print("    Recencia — Ningún cliente superó su umbral de frecuencia")
        return pd.DataFrame()

    # Score de prioridad (0 a 1)
    r_min, r_max   = df["rating_scaled"].min(), df["rating_scaled"].max()
    max_exc, max_nro = df["dias_excedido"].max(), df["nro_ventas"].max()

    df["score_recencia"] = (
        0.40 * (df["dias_excedido"] / max_exc  if max_exc  > 0 else 0)
        + 0.40 * (df["nro_ventas"]    / max_nro  if max_nro  > 0 else 0)
        + 0.20 * ((df["rating_scaled"] - r_min) / (r_max - r_min) if r_max > r_min else 0)
    ).round(4)

    df = df.sort_values(["cliente_id", "score_recencia"], ascending=[True, False])
    df["ranking"] = df.groupby("cliente_id").cumcount() + 1

    # Enriquecer con datos del cliente
    df = (df
        .merge(df_clientes[["cliente_id", "razon_social", "ruc", "vertical"]], on="cliente_id", how="left")
        .merge(df_segmentacion[["cliente_id", "nombre_segmento"]],             on="cliente_id", how="left")
    )
    df["family_id"]           = df[dimension_col].apply(map_family_id_fn)
    df["enviado_cliente"]     = (df["ranking"] == 1) & (df["nro_ventas"] > min_ventas)
    df["fecha_actualizacion"] = pd.Timestamp.now()
    df = df.rename(columns={"vertical": "sub_sector"})

    df = df[[
        "cliente_id", "razon_social", "ruc", "sub_sector",
        "family_id", dimension_col,
        "recencia", "frecuencia_compra", "nro_ventas",
        "score_recencia", "ranking",
        "enviado_cliente",
        "nombre_segmento", "fecha_actualizacion",
    ]]

    print(f"    Recencia — {len(df):,} oportunidades | Enviadas al CRM: {df['enviado_cliente'].sum():,}")
    return df


# ============================================================
# PASO 7 — CREACIÓN DE LEADS EN ODOO CRM
# ============================================================

def crear_leads_odoo(df_enviar, dimension_col, uid, models, odoo_db, odoo_pass,
                     campaign_id, tipo_lead, timestamp):
    """
    Crea oportunidades en el CRM de Odoo para los registros con enviado_cliente=True.

    Parámetros:
      tipo_lead   → "upsell", "recencia" o "complementarios"
      campaign_id → ID de la campaña en Odoo (definido en config.yaml → campanas_crm)
      timestamp   → Marca de tiempo para el nombre del lead (evita duplicados)
    """
    if df_enviar.empty:
        print(f"    {tipo_lead.capitalize()} — Sin leads para crear")
        return [], []

    leads_ok = []
    errores  = []

    for _, row in df_enviar.iterrows():
        fam_id = row.get("family_id")
        if pd.isna(fam_id) or fam_id is None:
            errores.append({"cliente_id": row["cliente_id"], "error": "family_id no encontrado en Odoo"})
            continue

        if tipo_lead == "complementarios":
            nombre = f"{tipo_lead.capitalize()} - {row.get('razon_social', '')} - {row.get('grupo_origen', '')} - {timestamp}"
        else:
            nombre = f"{tipo_lead.capitalize()} - {row.get('razon_social', '')} - {row[dimension_col]} - {timestamp}"

        # Descripción y campos específicos según tipo de lead
        if tipo_lead == "upsell":
            score_pct = float(row.get("score_scaled", 0))
            descripcion = f"Tipo: upsell | Score: {row.get('score', 0):.2f} | Probabilidad: {score_pct:.1f}%"
            campos_extra = {"probability": round(score_pct, 1)}
        elif tipo_lead == "recencia":
            dias = int(row.get("recencia", 0))
            freq = row.get("frecuencia_compra", 0)
            descripcion = f"Tipo: recencia | Días sin compra: {dias} | Frecuencia habitual: {freq:.0f} días"
            campos_extra = {}
        else:  # complementarios
            grupo  = row.get("grupo_origen", "")
            tipos  = row.get("tipos_disponibles", "")
            descripcion = f"Tipo: complementario | Grupo: {grupo} | Tipos a ofrecer: {tipos}"
            campos_extra = {}

        lead_vals = {
            "name":             nombre,
            "partner_id":       int(row["cliente_id"]),
            "type":             "opportunity",
            "campaign_id":      campaign_id,
            "crm_leads_family": [(0, 0, {"family_id": int(fam_id), "description": descripcion})],
            **campos_extra,
        }

        try:
            lead_id = models.execute_kw(odoo_db, uid, odoo_pass, "crm.lead", "create", [lead_vals])
            leads_ok.append({
                "lead_id":   lead_id,
                "cliente_id": row["cliente_id"],
                "familia":    row[dimension_col],
            })
        except Exception as e:
            errores.append({
                "cliente_id":  row["cliente_id"],
                "razon_social": row.get("razon_social", ""),
                "error":        str(e),
            })

    print(f"    {tipo_lead.capitalize()} — Leads creados: {len(leads_ok):,} | Errores: {len(errores):,}")
    if errores:
        for e in errores[:5]:
            print(f"      ERROR: {e}")

    return leads_ok, errores


# ============================================================
# MAIN — ORQUESTADOR PRINCIPAL
# ============================================================

def main():
    cfg = cargar_config("recomendaciones.yaml")

    destino = cfg["ejecucion"]["destino"]
    if destino not in ("redshift", "odoo", "ambos"):
        raise ValueError(f"Valor inválido en config.yaml → ejecucion.destino: '{destino}'. Usar: redshift | odoo | ambos")

    escribir_redshift = destino in ("redshift", "ambos")
    crear_leads       = destino in ("odoo", "ambos")

    print("=" * 60)
    print("  SISTEMA DE RECOMENDACIONES COMERCIALES")
    print(f"  Destino: {destino.upper()}")
    print("=" * 60)

    rs        = get_redshift_params()
    dim_col   = cfg["analisis"]["dimension"]
    schemas   = cfg["tablas_salida"]
    campanas  = cfg["campanas_crm"]
    cfg_rating = cfg["modelo_rating"]

    # Período de análisis: desde N años atrás hasta el 1° del mes actual
    fecha_corte  = datetime.today().replace(day=1)
    fecha_inicio = (fecha_corte - pd.DateOffset(years=cfg["analisis"]["periodo_anios"])).strftime("%Y-%m-%d")
    fecha_corte_str = fecha_corte.strftime("%Y-%m-%d")
    timestamp    = fecha_corte.strftime("%Y%m%d%H%M")

    print(f"\n  Período:   {fecha_inicio} → {fecha_corte_str}")
    print(f"  Dimensión: {dim_col}\n")

    # ---------------------------------------------------------
    # PASO 1 — Extracción de datos
    # --------------------------------------------------------
    print("[ PASO 1 ] Extrayendo datos de Redshift...")
    df_ventas      = extraer_ventas(rs, dim_col, fecha_inicio, fecha_corte_str)
    df_clientes    = extraer_clientes(rs)
    df_segmentacion = extraer_segmentacion(rs)
    familias_permitidas, verticales_sin_rest, verticales_con_mapeo = \
        cargar_mapeo_vertical_familia(cfg["archivos"]["mapeo_vertical_familia"])

    # --------------------------------------------------------
    # PASO 2 — Métricas por cliente-dimensión
    # --------------------------------------------------------
    print("\n[ PASO 2 ] Calculando métricas...")
    df_metrics = calcular_metricas(df_ventas, dim_col, fecha_corte_str)

    # --------------------------------------------------------
    # PASO 3 — Rating
    # --------------------------------------------------------
    print("\n[ PASO 3 ] Calculando rating...")
    df_metrics = calcular_rating(
        df_metrics,
        pesos             = cfg_rating["pesos"],
        rating_min        = cfg_rating["escala_min"],
        rating_max        = cfg_rating["escala_max"],
        columnas_invertir = set(cfg_rating["columnas_invertir"]),
    )

    # --------------------------------------------------------
    # Conexión a Odoo y mapeo nombre-familia → ID
    # Se conecta siempre: se necesita para obtener los family_id
    # que se guardan tanto en Redshift como en los leads de Odoo.
    # --------------------------------------------------------
    print("\n[ ODOO ] Conectando a Odoo...")
    uid, odoo_models, odoo_db, odoo_pass = conectar_odoo()

    families_odoo = odoo_models.execute_kw(
        odoo_db, uid, odoo_pass, "product.family", "search_read",
        [[]], {"fields": ["id", "name"], "limit": 5000}
    )
    name_to_id    = {f["name"].strip().upper(): f["id"] for f in families_odoo}
    map_family_id = lambda name: name_to_id.get(str(name).strip().upper()) if pd.notna(name) else None
    print(f"    Familias en Odoo: {len(families_odoo)}")
    if not crear_leads:
        print("    (modo 'redshift': no se crearán leads)")

    # --------------------------------------------------------
    # PASO 4 — Guardar tabla de rating en Redshift
    # --------------------------------------------------------
    df_rating = (
        df_metrics
        .merge(df_clientes[["cliente_id", "razon_social", "ruc", "vertical"]], on="cliente_id", how="left")
        .merge(df_segmentacion[["cliente_id", "nombre_segmento"]],             on="cliente_id", how="left")
        .assign(
            fecha_ultima_venta  = lambda d: d["ultima_compra"],
            fecha_actualizacion = pd.Timestamp.now(),
            family_id           = lambda d: d[dim_col].apply(map_family_id),
        )
        .rename(columns={"rating_scaled": "rating_final", "vertical": "sub_sector"})
    )
    if escribir_redshift:
        print("\n[ PASO 4 ] Guardando rating en Redshift...")
        cargar_tabla_rs(df=df_rating, tabla=schemas["rating"], esquema=schemas["schema"], overwrite_method="drop")
        print(f"    Rating guardado: {len(df_rating):,} filas")
    else:
        print("\n[ PASO 4 ] Rating calculado (no se escribe en Redshift)")

    # --------------------------------------------------------
    # PASO 5 — Modelo 1: Upsell por Vertical
    # --------------------------------------------------------
    print("\n[ PASO 5 ] Generando recomendaciones Upsell por Vertical...")
    df_upsell = generar_upsell(
        df_metrics, df_ventas, df_clientes, df_segmentacion,
        dim_col, cfg["modelo_upsell"],
        familias_permitidas, verticales_sin_rest, verticales_con_mapeo,
        cfg_rating["escala_min"], cfg_rating["escala_max"], map_family_id,
    )
    if not df_upsell.empty and escribir_redshift:
        cargar_tabla_rs(df=df_upsell, tabla=schemas["upsell"],      esquema=schemas["schema"], overwrite_method="drop")
        cargar_y_mantener_rs(df=df_upsell, tabla=schemas["upsell_hist"], esquema=schemas["schema"])

    # --------------------------------------------------------
    # PASO 6 — Modelo 2: Complementarios
    # --------------------------------------------------------
    print("\n[ PASO 6 ] Generando recomendaciones Complementarios...")
    df_comp = generar_complementarios(
        df_ventas, df_clientes, df_segmentacion,
        dim_col, cfg["modelo_complementarios"], map_family_id,
    )
    if not df_comp.empty and escribir_redshift:
        cargar_tabla_rs(df=df_comp, tabla=schemas["complementarios"],      esquema=schemas["schema"], overwrite_method="drop")
        cargar_y_mantener_rs(df=df_comp, tabla=schemas["complementarios_hist"], esquema=schemas["schema"])

    # --------------------------------------------------------
    # PASO 7 — Modelo 3: Recencia de Insumos
    # --------------------------------------------------------
    print("\n[ PASO 7 ] Generando recomendaciones Recencia de Insumos...")
    df_recencia = generar_recencia(
        df_metrics, df_ventas, df_clientes, df_segmentacion,
        dim_col, cfg["modelo_recencia"], map_family_id,
    )
    if not df_recencia.empty and escribir_redshift:
        cargar_tabla_rs(df=df_recencia, tabla=schemas["recencia"],      esquema=schemas["schema"], overwrite_method="drop")
        cargar_y_mantener_rs(df=df_recencia, tabla=schemas["recencia_hist"], esquema=schemas["schema"])

    # --------------------------------------------------------
    # PASO 8 — Crear leads en Odoo CRM
    # --------------------------------------------------------
    if crear_leads:
        print("\n[ PASO 8 ] Creando leads en Odoo CRM...")
        crear_leads_odoo(
            df_upsell[df_upsell["enviado_cliente"]] if not df_upsell.empty else pd.DataFrame(),
            dim_col, uid, odoo_models, odoo_db, odoo_pass,
            campaign_id=campanas["upsell_id"], tipo_lead="upsell", timestamp=timestamp,
        )
        crear_leads_odoo(
            df_comp[df_comp["enviado_cliente"]] if not df_comp.empty else pd.DataFrame(),
            dim_col, uid, odoo_models, odoo_db, odoo_pass,
            campaign_id=campanas["complementarios_id"], tipo_lead="complementarios", timestamp=timestamp,
        )
        crear_leads_odoo(
            df_recencia[df_recencia["enviado_cliente"]] if not df_recencia.empty else pd.DataFrame(),
            dim_col, uid, odoo_models, odoo_db, odoo_pass,
            campaign_id=campanas["recencia_id"], tipo_lead="recencia", timestamp=timestamp,
        )
    else:
        print("\n[ PASO 8 ] Omitido (modo 'redshift': no se crean leads en Odoo)")

    print("\n" + "=" * 60)
    print("  PROCESO COMPLETADO")
    print("=" * 60)


if __name__ == "__main__":
    main()
