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
