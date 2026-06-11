"""
McDonald's ETL - Carga del Excel a Redshift (4 tablas)

Configura las credenciales en un archivo .env (ver .env.example).
Uso:
    pip install -r requirements.txt
    python etl_load.py
"""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime

import openpyxl
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuración desde variables de entorno
# ---------------------------------------------------------------------------
REDSHIFT_HOST     = os.environ["REDSHIFT_HOST"]
REDSHIFT_PORT     = int(os.environ.get("REDSHIFT_PORT", 5439))
REDSHIFT_DB       = os.environ["REDSHIFT_DB"]
REDSHIFT_USER     = os.environ["REDSHIFT_USER"]
REDSHIFT_PASSWORD = os.environ["REDSHIFT_PASSWORD"]
SCHEMA               = os.environ.get("REDSHIFT_SCHEMA", "simulacion")
EXCEL_PATH           = Path(os.environ.get("EXCEL_PATH", "./datos/DATOS.xlsx"))
EXCEL_COMPETENCIA    = Path(os.environ.get("EXCEL_COMPETENCIA", "./datos/Competencia_por_local.xlsx"))
CSV_CALENDARIO       = Path(os.environ.get("CSV_CALENDARIO", "./datos/Calendario_de_acciones_historico_MKTParaguay.csv"))
EXCEL_LOCALES        = Path(os.environ.get("EXCEL_LOCALES", "./datos/Dimensión_Locales.xlsx"))

DDL_PATH = Path(__file__).parent / "create_tables.sql"

BATCH_SIZE = 1000


# ---------------------------------------------------------------------------
# Conexión
# ---------------------------------------------------------------------------
def get_connection():
    return psycopg2.connect(
        host=REDSHIFT_HOST,
        port=REDSHIFT_PORT,
        dbname=REDSHIFT_DB,
        user=REDSHIFT_USER,
        password=REDSHIFT_PASSWORD,
        connect_timeout=30,
    )


# ---------------------------------------------------------------------------
# Crear tablas
# ---------------------------------------------------------------------------
def create_tables(conn):
    log.info("Creando schema '%s' y tablas si no existen...", SCHEMA)
    ddl = DDL_PATH.read_text(encoding="utf-8").replace("{schema}", SCHEMA)

    with conn.cursor() as cur:
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA};")
    conn.commit()

    for statement in _split_sql(ddl):
        try:
            with conn.cursor() as cur:
                cur.execute(statement)
            conn.commit()
        except Exception as exc:
            conn.rollback()
            log.error("Error ejecutando DDL:\n%s\n→ %s", statement[:120], exc)
            raise

    log.info("Tablas creadas/verificadas.")


def _split_sql(sql: str) -> list[str]:
    statements = []
    for stmt in sql.split(";"):
        lines = [l for l in stmt.splitlines() if not l.strip().startswith("--")]
        clean = "\n".join(lines).strip()
        if clean:
            statements.append(clean)
    return statements


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _to_price(value):
    """Convierte celda a float, descartando errores de Excel (#DIV/0! etc.) y ceros."""
    if value is None:
        return None
    if isinstance(value, str):
        if value.startswith("#") or value.strip() == "":
            return None
        try:
            value = float(value.replace(",", "."))
        except ValueError:
            return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f != 0.0 else None


def truncate_and_insert(conn, table: str, columns: list, rows: list):
    if not rows:
        log.warning("Sin datos para %s, se omite.", table)
        return
    full_table = f"{SCHEMA}.{table}"
    cols_str = ", ".join(columns)
    with conn.cursor() as cur:
        cur.execute(f"TRUNCATE TABLE {full_table};")
        for i in range(0, len(rows), BATCH_SIZE):
            execute_values(
                cur,
                f"INSERT INTO {full_table} ({cols_str}) VALUES %s",
                rows[i : i + BATCH_SIZE],
            )
    conn.commit()
    log.info("%-35s → %d filas insertadas", full_table, len(rows))


# ---------------------------------------------------------------------------
# Parseo por hoja
# ---------------------------------------------------------------------------
def parse_precio_productos(ws) -> list:
    """
    Hoja 'Precios': col B=codigo, col C=descripcion, col D+=precio por mes.
    Retorna lista de (codigo, descripcion, anio, mes, precio).
    """
    rows = list(ws.iter_rows(values_only=True))
    header = rows[0]

    date_cols = [
        (idx, val.year, val.month)
        for idx, val in enumerate(header)
        if isinstance(val, datetime)
    ]

    records = []
    for row in rows[1:]:
        codigo = row[1]
        descripcion = row[2]
        if codigo is None:
            continue
        codigo = int(codigo)
        desc = str(descripcion).strip() if descripcion else ""

        for idx, anio, mes in date_cols:
            precio = _to_price(row[idx] if idx < len(row) else None)
            if precio is not None:
                records.append((codigo, desc, anio, mes, precio))

    log.info("precio_productos: %d registros", len(records))
    return records


