# PROMPT — REVISIÓN COMPLETA DEL SIMULADOR McDONALD'S PARAGUAY

> Copiá este prompt completo al inicio de tu conversación con el nuevo modelo.
> Luego adjuntá los archivos CSV de las tablas Redshift que tengas disponibles.

---

## ROL Y OBJETIVO

Sos un senior data engineer y analista de negocio especializado en simuladores
de escenarios comerciales. Tu tarea es **revisar en profundidad absolutamente
todo** el sistema: los datos, el código, la lógica de negocio, las fórmulas, los
JOINs SQL, el ETL, y la coherencia de los resultados.

Tenés acceso completo a:
1. La documentación detallada del sistema (adjunta como `DOCUMENTACION_COMPLETA.md`)
2. Todo el código fuente Python (adjunto archivo por archivo)
3. CSVs de las tablas reales de Redshift (adjuntos como archivos CSV)

---

## CONTEXTO DEL SISTEMA

Es un simulador de escenarios "what-if" para McDonald's Paraguay.
Dado un `scenario.yaml` que define una **palanca** (acción comercial),
el simulador toma el **forecast de ventas baseline** de Redshift,
aplica el impacto estimado, y genera un reporte comparando baseline vs. simulado.

### Las 6 palancas disponibles:

| Palanca | Qué simula |
|---------|-----------|
| `precio` | Cambio de precio: sube/baja un porcentaje, mide impacto por elasticidad precio-demanda |
| `promocion` | Campaña promocional: 2x1, descuento, precio fijo, free item |
| `lanzamiento` | Producto nuevo: aplica una curva S de adopción sobre periodos |
| `estructural` | Apertura/cierre/ampliación de local: ajusta el forecast por % de capacidad |
| `competencia` | Nuevo competidor o cierre: ajusta ventas de locales cercanos |
| `clima` | Temperatura anómala: ajusta categorías sensibles al clima por desvío de temperatura |

### Stack técnico:
- **Base de datos:** Amazon Redshift (compatible con PostgreSQL)
- **Driver Python:** `psycopg2`, `execute_values` para bulk inserts
- **Lenguaje:** Python 3.11
- **Librerías:** pandas, numpy, difflib (fuzzy matching), python-dotenv
- **ETL:** `mcdonalds_etl/etl_load.py` — carga Excel + CSV a Redshift
- **Simulador:** `mcdonalds_simulator/` — lee Redshift, simula, escribe resultados

---

## ESTRUCTURA DE ARCHIVOS

```
mcdonalds_etl/
├── etl_load.py          ← ETL principal: parsea Excel/CSV y carga 6 tablas
├── create_tables.sql    ← DDL de las tablas ETL en Redshift
├── requirements.txt
└── .env.example

mcdonalds_simulator/
├── run.py               ← Punto de entrada: lee scenario.yaml, corre el engine
├── scenario.yaml        ← Configuración del escenario a simular
├── core/
│   ├── db.py            ← Conexión a Redshift + helper query_df()
│   ├── engine.py        ← Orquestador: detecta palanca activa, carga forecast, ejecuta
│   ├── loader.py        ← Carga datos de Redshift: forecast, precios, fechas de campaña
│   └── elasticidades.py ← Calcula elasticidad precio-demanda por clasificacion_2
├── palancas/
│   ├── precio.py        ← Palanca de precio (simular u optimizar)
│   ├── promocion.py     ← Palanca de promoción (2x1, descuento, precio_fijo, free_item)
│   ├── lanzamiento.py   ← Palanca de lanzamiento de producto nuevo
│   ├── estructural.py   ← Palanca de cambio estructural de local
│   ├── competencia.py   ← Palanca de nuevo/cierre de competidor
│   └── clima.py         ← Palanca de temperatura
└── output/
    ├── formatter.py     ← Genera el texto narrativo del resultado
    └── writer.py        ← Escribe resultados en Redshift y CSV
```

---

## TABLAS REDSHIFT — REFERENCIA RÁPIDA

### Tablas FUENTE (no las tocamos, solo leemos):

**`forecasting.forecast_ventas_sucursal`** — el forecast mensual de ventas
```
clasificacion_2_sheet  VARCHAR   ← categoría de producto (ej: "Cuarto de Libra")
sucursal               VARCHAR   ← short_name del local (ej: "CABA")
periodo                VARCHAR   ← "YYYY-MM"
forecast               NUMERIC   ← unidades forecasted (puede ser NULL)
unidades               NUMERIC   ← unidades reales (para períodos pasados)
modelo                 VARCHAR   ← SIEMPRE NULL — ignorar
mejor_modelo           VARCHAR   ← nombre del modelo ganador (ej: "share3") — NULL = sin forecast
```
⚠️ **CRÍTICO:** El filtro correcto para obtener solo filas con forecast válido es
`mejor_modelo IS NOT NULL`. El campo `modelo` es siempre NULL y NO debe usarse como filtro.
⚠️ El valor real a usar es `COALESCE(forecast, unidades)` — `forecast` puede ser NULL
incluso cuando `mejor_modelo IS NOT NULL`.

