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
CREATE TABLE IF NOT EXISTS {schema}.promociones (
    campania      VARCHAR(500)  NOT NULL,
    codigo        BIGINT        NOT NULL,
    descripcion   VARCHAR(200)  NOT NULL,
    PRIMARY KEY (campania, codigo)
) DISTSTYLE ALL;

-- Hoja "Códigos Lanzamientos": lanzamientos y sus productos
CREATE TABLE IF NOT EXISTS {schema}.lanzamientos (
    lanzamiento   VARCHAR(500)  NOT NULL,
    codigo        BIGINT        NOT NULL,
    descripcion   VARCHAR(200)  NOT NULL,
    PRIMARY KEY (lanzamiento, codigo)
) DISTSTYLE ALL;

-- Hoja "Aperturas": locales con flags de canales
CREATE TABLE IF NOT EXISTS {schema}.apertura_restaurantes (
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