def parse_promociones(ws) -> list:
    """
    Hoja 'Códigos-Promo': col A=campaña (solo primera fila del grupo),
    col B=codigo, col C=descripcion, col D=fecha_desde (opcional), col E=fecha_hasta (opcional).
    Retorna lista de (campania, codigo, descripcion, fecha_desde, fecha_hasta).
    """
    rows = list(ws.iter_rows(values_only=True))
    records = []
    current_campania  = None
    current_fecha_desde = None
    current_fecha_hasta = None

    for row in rows:
        if not any(x is not None for x in row):
            continue
        if row[0] is not None:
            current_campania = str(row[0]).strip()
            # Fechas en col D y E, solo en la primera fila del grupo
            raw_desde = row[3] if len(row) > 3 else None
            raw_hasta = row[4] if len(row) > 4 else None
            current_fecha_desde = _parse_fecha(raw_desde)
            current_fecha_hasta = _parse_fecha(raw_hasta)
        codigo      = row[1] if len(row) > 1 else None
        descripcion = row[2] if len(row) > 2 else None
        if current_campania and codigo is not None:
            records.append((
                current_campania,
                int(codigo),
                str(descripcion).strip() if descripcion else "",
                current_fecha_desde,
                current_fecha_hasta,
            ))

    log.info("promociones: %d registros (%d con fechas)",
             len(records), sum(1 for r in records if r[3]))
    return records


def _parse_fecha(valor) -> str | None:
    """Convierte datetime, date o string YYYY-MM-DD a string ISO, o None."""
    if valor is None:
        return None
    from datetime import datetime, date
    if isinstance(valor, (datetime, date)):
        return valor.strftime("%Y-%m-%d")
    s = str(valor).strip()
    if s and s != "None":
        return s[:10]  # tomar solo YYYY-MM-DD si viene con hora
    return None


