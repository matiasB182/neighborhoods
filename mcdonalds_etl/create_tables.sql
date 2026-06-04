-- ============================================================
-- McDonald's ETL - DDL Redshift
-- Schema configurado via variable REDSHIFT_SCHEMA
-- Sin foreign keys (Redshift no las enforcea de todas formas)
-- ============================================================

CREATE TABLE IF NOT EXISTS {schema}.ref_productos (
    codigo        BIGINT        NOT NULL,
    descripcion   VARCHAR(200)  NOT NULL,
    PRIMARY KEY (codigo)
) DISTSTYLE ALL;

CREATE TABLE IF NOT EXISTS {schema}.fact_precios (
    codigo        BIGINT        NOT NULL,
    anio          SMALLINT      NOT NULL,
    mes           SMALLINT      NOT NULL,
    precio        NUMERIC(12,2),
    PRIMARY KEY (codigo, anio, mes)
) DISTKEY (codigo) SORTKEY (anio, mes);

CREATE TABLE IF NOT EXISTS {schema}.ref_campanias (
    campania_id   INT           NOT NULL,
    descripcion   VARCHAR(500)  NOT NULL,
    PRIMARY KEY (campania_id)
) DISTSTYLE ALL;

CREATE TABLE IF NOT EXISTS {schema}.ref_campania_productos (
    campania_id   INT           NOT NULL,
    codigo        BIGINT        NOT NULL,
    descripcion   VARCHAR(200)  NOT NULL,
    PRIMARY KEY (campania_id, codigo)
) DISTKEY (codigo) SORTKEY (campania_id);

CREATE TABLE IF NOT EXISTS {schema}.ref_lanzamientos (
    lanzamiento_id  INT          NOT NULL,
    descripcion     VARCHAR(500) NOT NULL,
    PRIMARY KEY (lanzamiento_id)
) DISTSTYLE ALL;

CREATE TABLE IF NOT EXISTS {schema}.ref_lanzamiento_productos (
    lanzamiento_id  INT          NOT NULL,
    codigo          BIGINT       NOT NULL,
    descripcion     VARCHAR(200) NOT NULL,
    PRIMARY KEY (lanzamiento_id, codigo)
) DISTKEY (codigo) SORTKEY (lanzamiento_id);

CREATE TABLE IF NOT EXISTS {schema}.ref_locales (
    api_id            INT         NOT NULL,
    short_name        VARCHAR(10) NOT NULL,
    fecha_apertura    DATE,
    tiene_mostrador   BOOLEAN     NOT NULL DEFAULT FALSE,
    tiene_automac     BOOLEAN     NOT NULL DEFAULT FALSE,
    tiene_delivery    BOOLEAN     NOT NULL DEFAULT FALSE,
    tiene_app         BOOLEAN     NOT NULL DEFAULT FALSE,
    tiene_kiosco      BOOLEAN     NOT NULL DEFAULT FALSE,
    PRIMARY KEY (api_id)
) DISTSTYLE ALL;
