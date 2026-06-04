"""
Recalcula las elasticidades precio-demanda históricas y las guarda en Redshift.

Cuándo correrlo:
  - La primera vez que se usa el simulador
  - Una vez por año, cuando hay un año nuevo de datos de ventas y precios

Uso:
    python recalcular_elasticidades.py
"""

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def main():
    log.info("Iniciando recálculo de elasticidades...")

    from core.elasticidades import calcular_y_guardar
    calcular_y_guardar()

    from core.db import query_df, TABLE_ELASTICIDADES
    df = query_df(f"""
        SELECT clasificacion_2, anio, elasticidad_precio,
               n_productos, n_cambios, precio_desde, precio_hasta, confianza
        FROM {TABLE_ELASTICIDADES}
        ORDER BY clasificacion_2, anio
    """)

    if df.empty:
        log.warning("No se generaron elasticidades. Revisá que haya datos de precios y ventas.")
        sys.exit(1)

    print(f"\n{'─'*105}")
    print(f"{'CATEGORÍA':<40} {'AÑO':>5} {'ELASTICIDAD':>12} {'PRODUCTOS':>10} {'N°CAMBIOS':>10} {'PRECIO DESDE':>13} {'PRECIO HASTA':>13} {'CONFIANZA':>10}")
    print(f"{'─'*105}")
    for _, row in df.iterrows():
        print(
            f"{str(row['clasificacion_2']):<40} "
            f"{int(row['anio']):>5} "
            f"{float(row['elasticidad_precio']):>12.4f} "
            f"{int(row['n_productos']):>10} "
            f"{int(row['n_cambios']):>10} "
            f"{float(row['precio_desde']):>13,.0f} "
            f"{float(row['precio_hasta']):>13,.0f} "
            f"{str(row['confianza']):>10}"
        )
    print(f"{'─'*105}")
    print(f"Total: {len(df)} filas ({df['clasificacion_2'].nunique()} categorías × {df['anio'].nunique()} años)\n")


if __name__ == "__main__":
    main()
