# DOCUMENTACIÓN COMPLETA — SIMULADOR DE ESCENARIOS McDONALD'S PARAGUAY

> Este documento describe en detalle absoluto el sistema de simulación de ventas de McDonald's Paraguay:
> todas las tablas, archivos de entrada, relaciones entre datos, y cada módulo de código explicado línea por línea.

---

## ÍNDICE

1. [Arquitectura general](#1-arquitectura-general)
2. [Variables de entorno (.env)](#2-variables-de-entorno-env)
3. [Tablas en Redshift — fuente de datos](#3-tablas-en-redshift--fuente-de-datos)
4. [Tablas en Redshift — cargadas por el ETL](#4-tablas-en-redshift--cargadas-por-el-etl)
5. [Tablas en Redshift — generadas por el simulador](#5-tablas-en-redshift--generadas-por-el-simulador)
6. [Archivos de entrada (Excel y CSV)](#6-archivos-de-entrada-excel-y-csv)
7. [Relaciones entre tablas](#7-relaciones-entre-tablas)
8. [ETL — mcdonalds_etl/](#8-etl--mcdonalds_etl)
9. [Simulador — mcdonalds_simulator/](#9-simulador--mcdonalds_simulator)
10. [Palancas — caso por caso](#10-palancas--caso-por-caso)
11. [Output y resultados](#11-output-y-resultados)
12. [scenario.yaml — guía de uso](#12-scenarioyaml--guía-de-uso)
13. [Flujo completo de una simulación](#13-flujo-completo-de-una-simulación)
14. [Problemas conocidos y limitaciones](#14-problemas-conocidos-y-limitaciones)

---

## 1. ARQUITECTURA GENERAL

El sistema tiene dos componentes separados:

```
mcdonalds_etl/          ← Carga datos desde Excel/CSV a Redshift (corre una vez)
mcdonalds_simulator/    ← Lee de Redshift y simula escenarios (corre cada vez)
```

### Flujo de datos completo

```
ARCHIVOS FUENTE
├── Excel principal (Precios, Códigos-Promo, Lanzamientos, Aperturas)
├── Excel Dimensión Locales (GPS, tamaño, tipo de local)
├── Excel Competencia (competidores por local)
└── CSV Calendario MKT (historial de campañas con fechas)
         │
         ▼
   mcdonalds_etl/etl_load.py
         │  parsea y carga
         ▼
REDSHIFT (tablas ETL)
├── simulacion.precio_productos
├── simulacion.promociones
├── simulacion.lanzamientos
├── simulacion.apertura_restaurantes
├── simulacion.competencia
└── simulacion.locales_dimension
         │
         │  más las tablas fuente ya existentes:
         │
REDSHIFT (tablas fuente)
├── forecasting.forecast_ventas_sucursal  ← forecast por categoría + sucursal + mes
├── stg.fact_ventas                       ← transacciones reales (ventas históricas)
├── stg.dim_articulo_venta                ← catálogo de productos con clasificaciones
└── stg.dim_restaurantes                  ← lista de restaurantes con sus atributos
         │
         ▼
   scenario.yaml  ←  el usuario define qué simular
         │
         ▼
   mcdonalds_simulator/run.py
         │
         ▼
   core/engine.py  →  core/loader.py  →  core/elasticidades.py
         │
         ▼
   palancas/{precio, promocion, lanzamiento, estructural, competencia, clima}.py
         │
         ▼
   output/formatter.py  →  consola + CSV
         │
         ▼
   simulacion.escenarios  (guardado en Redshift para historial)
```

---

## 2. VARIABLES DE ENTORNO (.env)

El archivo `.env` en la raíz del proyecto define todas las conexiones y nombres de tablas.
**Nunca commitear este archivo.** Cada variable se explica a continuación:

```env
# ── Conexión a Redshift ──────────────────────────────────────────────
REDSHIFT_HOST=mi-cluster.redshift.amazonaws.com   # hostname del cluster
REDSHIFT_PORT=5439                                 # puerto (default 5439)
REDSHIFT_DB=dev                                    # nombre de la base de datos
REDSHIFT_USER=admin                                # usuario
REDSHIFT_PASSWORD=secreto                          # contraseña
REDSHIFT_SCHEMA=simulacion                         # schema para tablas del ETL

# ── Tablas fuente (ya existen en Redshift, no las crea el ETL) ───────
TABLE_FORECAST=forecasting.forecast_ventas_sucursal   # forecast mensual por clf2 + sucursal
TABLE_FACT_VENTAS=stg.fact_ventas                     # ventas reales transacción por transacción
TABLE_DIM_ARTICULO=stg.dim_articulo_venta             # catálogo de productos
TABLE_DIM_RESTAURANTES=stg.dim_restaurantes           # catálogo de restaurantes

# ── Tablas cargadas por el ETL ────────────────────────────────────────
TABLE_PRECIO_PRODUCTOS=simulacion.precio_productos
TABLE_PROMOCIONES=simulacion.promociones
TABLE_LANZAMIENTOS=simulacion.lanzamientos
TABLE_APERTURA_RESTAURANTES=simulacion.apertura_restaurantes
TABLE_COMPETENCIA=simulacion.competencia

# ── Tablas generadas por el simulador ────────────────────────────────
TABLE_ELASTICIDADES=simulacion.elasticidades          # calculadas automáticamente al iniciar
TABLE_RESULTADOS=simulacion.escenarios                # historial de simulaciones guardadas

# ── Rutas a archivos de entrada (solo para el ETL) ───────────────────
EXCEL_PATH=/ruta/al/archivo.xlsx                      # Excel principal
EXCEL_COMPETENCIA=/ruta/competencia.xlsx              # Excel de competidores
EXCEL_LOCALES=/ruta/dimension_locales.xlsx            # Excel de dimensiones de locales
CSV_CALENDARIO=/ruta/calendario_mkt.csv               # CSV del calendario de marketing
```

---

## 3. TABLAS EN REDSHIFT — FUENTE DE DATOS

Estas tablas **ya existen** en Redshift antes de correr el ETL. Son la fuente de verdad del negocio.

### 3.1 `forecasting.forecast_ventas_sucursal`

**Qué es:** El forecast (pronóstico) de unidades vendidas, por categoría de producto, sucursal y mes.
Es la base de todo el simulador — "¿cuánto iba a vender sin ningún cambio?"

**Columnas:**

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `clasificacion_2_sheet` | VARCHAR | Nombre de la categoría (ej: "Combo Big Mac", "McFlurry") |
| `sucursal` | SMALLINT | Número identificador del restaurante (ej: 10, 12, 14) |
| `periodo` | VARCHAR | Mes en formato `YYYY-MM` (ej: "2025-06") |
| `unidades` | NUMERIC | Unidades históricas reales del mes (si el período ya pasó) |
| `forecast` | NUMERIC | Unidades pronosticadas por el modelo (puede ser NULL si solo hay histórico) |
| `modelo` | VARCHAR | Nombre del modelo que generó el forecast (ej: "ETS_add") — **actualmente siempre NULL** |
| `mejor_modelo` | VARCHAR | El modelo seleccionado como mejor para esta serie (ej: "share3") — **este es el que se usa** |
| `promedio_precio` | NUMERIC | Precio promedio ponderado del período (en Gs.) |
| `fecha_actualizacion` | TIMESTAMP | Cuándo se actualizó el forecast |

**Notas importantes:**
- `modelo` es siempre NULL en los datos actuales. El filtro correcto es `mejor_modelo IS NOT NULL`.
- `COALESCE(forecast, unidades)` da el mejor valor disponible: forecast si existe, sino el histórico real.
- El simulador usa `COALESCE(forecast, unidades)` como baseline en todas las palancas.
- Período disponible: 2023-01 a 2027-05 (53 períodos, 35 clasificaciones).
- **Problema conocido:** 2026-03, 2026-04 y 2026-05 tienen valores de COMBOS inflados ~20x. Ignorar esos meses para categorías de COMBOS.

**Ejemplo de fila:**
```
clasificacion_2_sheet = "Combo Big Mac"
sucursal              = 10
periodo               = "2025-06"
unidades              = NULL
forecast              = 1850
modelo                = NULL
mejor_modelo          = "share3"
```

---

### 3.2 `stg.fact_ventas`

**Qué es:** Cada fila es una línea de factura — un producto vendido en una transacción específica.
Es el registro más granular del negocio: cada venta individual de cada producto en cada restaurante.

**Columnas:**

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `fecha_hora` | TIMESTAMP | Fecha y hora exacta de la transacción |
| `fecha` | DATE | Fecha del día (sin hora) |
| `fecha_real` | DATE | Fecha real (puede diferir si hay cierres de caja nocturnos) |
| `fecha_comodin` | DATE | Fecha alternativa para reportes |
| `hora` | VARCHAR | Hora en texto |
| `tienda` | SMALLINT | Número de la sucursal |
| `caja` | SMALLINT | Número de caja registradora |
| `pod_origen` | SMALLINT | Punto de origen del pedido (mostrador, app, etc.) |
| `pod_area_venta` | VARCHAR | Área de venta (Salón, Drive-Thru, Delivery...) |
| `area_venta` | VARCHAR | Área física de la tienda |
| `no_resolucion` | VARCHAR | Número de resolución fiscal |
| `no_docu` | INTEGER | Número de documento de la transacción |
| `transaccion` | INTEGER | ID de la transacción |
| `no_serie` | VARCHAR | Número de serie del timbrado |
| `timbrado` | BIGINT | Número de timbrado fiscal (requerimiento impositivo Paraguay) |
| `nota_credito` | INTEGER | Indicador de nota de crédito |
| `nota_credito_resolucion` | VARCHAR | Resolución de nota de crédito |
| `tipo` | VARCHAR | Tipo de transacción |
| `para_aca_llevar` | VARCHAR | "Para acá" o "para llevar" |
| `cierre_ventas` | VARCHAR | Indicador de cierre de ventas |
| `cliente` | SMALLINT | ID del cliente (si aplica) |
| `idcliente` | VARCHAR | ID alternativo del cliente |
| `cajero` | VARCHAR | Código del cajero |
| `nombre_cajero` | VARCHAR | Nombre del cajero |
| `total_factura` | BIGINT | Total de la factura en Gs. |
| `monto_desc_factura` | BIGINT | Descuento aplicado a la factura en Gs. |
| `monto_factura` | BIGINT | Monto neto de la factura en Gs. |
| `monto_cambio_factura` | BIGINT | Vuelto de la factura en Gs. |
| `no_linea` | INTEGER | Número de línea dentro de la factura (1, 2, 3...) |
| `producto` | VARCHAR | **Código del producto vendido** — join con `dim_articulo_venta.codigo` |
| `descripcion` | VARCHAR | Descripción del producto |
| `cantidad` | INTEGER | **Unidades vendidas** (columna clave para todos los análisis) |
| `precio_u` | BIGINT | Precio unitario en Gs. |
| `sub_total` | BIGINT | Subtotal de la línea en Gs. |
| `porcentaje_proporcional` | NUMERIC | % proporcional del descuento |
| `descuento_asignado_producto` | NUMERIC | Descuento asignado a este producto |
| `precio_final_producto` | NUMERIC | Precio final después de descuentos |

**Join principal:**
```sql
JOIN stg.dim_articulo_venta dav
    ON CAST(fv.producto AS VARCHAR) = CAST(dav.codigo AS VARCHAR)
```
**Nota:** Ambas columnas se castean a VARCHAR para evitar problemas de tipo (producto es VARCHAR, codigo es BIGINT).

---

### 3.3 `stg.dim_articulo_venta`

**Qué es:** El catálogo de productos. Mapea cada código de producto a su nombre, categoría y tipo.
Es la tabla de dimensión más importante — sin ella, `fact_ventas` solo tiene códigos numéricos sin significado.

**Columnas:**

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `codigo` | BIGINT | Código PLU/barcode del producto — join con `fact_ventas.producto` |
| `descripcion` | VARCHAR | Nombre del producto (ej: "Big Mac 200g") |
| `clasificacion_2_sheet` | VARCHAR | Agrupación comercial de nivel 2 (ej: "Combo Big Mac") — **la más usada** |
| `tipo_sheet` | VARCHAR | Agrupación de nivel superior (ej: "COMBOS", "HAMBURGUESAS", "POSTRES") |
| `codigo_sheet` | VARCHAR | Código alternativo (puede coincidir con código de `precio_productos`) |

**Valores conocidos de `tipo_sheet`:** COMBOS, HAMBURGUESAS, POSTRES, CAJITAS FELICES, BEBIDAS, PAPAS, DESAYUNOS, MCCAFE, PENDIENTE (= sin clasificar aún)

**Ejemplo:**
```
codigo                = 8132
descripcion           = "McCombo CDL + Papas + Bebida Promo 2x1"
clasificacion_2_sheet = "Promo 2x1 Cuarto de Libra"
tipo_sheet            = "COMBOS"
```

**Nota importante sobre "Promo 2x1":**
Cuando McDonald's lanza un 2x1, crea un nuevo SKU específico (ej: "Promo 2x1 Cuarto de Libra") que solo existe durante la campaña. Este SKU tiene sus propios códigos y aparece en `fact_ventas` con miles de unidades el día de la promo. No tiene forecast propio en `forecast_ventas_sucursal`.

---

### 3.4 `stg.dim_restaurantes`

**Qué es:** Catálogo de todos los restaurantes McDonald's Paraguay.

**Columnas relevantes:**

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `api_id_integer` | INTEGER | ID numérico del restaurante — join con `apertura_restaurantes.api_id` |
| `short_name` | VARCHAR | Nombre corto del local (ej: "FDM", "SHO", "LRI") |
| `nombre` | VARCHAR | Nombre completo del local |
| `barrio` | VARCHAR | Barrio donde está ubicado |
| `distrito` | VARCHAR | Distrito |
| `departamento` | VARCHAR | Departamento |

**Join principal:**
```sql
JOIN stg.dim_restaurantes dr ON CAST(fv.tienda AS VARCHAR) = CAST(dr.api_id_integer AS VARCHAR)
```

---

## 4. TABLAS EN REDSHIFT — CARGADAS POR EL ETL

Estas tablas **las crea y llena** `mcdonalds_etl/etl_load.py` a partir de archivos Excel y CSV.

### 4.1 `simulacion.precio_productos`

**Qué es:** Precios históricos de cada producto por mes. Se usa para calcular elasticidades y para mostrar ingresos estimados en las simulaciones de precio.

**Columnas:**

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `codigo` | BIGINT | Código del producto — join con `dim_articulo_venta.codigo` |
| `descripcion` | VARCHAR(200) | Descripción del producto |
| `anio` | SMALLINT | Año (ej: 2024) |
| `mes` | SMALLINT | Mes (1-12) |
| `precio` | NUMERIC(12,2) | Precio del producto en ese mes en Gs. |

**PK:** `(codigo, anio, mes)`
**Origen:** Hoja "Precios" del Excel principal — columnas de fechas son las columnas, filas son productos.

---

### 4.2 `simulacion.promociones`

**Qué es:** Catálogo de todas las campañas promocionales históricas, con los productos que participaron y las fechas de cada campaña.

**Columnas:**

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `campania` | VARCHAR(500) | Nombre de la campaña (ej: "Día de la hamburguesa: 2x1 CDL") |
| `codigo` | BIGINT | Código del producto que participó en la campaña |
| `descripcion` | VARCHAR(200) | Descripción del producto |
| `fecha_desde` | DATE | Fecha de inicio de la campaña (viene del CSV calendario) |
| `fecha_hasta` | DATE | Fecha de fin de la campaña (viene del CSV calendario) |

**PK:** `(campania, codigo)` — Redshift no enforcea PKs, hay que deduplicar en el ETL.

**Origen doble:**
- Hoja "Códigos-Promo" del Excel → tiene campaña + código + descripción (sin fechas)
- CSV Calendario MKT → tiene campaña + fecha_desde + fecha_hasta (sin códigos de producto)
- El ETL mergea ambos priorizando el CSV (que tiene fechas) sobre el Excel (que tiene los códigos).

**Uso en el simulador:**
- Buscar campañas históricas similares para estimar uplift de 2x1 o producto gratis
- Obtener los códigos de producto de una campaña para medir sus ventas históricas en `fact_ventas`
- Filtrar por tipo de promo (2x1, gratis, descuento) inferido del nombre de la campaña

---

### 4.3 `simulacion.lanzamientos`

**Qué es:** Catálogo de lanzamientos históricos de productos, con los productos involucrados.

**Columnas:**

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `lanzamiento` | VARCHAR(500) | Nombre del lanzamiento (ej: "Lanzamiento McCombo Asunciónico") |
| `codigo` | BIGINT | Código del producto lanzado |
| `descripcion` | VARCHAR(200) | Descripción del producto |

**PK:** `(lanzamiento, codigo)`
**Origen:** Hoja "Códigos Lanzamientos" del Excel principal.

---

### 4.4 `simulacion.apertura_restaurantes`

**Qué es:** Lista de restaurantes con sus canales de venta habilitados. Un canal habilitado significa que el restaurante puede operar por ese medio.

**Columnas:**

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `api_id` | INT | ID del restaurante — join con `dim_restaurantes.api_id_integer` |
| `short_name` | VARCHAR(10) | Nombre corto (ej: "FDM") |
| `fecha_apertura` | DATE | Fecha en que abrió el restaurante |
| `tiene_mostrador` | BOOLEAN | ¿Tiene servicio de mostrador? (M en Excel) |
| `tiene_automac` | BOOLEAN | ¿Tiene Automac (drive-thru)? (A en Excel) |
| `tiene_delivery` | BOOLEAN | ¿Tiene delivery? (D en Excel) |
| `tiene_kiosco_digital` | BOOLEAN | ¿Tiene kiosco digital? (X en Excel) |
| `tiene_centro_postres` | BOOLEAN | ¿Tiene centro de postres? (K en Excel) |

**Origen:** Hoja "Aperturas" del Excel principal. Las columnas M/A/D/X/K son flags de canal.

---

### 4.5 `simulacion.competencia`

**Qué es:** Competidores cercanos a cada local McDonald's, con distancia y tipo de competidor.

**Columnas:**

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `local_numero` | INT | Número del local McDonald's |
| `short_name` | VARCHAR(10) | Nombre corto del local MCD |
| `competidor` | VARCHAR(200) | Nombre del competidor (ej: "Burger King Multiplaza") |
| `radio_km` | NUMERIC(4,1) | Distancia en kilómetros entre MCD y el competidor |
| `tipo` | VARCHAR(50) | Tipo de competidor (ej: "Hamburguesas", "Pollo", "Pizza") |

**PK:** `(local_numero, competidor)`
**Origen:** Excel de competencia (archivo separado).

---

### 4.6 `simulacion.locales_dimension`

**Qué es:** Atributos físicos y geográficos de cada local. Complementa `apertura_restaurantes` con datos de infraestructura.

**Columnas:**

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `short_name` | VARCHAR(10) | Nombre corto — join con `apertura_restaurantes.short_name` |
| `lat` | NUMERIC(10,7) | Latitud GPS (ej: -25.2867) |
| `lon` | NUMERIC(10,7) | Longitud GPS (ej: -57.6470) |
| `ciudad` | VARCHAR(100) | Ciudad donde está el local |
| `estado` | VARCHAR(100) | Estado/Departamento |
| `store_type` | VARCHAR(5) | Tipo de local: IS=Inline Store, FS=Free Standing, MS=Mall Store, FC=Food Court |
| `dt_type` | VARCHAR(10) | Tipo de Automac: Single=1 calle, Double=2 calles, NULL=sin Automac |
| `num_soks` | SMALLINT | Cantidad de kioscos de autoservicio (SOKs) |
| `bldg_size_m2` | NUMERIC(8,2) | Tamaño del edificio en m² |
| `land_size_m2` | NUMERIC(10,2) | Tamaño del terreno en m² |
| `tiene_mccafe` | BOOLEAN | ¿Tiene McCafé? |
| `tiene_playplace` | BOOLEAN | ¿Tiene área de juegos infantil? |
| `brand_extension` | VARCHAR(200) | Canales adicionales: Delivery, Desert Center, Walkup window, etc. |
| `last_reimage_date` | SMALLINT | Año del último reimage (renovación del local, ej: 2021) |

**PK:** `short_name`
**Origen:** Excel "Dimensión Locales". Las columnas de GPS estaban ocultas en el Excel y tienen un error de FDM que divide por 1,000,000.

---

## 5. TABLAS EN REDSHIFT — GENERADAS POR EL SIMULADOR

### 5.1 `simulacion.elasticidades`

**Qué es:** Elasticidades precio-demanda calculadas automáticamente por el simulador al primer uso.

**Columnas:**

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `clasificacion_2` | VARCHAR(200) | Categoría de producto |
| `elasticidad_precio` | FLOAT | Elasticidad promedio (Δ% unidades / Δ% precio). Negativa = baja de precio sube ventas |
| `n_productos` | INT | Cuántos productos distintos se usaron para calcularla |
| `n_cambios` | INT | Cuántos cambios de precio históricos se observaron |
| `precio_desde` | FLOAT | Precio mínimo histórico observado |
| `precio_hasta` | FLOAT | Precio máximo histórico observado |
| `confianza` | VARCHAR(10) | "alta" si n_cambios >= 2, "media" si n_cambios = 1 |
| `fecha_calculo` | TIMESTAMP | Cuándo se calculó |

**Default si no hay datos:** -0.5 con confianza "supuesto".

---

### 5.2 `simulacion.escenarios`

**Qué es:** Historial de todas las simulaciones que se corrieron. Cada `python run.py` guarda sus resultados acá.

**Columnas:** nombre del escenario, clasificacion_2, sucursal, periodo, forecast base, unidades simuladas, delta, tipo de palanca, timestamp, y todas las columnas adicionales que agrega cada palanca.

---

## 6. ARCHIVOS DE ENTRADA (EXCEL Y CSV)

### 6.1 Excel principal (variable: `EXCEL_PATH`)

Tiene 4 hojas que se cargan por separado:

#### Hoja "Precios"
```
Col A: (vacío / header)
Col B: codigo del producto (BIGINT)
Col C: descripcion del producto
Col D en adelante: una columna por mes, header = fecha (datetime de Excel)
                   el valor de cada celda = precio en Gs. para ese mes
```
El ETL hace "unpivot": convierte las columnas de meses en filas `(codigo, anio, mes, precio)`.

#### Hoja "Códigos-Promo"
```
Col A: nombre de la campaña (solo en la primera fila del grupo de productos)
Col B: codigo del producto (BIGINT)
Col C: descripcion del producto
Col D: fecha_desde de la campaña (DATE, opcional — generalmente vacío)
Col E: fecha_hasta de la campaña (DATE, opcional — generalmente vacío)
```
Las fechas reales vienen del CSV del calendario, no de acá.

#### Hoja "Códigos Lanzamientos"
```
Col A: nombre del lanzamiento (solo en la primera fila del grupo)
Col B: codigo del producto
Col C: descripcion del producto
```

#### Hoja "Aperturas"
```
Col A: api_id del restaurante
Col B: short_name
Col C: fecha_apertura
Col D: M (tiene_mostrador — "Y"/"N")
Col E: A (tiene_automac — "Y"/"N")
Col F: D (tiene_delivery — "Y"/"N")
Col G: X (tiene_kiosco_digital — "Y"/"N")
Col H: K (tiene_centro_postres — "Y"/"N")
```

---

### 6.2 Excel Dimensión Locales (variable: `EXCEL_LOCALES`)

Una fila por restaurante, hoja única. Las columnas de GPS estaban ocultas:

```
Col 0  (A): short_name
Col 1-6:    datos varios (nombre completo, dirección, etc.) — no se usan
Col 7  (H): lat (latitud GPS) — OCULTA en Excel original
Col 8  (I): lon (longitud GPS) — OCULTA en Excel original
Col 9  (J): brand_extension (canales extra: "Delivery, Desert Center")
Col 10 (K): last_reimage_date (año de renovación)
Col 14 (O): ciudad
Col 15 (P): estado/departamento
Col 16 (Q): store_type (IS/FS/MS/FC)
Col 17 (R): dt_type (Single/Double/None)
Col 18 (S): num_soks (cantidad de kioscos)
Col 19 (T): bldg_size_m2
Col 20 (U): land_size_m2
Col 21 (V): tiene_mccafe (Y/N)
Col 22 (W): tiene_playplace (Y/N)
```

**Corrección GPS para FDM:** El local FDM tiene coordenadas como `-25193188` (error de tipeo — falta el punto decimal). El ETL detecta `abs(valor) > 90` y divide por 1,000,000 para corregir a `-25.193188`.

---

### 6.3 CSV Calendario de Marketing (variable: `CSV_CALENDARIO`)

**Nombre:** `Calendario_de_acciones_historico_MKTParaguay.csv`
**Separador:** punto y coma (`;`)
**Encoding:** latin-1

**Estructura compleja:** el CSV tiene múltiples años en el mismo archivo, organizados por columnas:

```
Fila 1 (header de años):  ... | 2026 | ... | 2025 | ... | 2024 | ...
Fila 2 (header de cols):  ... | Inicio | Fin | Código | Descripcion | Inicio | Fin | ...
Col 1:  mes en español (ENERO, FEBRERO, ...) — se hereda hasta que cambia
Col 2:  inicio del evento (día del mes, puede ser "6 al 16", "22-ene", "Vigente")
Col 3:  fin del evento
Col 4:  códigos de productos (pueden ser múltiples separados por salto de línea)
Col 5:  descripción/nombre de la campaña
(luego se repite el bloque para el año anterior)
```

**Formatos de fecha soportados:**
- `"15"` → día simple del mes actual
- `"6 al 16"` → rango: inicio=6, fin=16
- `"6, 13, 20 y 27"` → múltiples días: inicio=6, fin=27
- `"22-ene"` → día y mes abreviado (sin año → usa el año de la columna)
- `"09-abr-26"` → día, mes y año de 2 dígitos
- `"Vigente"` → campaña permanente, se omite (sin fecha exacta)
- `""` (vacío) → sin fecha, se omite

**Formatos de código soportados:**
- `"9546"` → código simple
- `"9546.9547.9548"` → múltiples separados por punto
- `"9.158"` → el punto es separador de miles → se convierte a `9158`
- Solo se aceptan códigos entre 100 y 999999

---

### 6.4 Excel Competencia (variable: `EXCEL_COMPETENCIA`)

Una fila por competidor por local:

```
Col A: local_numero (INT)
Col B: short_name del local MCD
Col C: nombre del competidor
Col D: radio_km (distancia en km)
Col E: tipo de competidor
```

---

## 7. RELACIONES ENTRE TABLAS

```
fact_ventas.producto ──────────────────── dim_articulo_venta.codigo
fact_ventas.tienda ────────────────────── dim_restaurantes.api_id_integer

forecast_ventas_sucursal.clasificacion_2_sheet ── dim_articulo_venta.clasificacion_2_sheet
forecast_ventas_sucursal.sucursal ──────────────── dim_restaurantes.api_id_integer (implícito)

precio_productos.codigo ────────────────── dim_articulo_venta.codigo
                                           (con CAST a VARCHAR en ambos lados)

promociones.codigo ─────────────────────── dim_articulo_venta.codigo
lanzamientos.codigo ────────────────────── dim_articulo_venta.codigo

apertura_restaurantes.api_id ──────────── dim_restaurantes.api_id_integer
locales_dimension.short_name ──────────── apertura_restaurantes.short_name
competencia.local_numero ──────────────── dim_restaurantes.api_id_integer (implícito)
```

**Nota sobre tipos:** En casi todos los joins se necesita `CAST(... AS VARCHAR)` porque algunos IDs están como INT en una tabla y VARCHAR en otra. Es un problema histórico de cómo se construyó el DW.

---

## 8. ETL — mcdonalds_etl/

### 8.1 `create_tables.sql`

DDL de las 6 tablas que crea el ETL. Se usa `CREATE TABLE IF NOT EXISTS` para no fallar si ya existen. El schema se inyecta con `{schema}` que Python reemplaza con el valor de `REDSHIFT_SCHEMA`.

Diseño de distribución en Redshift:
- `precio_productos`: `DISTKEY(codigo) SORTKEY(anio, mes)` — optimizado para joins por código y búsquedas por período
- `promociones`, `lanzamientos`, `competencia`, `apertura_restaurantes`, `locales_dimension`: `DISTSTYLE ALL` — son tablas pequeñas, se replican en todos los nodos para joins eficientes

### 8.2 `etl_load.py`

**Función `main()`:**
1. Lee las 4 hojas del Excel principal
2. Parsea el CSV del calendario de marketing
3. Mergea promociones (CSV con fechas + Excel con códigos), deduplicando y priorizando fechas del CSV
4. Parsea Excel de competencia
5. Parsea Excel de dimensión de locales
6. Conecta a Redshift
7. Crea tablas (si no existen)
8. Hace TRUNCATE + INSERT para cada tabla (reemplaza todo en cada corrida)

**Función `truncate_and_insert(conn, table, columns, rows)`:**
- Hace `TRUNCATE TABLE` para borrar datos anteriores
- Inserta en lotes de `BATCH_SIZE` usando `execute_values` de psycopg2 (inserción masiva eficiente)
- Commitea al final

**Función `parse_precio_productos(ws)`:**
- Lee la hoja "Precios"
- Detecta columnas de fechas en el header (son objetos `datetime` de Excel)
- Para cada producto (fila) y cada mes (columna): genera una fila `(codigo, descripcion, anio, mes, precio)`
- Omite filas sin código o con precio vacío/nulo

**Función `parse_promociones(ws)`:**
- Lee la hoja "Códigos-Promo"
- La campaña está solo en la primera fila de cada grupo → se hereda con `current_campania`
- Las fechas opcionales en cols D y E se parsean con `_parse_fecha(valor)`
- Genera `(campania, codigo, descripcion, fecha_desde, fecha_hasta)`

**Función `_parse_fecha(valor)`:**
- Convierte `datetime`/`date` de Excel a string `"YYYY-MM-DD"`
- Si es string, toma los primeros 10 caracteres (por si viene con hora)
- Retorna `None` si está vacío

**Función `parse_calendario_csv(path)`:**
- Detecta los años en el header buscando `re.match(r'^20\d\d$', v)` en las primeras 10 filas
- Mapea año → columna base (ej: 2026 → col 2, 2025 → col 6, 2024 → col 10)
- Hereda el mes de la col 1 cuando encuentra "ENERO", "FEBRERO", etc.
- Para cada año detectado, lee los campos `Inicio`, `Fin`, `Código`, `Descripcion`
- Parsea fechas con `_parsear_fecha(texto, year, mes, tipo)` donde `tipo` es "inicio" o "fin"
- Extrae códigos con `_extraer_codigos(texto)`: maneja miles con punto, múltiples por línea
- Solo incluye filas donde `fecha_desde` no es None (descarta eventos sin fecha)
- Deduplica por `(campania, codigo, fecha_desde)` para evitar duplicados entre años

**Función `parse_locales_dimension(path)`:**
- Lee con `openpyxl` en modo `read_only=True, data_only=True` para ignorar fórmulas
- Columna 7 = lat, columna 8 = lon — **estaban ocultas** en el Excel original
- `_fix_gps(v)`: si `abs(valor) > 90`, divide por 1,000,000 (corrige error de FDM)
- `_yn(v)`: convierte "Y"/"N" a True/False para los campos booleanos

**Deduplicación al mergear Excel + CSV:**
```python
# CSV va primero → sus fechas tienen prioridad
for r in promo_csv + promo_excel:
    key = (campania, codigo)
    if key no existe → agregar
    if existe pero sin fecha y este tiene fecha → reemplazar
```

---

## 9. SIMULADOR — mcdonalds_simulator/

### 9.1 `run.py` — Punto de entrada

**Qué hace paso a paso:**

1. **Configura logging:** Formato `HH:MM:SS [LEVEL] mensaje` en consola
2. **Lee argumentos:** `--scenario` (default: `scenario.yaml`)
3. **Verifica que el YAML existe:** Si no, imprime error y termina
4. **Carga el YAML:** `yaml.safe_load()` → diccionario Python
5. **Asegura elasticidades:** `_asegurar_elasticidades()` — si la tabla está vacía, la calcula (primera vez tarda ~30 segundos)
6. **Corre el escenario:** `correr_escenario(config)` → devuelve `(df, nombre)`
7. **Si df está vacío:** error y termina
8. **Formatea:** `resumen_consola(df, nombre, [palanca_activa])` → string con el reporte visual
9. **Imprime** el reporte en consola
10. **Guarda CSV:** `guardar(df, nombre, [palanca_activa])` → archivo en `output/resultados/`

---

### 9.2 `core/engine.py` — Motor del simulador

**Función `correr_escenario(config)`:**

1. **Extrae nombre:** del YAML (`escenario.nombre`)
2. **Busca la palanca activa:** primera palanca con `activo: true`; si ninguna, error
3. **Valida el tipo:** debe ser uno de: precio, promocion, lanzamiento, estructural, competencia, clima
4. **Resuelve fechas:**
   - Si el YAML tiene `fecha_desde` (formato YYYY-MM-DD) → extrae el período YYYY-MM de ella
   - Si el YAML tiene `periodo_desde` (formato YYYY-MM) → lo usa directamente
5. **Resuelve clasificacion_2:**
   - Llama `resolver_clasificacion_2(texto)` que hace fuzzy matching contra la DB
   - Si no encuentra nada → error
6. **Carga el forecast baseline:** `load_forecast(clf2_exactos, sucursal, periodo_desde, periodo_hasta)`
7. **Si el forecast está vacío:** imprime qué filtros se aplicaron y termina
8. **Importa dinámicamente el módulo de la palanca:** `importlib.import_module("palancas.precio")`
9. **Llama `modulo.aplicar(df, params, periodo_desde, periodo_hasta)`**
10. **Si la palanca no agrega `unidades_simuladas`:** la copia del forecast (sin cambio)
11. **Retorna `(df, nombre)`**

---

### 9.3 `core/loader.py` — Acceso a datos

#### `_score_fuzzy(query, candidato)`

**Propósito:** Dar un puntaje de similitud entre un texto del usuario y un nombre de clasificación.

**Algoritmo:**
1. Si el query completo está contenido en el candidato → retorna 100.0 (match exacto)
2. Divide en palabras (mínimo 2 caracteres)
3. **Bonus por substring:** para cada palabra del query, si aparece dentro del candidato → +2.0 / n_palabras
4. **Score fuzzy por palabra:** para cada palabra del query, toma el máximo `SequenceMatcher.ratio()` contra todas las palabras del candidato, promedia
5. Retorna `word_ratio + substring_bonus`

**Umbral mínimo:** 1.5 — si el mejor candidato tiene score < 1.5, se considera que no hay match y se retorna error.

#### `resolver_clasificacion_2(texto)`

**Propósito:** Convertir texto libre del usuario (ej: "big mac") al nombre exacto en la DB (ej: "Big Mac").

**Algoritmo:**
1. Divide el texto en palabras de más de 2 caracteres
2. Intenta un `AND` exacto en la DB: `LOWER(clasificacion_2_sheet) LIKE '%big%' AND LIKE '%mac%'`
3. Si devuelve exactamente 1 resultado → lo usa (match exacto, muy confiable)
4. Si devuelve 0 o más de 1 → trae TODOS los candidatos de la DB y aplica `_score_fuzzy`
5. Ordena por score descendente
6. Si el mejor score < 1.5 → logea error y retorna `[]`
7. Si el score es bueno → logea la resolución y retorna `[mejor_candidato]`

#### `load_forecast(clasificacion_2, sucursal, periodo_desde, periodo_hasta)`

**Qué retorna:** DataFrame con columnas `[clasificacion_2, sucursal, periodo, forecast]`

**Filtros aplicados:**
- `periodo >= periodo_desde AND periodo <= periodo_hasta`
- `mejor_modelo IS NOT NULL` (filtra para quedarse con el forecast seleccionado, no con todas las corridas de modelos)
- Si `clasificacion_2` no es None → filtra por esas clasificaciones exactas
- Si `sucursal` no es None → filtra por esa sucursal

**Columna `forecast` del resultado:** `COALESCE(forecast, unidades)` — usa el forecast del modelo si existe, sino usa las unidades históricas reales.

#### `load_precio_clasificacion2(clasificacion_2, periodo_desde, periodo_hasta)`

**Qué retorna:** DataFrame con `[clasificacion_2, periodo, precio_promedio_ponderado]`

**Cómo calcula el precio ponderado:**
```sql
SUM(pp.precio * fv.cantidad) / SUM(fv.cantidad)
```
Es el precio promedio ponderado por volumen vendido — más preciso que un simple promedio.

#### `load_ventas_historicas(clasificacion_2, sucursal, periodo_desde, periodo_hasta)`

**Qué retorna:** DataFrame con ventas reales de `fact_ventas` agregadas por clasificacion_2 + sucursal + período.

#### `load_fechas_campania(clasificacion_2, tipo_sheet, campanas)`

**Qué retorna:** DataFrame con `[campania, fecha_desde, fecha_hasta]` para campañas que tienen fechas.

**Tres modos:**
1. Si se pasa `campanas` (lista de nombres) → filtra exactamente esas campañas
2. Si se pasa `tipo_sheet` → filtra por tipo_sheet via join con dim_articulo
3. Si no → filtra por clasificacion_2_sheet exacta

---

### 9.4 `core/db.py` — Conexión

Lee las variables de entorno al importar. Dos funciones principales:

- **`query_df(sql, params)`:** Ejecuta SQL y retorna DataFrame. Usa una conexión nueva por query (sin connection pool). En caso de error que NO sea tabla inexistente, loguea el SQL fallido completo.
- **`execute(sql, params)`:** Ejecuta SQL sin retornar resultados (para DDL e INSERT). Commitea automáticamente.

---

### 9.5 `core/elasticidades.py` — Cálculo de elasticidades

**Concepto:** La elasticidad mide cuánto cambian las ventas cuando cambia el precio.
- Elasticidad = -2.0 significa: si el precio sube 10%, las ventas bajan 20%
- Elasticidad = -0.5 (default) significa: si el precio sube 10%, las ventas bajan 5%

**Cómo se calcula (`calcular_y_guardar()`):**

1. **`precios_con_lag`:** Para cada producto en `precio_productos`, calcula el precio del mes anterior con `LAG(precio)`
2. **`cambios_precio`:** Filtra solo los meses donde hubo cambio de precio; calcula `(precio_actual - precio_anterior) / precio_anterior`
3. **`ventas_por_producto`:** Agrega `fact_ventas` por producto y período → total de unidades por mes
4. **`ventas_con_lag`:** Igual que precios, calcula las unidades del mes anterior con `LAG(unidades)`
5. **`cambios_cantidad`:** Calcula `(unidades - unidades_anterior) / unidades_anterior`
6. **`elasticidades_por_producto`:** Hace JOIN entre cambios de precio y cambios de cantidad en el mismo producto y período → `elasticidad = cambio_pct_cantidad / cambio_pct_precio`
   - Filtra cambios de precio > 0.1% (evita ruido)
   - Filtra elasticidades absolutas > 10 (evita outliers extremos)
7. **`con_clasificacion`:** Join con `dim_articulo_venta` para agregar por `clasificacion_2_sheet`
8. **Resultado final:** Promedio de elasticidades para cada clasificacion_2

**`get_elasticidad(clasificacion_2)`:**
- Busca la elasticidad en la tabla
- Si no encuentra → retorna `(-0.5, "supuesto")`
- Niveles de confianza: "alta" si ≥ 2 cambios observados, "media" si solo 1

---

## 10. PALANCAS — CASO POR CASO

### 10.1 `palancas/precio.py` — Palanca de Precio

**¿Cuándo usar?** Cuando se quiere simular qué pasa si sube o baja el precio de una categoría.

**Modos:**

#### Modo `simular`

Aplica un cambio de precio fijo y calcula el impacto.

**Parámetros requeridos:** `cambio_pct` (ej: 0.10 = +10%, -0.05 = -5%)

**Fórmula completa:**
```
impacto_volumen    = cambio_pct × elasticidad
unidades_simuladas = forecast × (1 + impacto_volumen)

precio_simulado    = precio_base × (1 + cambio_pct)
ingreso_base       = forecast × precio_base
ingreso_simulado   = unidades_simuladas × precio_simulado
```

**Ejemplo concreto:**
```
forecast        = 1000 unidades
cambio_pct      = +0.10 (+10% de precio)
elasticidad     = -1.5
impacto_volumen = 0.10 × (-1.5) = -0.15 → -15% en unidades
unidades_sim    = 1000 × (1 - 0.15) = 850 unidades
precio_base     = Gs. 25.000
precio_sim      = Gs. 25.000 × 1.10 = Gs. 27.500
ingreso_base    = 1000 × 25.000 = Gs. 25.000.000
ingreso_sim     = 850 × 27.500 = Gs. 23.375.000 → baja el ingreso
```

#### Modo `optimizar`

Busca el cambio de precio que maximiza el objetivo, probando cada 1% dentro del rango.

**Objetivos:**
- **`max_ingreso`:** Encuentra el % de cambio que maximiza `unidades_simuladas × precio_simulado`. Generalmente hay un punto óptimo donde el aumento de precio compensa la caída de volumen.
- **`max_unidades`:** Encuentra el % que maximiza unidades. En teoría siempre baja el precio (más barato = más unidades).
- **`breakeven`:** Encuentra la máxima suba de precio donde el ingreso total no cae respecto al baseline. Es el límite seguro de suba.

**Parámetros:** `rango_desde` (ej: -0.30), `rango_hasta` (ej: 0.30)

**Cómo funciona internamente:**
1. Crea un array de pasos: `[-0.30, -0.29, -0.28, ..., 0.00, 0.01, ..., 0.30]`
2. Para cada paso, llama `_aplicar_cambio()` y calcula unidades e ingreso resultantes
3. Construye un DataFrame con todos los resultados
4. Para `max_ingreso`: `idxmax()` sobre columna ingreso
5. Para `breakeven`: filtra pasos ≥ 0 donde ingreso ≥ ingreso_base, toma el máximo

---

### 10.2 `palancas/promocion.py` — Palanca de Promoción

**¿Cuándo usar?** Para simular el impacto de una promoción en un período de fechas específico.

**Concepto clave — Escalado por días:**
El forecast está en unidades por mes. Si la promo dura solo 3 días:
```
forecast_mensual  = 1000 unidades
días_del_mes      = 30
forecast_promo    = 1000 / 30 × 3 = 100 unidades  ← base de comparación
```

**Subtipos:**

#### Subtipo `descuento`

Para descuentos porcentuales (ej: "20% OFF en Big Mac").

**Fórmula:**
```
impacto = cambio_pct × elasticidad     (cambio_pct es negativo, ej: -0.20)
unidades_simuladas_promo = forecast_promo × (1 + impacto)
delta = unidades_simuladas_promo - forecast_promo
```

**Función interna:** `_calcular_promo_elasticidad(df, subtipo, params, fecha_desde, fecha_hasta)`
- Calcula el forecast del período de promo escalado por días
- Llama `get_elasticidad()` para obtener la elasticidad de la categoría
- Aplica la fórmula

#### Subtipo `2x1`

Para promociones "lleva 2, paga 1".

**La lógica histórica (incorrecta):** Se usaba elasticidad aplicando -50% de descuento. Esto no reflejaba la realidad porque en un 2x1 el cliente paga el precio normal pero recibe 2 productos.

**La lógica actual (correcta):** Se mide el **uplift real** de campañas 2x1 históricas.

**Función `_uplift_2x1(clasificacion_2, fecha_desde, fecha_hasta)`:**

1. **Busca campañas similares:** `_campanias_similares(clasificacion_2, "2x1")`
   - Primero busca campañas 2x1 del mismo `tipo_sheet` (misma familia de productos)
   - Si no hay → busca 2x1 en TODA la tabla de promociones (cross-categoría)
   - Filtra por `_inferir_tipo_promo(nombre_campania)` que detecta "2x1" en el nombre

2. **Busca fechas de esas campañas:** `load_fechas_campania(campanas=campanias)`

3. **Para cada campaña con fechas:** llama `_uplift_con_fechas()`

**Función `_uplift_con_fechas(campanias, clasificacion_2, tipo_sheet)`:**

Para cada campaña que tiene `fecha_desde` en la DB:

1. **Obtiene los clasificacion_2_sheet de la campaña:** con `_datos_campania(campania)`
   - Hace JOIN entre `promociones` y `dim_articulo_venta` para obtener los clf2 de los productos de la campaña
   
2. **Ventas reales:** Suma `fact_ventas.cantidad` para todos los productos de esos clf2 en el período de la campaña

3. **Forecast baseline:** Si los clf2 de la campaña tienen forecast → lo usa directamente.
   Si NO tienen forecast (como "Promo 2x1 Cuarto de Libra") → fallback:
   - Obtiene el `tipo_sheet` de esos clf2
   - Busca TODAS las clasificaciones del mismo `tipo_sheet`
   - Usa el forecast de esas clasificaciones como baseline
   - También recalcula las ventas a nivel `tipo_sheet` para comparar manzanas con manzanas

4. **Forecast diario:** `fc_mensual / n_meses / días_del_mes`

5. **Forecast del período:** `fc_diario × n_días_campaña`

6. **Uplift:** `(ventas_reales - forecast_período) / forecast_período`

7. **Promedia** los uplifts de todas las campañas y asigna confianza (alta ≥ 3, media ≥ 1)

**Si no hay campañas con fechas:** usa el supuesto `UPLIFT_2X1_DEFAULT = 0.40` (+40%)

**Aplicación del uplift:**
```
unidades_simuladas_promo = forecast_promo × (1 + uplift)
delta = unidades_simuladas_promo - forecast_promo
```
El resultado se muestra SOLO para el período de promo, no para todo el mes.

#### Subtipo `precio_fijo`

Similar a `descuento` pero el `cambio_pct` se calcula como `(precio_fijo - precio_actual) / precio_actual`.

#### Subtipo `producto_gratis`

Igual que `2x1` pero busca campañas de tipo "producto gratis" y usa `UPLIFT_GRATIS_DEFAULT = 0.10` (+10%) como supuesto.

**Función `_inferir_tipo_promo(campania)`:**
Detecta el tipo de promo por palabras clave en el nombre de la campaña:
- Contiene "2x1" → tipo "2x1"
- Contiene "gratis", "regalo", "te llevás" → tipo "producto_gratis"
- Contiene "gs.", " mil", "miles" → tipo "precio_fijo"
- Contiene "% off", "% de desc" → tipo "descuento_pct"
- Cualquier otro → tipo "otro"

**Filtro por canal (`canal` en YAML):**
Si se especifica `canal: automac`, la palanca solo aplica a las sucursales que tienen Automac habilitado (join con `apertura_restaurantes`).

---

### 10.3 `palancas/lanzamiento.py` — Palanca de Lanzamiento

**¿Cuándo usar?** Para estimar el impacto de lanzar un nuevo producto o retomar un producto existente.

**Concepto clave — Curva de lanzamiento:**
Cuando se lanza un producto nuevo, hay un patrón típico de adopción:
- Mes 0 (lanzamiento): +18% sobre el forecast base (hype inicial)
- Mes 1: +12%
- Mes 2: +7%
- Mes 3: +4%
- Mes 4: +2%
- Mes 5+: 0% (normalización)

**Dos modos:**

#### Con `proxy_lanzamiento`

Si se especifica el nombre de un lanzamiento histórico similar, usa la curva real de ese lanzamiento.

Internamente:
1. Busca el lanzamiento en `simulacion.lanzamientos` por nombre (fuzzy matching)
2. Obtiene los `clasificacion_2_sheet` de ese lanzamiento via `dim_articulo_venta`
3. Busca en `fact_ventas` las ventas mensuales de esos clf2 desde el primer mes de venta
4. Construye la curva de uplift: `(ventas_mes_N - forecast_baseline) / forecast_baseline` para cada mes relativo
5. Aplica esa curva al forecast del período simulado

#### Sin proxy (curva default)

Usa la curva default: `[0.18, 0.12, 0.07, 0.04, 0.02, 0.00, ...]`

**Aplicación:**
Para cada mes del período simulado:
```
mes_relativo = mes_actual - mes_lanzamiento
uplift       = curva[mes_relativo]  (o 0.0 si supera la duración de la curva)
unidades_sim = forecast × (1 + uplift)
```

---

### 10.4 `palancas/estructural.py` — Palanca Estructural

**¿Cuándo usar?** Para estimar qué pasa si un local agrega un nuevo canal (ej: habilitar Delivery en un local que no lo tiene).

**Concepto clave — Comparación de pares:**
Compara las ventas de locales que YA TIENEN el canal habilitado contra los que NO lo tienen.
```
efecto = (ventas_con_canal - ventas_sin_canal) / ventas_sin_canal
```

**Parámetro `canal`:** "automac", "delivery", "kiosco_digital", "mostrador", "centro_postres"

**Parámetro `zona`:** "barrio", "distrito", "dpto" — para hacer la comparación entre locales de la misma zona (más justo)

**Pasos internos:**
1. Carga `apertura_restaurantes` para saber qué locales tienen el canal
2. Si hay zona especificada → filtra por locales de la misma zona
3. Calcula promedio de ventas del período para locales CON y SIN el canal
4. Calcula el efecto porcentual
5. Aplica ese efecto al forecast del local objetivo:
   ```
   unidades_sim = forecast × (1 + efecto)
   ```

---

### 10.5 `palancas/competencia.py` — Palanca de Competencia

**¿Cuándo usar?** Para estimar el impacto de un nuevo competidor que abre cerca de un local MCD.

**Concepto clave — Comparación por distancia:**
Busca locales MCD que ya tienen un competidor a distancia similar y compara sus ventas con locales sin competidor cercano.

**Pasos:**
1. Carga `simulacion.competencia` para saber qué locales tienen competidores y a qué distancia
2. Busca locales con competidores en el rango `distancia_km ± 0.3 km` (banda de tolerancia)
3. Si hay suficientes locales con esa banda → calcula el efecto estadístico
4. Si no hay suficientes → usa tablas de fallback por banda de distancia:
   - < 300m → -15%
   - 300-600m → -10%
   - 600m-1km → -5%
   - > 1km → -2%

---

### 10.6 `palancas/clima.py` — Palanca de Clima

**¿Cuándo usar?** Para simular cómo afecta el clima (ej: una ola de calor, lluvias intensas) a las ventas.

**Concepto clave — Coeficientes de sensibilidad:**
Cada categoría de producto tiene diferente sensibilidad al clima:
```python
COEF_CLIMA = {
    "McFlurry":    -0.40,   # muy sensible: con frío se vende mucho menos
    "Sundae":      -0.35,
    "McCafe":      +0.20,   # con frío se vende más (café caliente)
    "Bebidas":     -0.15,
    "Combos":      -0.05,   # poco sensible
    "default":     -0.05,
}
```

**Fórmula:**
```
efecto = variacion_temperatura_pct × coef_clima[categoria]
unidades_sim = forecast × (1 + efecto)
```

**Nota:** Esta palanca es 100% basada en supuestos, no en datos históricos. El coeficiente de clima es una estimación del equipo.

---

## 11. OUTPUT Y RESULTADOS

### `output/formatter.py` — Reporte en consola

**Función `resumen_consola(df, nombre, palancas_activas)`:**

Genera el texto del reporte que se imprime. Estructura:

```
═══════════════════════════════════
  SIMULADOR MCD — [nombre escenario]
═══════════════════════════════════
  Período:              2025-06
  Categoría:            Big Mac
  Sucursales afectadas: 29
  Palanca:              PROMOCION
───────────────────────────────────
  RESULTADOS
  Unidades base (mes):      15.000
  Unidades simuladas:       18.000
  Delta unidades:       +3.000 (+20.0%)
  [Ingresos si hay precio]
───────────────────────────────────

  POR QUÉ ESTE RESULTADO
  [Explicación detallada según el tipo de palanca]

═══════════════════════════════════
```

**Sección "POR QUÉ ESTE RESULTADO":**
Cada palanca tiene su propia lógica de justificación:
- **Precio:** muestra la elasticidad usada, su confianza, el impacto calculado
- **Promoción:** muestra si usó uplift medido o supuesto, las campañas históricas de referencia, y su confianza
- **Lanzamiento:** muestra la curva usada y si fue de un proxy histórico
- **Estructural:** muestra cuántos locales se compararon y el efecto medido
- **Competencia:** muestra si usó datos históricos o la tabla de fallback
- **Clima:** advierte que es basado en supuestos

**`_explicar_confianza(lines, confianza, valor)`:**
Agrega una línea explicando qué tan confiable es el número:
- "alta" → "Basado en X cambios de precio históricos observados en datos reales"
- "media" → "Solo se observó 1 cambio de precio — tratar como orientativo"
- "supuesto" → "No hay datos históricos. Se usó el valor por defecto..."

### `output/writer.py` — Guardado de resultados

Guarda el DataFrame resultado como CSV en `output/resultados/[nombre_escenario].csv`.
También inserta los resultados en `simulacion.escenarios` en Redshift para historial.

---

## 12. SCENARIO.YAML — GUÍA DE USO

El archivo YAML tiene dos secciones:

```yaml
escenario:
  nombre: "Nombre descriptivo del escenario"

palancas:
  - tipo: precio
    activo: false   ← solo una puede ser true
    ...
  - tipo: promocion
    activo: true    ← esta es la que corre
    ...
```

### Parámetros comunes a TODAS las palancas

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `tipo` | string | Una de: precio, promocion, lanzamiento, estructural, competencia, clima |
| `activo` | bool | Solo una palanca puede tener `true` |
| `clasificacion_2` | string | Nombre de la categoría (fuzzy matching activo — no tiene que ser exacto) |
| `sucursal` | int o null | Número de sucursal. `null` = todas |
| `fecha_desde` | YYYY-MM-DD | Fecha de inicio (se extrae período YYYY-MM de aquí) |
| `fecha_hasta` | YYYY-MM-DD | Fecha de fin (puede ser el mismo día para un evento de 1 día) |

### Parámetros específicos por palanca

**Precio — simular:**
```yaml
modo: simular
cambio_pct: 0.10    # +10% de precio
```

**Precio — optimizar:**
```yaml
modo: optimizar
objetivo: max_ingreso   # o max_unidades o breakeven
rango_desde: -0.30
rango_hasta: 0.30
```

**Promoción:**
```yaml
subtipo: 2x1         # o descuento, precio_fijo, producto_gratis
cambio_pct: -0.20    # solo para descuento (negativo = descuento)
canal: automac       # opcional: automac, delivery, app, restaurante, null=todos
```

**Lanzamiento:**
```yaml
proxy_lanzamiento: "Lanzamiento McCombo Asunciónico"  # opcional
meses_proyeccion: 6
```

**Estructural:**
```yaml
canal: delivery
zona: barrio         # opcional: barrio, distrito, dpto
```

**Competencia:**
```yaml
competidor: "Burger King"
distancia_km: 0.5
```

**Clima:**
```yaml
variacion_temperatura_pct: -0.15   # -15% de temperatura relativa
```

---

## 13. FLUJO COMPLETO DE UNA SIMULACIÓN

Ejemplo: "¿Qué pasaría si hacemos un 2x1 en Big Mac el 20 de junio de 2026?"

### Paso 1: Usuario edita scenario.yaml
```yaml
palancas:
  - tipo: promocion
    activo: true
    clasificacion_2: "big mac"
    fecha_desde: "2026-06-20"
    fecha_hasta: "2026-06-20"
    subtipo: 2x1
```

### Paso 2: `run.py` inicia
- Carga el YAML
- Verifica que la tabla de elasticidades existe (si no, la calcula)
- Llama `correr_escenario(config)`

### Paso 3: `engine.py` procesa
- Extrae `fecha_desde = "2026-06-20"` → `periodo_desde = periodo_hasta = "2026-06"`
- Llama `resolver_clasificacion_2("big mac")`
  - Busca `LIKE '%big%' AND LIKE '%mac%'` en la DB → 1 resultado → "Big Mac"
- Llama `load_forecast(["Big Mac"], None, "2026-06", "2026-06")`
  - Query: `SELECT clasificacion_2_sheet, sucursal, periodo, COALESCE(forecast,unidades) FROM forecast WHERE mejor_modelo IS NOT NULL AND periodo BETWEEN '2026-06' AND '2026-06' AND clasificacion_2_sheet IN ('Big Mac')`
  - Resultado: 29 filas (una por sucursal)
- Importa `palancas.promocion` y llama `aplicar(df, params, ...)`

### Paso 4: `palancas/promocion.py` calcula
- Detecta `subtipo = "2x1"`
- Calcula días: 1 día (del 20 al 20)
- Calcula `forecast_promo = forecast_mensual / 30 × 1`
- Llama `_uplift_2x1("Big Mac", "2026-06-20", "2026-06-20")`
  - Busca campañas 2x1 en COMBOS (tipo_sheet de Big Mac)
  - No hay 2x1 en COMBOS específicamente → busca en toda la tabla → 16 campañas
  - Busca cuáles tienen `fecha_desde` en `simulacion.promociones` → 5-6 campañas con fechas
  - Para cada campaña con fecha: consulta ventas reales en `fact_ventas` durante esa fecha
    - Ejemplo: "Día de la hamburguesa: 2x1 CDL" (2025-05-28)
    - Los códigos de esta campaña → clf2 = "Promo 2x1 Cuarto de Libra"
    - Ventas reales en fact_ventas para ese clf2 el 2025-05-28 = 43.672 unidades
    - "Promo 2x1 CDL" no tiene forecast propio → fallback: usa forecast de tipo_sheet COMBOS
    - Forecast diario COMBOS 2025-05 = 506.282 / 31 ≈ 16.341 unidades/día
    - Uplift = (43.672 - 16.341) / 16.341 ≈ +167%
  - Promedia uplifts de todas las campañas → resultado final: ~+68% confianza alta
- Aplica: `unidades_simuladas = forecast_promo × 1.68`
- Agrega columnas: `promo_uplift`, `promo_confianza`, `promo_campanias`, etc.

### Paso 5: `formatter.py` genera el reporte
- Calcula totales: sum(forecast_promo), sum(unidades_simuladas)
- Calcula delta y % de cambio
- Construye la sección "POR QUÉ": muestra el uplift, su confianza, las campañas históricas de referencia
- Imprime en consola

### Paso 6: `writer.py` guarda
- CSV en `output/resultados/nombre_escenario.csv`
- INSERT en `simulacion.escenarios`

---

## 14. PROBLEMAS CONOCIDOS Y LIMITACIONES

### Datos

1. **Forecast inflado en 2026-03, 2026-04, 2026-05 para COMBOS:** Los valores son ~20x más grandes de lo normal. Causa desconocida (posible error del modelo de forecast). Evitar usar el simulador para períodos COMBOS en esos 3 meses hasta que se corrija.

2. **"Promo 2x1" SKUs sin forecast:** Los productos especiales de campaña (ej: "Promo 2x1 Cuarto de Libra") no tienen forecast propio en `forecast_ventas_sucursal`. El simulador resuelve esto con un fallback al `tipo_sheet`, pero el cálculo es menos preciso.

3. **Fechas de campañas incompletas:** De las 16 campañas 2x1 históricas, solo 5-6 tienen `fecha_desde` cargada en `simulacion.promociones`. Las otras solo existen en el Excel sin fecha.

4. **Columna `modelo` siempre NULL:** En `forecast_ventas_sucursal`, `modelo` es siempre NULL y el modelo seleccionado está en `mejor_modelo`. El filtro correcto es `mejor_modelo IS NOT NULL`.

### Código

5. **Sin connection pool:** Cada `query_df()` abre y cierra una conexión a Redshift. Para simulaciones complejas esto puede ser lento. No es un problema para uso individual pero sería un cuello de botella en uso concurrente.

6. **Fuzzy matching solo devuelve 1 resultado:** `resolver_clasificacion_2()` siempre devuelve el mejor match. Si el usuario quiere simular múltiples categorías similares, debe correr el simulador varias veces.

7. **`palancas/clima.py` basado en supuestos:** Los coeficientes de sensibilidad climática no están basados en datos históricos sino en estimaciones del equipo. Los resultados de esta palanca son orientativos.

8. **ETL hace TRUNCATE + INSERT:** Cada corrida del ETL borra y recarga todos los datos. No hay historial incremental. Si hay un error en el Excel de origen, se pierden todos los datos anteriores.

### Para el desarrollo con Claude AI

9. **Para integrar con la API de Claude:** La tabla `simulacion.escenarios` guarda el historial de simulaciones. Cuando el usuario hace una pregunta como "¿cuánto generó mi escenario de 2x1?", se puede consultar esa tabla para enriquecer el contexto.

10. **Modelo recomendado para integraciones:** Usar `claude-opus-4-8` para análisis complejos de múltiples escenarios o `claude-sonnet-4-6` para respuestas más rápidas en consultas simples.

---

*Documento generado automáticamente a partir del código fuente. Última actualización: junio 2026.*
