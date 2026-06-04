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
SCHEMA            = os.environ.get("REDSHIFT_SCHEMA", "mcd")
EXCEL_PATH        = Path(os.environ.get("EXCEL_PATH", "./datos/DATOS.xlsx"))

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
    col B=codigo, col C=descripcion.
    Retorna lista de (campania, codigo, descripcion).
    """
    rows = list(ws.iter_rows(values_only=True))
    records = []
    current_campania = None

    for row in rows:
        if not any(x is not None for x in row):
            continue
        if row[0] is not None:
            current_campania = str(row[0]).strip()
        codigo = row[1] if len(row) > 1 else None
        descripcion = row[2] if len(row) > 2 else None
        if current_campania and codigo is not None:
            records.append((
                current_campania,
                int(codigo),
                str(descripcion).strip() if descripcion else "",
            ))

    log.info("promociones: %d registros", len(records))
    return records


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
    cols E-I = flags M(mostrador), A(automac), D(delivery), X(app), K(kiosco).
    Retorna lista de (api_id, short_name, fecha_apertura, mostrador, automac,
                      delivery, app, kiosco).
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
            bools[0],  # M - mostrador
            bools[1],  # A - automac
            bools[2],  # D - delivery
            bools[3],  # X - app
            bools[4],  # K - kiosco
        ))

    log.info("apertura_restaurantes: %d registros", len(records))
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
    promociones  = parse_promociones(wb["Códigos-Promo"])
    lanzamientos = parse_lanzamientos(wb["Códigos Lanzamientos"])
    aperturas    = parse_apertura_restaurantes(wb["Aperturas"])
    wb.close()

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
            ["campania", "codigo", "descripcion"],
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
             "tiene_app", "tiene_kiosco"],
            aperturas,
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
