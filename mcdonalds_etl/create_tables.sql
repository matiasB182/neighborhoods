-- ============================================================
-- McDonald's ETL - DDL Redshift (4 tablas, una por hoja)
-- Schema configurado via variable REDSHIFT_SCHEMA
-- ============================================================

-- Hoja "Precios" unpivoteada: una fila por producto x mes
CREATE TABLE IF NOT EXISTS {schema}.precio_productos (
    codigo        BIGINT        NOT NULL,
    descripcion   VARCHAR(200)  NOT NULL,
    anio          SMALLINT      NOT NULL,
    mes           SMALLINT      NOT NULL,
    precio        NUMERIC(12,2),
    PRIMARY KEY (codigo, anio, mes)
) DISTKEY (codigo) SORTKEY (anio, mes);

-- Hoja "Códigos-Promo": campañas y sus productos
-- fecha_desde/fecha_hasta: fechas exactas de la promo (col D y E del Excel, opcionales)
CREATE TABLE IF NOT EXISTS {schema}.promociones (
    campania      VARCHAR(500)  NOT NULL,
    codigo        BIGINT        NOT NULL,
    descripcion   VARCHAR(200)  NOT NULL,
    fecha_desde   DATE,
    fecha_hasta   DATE,
    PRIMARY KEY (campania, codigo)
) DISTSTYLE ALL;

-- Hoja "Códigos Lanzamientos": lanzamientos y sus productos
CREATE TABLE IF NOT EXISTS {schema}.lanzamientos (
    lanzamiento   VARCHAR(500)  NOT NULL,
    codigo        BIGINT        NOT NULL,
    descripcion   VARCHAR(200)  NOT NULL,
    PRIMARY KEY (lanzamiento, codigo)
) DISTSTYLE ALL;

-- Competencia por local: competidores, radio y tipo
CREATE TABLE IF NOT EXISTS {schema}.competencia (
    local_numero    INT           NOT NULL,
    short_name      VARCHAR(10)   NOT NULL,
    competidor      VARCHAR(200)  NOT NULL,
    radio_km        NUMERIC(4,1)  NOT NULL,
    tipo            VARCHAR(50),
    PRIMARY KEY (local_numero, competidor)
) DISTSTYLE ALL;

-- Hoja "Aperturas": locales con flags de canales
-- M=Mostrador, A=Automac, D=Delivery, X=Kiosco Digital, K=Centro de Postres
CREATE TABLE IF NOT EXISTS {schema}.apertura_restaurantes (
    api_id                  INT         NOT NULL,
    short_name              VARCHAR(10) NOT NULL,
    fecha_apertura          DATE,
    tiene_mostrador         BOOLEAN     NOT NULL DEFAULT FALSE,
    tiene_automac           BOOLEAN     NOT NULL DEFAULT FALSE,
    tiene_delivery          BOOLEAN     NOT NULL DEFAULT FALSE,
    tiene_kiosco_digital    BOOLEAN     NOT NULL DEFAULT FALSE,
    tiene_centro_postres    BOOLEAN     NOT NULL DEFAULT FALSE,
    PRIMARY KEY (api_id)
) DISTSTYLE ALL;

-- Excel "Dimensión Locales": info geográfica y física de cada local
-- Complementa apertura_restaurantes, join por short_name.
-- lat/lon: coordenadas GPS para cálculos de distancia (palanca competencia)
-- ciudad/estado: para filtros de zona (barrio/distrito/dpto)
-- store_type: IS=Inline Store, FS=Free Standing, MS=Mall Store, FC=Food Court
-- dt_type: Single=1 calle Automac, Double=2 calles, None=sin Automac
CREATE TABLE IF NOT EXISTS {schema}.locales_dimension (
    short_name          VARCHAR(10)     NOT NULL,
    lat                 NUMERIC(10,7),
    lon                 NUMERIC(10,7),
    ciudad              VARCHAR(100),
    estado              VARCHAR(100),
    store_type          VARCHAR(5),      -- IS=Inline, FS=Free Standing, MS=Mall, FC=Food Court
    dt_type             VARCHAR(10),     -- Single / Double / NULL=sin Automac
    num_soks            SMALLINT,        -- cantidad de kioscos de autoservicio
    bldg_size_m2        NUMERIC(8,2),    -- tamaño del edificio en m2
    land_size_m2        NUMERIC(10,2),   -- tamaño del terreno en m2
    tiene_mccafe        BOOLEAN         NOT NULL DEFAULT FALSE,
    tiene_playplace     BOOLEAN         NOT NULL DEFAULT FALSE,
    brand_extension     VARCHAR(200),    -- canales: Delivery, Desert Center, Walkup window, etc.
    last_reimage_date   SMALLINT,        -- año del último reimage (renovación)
    PRIMARY KEY (short_name)
) DISTSTYLE ALL;