**`ventas.fact_ventas`** — ventas diarias reales
```
fecha         DATE
producto      VARCHAR/INT  ← código de producto (JOIN con dim_articulo.codigo vía CAST)
cantidad      NUMERIC      ← unidades vendidas (el campo es "cantidad", NO "unidades")
restaurante   VARCHAR      ← short_name del local
```

**`dimensiones.dim_articulo_venta`** — catálogo de productos
```
codigo               INT/VARCHAR
descripcion          VARCHAR
clasificacion_2_sheet VARCHAR  ← agrupa productos en categorías del forecast
tipo_sheet           VARCHAR   ← agrupa categorías en familias (ej: "COMBOS", "POSTRES")
```

**`dimensiones.dim_restaurantes`** — catálogo de locales
```
short_name   VARCHAR   ← clave de negocio (ej: "CABA", "LAMBARE")
api_id       INT
nombre       VARCHAR
ciudad       VARCHAR
```

### Tablas ETL (cargadas desde Excel/CSV por `etl_load.py`):

**`simulacion.precio_productos`**
```
codigo        BIGINT    ← código de producto
descripcion   VARCHAR
anio          SMALLINT
mes           SMALLINT
precio        NUMERIC   ← precio de venta en Gs.
```

**`simulacion.promociones`**
```
campania      VARCHAR   ← nombre de la campaña (ej: "2x1 Big Mac 2025")
codigo        BIGINT    ← código de producto incluido en la promo
descripcion   VARCHAR
fecha_desde   DATE      ← inicio exacto de la promo (puede ser NULL si no hay CSV)
fecha_hasta   DATE      ← fin exacto de la promo (puede ser NULL si no hay CSV)
```
⚠️ `fecha_desde`/`fecha_hasta` solo están pobladas para campañas que aparecen en el
CSV de calendario de marketing. El Excel de promociones NO trae fechas.
La ETL deduplica priorizando la fila del CSV (con fechas) sobre la del Excel (sin fechas).

**`simulacion.lanzamientos`**
```
lanzamiento   VARCHAR
codigo        BIGINT
descripcion   VARCHAR
```

**`simulacion.apertura_restaurantes`**
```
api_id              INT
short_name          VARCHAR
fecha_apertura      DATE
tiene_mostrador     BOOLEAN
tiene_automac       BOOLEAN
tiene_delivery      BOOLEAN
tiene_kiosco_digital BOOLEAN
tiene_centro_postres BOOLEAN
```

**`simulacion.competencia`**
```
local_numero   INT
short_name     VARCHAR
competidor     VARCHAR
radio_km       NUMERIC
tipo           VARCHAR
```

### Tablas generadas por el simulador:

**`simulacion.elasticidades`**
```
clasificacion_2   VARCHAR
sucursal          VARCHAR   ← NULL = elasticidad agregada
elasticidad       NUMERIC
n_observaciones   INT
periodos          VARCHAR
```

**`simulacion.resultados`**
```
run_id            VARCHAR
escenario         VARCHAR
tipo_palanca      VARCHAR
clasificacion_2   VARCHAR
sucursal          VARCHAR
periodo           VARCHAR
forecast          NUMERIC
unidades_simuladas NUMERIC
delta_unidades    NUMERIC
delta_pct         NUMERIC
precio_base       NUMERIC
ingreso_base      NUMERIC
ingreso_simulado  NUMERIC
created_at        TIMESTAMP
```

---

## JOINS CRÍTICOS — PATRONES CORRECTOS

```sql
-- fact_ventas → dim_articulo: SIEMPRE con CAST (ambos pueden ser distintos tipos)
JOIN dimensiones.dim_articulo_venta dav
  ON CAST(fv.producto AS VARCHAR) = CAST(dav.codigo AS VARCHAR)

-- forecast → dim_articulo: por clasificacion_2_sheet (NO por código)
JOIN dimensiones.dim_articulo_venta dav
  ON f.clasificacion_2_sheet = dav.clasificacion_2_sheet

-- Evitar fanout al unir por tipo_sheet: usar DISTINCT
SELECT DISTINCT clasificacion_2_sheet
FROM dimensiones.dim_articulo_venta
WHERE tipo_sheet = 'COMBOS'
-- Luego usar esa lista para filtrar forecast, NO hacer JOIN directo
```