def parse_calendario_csv(path: Path) -> list:
    """
    Parsea el CSV del calendario de acciones de marketing.

    Estructura del CSV:
      - Separador: punto y coma (;)
      - Filas de encabezado: fila con años (2026, 2025, 2024...) + fila con
        "Inicio;Fin;Código;Descripcion" repetido por año.
      - Cada año ocupa 4 columnas: Inicio | Fin | Código | Descripcion.
        2026 → cols 2-5  |  2025 → cols 6-9  |  2024 → cols 10-13  ...
      - El mes se detecta por el valor en col 1 (ENERO, FEBRERO, etc.) y se
        hereda hasta que aparezca otro mes.
      - Inicio/Fin son días del mes. Pueden ser: número simple, "6, 13, 20 y 27",
        "6 al 16", "22-ene", "09-abr-26", "Vigente", vacío.
      - Código puede contener: múltiples números separados por guiones, espacios
        o saltos de línea; puntos como separador de miles (9.158 → 9158).

    Solo incluye filas con códigos numéricos válidos (entre 100 y 999999).
    Retorna lista de (campania, codigo, descripcion, fecha_desde, fecha_hasta).
    """
    import csv as csv_mod
    import re
    import calendar as cal
    from datetime import date as dt_date

    MESES_ES = {
        "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4,
        "MAYO": 5, "JUNIO": 6, "JULIO": 7, "AGOSTO": 8,
        "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12,
    }
    MES_ABREV = {
        "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
        "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
    }
    TARGET_YEARS = {2024, 2025, 2026}

    def _extraer_codigos(texto):
        tokens = re.findall(r'\b\d[\d.]*\b', texto.replace('\n', ' ').replace('\r', ''))
        codigos = []
        for t in tokens:
            try:
                c = int(t.replace('.', ''))
                if 100 <= c <= 999999:
                    codigos.append(c)
            except ValueError:
                pass
        return list(dict.fromkeys(codigos))

    def _parsear_fecha(texto, year, mes, tipo):
        """tipo: 'inicio' → día mínimo | 'fin' → día máximo."""
        if not texto:
            return None
        t = texto.strip().lower()
        if t in ('vigente', 'se queda', 'hasta agotar stock', 'todo el mes', ''):
            return None

        # "22-ene" o "09-abr-26"
        m = re.match(r'^(\d{1,2})[- ]([a-záéíóú]{3})(?:[- ](\d{2,4}))?', t)
        if m:
            dia  = int(m.group(1))
            mes_ = MES_ABREV.get(m.group(2), mes)
            yr_  = int(m.group(3)) if m.group(3) else year
            if yr_ < 100:
                yr_ += 2000
            try:
                return dt_date(yr_, mes_, min(dia, cal.monthrange(yr_, mes_)[1]))
            except ValueError:
                return None

        # "X al Y"
        m = re.match(r'^(\d+)\s*al\s*(\d+)', t)
        if m:
            d1, d2 = int(m.group(1)), int(m.group(2))
            dia = d1 if tipo == "inicio" else d2
            try:
                return dt_date(year, mes, min(dia, cal.monthrange(year, mes)[1]))
            except ValueError:
                return None

        # Uno o varios días: "6, 13, 20 y 27" | "1 y 2" | "15"
        nums = [int(x) for x in re.findall(r'\d+', t) if 1 <= int(x) <= 31]
        if nums:
            dia = min(nums) if tipo == "inicio" else max(nums)
            try:
                return dt_date(year, mes, min(dia, cal.monthrange(year, mes)[1]))
            except ValueError:
                return None

        return None

    if not path.exists():
        log.warning("CSV calendario no encontrado: %s — se omite.", path)
        return []

    with open(path, encoding='latin-1', errors='replace') as f:
        reader = csv_mod.reader(f, delimiter=';')
        all_rows = list(reader)

    # Detectar columna base de cada año objetivo (primeras 10 filas)
    year_col_map = {}
    for row in all_rows[:10]:
        for col_idx, val in enumerate(row):
            v = val.strip()
            if re.match(r'^20\d\d$', v):
                yr = int(v)
                if yr in TARGET_YEARS:
                    year_col_map[yr] = col_idx
        if year_col_map:
            break

    if not year_col_map:
        log.warning("No se detectaron columnas de año en el CSV. Se omite.")
        return []

    log.info("Calendario CSV — años detectados: %s", year_col_map)

    max_col   = max(year_col_map.values()) + 4
    records   = []
    cur_month = None

    for row in all_rows:
        while len(row) < max_col:
            row.append('')

        col1 = row[1].strip().upper() if len(row) > 1 else ''
        if col1 in MESES_ES:
            cur_month = MESES_ES[col1]

        if cur_month is None:
            continue

        for year, base in year_col_map.items():
            inicio_raw = row[base].strip()
            fin_raw    = row[base + 1].strip()
            codigo_raw = row[base + 2].strip()
            desc_raw   = row[base + 3].strip()

            if not codigo_raw or not desc_raw:
                continue

            codigos = _extraer_codigos(codigo_raw)
            if not codigos:
                continue

            fd = _parsear_fecha(inicio_raw, year, cur_month, "inicio")
            fh = _parsear_fecha(fin_raw,    year, cur_month, "fin")

            if fd is None:
                continue
            if fh and fh < fd:
                fh = None  # fecha inválida, descartar

            fd_str = fd.strftime('%Y-%m-%d')
            fh_str = fh.strftime('%Y-%m-%d') if fh else None
            desc   = desc_raw[:500]

            for codigo in codigos:
                records.append((desc, codigo, '', fd_str, fh_str))

    # Deduplicar por (campania, codigo, fecha_desde)
    seen, unique = set(), []
    for r in records:
        key = (r[0], r[1], r[3])
        if key not in seen:
            seen.add(key)
            unique.append(r)

    log.info("Calendario CSV: %d registros, %d campañas únicas",
             len(unique), len({r[0] for r in unique}))
    return unique


def parse_lanzamientos(ws) -> list:
    """
    Hoja 'Códigos Lanzamientos': misma estructura que Códigos-Promo.
    Retorna lista de (lanzamiento, codigo, descripcion).
    """
    rows = list(ws.iter_rows(values_only=True))
    records = []
    current_lanzamiento = None

    for row in rows:
        if not any(x is not None for x in row):
            continue
        if row[0] is not None:
            current_lanzamiento = str(row[0]).strip()
        codigo = row[1] if len(row) > 1 else None
        descripcion = row[2] if len(row) > 2 else None
        if current_lanzamiento and codigo is not None:
            records.append((
                current_lanzamiento,
                int(codigo),
                str(descripcion).strip() if descripcion else "",
            ))

    log.info("lanzamientos: %d registros", len(records))
    return records


