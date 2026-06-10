"""
Recalcula las elasticidades precio-demanda históricas y las guarda en Redshift.

Cuándo correrlo:
  - La primera vez que se usa el simulador
  - Una vez por año, cuando hay un año nuevo de datos de ventas y precios

Uso:
    python recalcular_elasticidades.py                        # resumen por categoría
    python recalcular_elasticidades.py --debug "Cuarto de Libra"  # detalle evento a evento
"""

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def _debug_categoria(clasificacion_2: str):
    """Muestra el detalle evento a evento para una categoría."""
    from core.db import query_df, TABLE_PRECIO_PRODUCTOS, TABLE_FACT_VENTAS, TABLE_DIM_ARTICULO

    sql = f"""
        WITH precios_con_lag AS (
            SELECT
                CAST(pp.codigo AS VARCHAR)                          AS codigo,
                pp.anio,
                pp.mes,
                TO_CHAR(TO_DATE(pp.anio::VARCHAR || '-' || LPAD(pp.mes::VARCHAR,2,'0'), 'YYYY-MM'), 'YYYY-MM') AS periodo,
                pp.precio                                           AS precio_actual,
                LAG(pp.precio) OVER (
                    PARTITION BY pp.codigo
                    ORDER BY pp.anio, pp.mes
                )                                                   AS precio_anterior
            FROM {TABLE_PRECIO_PRODUCTOS} pp
            WHERE pp.precio IS NOT NULL
        ),
        cambios_precio AS (
            SELECT
                codigo,
                periodo,
                precio_actual,
                precio_anterior,
                (precio_actual - precio_anterior) / NULLIF(precio_anterior, 0) AS cambio_pct_precio
            FROM precios_con_lag
            WHERE precio_anterior IS NOT NULL
              AND precio_anterior != precio_actual
              AND ABS((precio_actual - precio_anterior) / NULLIF(precio_anterior, 0)) > 0.001
        ),
        ventas_por_producto AS (
            SELECT
                CAST(fv.producto AS VARCHAR)                        AS codigo,
                TO_CHAR(fv.fecha, 'YYYY-MM')                       AS periodo,
                SUM(fv.cantidad)                                    AS unidades
            FROM {TABLE_FACT_VENTAS} fv
            GROUP BY 1, 2
        ),
        ventas_con_lag AS (
            SELECT
                codigo,
                periodo,
                unidades,
                LAG(unidades) OVER (
                    PARTITION BY codigo
                    ORDER BY periodo
                ) AS unidades_anterior
            FROM ventas_por_producto
        ),
        cambios_cantidad AS (
            SELECT
                codigo,
                periodo,
                unidades,
                unidades_anterior,
                (unidades - unidades_anterior) / NULLIF(unidades_anterior, 0) AS cambio_pct_cantidad
            FROM ventas_con_lag
            WHERE unidades_anterior IS NOT NULL
        ),
        detalle AS (
            SELECT
                dav.clasificacion_2_sheet                           AS clasificacion_2,
                cp.codigo,
                cp.periodo,
                cp.precio_anterior,
                cp.precio_actual,
                cp.cambio_pct_precio,
                cc.unidades_anterior,
                cc.unidades,
                cc.cambio_pct_cantidad,
                cc.cambio_pct_cantidad / NULLIF(cp.cambio_pct_precio, 0) AS elasticidad
            FROM cambios_precio cp
            JOIN cambios_cantidad cc
                ON cp.codigo   = cc.codigo
                AND cp.periodo = cc.periodo
            JOIN {TABLE_DIM_ARTICULO} dav
                ON CAST(dav.codigo AS VARCHAR) = cp.codigo
            WHERE dav.clasificacion_2_sheet = %(clf2)s
              AND ABS(cc.cambio_pct_cantidad / NULLIF(cp.cambio_pct_precio, 0)) < 10
        )
        SELECT * FROM detalle ORDER BY codigo, periodo
    """
    df = query_df(sql, {"clf2": clasificacion_2})

    if df.empty:
        print(f"\nNo se encontraron eventos para '{clasificacion_2}'.")
        return

    print(f"\nDetalle evento a evento — {clasificacion_2}")
    print(f"{'─'*110}")
    print(f"{'CODIGO':<10} {'PERIODO':>8} {'P.ANTERIOR':>12} {'P.ACTUAL':>12} {'%PRECIO':>9} {'U.ANTERIOR':>12} {'U.ACTUAL':>10} {'%UNIDADES':>11} {'ELASTICIDAD':>12}")
    print(f"{'─'*110}")
    for _, row in df.iterrows():
        print(
            f"{str(row['codigo']):<10} "
            f"{str(row['periodo']):>8} "
            f"{float(row['precio_anterior']):>12,.0f} "
            f"{float(row['precio_actual']):>12,.0f} "
            f"{float(row['cambio_pct_precio'])*100:>8.1f}% "
            f"{float(row['unidades_anterior']):>12,.0f} "
            f"{float(row['unidades']):>10,.0f} "
            f"{float(row['cambio_pct_cantidad'])*100:>10.1f}% "
            f"{float(row['elasticidad']):>12.4f}"
        )
    print(f"{'─'*110}")
    print(f"Promedio elasticidad: {df['elasticidad'].mean():.4f}  ({len(df)} eventos)\n")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", metavar="CATEGORIA",
                        help="Muestra el detalle evento a evento para una categoría")
    args = parser.parse_args()

    if args.debug:
        _debug_categoria(args.debug)
        return

    log.info("Iniciando recálculo de elasticidades...")

    from core.elasticidades import calcular_y_guardar
    calcular_y_guardar()

    from core.db import query_df, TABLE_ELASTICIDADES
    df = query_df(f"""
        SELECT clasificacion_2, elasticidad_precio,
               n_productos, n_cambios, precio_desde, precio_hasta, confianza
        FROM {TABLE_ELASTICIDADES}
        ORDER BY clasificacion_2
    """)

    if df.empty:
        log.warning("No se generaron elasticidades. Revisá que haya datos de precios y ventas.")
        sys.exit(1)

    print(f"\n{'─'*100}")
    print(f"{'CATEGORÍA':<40} {'ELASTICIDAD':>12} {'PRODUCTOS':>10} {'N°CAMBIOS':>10} {'PRECIO DESDE':>13} {'PRECIO HASTA':>13} {'CONFIANZA':>10}")
    print(f"{'─'*100}")
    for _, row in df.iterrows():
        print(
            f"{str(row['clasificacion_2']):<40} "
            f"{float(row['elasticidad_precio']):>12.4f} "
            f"{int(row['n_productos']):>10} "
            f"{int(row['n_cambios']):>10} "
            f"{float(row['precio_desde']):>13,.0f} "
            f"{float(row['precio_hasta']):>13,.0f} "
            f"{str(row['confianza']):>10}"
        )
    print(f"{'─'*100}")
    print(f"Total: {len(df)} categorías\n")


if __name__ == "__main__":
    main()