---

## FÓRMULAS CLAVE

### Palanca PRECIO
```
elasticidad       = Δ%_unidades / Δ%_precio  (promedio histórico por clasificacion_2)
impacto_volumen   = cambio_pct × elasticidad
unidades_simuladas = forecast × (1 + impacto_volumen)
ingreso_simulado  = unidades_simuladas × (precio_base × (1 + cambio_pct))
```

### Palanca PROMOCION — 2x1
```
# Método preferido: medir uplift real desde historial
uplift_real = (ventas_durante_promo - forecast_mismo_periodo) / forecast_mismo_periodo

# El forecast del periodo se escala a los días de la promo:
fc_diario  = fc_mensual / dias_del_mes
fc_periodo = fc_diario × n_dias_promo

# Si no hay historial suficiente: fallback +40%
unidades_simuladas = forecast_mensual × (1 + uplift)
```

### Palanca PROMOCION — descuento / precio_fijo
```
elasticidad        = get_elasticidad(clasificacion_2)
cambio_precio_pct  = (precio_nuevo - precio_base) / precio_base
impacto_volumen    = cambio_precio_pct × elasticidad
unidades_simuladas = forecast × (1 + impacto_volumen)
```

### Palanca LANZAMIENTO
```
# Curva S de adopción sobre N periodos
# Mes 1: penetracion_inicial × tamaño_mercado_categoria
# Mes N: se interpola hacia penetracion_objetivo usando sigmoid
```

### Palanca ESTRUCTURAL
```
unidades_simuladas = forecast × factor_capacidad
# factor_capacidad: ej. 1.30 para +30% de capacidad, 0 para cierre
```

### Palanca COMPETENCIA
```
# Para cada local dentro del radio del nuevo competidor:
impacto_distancia = f(distancia_km, tipo_competidor)
unidades_simuladas = forecast × (1 - impacto_distancia)
```

### Palanca CLIMA
```
# Desvío de temperatura vs. promedio histórico del período
delta_temp = temperatura_simulada - temperatura_historica_promedio
impacto    = delta_temp × sensibilidad_categoria  (por clasificacion_2)
unidades_simuladas = forecast × (1 + impacto)
```

---

## PROBLEMAS CONOCIDOS Y BUGS CORREGIDOS

### 1. `modelo` vs `mejor_modelo` (bug crítico — ya corregido)
El campo `modelo` en `forecast_ventas_sucursal` es SIEMPRE NULL.
El filtro correcto es `mejor_modelo IS NOT NULL`.
Antes usaba `CAST(modelo AS VARCHAR) = CAST(mejor_modelo AS VARCHAR)` que nunca matcheaba.

### 2. Fanout por tipo_sheet en JOINs (ya corregido)
Hacer JOIN con `dim_articulo_venta` por `tipo_sheet` multiplica filas porque
hay N clasificaciones por tipo. Se resuelve con un DISTINCT antes de filtrar el forecast.

### 3. ETL fechas de promo siempre NULL (ya corregido)
El Excel de promociones no tiene fechas. El CSV de marketing sí.
La deduplicación prioritizaba el Excel (sin fechas) sobre el CSV (con fechas).
Corregido: promo_csv se procesa primero y gana sobre promo_excel.

### 4. `cantidad` vs `unidades` en fact_ventas
`fact_ventas` usa `cantidad` como nombre de columna. Nunca `unidades`.

### 5. CAST obligatorio en JOINs con fact_ventas
`fv.producto` puede ser VARCHAR o INT según la data. `dav.codigo` también varía.
El JOIN debe usar `CAST(... AS VARCHAR) = CAST(... AS VARCHAR)` siempre.

### 6. Promo-only SKUs sin forecast
Productos como "Promo 2x1 Cuarto de Libra" existen SOLO durante campañas 2x1.
No tienen forecast baseline. El uplift para estos debe calcularse usando
el tipo_sheet completo (forecast y ventas) como proxy.

### 7. Forecast inflado en COMBOS 2026-03/04/05
Los valores de forecast para tipo_sheet=COMBOS en esos 3 meses son ~20x el valor normal.
Es un problema de calidad de datos en el modelo de forecasting, no un bug de código.

### 8. Fuzzy matching — umbral mínimo 1.5
`resolver_clasificacion_2` usa scoring fuzzy. Si el mejor score < 1.5 retorna []
y loguea error. Antes devolvía el mejor match aunque fuera totalmente incorrecto.

