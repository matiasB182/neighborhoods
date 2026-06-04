-- ============================================================
-- McDonald's ETL - DDL Redshift
-- Schema configurado via variable REDSHIFT_SCHEMA
-- ============================================================

-- Productos (maestro de ítems del menú)
CREATE TABLE IF NOT EXISTS {schema}.ref_productos (
    codigo        BIGINT        NOT NULL,
    descripcion   VARCHAR(200)  NOT NULL,
    CONSTRAINT pk_productos PRIMARY KEY (codigo)
)
DISTSTYLE ALL;

-- Precios históricos mensuales (unpivot de la hoja Precios)
CREATE TABLE IF NOT EXISTS {schema}.fact_precios (
    codigo        BIGINT          NOT NULL,
    anio          SMALLINT        NOT NULL,
    mes           SMALLINT        NOT NULL,
    precio        NUMERIC(12,2),
    CONSTRAINT pk_precios PRIMARY KEY (codigo, anio, mes)
)
DISTKEY (codigo)
SORTKEY (anio, mes);

-- Campañas promocionales
CREATE TABLE IF NOT EXISTS {schema}.ref_campanias (
    campania_id   INT IDENTITY(1,1),
    descripcion   VARCHAR(500)  NOT NULL,
    CONSTRAINT pk_campanias PRIMARY KEY (campania_id)
)
DISTSTYLE ALL;

-- Productos por campaña
CREATE TABLE IF NOT EXISTS {schema}.ref_campania_productos (
    campania_id   INT           NOT NULL,
    codigo        BIGINT        NOT NULL,
    descripcion   VARCHAR(200)  NOT NULL,
    CONSTRAINT pk_campania_prod PRIMARY KEY (campania_id, codigo),
    CONSTRAINT fk_cp_campania FOREIGN KEY (campania_id)
        REFERENCES {schema}.ref_campanias(campania_id)
)
DISTKEY (codigo)
SORTKEY (campania_id);

-- Lanzamientos de productos
CREATE TABLE IF NOT EXISTS {schema}.ref_lanzamientos (
    lanzamiento_id  INT IDENTITY(1,1),
    descripcion     VARCHAR(500)  NOT NULL,
    CONSTRAINT pk_lanzamientos PRIMARY KEY (lanzamiento_id)
)
DISTSTYLE ALL;

-- Productos por lanzamiento
CREATE TABLE IF NOT EXISTS {schema}.ref_lanzamiento_productos (
    lanzamiento_id  INT           NOT NULL,
    codigo          BIGINT        NOT NULL,
    descripcion     VARCHAR(200)  NOT NULL,
    CONSTRAINT pk_lanz_prod PRIMARY KEY (lanzamiento_id, codigo),
    CONSTRAINT fk_lp_lanz FOREIGN KEY (lanzamiento_id)
        REFERENCES {schema}.ref_lanzamientos(lanzamiento_id)
)
DISTKEY (codigo)
SORTKEY (lanzamiento_id);

-- Locales con flags de canales
CREATE TABLE IF NOT EXISTS {schema}.ref_locales (
    api_id            INT          NOT NULL,
    short_name        VARCHAR(10)  NOT NULL,
    fecha_apertura    DATE,
    tiene_mostrador   BOOLEAN      NOT NULL DEFAULT FALSE,
    tiene_automac     BOOLEAN      NOT NULL DEFAULT FALSE,
    tiene_delivery    BOOLEAN      NOT NULL DEFAULT FALSE,
    tiene_app         BOOLEAN      NOT NULL DEFAULT FALSE,
    tiene_kiosco      BOOLEAN      NOT NULL DEFAULT FALSE,
    CONSTRAINT pk_locales PRIMARY KEY (api_id)
)
DISTSTYLE ALL;