def parse_apertura_restaurantes(ws) -> list:
    """
    Hoja 'Aperturas': col B=short_name, col C=fecha_apertura, col D=api_id,
    cols E-I = flags M(Mostrador), A(Automac), D(Delivery), X(Kiosco Digital), K(Centro de Postres).
    """
    rows = list(ws.iter_rows(values_only=True))
    records = []

    for row in rows[1:]:  # fila 0 es header
        if not any(x is not None for x in row):
            continue
        short_name = row[1]
        fecha_raw  = row[2]
        api_id_raw = row[3]

        if short_name is None or api_id_raw is None:
            continue

        fecha = fecha_raw.date() if isinstance(fecha_raw, datetime) else fecha_raw
        flags = [row[i] if i < len(row) else None for i in range(4, 9)]
        bools = [v is not None and str(v).strip() != "" for v in flags]

        records.append((
            int(api_id_raw),
            str(short_name).strip(),
            fecha,
            bools[0],  # M - Mostrador
            bools[1],  # A - Automac
            bools[2],  # D - Delivery
            bools[3],  # X - Kiosco Digital
            bools[4],  # K - Centro de Postres
        ))

    log.info("apertura_restaurantes: %d registros", len(records))
    return records


# ---------------------------------------------------------------------------
# Competencia
# ---------------------------------------------------------------------------
def parse_competencia(path: Path) -> list:
    """
    Excel Competencia_por_local.xlsx, hoja 'Trading':
      Estructura jerárquica: fila header tiene (None, numero, short_name, 'RADIO', 'TIPO')
      Filas de competidores: (None, None, nombre_competidor, radio_str, tipo)
      Radio viene como string '0,5 KM' o '1 KM' → convertimos a float.
    Retorna lista de (local_numero, short_name, competidor, radio_km, tipo).
    """
    if not path.exists():
        log.warning("No se encontró el archivo de competencia: %s. Se omite.", path)
        return []

    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    ws = wb.active
    rows = [r for r in ws.iter_rows(values_only=True) if any(x is not None for x in r)]
    wb.close()

    records = []
    current_numero = None
    current_short  = None

    for row in rows:
        # Fila de header de local: col B = número, col C = short_name, col D = 'RADIO'
        if row[1] is not None and str(row[3]).strip().upper() == "RADIO":
            current_numero = int(row[1])
            current_short  = str(row[2]).strip()
            continue

        # Fila de competidor
        competidor = row[2]
        radio_raw  = row[3]
        tipo       = row[4]

        if current_numero is None or competidor is None:
            continue

        # Convertir '0,5 KM' o '1 KM' → float
        try:
            radio_km = float(str(radio_raw).replace(",", ".").replace(" KM", "").strip())
        except (ValueError, AttributeError):
            radio_km = None

        if radio_km is not None:
            records.append((
                current_numero,
                current_short,
                str(competidor).strip(),
                radio_km,
                str(tipo).strip() if tipo else None,
            ))

    log.info("competencia: %d registros", len(records))
    return records


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    log.info("=== McDonald's ETL iniciando ===")

    if not EXCEL_PATH.exists():
        log.error("No se encontró el archivo: %s", EXCEL_PATH)
        sys.exit(1)

    log.info("Abriendo Excel: %s", EXCEL_PATH)
    wb = openpyxl.load_workbook(str(EXCEL_PATH), read_only=True, data_only=True)

    precios      = parse_precio_productos(wb["Precios"])
    promo_excel  = parse_promociones(wb["Códigos-Promo"])
    lanzamientos = parse_lanzamientos(wb["Códigos Lanzamientos"])
    aperturas    = parse_apertura_restaurantes(wb["Aperturas"])
    wb.close()

    promo_csv   = parse_calendario_csv(CSV_CALENDARIO)
    promociones = promo_excel + promo_csv
    log.info("Promociones total: %d (Excel: %d | Calendario CSV: %d)",
             len(promociones), len(promo_excel), len(promo_csv))

    competencia = parse_competencia(EXCEL_COMPETENCIA)

    conn = get_connection()
    try:
        create_tables(conn)

        truncate_and_insert(
            conn, "precio_productos",
            ["codigo", "descripcion", "anio", "mes", "precio"],
            precios,
        )
        truncate_and_insert(
            conn, "promociones",
            ["campania", "codigo", "descripcion", "fecha_desde", "fecha_hasta"],
            promociones,
        )
        truncate_and_insert(
            conn, "lanzamientos",
            ["lanzamiento", "codigo", "descripcion"],
            lanzamientos,
        )
        truncate_and_insert(
            conn, "apertura_restaurantes",
            ["api_id", "short_name", "fecha_apertura",
             "tiene_mostrador", "tiene_automac", "tiene_delivery",
             "tiene_kiosco_digital", "tiene_centro_postres"],
            aperturas,
        )
        truncate_and_insert(
            conn, "competencia",
            ["local_numero", "short_name", "competidor", "radio_km", "tipo"],
            competencia,
        )

    except Exception as exc:
        conn.rollback()
        log.error("Error durante la carga: %s", exc)
        raise
    finally:
        conn.close()

    log.info("=== ETL finalizado con éxito ===")


if __name__ == "__main__":
    main()