---

## PREGUNTAS A RESPONDER EN LA REVISIÓN

Por favor revisá todo con este nivel de detalle y respondé las siguientes preguntas.
Podés agregar cualquier otra observación que consideres importante.

### A. DATOS Y ETL

1. **¿Los CSVs adjuntos son coherentes con los esquemas documentados?**
   Verificá tipos de datos, rangos de valores, nulos inesperados, y
   si hay columnas que no coinciden con los nombres esperados por el código.

2. **¿La tabla `simulacion.promociones` tiene fechas pobladas para suficientes campañas?**
   ¿Qué campañas tienen `fecha_desde`/`fecha_hasta` NULL? ¿Impacta en el uplift calculado?

3. **¿El ETL maneja correctamente todos los tipos de Excel/CSV de entrada?**
   Revisá `etl_load.py` buscando posibles errores de parseo, encodings, tipos de datos.

4. **¿La deduplicación de promociones (CSV gana sobre Excel) funciona correctamente?**
   Revisá el bloque `seen_promo` en `etl_load.py`.

5. **¿Qué períodos tienen forecast válido (`mejor_modelo IS NOT NULL`) para cada
   `clasificacion_2_sheet`?** ¿Hay gaps que podrían causar que el simulador no encuentre datos?

### B. LÓGICA DEL SIMULADOR

6. **¿La función `_score_fuzzy` en `loader.py` tiene buena cobertura?**
   Probá mentalmente con inputs como "big mac", "cuarto de libra", "mcflurry oreo",
   "combo doble", "cajita feliz". ¿Podría retornar un match incorrecto con threshold 1.5?

7. **¿`load_forecast` aplica los filtros correctamente?**
   Revisá el SQL completo: el filtro `mejor_modelo IS NOT NULL`,
   el filtro por `clasificacion_2_sheet`, el filtro por `sucursal`, el rango de `periodo`.

8. **¿`_uplift_con_fechas` en `promocion.py` calcula el uplift correctamente?**
   Revisá paso a paso:
   - ¿El forecast se escala bien a los días de la promo?
   - ¿Las ventas se suman correctamente por período?
   - ¿El caso fallback (promo-only SKUs sin forecast) funciona?
   - ¿El promedio de uplifts entre campañas es correcto?

9. **¿`_campanias_similares` devuelve las campañas correctas?**
   Revisá la lógica de priorización:
   - Primero: misma clasificacion_2 + mismo subtipo
   - Fallback: cualquier clasificacion_2 + mismo subtipo
   - NUNCA mezcla subtipos (2x1 no usa datos de "descuento")

10. **¿La palanca `precio` calcula las elasticidades correctamente?**
    Revisá `elasticidades.py`: la query a `fact_ventas` + `precio_productos`,
    el cálculo de Δ%_precio y Δ%_unidades, y el promedio ponderado.

11. **¿La palanca `lanzamiento` tiene una curva S realista?**
    Revisá los parámetros por defecto y si la interpolación sigmoid es correcta.

12. **¿La palanca `competencia` calcula bien el radio de impacto?**
    Revisá el cálculo de distancia (Haversine o Euclidea) y la función de decaimiento.

13. **¿La palanca `clima` tiene coeficientes de sensibilidad razonables?**
    ¿De dónde vienen esos coeficientes? ¿Son hardcodeados o calculados?

### C. OUTPUT Y RESULTADOS

14. **¿`formatter.py` genera textos correctos para todos los casos?**
    Revisá especialmente:
    - 2x1 con historial (alta/media confianza)
    - 2x1 sin historial (fallback +40%)
    - descuento y precio_fijo (explicación por elasticidad)
    - free_item

15. **¿`writer.py` escribe correctamente en `simulacion.resultados`?**
    Verificá que todos los campos requeridos estén presentes en el DataFrame
    antes de insertar, y que no haya type mismatches con el DDL.

### D. COHERENCIA GENERAL

16. **¿Hay columnas calculadas que podrían tener NaN/inf propagados?**
    Revisá divisiones por cero, log(0), o multiplicaciones con NaN.

17. **¿Hay casos de `scenario.yaml` que podrían romper el simulador?**
    Por ejemplo: periodo_desde > periodo_hasta, clasificacion_2 que no existe,
    sucursal inexistente, cambio_pct = -1.0 (precio → 0), etc.

18. **¿Los tipos de datos en los JOINs son consistentes en todo el código?**
    Buscar cualquier JOIN sin CAST que pueda fallar silenciosamente.

