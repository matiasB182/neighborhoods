# Simulador de Escenarios — McDonald's Paraguay

> Documentación completa y autocontenida del simulador. Explica **qué hace**, **cómo lo calcula** (con fórmulas y ejemplos numéricos) y **de dónde saca los datos**. Está pensada tanto para alguien técnico que va a tocar el código como para alguien de negocio que quiere entender de dónde sale cada número.

---

## Índice

1. [Qué es el simulador](#1-qué-es-el-simulador)
2. [Cómo funciona, a grandes rasgos](#2-cómo-funciona-a-grandes-rasgos)
3. [Conceptos base (leer antes que nada)](#3-conceptos-base)
4. [De dónde salen los datos](#4-de-dónde-salen-los-datos)
5. [La elasticidad: el cálculo central](#5-la-elasticidad-el-cálculo-central)
6. [Las palancas, una por una](#6-las-palancas-una-por-una)
   - [6.1 Precio](#61-precio)
   - [6.2 Promoción](#62-promoción)
   - [6.3 Lanzamiento](#63-lanzamiento)
   - [6.4 Estructural](#64-estructural)
   - [6.5 Competencia](#65-competencia)
   - [6.6 Clima](#66-clima)
7. [Combinar varias palancas (composición)](#7-combinar-varias-palancas-composición)
8. [La salida: qué entrega el simulador](#8-la-salida-qué-entrega-el-simulador)
9. [Cómo correrlo](#9-cómo-correrlo)
10. [Glosario](#10-glosario)

---

## 1. Qué es el simulador

Es una herramienta que responde preguntas del tipo **"¿qué pasaría si…?"** sobre las ventas de McDonald's Paraguay:

- ¿Qué pasa con las ventas y los ingresos si **subo 10% el precio** del Big Mac?
- ¿Cuánto vende de más un **2x1** de McFlurry un viernes?
- ¿Cuánto rinde **lanzar** un producto nuevo?
- ¿Cuánto caen las ventas de un local si **abre un competidor** a 500 m?
- ¿Cómo afecta un **invierno más frío** a los helados?

La idea clave: el sistema **parte del forecast de ventas** (lo que se espera vender sin ningún cambio) y le aplica una **palanca** (una fórmula) para estimar qué pasaría con el cambio. Cuando hay **datos históricos reales** los usa; cuando no, usa **supuestos documentados** y lo avisa.

No es una bola de cristal: es un estimador honesto que **siempre dice en qué evidencia se apoya** (alta/media/baja/supuesto) y muestra un **rango probable**, no un número mágico.

---

## 2. Cómo funciona, a grandes rasgos

El flujo de una simulación, de principio a fin:

```
 1. Entrada: un escenario (scenario.yaml o un dict de Python)
        │     describe qué palanca activar y con qué parámetros
        ▼
 2. run.py → core/engine.py::correr_escenario(config)
        │
        ▼
 3. core/loader.py  → carga el FORECAST baseline desde Redshift
        │             (cuántas unidades se esperaban vender)
        ▼
 4. palancas/<X>.py → aplica la fórmula de la palanca sobre el forecast
        │             (devuelve "unidades_simuladas")
        ▼
 5. output/formatter.py → arma el reporte en español llano
    output/writer.py    → (opcional) guarda CSV + tabla Redshift
        ▼
 6. Salida: reporte de texto + DataFrame con el detalle
```

**Pieza por pieza:**

| Componente | Rol |
|---|---|
| `run.py` | Punto de entrada por línea de comandos. Lee el YAML y orquesta. |
| `core/engine.py` | El motor. Decide si corre **una** palanca o **compone varias**. |
| `core/loader.py` | Todo el acceso a datos (forecast, ventas, precios, etc.). |
| `core/ventana.py` | Traduce las fechas del escenario a una ventana concreta. |
| `core/elasticidades.py` | Calcula y lee la sensibilidad al precio por categoría. |
| `palancas/*.py` | Las 6 palancas (precio, promoción, lanzamiento, estructural, competencia, clima). |
| `output/formatter.py` | Convierte los números en un reporte que entiende cualquiera. |
| `output/writer.py` | Persiste resultados (CSV en disco + tabla en Redshift). |

> **Nota técnica:** el motor `correr_escenario(config)` recibe un **diccionario** (la misma forma que el `scenario.yaml`) y devuelve un `DataFrame` en memoria. No necesita escribir archivos para funcionar: el CSV solo se genera si se llama explícitamente a `writer.guardar()`, cosa que hace `run.py` pero que un integrador (ej. GENIA) puede omitir.

---

## 3. Conceptos base

Cinco ideas que aparecen en todas las palancas. Vale la pena leerlas una vez.

### 3.1 Forecast (la base de todo)

El **forecast** es la estimación de ventas esperadas **sin ningún cambio**. Vive en la tabla `forecasting.forecast_ventas_sucursal`, granulado por **categoría de producto × sucursal × mes**.

Todas las palancas hacen lo mismo conceptualmente:

```
unidades_simuladas = forecast × (1 + efecto)
```

donde `efecto` es lo que cada palanca estima. Si una promo da +40%, `efecto = 0.40`. Si un competidor resta 8%, `efecto = -0.08`.

### 3.2 La categoría de producto (`clasificacion_2`) y el matching difuso

El simulador trabaja a nivel de **categoría** (`clasificacion_2`), no de producto individual. Ejemplos: `"big mac"`, `"combo cuarto de libra"`, `"mcflurry"`.

El usuario escribe la categoría en **texto libre** y el sistema busca la más parecida con un **matching difuso** (`resolver_clasificacion_2` en `loader.py`). Tolera errores de tipeo y nombres parciales:

- `"cuarto de libra"` puntúa más alto en `"Cuarto de Libra"` que en `"3 Combos Doble Cuarto de Libra"` (penaliza el texto sobrante).
- Si el texto es **ambiguo** (varias categorías empatan dentro del 5%), el sistema **no adivina**: pide que se especifique el nombre completo.
- Si nada coincide razonablemente (score < 1.5), avisa que no encontró la categoría.

### 3.3 La ventana de tiempo

Cada palanca actúa en una **ventana de fechas** (`fecha_desde` → `fecha_hasta`). La resuelve `core/ventana.py`:

- **Con fecha exacta** (`YYYY-MM-DD`): se usa tal cual.
- **Sin fecha**, depende del tipo de palanca:
  - **Precio, competencia, estructural** → se asume un cambio **permanente**: vigente desde el mes actual hasta el final del forecast. (Un cambio de lista o un competidor que abre "rige hacia adelante".)
  - **Clima, lanzamiento, promoción** → **requieren fecha** (son escenarios acotados en el tiempo); si no la traen, el sistema da un error claro.

### 3.4 Confianza (qué tan respaldado está el número)

Cada resultado viene con una etiqueta de confianza:

| Confianza | Qué significa |
|---|---|
| **alta** | Muchos eventos históricos reales. Número confiable. |
| **media** | Pocos eventos. Tomarlo como referencia. |
| **baja** | Muy pocos eventos. Orientativo. |
| **supuesto** | No hay datos; se usó un supuesto de industria documentado. |

### 3.5 Banda P10–P90 (el rango probable)

El simulador no entrega solo un número: entrega un **rango probable**. La banda P10–P90 significa "es razonable esperar un resultado entre estos dos valores". Sale de la **incertidumbre real medida** (dispersión de las elasticidades, de los uplifts de campañas, etc.). Si no hay base para estimar dispersión, la banda se colapsa al punto (no se inventa un rango).

El valor `1.2816` que aparece en el código es el cuantil de la normal para una banda del 80% (P10 a P90).

---

## 4. De dónde salen los datos

El simulador **lee** de Redshift. Estas son las tablas que consume (los nombres exactos están en `.env`):

### Tablas fuente (datos de operación)

| Tabla | Qué tiene | Para qué se usa |
|---|---|---|
| `forecasting.forecast_ventas_sucursal` | Forecast por categoría × sucursal × mes | La **base** de todas las simulaciones |
| `stg.fact_ventas` | Ventas reales (ticket a ticket): producto, fecha, tienda, cantidad, canal | Elasticidades, uplifts de promo, comparaciones entre locales |
| `stg.dim_articulo_venta` | Catálogo de productos: código, categoría (`clasificacion_2_sheet`), familia (`tipo_sheet`) | Une `fact_ventas` con las categorías |
| `stg.dim_restaurantes` | Catálogo de locales: `api_id_integer`, nombre | Une ventas con sucursales |

### Tablas de soporte (cargadas desde planillas por el ETL)

| Tabla | Qué tiene | Palanca que la usa |
|---|---|---|
| `simulacion.precio_productos` | Precios de lista por producto × mes | Precio, Promoción |
| `simulacion.promociones` | Campañas históricas (código, fechas) | Promoción (uplift 2x1 / gratis) |
| `simulacion.lanzamientos` | Lanzamientos históricos | Lanzamiento |
| `simulacion.apertura_restaurantes` | Canales operativos por local (Automac, delivery…) | Estructural |
| `simulacion.competencia` | Competidores por local y distancia | Competencia |
| `simulacion.locales_dimension` | Atributos físicos del local (m², tipo, Playland, McCafé) | Estructural, segmentos de elasticidad |

### Tablas que genera el propio simulador (cache de cálculos pesados)

Estas son **las tablas que crea el simulador** (no vienen de la operación). Guardan el resultado de cálculos pesados que recorren años de ventas, para no rehacerlos en cada simulación. Se calculan una vez (offline) y después se leen rápido.

A continuación, qué tiene cada una con un ejemplo de fila.

---

#### `simulacion.whatif_elasticidades` — la sensibilidad al precio
*La genera:* `core/elasticidades.py` + `core/elasticidad_eventos.py` · *La usa:* Precio, Promoción (descuento)

Una fila por **categoría × segmento**. Es el insumo de toda decisión de precio.

| Columna | Qué es |
|---|---|
| `clasificacion_2` | La categoría (ej. "big mac") |
| `segmento` | Tipo de local (`todos`, `playland`, `mall`, …) |
| `elasticidad_precio` | La elasticidad medida (negativa = sube precio, baja venta) |
| `elasticidad_p10` / `elasticidad_p90` | La banda (rango probable) |
| `n_productos` / `n_cambios` | Cuántos productos y cuántos cambios de precio se usaron |
| `precio_desde` / `precio_hasta` | Rango de precios observado |
| `confianza` | alta / media / baja |
| `metodo` | `mensual` o `eventos` (event study) |

**Ejemplo de fila:** `big mac | todos | −0.62 | −0.71 | −0.53 | 4 productos | 9 cambios | 28.000 → 42.000 Gs | alta | eventos`
→ *"Subir 1% el precio del Big Mac baja las ventas ~0.62%, con buena evidencia (9 cambios de precio reales medidos)."*

---

#### `simulacion.uplifts_medidos` — el efecto real de cada promo histórica
*La genera:* el backtest (`backtest/promocion_bt.py`) · *La usa:* Promoción (2x1, producto gratis)

Una fila por **campaña histórica** medida contra `fact_ventas`.

| Columna | Qué es |
|---|---|
| `campania` | Nombre de la campaña (ej. "2x1 McFlurry viernes") |
| `subtipo` | `2x1`, `producto_gratis`, … |
| `nivel` | A qué nivel se midió (la categoría o la familia `tipo_sheet`) |
| `fecha_desde` / `fecha_hasta` / `n_dias` | Cuándo y cuántos días duró |
| `restringida` | Si era restringida (tarjeta/app/canal) o abierta a todos |
| `diaria_promo` / `diaria_base` | Venta diaria durante la promo vs. baseline |
| `uplift` | El efecto: `diaria_promo / diaria_base − 1` |
| `uplift_total_local` | Cuánto subió el **total del local** (no solo la categoría) |
| `uplift_hermanas` | Efecto en categorías parecidas (canibalización) |

**Ejemplo de fila:** `2x1 McFlurry viernes | 2x1 | tipo_sheet 'POSTRES' | 2025-03-07 → 2025-03-07 | 1 día | abierta | 420/día | 290/día | +0.45 | +0.08 | −0.03`
→ *"Ese 2x1 vendió 420 unidades/día vs. 290 normales: +45% de uplift. El total del local subió 8%, y las categorías hermanas cayeron 3% (parte se canibalizó)."*

---

#### `simulacion.curvas_lanzamiento` — la curva de despegue de cada lanzamiento
*La genera:* `core/curvas_lanzamiento.py` · *La usa:* Lanzamiento

Una fila por **lanzamiento × mes_relativo** (mes 0 = lanzamiento, 1, 2, …).

| Columna | Qué es |
|---|---|
| `lanzamiento` | Nombre del producto lanzado |
| `tipo_sheet` / `clasificacion_2` | Familia y categoría |
| `mes_relativo` | 0 = mes del lanzamiento, 1 = siguiente, … |
| `share_tipo` | Qué fracción de la familia representó ese SKU ese mes |
| `incrementalidad` | Qué parte de lo que vendió fue **neto** (no canibalización) |
| `base_mensual_tipo` | Volumen base de la familia (para reescalar) |

**Ejemplo de fila:** `McFlurry Braunitos | POSTRES | mcflurry | mes 0 | 0.22 | 0.60 | 50.000`
→ *"En su primer mes, el McFlurry Braunitos representó el 22% de la familia Postres; el 60% de eso fue venta nueva, el resto canibalizó otros postres."*

---

#### `simulacion.impacto_aperturas` y `…rampup_aperturas` — efecto de abrir un local
*La genera:* `core/impacto_aperturas.py` · *La usa:* Competencia

**`impacto_aperturas`** — cuánto resta una apertura a los locales cercanos, por banda de distancia (event study de aperturas propias):

| Columna | Qué es |
|---|---|
| `banda_desde_km` / `banda_hasta_km` | El tramo de distancia (ej. 0–0.5 km) |
| `efecto` | Cambio de ventas de los locales en esa banda |
| `efecto_p10` / `efecto_p90` | La banda probable |
| `n_pares` | Cuántas comparaciones apertura-local se usaron |
| `confianza` | alta / media / baja |

**Ejemplo de fila:** `0.0 → 0.5 km | −0.12 | −0.18 | −0.06 | 14 pares | media`
→ *"Abrir un local a menos de 500 m le restó ~12% de ventas a los vecinos (medido sobre 14 casos)."*

**`rampup_aperturas`** — cuánto tarda un local nuevo en llegar a su nivel de régimen: `mes_relativo | pct_nivel_regimen | n_locales`. Ejemplo: `mes 0 | 0.65 | 12` → *"En su primer mes, un local nuevo vende el 65% de lo que vendería ya maduro."*

---

#### `simulacion.sensibilidad_clima` y `…clima_normales` — reacción al clima
*La genera:* `core/sensibilidad_clima.py` · *La usa:* Clima

**`sensibilidad_clima`** — cuánto reacciona cada categoría a temperatura y lluvia (regresión sobre ventas diarias reales):

| Columna | Qué es |
|---|---|
| `clasificacion_2` | La categoría |
| `beta_temp` | Cambio de ventas por cada +1 °C |
| `beta_lluvia` | Cambio de ventas en día de lluvia vs. seco |
| `t_temp` / `t_lluvia` | Significancia estadística (qué tan confiable es cada beta) |
| `se_temp` / `se_lluvia` | Margen de error de cada beta (arma la banda) |
| `n_obs` | Cuántas observaciones diarias se usaron |
| `confianza` | alta / media / baja |

**Ejemplo de fila:** `mcflurry | beta_temp +0.018 | t 4.2 | beta_lluvia −0.09 | t −3.1 | 8.400 obs | alta`
→ *"Cada grado más de calor sube el McFlurry ~1.8%; un día de lluvia lo baja ~9%. Ambos efectos son estadísticamente sólidos."*

**`clima_normales`** — el clima típico de cada mes: `mes | temp_media | pct_dias_lluvia`. Ejemplo: `6 (junio) | 18.5 °C | 30% días con lluvia`. Sirve para traducir "20% más frío" a grados y días concretos.

---

#### `simulacion.whatif_resultados` — el historial de simulaciones
*La genera:* `output/writer.py` · *La usa:* registro/auditoría

Una fila por **categoría × sucursal × mes** de cada simulación que se corre y guarda. Columnas: `escenario_nombre`, `clasificacion_2`, `sucursal`, `periodo`, `forecast_base`, `forecast_simulado`, `delta_abs`, `delta_pct`, `ingreso_base`, `ingreso_simulado`, `palancas_json` (los parámetros usados).

**Ejemplo de fila:** `"Subir 10% Big Mac" | big mac | (todas) | 2026-07 | 10.000 | 9.200 | −800 | −8% | 350.000.000 | 354.200.000 | [{"tipo":"precio",…}]`

---

> **Importante para producción:** las tablas de cache (elasticidades, uplifts, clima, aperturas, curvas) deben existir **antes** de simular. Calcularlas tarda minutos (recorren años de ventas diarias), así que se corren por adelantado, **nunca dentro de una simulación interactiva**.

---

## 5. La elasticidad: el cálculo central

La elasticidad es el corazón de las palancas de **precio** y **descuento**, y es lo más sutil del sistema. Conviene entenderla bien.

### 5.1 Qué es

La **elasticidad precio-demanda** mide cuánto cae la demanda cuando sube el precio:

```
elasticidad = (cambio % en unidades) / (cambio % en precio)
```

**Ejemplo:** si cuando el precio subió 10%, las ventas cayeron 8%:

```
elasticidad = -8% / +10% = -0.80
```

Se lee: *"por cada 1% que sube el precio, las ventas caen 0.80%"*. Una elasticidad **siempre debería ser negativa** (más caro → se vende menos).

### 5.2 Cómo se calcula (metodología)

En `core/elasticidades.py`:

1. **Por producto individual:** se busca cada mes en que el precio de ESE producto cambió, y se mide cuánto cambiaron las unidades de ESE producto ese mes.
2. **Se excluyen los meses con promoción activa** del producto: ahí el cambio de unidades refleja la promo, no el precio.
3. **Se toma la MEDIANA** de las elasticidades de todos los productos de la misma categoría (la mediana es robusta a un evento atípico; el promedio se distorsiona).
4. **Por segmento de local:** se calcula también por tipo de local (con/sin Playland, mall, free-standing, etc.), porque el cliente "cautivo" de un local con Playland es menos sensible al precio que el de un local de paso.

**Confianza según cantidad de cambios observados:**

| Cambios de precio observados | Confianza |
|---|---|
| ≥ 5 | alta |
| 2–4 | media |
| 1 | baja |
| 0 | supuesto (default −0.5) |

**Banda P10–P90** de la elasticidad: `mediana ± 1.2816 × (desvío / √n)`. Cuantos más cambios medidos, más angosta.

### 5.3 El "guardrail" del signo equivocado (clave)

A veces la elasticidad **medida sale positiva** (ej. el Combo Big Mac mide +0.35). Eso **no es creíble**: significaría "subo el precio y vendo más". Pasa porque las subas de precio coincidieron históricamente con lanzamientos o campañas que inflaron el volumen — un factor no controlado.

La función `elasticidad_efectiva` maneja esto:

```
si elasticidad_medida >= -0.05 (signo equivocado o casi nulo):
    → se reemplaza por el supuesto conservador -0.5
    → confianza pasa a "supuesto"
    → se marca "no creíble"
```

Y en la palanca de precio, cuando esto pasa, el reporte muestra **solo la dirección** del cambio (sube/baja), **no una magnitud inventada**. Es una decisión de diseño deliberada: mejor decir "esto sube, no sé cuánto" que dar un número falso.

### 5.4 ¿Y si quiero la elasticidad de un tipo de local específico?

A veces no querés la elasticidad "de toda la categoría" sino la de un segmento: por ejemplo, *"¿qué tan sensibles al precio son los clientes de los locales CON Playland?"*. El problema: un segmento suele tener **muchos menos datos** que el total, y con pocos datos el número que sale puede ser pura casualidad (ruido).

La solución: **no creerle del todo a un segmento con pocos datos**. Se mezcla su número con el de la categoría completa, dándole más peso al segmento cuanto más respaldo (más mediciones) tenga.

**La analogía:** es como puntuar un restaurante. Si tiene **3 reseñas** de 5 estrellas, no te la jugás a que es perfecto: asumís que probablemente esté cerca del promedio general, hasta que junte más reseñas. Si tiene **500 reseñas**, ahí sí le creés su propio promedio.

**El peso que se le da al segmento** depende de cuántas mediciones tenga:

```
peso_del_segmento = mediciones / (mediciones + 10)
elasticidad_final = (1 − peso) × elasticidad_categoría  +  peso × elasticidad_segmento
```

El "+10" es cuántas mediciones hacen falta para empezar a creerle al segmento. Mirá cómo cambia el peso según los datos:

| Mediciones del segmento | Peso al segmento | En la práctica |
|---|---|---|
| 2 | 2 / 12 = **17%** | casi se usa el número de la categoría |
| 10 | 10 / 20 = **50%** | mitad categoría, mitad segmento |
| 50 | 50 / 60 = **83%** | casi todo el número propio del segmento |

**Ejemplo concreto:** la categoría "big mac" mide elasticidad **−0.6** en general. El segmento "con Playland" mide **−0.9**, pero con solo **4 mediciones** → peso = 4 / 14 = 29%:

```
elasticidad_final = 0.71 × (−0.6)  +  0.29 × (−0.9)  =  −0.69
```

→ Se inclina hacia el −0.6 confiable, sin ignorar del todo la señal del segmento (que es algo más sensible). Así, un segmento con muestra chica y un número raro **no arruina** el resultado.

> El nombre técnico de esto es *empirical Bayes shrinkage* ("encogimiento hacia la media"), pero la idea es simplemente: **menos datos = más caso al promedio general; más datos = más caso al número propio**.

---

## 6. Las palancas, una por una

Cada palanca responde a una pregunta de negocio, aplica una fórmula y reporta confianza + rango. Acá va el detalle de cada una con ejemplos numéricos reales.

---

### 6.1 Precio

**Archivo:** `palancas/precio.py` · **Pregunta:** ¿qué pasa con ventas e ingresos si cambio el precio?

Tiene dos modos: **simular** (un cambio fijo) y **optimizar** (buscar el mejor precio).

#### Modo `simular`

**Fórmula:**

```
impacto_volumen   = cambio_pct × elasticidad
factor            = máximo(0, 1 + impacto_volumen)        ← nunca unidades negativas
unidades_simuladas = forecast × factor

precio_nuevo      = precio_actual × (1 + cambio_pct)
ingreso_base      = forecast × precio_actual
ingreso_simulado  = unidades_simuladas × precio_nuevo
```

**Ejemplo:** subir 10% el precio de una categoría con elasticidad −0.80, forecast 10.000 unidades, precio Gs. 35.000.

```
impacto_volumen   = +0.10 × (−0.80) = −0.08   → las ventas caen 8%
unidades_simuladas = 10.000 × 0.92 = 9.200 unidades

precio_nuevo      = 35.000 × 1.10 = Gs. 38.500
ingreso_base      = 10.000 × 35.000 = Gs. 350.000.000
ingreso_simulado  =  9.200 × 38.500 = Gs. 354.200.000   (+1,2%)
```

→ Se venden menos unidades pero se gana **más plata**. Ese es el insight típico de la palanca de precio.

**Guardrails:**
- Si `|cambio_pct| > 30%` (`CAMBIO_MAX_CONFIABLE`): avisa que está **fuera del rango histórico** observado — el modelo lineal de elasticidad ya no es confiable, es extrapolación.
- Si la elasticidad no es creíble: muestra **solo dirección**, sin magnitud (ver §5.3).

#### Modo `optimizar`

En vez de un cambio fijo, **prueba todos los cambios** dentro de un rango (en pasos de 1%) y elige el mejor según el objetivo:

| Objetivo | Qué busca |
|---|---|
| `max_ingreso` | El % que genera más Gs. totales |
| `max_unidades` | El % que genera más unidades (siempre baja el precio) |
| `breakeven` | Hasta dónde se puede subir sin perder ingreso |

Por defecto explora solo **±15%** (`OPTIM_CAMBIO_CONFIABLE`): el "mejor precio" recomendado es el mejor que la **evidencia respalda**, no una extrapolación teórica.

**Dos avisos importantes que genera:**
- **`en_borde`**: si el óptimo cae justo en el extremo del rango, **no es un óptimo real**. Con elasticidad de magnitud baja (< ~0.6), el modelo lineal *siempre* recomienda subir al máximo. Es una propiedad de la matemática, no evidencia de que esa suba funcione.
- **`extrapola`**: si el óptimo recomienda un cambio grande (lejos de lo observado históricamente), se presenta con confianza degradada.

---

### 6.2 Promoción

**Archivo:** `palancas/promocion.py` · **Pregunta:** ¿cuánto impacto tiene una promo puntual?

**Concepto clave — `forecast_promo`:** las promos duran días, no meses. No tiene sentido comparar una promo de 3 días contra el forecast de todo el mes. Por eso se **escala** el forecast mensual a los días de la promo:

```
forecast_promo = forecast_mensual ÷ días_del_mes × días_de_la_promo
```

Ejemplo: forecast junio = 10.000 (30 días), promo de 3 días → `forecast_promo = 10.000 ÷ 30 × 3 = 1.000` unidades base.

**Parámetro `canal` (opcional):** automac / delivery / app / restaurante. El efecto escala por la **participación real del canal** en cada local (medida de `fact_ventas.area_venta`). Un local sin ese canal tiene participación 0 y no recibe efecto.

Tiene 4 subtipos:

#### 6.2.1 Descuento

Usa la **elasticidad** (igual que precio) pero sobre el `forecast_promo`.

```
impacto_volumen    = cambio_pct × elasticidad × share_canal
unidades_simuladas = forecast_promo × (1 + impacto_volumen)
ingreso_simulado   = unidades_simuladas × (precio_actual × (1 + cambio_pct))
```

**Ejemplo:** 30% OFF, elasticidad −0.80, forecast_promo 1.000, precio Gs. 35.000.

```
impacto_volumen    = −0.30 × (−0.80) = +0.24   → +24% volumen
unidades_simuladas = 1.000 × 1.24 = 1.240 unidades
ingreso_base       = 1.000 × 35.000 = Gs. 35.000.000
ingreso_simulado   = 1.240 × 24.500 = Gs. 30.380.000   (−13%)
```

→ Se vende más, pero se gana menos (el descuento es grande).

#### 6.2.2 Precio fijo

Igual que descuento, pero se indica el precio en Gs. y el sistema calcula el % implícito:

```
cambio_pct = (precio_fijo − precio_actual) / precio_actual
```

Ejemplo: precio actual Gs. 22.000, precio promo Gs. 15.000 → `cambio_pct = (15.000 − 22.000) / 22.000 = −31,8%`. De ahí en adelante, idéntico al descuento.

#### 6.2.3 2x1

Aquí **no se usa elasticidad** (el efecto psicológico de "llevás 2" es distinto a un descuento). Se mide el **uplift real** de campañas 2x1 históricas similares:

```
venta_diaria_promo    = promedio de ventas de los días de la campaña
venta_diaria_baseline = promedio de los MISMOS DÍAS DE SEMANA en las
                        ±4 semanas, excluyendo la campaña y los días con
                        otra campaña de las mismas categorías
uplift                = venta_diaria_promo / venta_diaria_baseline − 1
```

El **matching por día de semana** es clave: comparar un 2x1 de viernes contra el promedio del mes (que incluye lunes) inflaba el uplift. Se toma la **mediana** de la celda más específica con datos (misma restricción + misma duración → misma restricción → todas).

**Ejemplo:** forecast_promo 200, uplift histórico +45% → `unidades_simuladas = 200 × 1,45 = 290`.

**Sin campañas históricas con fechas:** se usa el supuesto **+40%** (conservador, se avisa).

#### 6.2.4 Producto gratis

Misma lógica que el 2x1 (uplift medido), supuesto por defecto **+10%**.

#### Acción `eliminar`

Todas las promos aceptan `accion: eliminar`, que simula **cancelar** una promo que el forecast ya contempla (recurrente/planificada). En vez de sumar el efecto, lo **divide**: `factor = 1 / (1 + efecto)`. Responde *"¿cuánto perdemos si NO hacemos el 2x1 del día de la hamburguesa este año?"*.

---

### 6.3 Lanzamiento

**Archivo:** `palancas/lanzamiento.py` · **Pregunta:** ¿cuánto rinde lanzar un producto nuevo?

**Concepto:** un producto nuevo tiene un **pico inicial** (novedad, publicidad) que decae mes a mes hasta el nivel base. El sistema mide ese patrón de lanzamientos históricos reales (a nivel SKU) y lo aplica al forecast.

**Fórmula (con curvas medidas):**

```
unidades_simuladas[mes] = forecast[mes] × (1 + uplift[mes_relativo])
```

donde `mes_relativo = 0` es el mes del lanzamiento, 1 el siguiente, etc.

**Orden de prioridad de la fuente:**
1. Si se pasa un `proxy_lanzamiento` (un lanzamiento histórico similar) → usa su curva medida.
2. Si no → mediana de las curvas de los lanzamientos de la **misma categoría**.
3. Si tampoco hay → **patrón default conservador**:

```
mes 0: +18%   mes 1: +12%   mes 2: +7%
mes 3:  +4%   mes 4:  +2%   mes 5: +1%
```

**Concepto fino — incrementalidad:** parte de lo que vende el producto nuevo es **crecimiento neto** y parte **canibaliza** variantes existentes. El reporte separa "cuánto vende el SKU" de "cuánto es neto para la categoría". Si no se puede medir, se asume incrementalidad 0,5 (la mitad es neta).

**Ejemplo:** forecast McFlurry mayo (mes 0) = 5.000, uplift mes 0 = +18% → `5.000 × 1,18 = 5.900`. Forecast junio (mes 1) = 5.200, uplift +12% → `5.200 × 1,12 = 5.824`.

---

### 6.4 Estructural

**Archivo:** `palancas/estructural.py` · **Pregunta:** ¿cuánto sube si agrego un canal/atributo a una sucursal? (Automac, Playland, McCafé, delivery, kiosco, etc.)

**Método principal — matching emparejado:** cada local que **tiene** el atributo se compara contra los locales **sin** el atributo más parecidos (mismo tipo de local y tamaño en m² más cercano, hasta 3 vecinos).

```
para cada local t CON el canal:
    vecinos   = hasta 3 locales sin el canal, mismo store_type, m² más parecido
    efecto(t) = ventas(t) / promedio(ventas(vecinos)) − 1
efecto = mediana de efecto(t) sobre todos los locales tratados

unidades_simuladas = forecast × (1 + efecto)
```

El emparejamiento quita el sesgo grueso: los Playland están en locales más grandes y mejor ubicados, así que comparar contra "todos los demás" le atribuiría al Playland lo que es del local.

**Fallback:** si no hay atributos físicos para emparejar, una comparación cruda (promedio con vs. promedio sin), opcionalmente restringida por zona (barrio/distrito/dpto).

**Ejemplo:** locales con Automac venden 12.000/mes, sin Automac 9.000/mes → `efecto = (12.000 − 9.000)/9.000 = +33%`. Forecast del local sin Automac = 8.500 → `8.500 × 1,33 = 11.305`.

> **Límite siempre presente:** es **observacional, no causal**. Por eso la confianza llega como máximo a "media". Además, agregar un canal de venta suele **canibalizar** al mostrador, así que el total del local sube menos de lo que sugiere la comparación cruda.

---

### 6.5 Competencia

**Archivo:** `palancas/competencia.py` · **Pregunta:** ¿cuánto caen las ventas de un local si abre un competidor cerca?

**Orden de prioridad:**
1. **Banda medida** (event study de las aperturas **propias** 2023–2025): cómo cambiaron las ventas de los locales cercanos a una apertura vs. los lejanos (control). *Caveat:* es competencia intramarca — otro McDonald's es el competidor "máximo", uno de otra marca probablemente impacte algo menos.
2. **Cross-sectional:** locales que ya tienen competidor a distancia similar vs. los que no. Si sale ≥ 0 (no creíble: los locales con competidor cerca suelen estar mejor ubicados y vender más), se descarta.
3. **Fallback por banda de distancia (supuestos):**

| Distancia | Efecto |
|---|---|
| < 300 m | −15% |
| 300–600 m | −10% |
| 600 m – 1 km | −6% |
| 1–2 km | −3% |
| > 2 km | −1% |

```
unidades_simuladas[sucursal_afectada] = forecast × (1 + efecto)
unidades_simuladas[resto]             = forecast            (sin cambio)
```

El efecto se acota a **≤ 0** (un competidor no puede subir las ventas).

**Ejemplo:** competidor a 500 m, efecto −8%, forecast del local 11.500 → `11.500 × 0,92 = 10.580` (−920 unidades).

---

### 6.6 Clima

**Archivo:** `palancas/clima.py` · **Pregunta:** ¿cómo afecta un mes más frío/caluroso/lluvioso a las ventas?

**Método principal (sensibilidad medida):** cada categoría tiene betas medidos por regresión de ventas diarias × clima diario (controlando local, día de semana, mes, año y promos):

```
efecto = beta_temp × Δtemp_°C + beta_lluvia × Δshare_lluvia
unidades_simuladas = forecast × (1 + efecto)
```

El escenario se expresa de dos formas (al menos una):
- `variacion_pct`: eje combinado. −0.20 = "20% más frío/lluvioso que lo normal del período" (se traduce a °C y días de lluvia usando las normales históricas).
- `delta_temp_c` y/o `delta_lluvia_pct`: magnitudes físicas directas (ej. −3 °C, +30% días de lluvia).

**Fallback (coeficientes supuestos de industria):**

```
efecto = variacion_pct × coeficiente
```

| Categoría | Coeficiente | Lectura |
|---|---|---|
| McFlurry / helados | −0.40 | caen mucho con el frío |
| Sundae | −0.35 | caen con el frío |
| McCafé / café | +0.20 | sube con el frío |
| Combos / hamburguesas | −0.05 | casi no se mueven |
| Papas | −0.02 | prácticamente insensibles |

**Ejemplo (junio 20% más frío, `variacion_pct = −0.20`):**
- McFlurry: `−0.20 × −0.40 = −0.08` → caen 8% (3.000 → 2.760).
- McCafé: `−0.20 × +0.20 = +0.04` → suben 4% (1.000 → 1.040).
- Combos: `−0.20 × −0.05 = −0.01` → caen 1% (casi nada).

---

## 7. Combinar varias palancas (composición)

**Archivo:** `core/engine.py` (`_correr_varias`)

Se pueden activar **varias palancas a la vez** y el sistema las **compone**: aplica cada una sobre el resultado de la anterior, asumiendo que **no interactúan**. Cada palanca afecta solo a **su** categoría/sucursal y a **su** ventana de días.

**Cómo se compone:**
1. Se carga un único forecast que cubre la unión de todos los alcances.
2. Se inicializan las `unidades_simuladas` en el forecast.
3. Se aplica cada palanca **en cadena**, en este orden (el volumen es multiplicativo, así que el orden no cambia las unidades; el precio va último para que su cálculo de ingresos use las unidades ya compuestas):

   ```
   clima → competencia → estructural → lanzamiento → promoción → precio
   ```
4. El efecto de cada palanca se **restringe a su alcance** y se **diluye por la fracción del mes** que cubre su ventana (`fraccion_mes`). Una promo de 3 días en un mes de 30 aplica su efecto sobre 0,1 del mes.
5. Las bandas P10–P90 se combinan asumiendo **independencia** entre palancas (las log-varianzas se suman).

**Guardrails (reglas que el motor impone):**
- Una sola palanca de **precio** por escenario.
- Una sola **promoción** por escenario.
- **Precio + promoción sobre la misma categoría** → bloqueado (doble conteo: la promo ya midió su uplift al precio normal). En categorías distintas sí se pueden combinar.
- Promos de tipo **descuento** y **precio_fijo** (que cambian precio) van **solas**. En combinación se soportan **2x1** y **producto_gratis**.

El reporte combinado muestra una **cascada** (base → +palanca → +palanca → … → total) para ver el aporte de cada una.

---

## 8. La salida: qué entrega el simulador

El simulador produce tres cosas (la primera siempre; las otras dos solo en el flujo de línea de comandos):

### 8.1 Reporte en consola (`output/formatter.py`)

Pensado para alguien que **no es analista**. Estructura:

1. **Qué simulaste** — el escenario en una línea.
2. **En una frase** — el resultado en una o dos oraciones.
3. **Los números** — base vs. simulado, en unidades y en plata.
4. **De dónde sale este número** — la cuenta paso a paso, con los valores reales.
5. **Cómo leer este número** — en qué evidencia se apoya y para qué sirve.

### 8.2 CSV (`output/writer.py` → `output/resultados/`)

Para abrir en Excel. Incluye las columnas de negocio (base, simulado, delta, ingresos) **más** las columnas técnicas (elasticidad usada, confianza, banda P10–P90, fuente de cada palanca) y una columna `explicacion` con el texto del reporte. Útil para analistas y para auditar de dónde salió cada número.

### 8.3 Tabla en Redshift (`simulacion.whatif_resultados`)

Un registro de cada simulación corrida (escenario, categoría, sucursal, mes, base, simulado, deltas, ingresos, parámetros). Sirve como historial.

> El CSV y la tabla Redshift solo se generan si se llama a `writer.guardar()`. El motor en sí devuelve un `DataFrame` en memoria sin escribir nada — útil para integraciones que solo quieren el resultado.

---

## 9. Cómo correrlo

### Preparación (una vez)

1. Copiar `.env.example` a `.env` y completar las credenciales de Redshift y los nombres de tablas.
2. Instalar dependencias: `pip install -r requirements.txt`.
3. Generar las tablas de cache (tardan minutos, se corren por adelantado):
   ```
   python recalcular_elasticidades.py
   # y los demás generadores de core/ según se necesiten
   ```

### Correr un escenario

1. Editar `scenario.yaml`: poner un nombre, activar la palanca deseada (`activo: true`) y completar sus parámetros.
2. Ejecutar:
   ```
   python run.py --scenario scenario.yaml
   ```
3. El reporte sale por consola y el CSV queda en `output/resultados/`.

El `scenario.yaml` tiene documentación inline exhaustiva de cada palanca y sus parámetros — es la mejor referencia para armar un escenario.

### Desde código (sin archivos)

```python
from core.engine import correr_escenario
from output.formatter import resumen_consola

config = {
    "escenario": {"nombre": "Subir 10% el Big Mac"},
    "palancas": [
        {"tipo": "precio", "activo": True, "modo": "simular",
         "clasificacion_2": "big mac", "sucursal": None,
         "fecha_desde": "2026-07-01", "fecha_hasta": "2026-09-30",
         "cambio_pct": 0.10},
    ],
}

df, nombre = correr_escenario(config)          # DataFrame en memoria, no escribe nada
print(resumen_consola(df, nombre, config["palancas"]))
```

---

## 10. Glosario

| Término | Significado |
|---|---|
| **Forecast** | Estimación de ventas esperadas sin ningún cambio (la base). |
| **clasificacion_2** | La categoría de producto (ej. "big mac", "mcflurry"). |
| **tipo_sheet** | La familia de producto (agrupa varias categorías). |
| **Unidades base** | Cuántas unidades se esperaban vender (el forecast). |
| **Unidades simuladas** | Cuántas se estiman vender CON el cambio. |
| **Delta** | Diferencia entre simulado y base (en unidades o %). |
| **Ingreso base / simulado** | Gs. sin / con el cambio (unidades × precio). |
| **Elasticidad** | Sensibilidad de las ventas al precio (ver §5). |
| **Uplift** | Aumento % de ventas que genera una promo o lanzamiento. |
| **forecast_promo** | El forecast mensual escalado a los días que dura una promo. |
| **Efecto** | El multiplicador que estima cada palanca (ej. +0.40 = +40%). |
| **Confianza** | Cuán respaldado está el número: alta / media / baja / supuesto. |
| **Banda P10–P90** | Rango probable del resultado (intervalo del 80%). |
| **Incrementalidad** | Qué parte de lo que vende un producto nuevo es crecimiento neto (no canibalización). |
| **Segmento** | Tipo de local para la elasticidad (con/sin Playland, mall, free-standing, etc.). |
| **Composición** | Combinar varias palancas en un mismo escenario. |
