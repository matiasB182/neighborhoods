"""
McDonald's ETL - Carga del Excel a Redshift

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
        # Redshift no admite múltiples statements en execute(), ejecutamos uno a uno
        for statement in _split_sql(ddl):
            cur.execute(statement)
    conn.commit()
    log.info("Tablas creadas/verificadas.")


def _split_sql(sql: str) -> list[str]:
    """Separa statements por ';' ignorando bloques vacíos y comentarios."""
    statements = []
    for stmt in sql.split(";"):
        clean = stmt.strip()
        if clean and not clean.startswith("--"):
            statements.append(clean)
    return statements


# ---------------------------------------------------------------------------
# Parseo del Excel
# ---------------------------------------------------------------------------
def load_workbook(path: Path):
    if not path.exists():
        log.error("No se encontró el archivo: %s", path)
        sys.exit(1)
    log.info("Abriendo Excel: %s", path)
    return openpyxl.load_workbook(str(path), read_only=True, data_only=True)


# ---- Precios ---------------------------------------------------------------
def parse_precios(ws) -> tuple[list, list]:
    """
    Hoja 'Precios':
      Col B = codigo, Col C = descripcion, Col D en adelante = precio por mes.
    Retorna (productos, precios) como listas de tuplas listas para insertar.
    """
    rows = list(ws.iter_rows(values_only=True))
    header = rows[0]

    # Detectar columnas de fechas (desde índice 3 en adelante)
    date_cols = []
    for idx, val in enumerate(header):
        if isinstance(val, datetime):
            date_cols.append((idx, val.year, val.month))

    productos = []
    precios = []
    seen_codigos = set()

    for row in rows[1:]:
        codigo = row[1]
        descripcion = row[2]
        if codigo is None:
            continue
        codigo = int(codigo)

        if codigo not in seen_codigos:
            productos.append((codigo, str(descripcion).strip()))
            seen_codigos.add(codigo)

        for idx, anio, mes in date_cols:
            precio_raw = row[idx] if idx < len(row) else None
            precio = float(precio_raw) if precio_raw not in (None, 0, 0.0) else None
            if precio is not None:
                precios.append((codigo, anio, mes, precio))

    log.info("Precios: %d productos, %d registros de precio", len(productos), len(precios))
    return productos, precios


# ---- Campañas / Lanzamientos -----------------------------------------------
def parse_campania_sheet(ws) -> tuple[list, list]:
    """
    Estructura común para 'Códigos-Promo' y 'Códigos Lanzamientos':
      Col A = nombre de campaña/lanzamiento (solo en primera fila del grupo)
      Col B = codigo del producto
      Col C = descripcion del producto

    Retorna (groups, items):
      groups = [(descripcion,), ...]
      items  = [(group_idx_1based, codigo, descripcion), ...]
    """
    rows = list(ws.iter_rows(values_only=True))
    groups = []
    items = []
    current_group_id = 0

    for row in rows:
        if not any(x is not None for x in row):
            continue

        group_name = row[0]
        codigo_raw = row[1] if len(row) > 1 else None
        descripcion = row[2] if len(row) > 2 else None

        if group_name is not None:
            groups.append((str(group_name).strip(),))
            current_group_id = len(groups)  # 1-based, coincide con IDENTITY

        if codigo_raw is not None and current_group_id > 0:
            items.append((
                current_group_id,
                int(codigo_raw),
                str(descripcion).strip() if descripcion else "",
            ))

    return groups, items


# ---- Locales ---------------------------------------------------------------
def parse_locales(ws) -> list:
    """
    Hoja 'Aperturas':
      Col B = short_name, Col C = fecha_apertura, Col D = api_id (int)
      Cols E-I = flags: M(mostrador), A(automac), D(delivery), X(app), K(kiosco)
    """
    rows = list(ws.iter_rows(values_only=True))
    locales = []

    for row in rows[1:]:  # fila 0 es header
        if not any(x is not None for x in row):
            continue

        short_name     = row[1]
        fecha_apertura = row[2]
        api_id_raw     = row[3]

        if short_name is None or api_id_raw is None:
            continue

        # Flags desde col índice 4 hasta 8
        flag_values = [row[i] if i < len(row) else None for i in range(4, 9)]
        flag_keys   = ["M", "A", "D", "X", "K"]
        flags = {k: (v is not None and str(v).strip() != "") for k, v in zip(flag_keys, flag_values)}

        fecha = fecha_apertura.date() if isinstance(fecha_apertura, datetime) else fecha_apertura

        locales.append((
            int(api_id_raw),
            str(short_name).strip(),
            fecha,
            flags["M"],
            flags["A"],
            flags["D"],
            flags["X"],
            flags["K"],
        ))

    log.info("Locales: %d registros", len(locales))
    return locales


# ---------------------------------------------------------------------------
# Inserción con TRUNCATE + carga (idempotente)
# ---------------------------------------------------------------------------
BATCH_SIZE = 1000


def truncate_and_insert(conn, table: str, columns: list[str], rows: list):
    if not rows:
        log.warning("Sin datos para %s, se omite.", table)
        return

    full_table = f"{SCHEMA}.{table}"
    cols_str = ", ".join(columns)

    with conn.cursor() as cur:
        cur.execute(f"TRUNCATE TABLE {full_table};")
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i : i + BATCH_SIZE]
            execute_values(
                cur,
                f"INSERT INTO {full_table} ({cols_str}) VALUES %s",
                batch,
            )
    conn.commit()
    log.info("%-35s → %d filas insertadas", full_table, len(rows))


def insert_groups_and_items(
    conn,
    group_table: str,
    item_table: str,
    group_id_col: str,
    groups: list,
    items: list,
):
    """
    Inserta grupos (campañas / lanzamientos) y sus productos asociados.
    Como Redshift IDENTITY no devuelve IDs en bulk, usamos secuencia manual.
    """
    if not groups:
        return

    full_group = f"{SCHEMA}.{group_table}"
    full_item  = f"{SCHEMA}.{item_table}"

    with conn.cursor() as cur:
        # Limpiar en orden para respetar FK
        cur.execute(f"TRUNCATE TABLE {full_item};")
        cur.execute(f"TRUNCATE TABLE {full_group};")

        # Redshift soporta IDENTITY pero con TRUNCATE se resetea el contador.
        # Insertamos generando IDs manualmente para poder referenciarlos en items.
        group_rows = [(i + 1, desc) for i, (desc,) in enumerate(groups)]
        execute_values(
            cur,
            f"INSERT INTO {full_group} ({group_id_col}, descripcion) VALUES %s",
            group_rows,
        )

        if items:
            execute_values(
                cur,
                f"INSERT INTO {full_item} ({group_id_col}, codigo, descripcion) VALUES %s",
                items,
            )

    conn.commit()
    log.info("%-35s → %d grupos, %d items", full_group, len(groups), len(items))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    log.info("=== McDonald's ETL iniciando ===")

    wb = load_workbook(EXCEL_PATH)

    # Parseo
    productos, precios       = parse_precios(wb["Precios"])
    promo_groups, promo_items = parse_campania_sheet(wb["Códigos-Promo"])
    lanz_groups,  lanz_items  = parse_campania_sheet(wb["Códigos Lanzamientos"])
    locales                  = parse_locales(wb["Aperturas"])

    wb.close()

    # Carga
    conn = get_connection()
    try:
        create_tables(conn)

        truncate_and_insert(conn, "ref_productos", ["codigo", "descripcion"], productos)
        truncate_and_insert(conn, "fact_precios",  ["codigo", "anio", "mes", "precio"], precios)
        truncate_and_insert(
            conn, "ref_locales",
            ["api_id", "short_name", "fecha_apertura",
             "tiene_mostrador", "tiene_automac", "tiene_delivery",
             "tiene_app", "tiene_kiosco"],
            locales,
        )

        insert_groups_and_items(
            conn,
            group_table="ref_campanias",
            item_table="ref_campania_productos",
            group_id_col="campania_id",
            groups=promo_groups,
            items=promo_items,
        )
        insert_groups_and_items(
            conn,
            group_table="ref_lanzamientos",
            item_table="ref_lanzamiento_productos",
            group_id_col="lanzamiento_id",
            groups=lanz_groups,
            items=lanz_items,
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