19. **¿Hay hardcoding de nombres de tablas, schemas, o columnas fuera de `db.py`?**
    Todo debería venir de las variables de entorno en `db.py`.

20. **¿El simulador es determinístico?** Dado el mismo `scenario.yaml` y los mismos datos,
    ¿siempre produce el mismo resultado? ¿Hay algún componente no determinístico?

---

## INSTRUCCIONES DE REVISIÓN

1. **Leé primero** `DOCUMENTACION_COMPLETA.md` completo para entender la arquitectura.

2. **Luego revisá** cada archivo de código **en este orden**:
   ```
   mcdonalds_etl/create_tables.sql
   mcdonalds_etl/etl_load.py
   mcdonalds_simulator/core/db.py
   mcdonalds_simulator/core/loader.py
   mcdonalds_simulator/core/elasticidades.py
   mcdonalds_simulator/core/engine.py
   mcdonalds_simulator/palancas/precio.py
   mcdonalds_simulator/palancas/promocion.py
   mcdonalds_simulator/palancas/lanzamiento.py
   mcdonalds_simulator/palancas/estructural.py
   mcdonalds_simulator/palancas/competencia.py
   mcdonalds_simulator/palancas/clima.py
   mcdonalds_simulator/output/formatter.py
   mcdonalds_simulator/output/writer.py
   mcdonalds_simulator/run.py
   ```

3. **Analizá los CSVs** adjuntos buscando:
   - Valores fuera de rango
   - Nulls inesperados
   - Columnas con nombres distintos a los esperados
   - Tipos de datos inconsistentes
   - Duplicados que no deberían existir
   - Distribuciones anómalas (ej: forecast inflado en ciertos períodos)

4. **Para cada problema encontrado**, reportalo con:
   - Archivo y función específica (o tabla/columna en CSV)
   - Descripción del problema
   - Impacto en el negocio (¿qué resultado incorrecto produce?)
   - Solución propuesta con el código o SQL exacto

5. **Al final**, entregá:
   - Un resumen ejecutivo de los problemas encontrados ordenados por severidad (crítico/alto/medio/bajo)
   - Una lista de mejoras recomendadas (aunque no sean bugs, sino oportunidades)
   - Tu evaluación general de la calidad del sistema (confiabilidad de los resultados)

---

## ARCHIVOS ADJUNTOS A ESTE PROMPT

Adjuntá los siguientes archivos en este orden:

### Documentación:
- [ ] `DOCUMENTACION_COMPLETA.md`

### Código ETL:
- [ ] `mcdonalds_etl/create_tables.sql`
- [ ] `mcdonalds_etl/etl_load.py`

### Código simulador — core:
- [ ] `mcdonalds_simulator/core/db.py`
- [ ] `mcdonalds_simulator/core/loader.py`
- [ ] `mcdonalds_simulator/core/elasticidades.py`
- [ ] `mcdonalds_simulator/core/engine.py`

### Código simulador — palancas:
- [ ] `mcdonalds_simulator/palancas/precio.py`
- [ ] `mcdonalds_simulator/palancas/promocion.py`
- [ ] `mcdonalds_simulator/palancas/lanzamiento.py`
- [ ] `mcdonalds_simulator/palancas/estructural.py`
- [ ] `mcdonalds_simulator/palancas/competencia.py`
- [ ] `mcdonalds_simulator/palancas/clima.py`

### Código simulador — output:
- [ ] `mcdonalds_simulator/output/formatter.py`
- [ ] `mcdonalds_simulator/output/writer.py`
- [ ] `mcdonalds_simulator/run.py`
- [ ] `mcdonalds_simulator/scenario.yaml`

### CSVs de datos Redshift:
- [ ] `forecasting_forecast_ventas_sucursal.csv` (o el nombre que tenga)
- [ ] `ventas_fact_ventas.csv` (muestra de ventas — puede ser un extracto, no necesitás todo)
- [ ] `dimensiones_dim_articulo_venta.csv`
- [ ] `dimensiones_dim_restaurantes.csv`
- [ ] `simulacion_precio_productos.csv`
- [ ] `simulacion_promociones.csv`
- [ ] `simulacion_lanzamientos.csv`
- [ ] `simulacion_apertura_restaurantes.csv`
- [ ] `simulacion_competencia.csv`
- [ ] `simulacion_elasticidades.csv`

---

*Recordatorio para el modelo: este sistema es de producción real para decisiones comerciales
de McDonald's Paraguay. La precisión de los números importa — un error en una fórmula
puede llevar a decisiones de precios o inversiones incorrectas. Sé muy riguroso.*
