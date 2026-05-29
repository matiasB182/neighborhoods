#!/usr/bin/env python3
"""Genera Tableau Packaged Workbook (.twbx) — Tablero Recomendaciones Comerciales"""

import zipfile
import os

UPLOAD_DIR = '/root/.claude/uploads/b93c094c-6396-4d3a-beb2-975e0f3decf5/'
OUTPUT_DIR = '/home/user/neighborhoods/'
OUTPUT_FILE = 'Tablero_Recomendaciones.twbx'

UPSELL_SRC = UPLOAD_DIR + 'ed9fbd21-recomendaciones_upsell_202605291036.csv'
RECENCIA_SRC = UPLOAD_DIR + '7894d62d-recomendaciones_recencia_202605291036.csv'
COMPLEMENTARIOS_SRC = UPLOAD_DIR + '319047f9-recomendaciones_complementarios_202605291035.csv'

UPSELL_CSV = 'recomendaciones_upsell.csv'
RECENCIA_CSV = 'recomendaciones_recencia.csv'
COMPLEMENTARIOS_CSV = 'recomendaciones_complementarios.csv'


# ─── DATASOURCES ────────────────────────────────────────────────────────────

def ds_upsell():
    return """  <datasource hasconnection='true' inline='true' name='upsell' caption='Recomendaciones Upsell'>
    <connection class='textscan' filename='./Data/Datasources/recomendaciones_upsell.csv' locale='es_PY' separator=',' start-of-week='sunday'>
      <relation name='recomendaciones_upsell.csv' table='[recomendaciones_upsell#csv]' type='table' />
    </connection>
    <column caption='ID Cliente'           datatype='string'   name='[cliente_id]'         role='dimension' type='nominal'/>
    <column caption='Razón Social'         datatype='string'   name='[razon_social]'        role='dimension' type='nominal'/>
    <column caption='RUC'                  datatype='string'   name='[ruc]'                 role='dimension' type='nominal'/>
    <column caption='Sub Sector'           datatype='string'   name='[sub_sector]'          role='dimension' type='nominal'/>
    <column caption='Family ID'            datatype='integer'  name='[family_id]'           role='dimension' type='ordinal'/>
    <column caption='Familia'              datatype='string'   name='[familia]'             role='dimension' type='nominal'/>
    <column caption='Equipo Actual'        datatype='string'   name='[grupo_equipo]'        role='dimension' type='nominal'/>
    <column caption='Recomendación'        datatype='string'   name='[grupo_comp]'          role='dimension' type='nominal'/>
    <column caption='Confianza'            datatype='real'     name='[confianza]'           role='measure'   type='quantitative'/>
    <column caption='Ranking'              datatype='integer'  name='[ranking]'             role='dimension' type='ordinal'/>
    <column caption='Enviado al Cliente'   datatype='boolean'  name='[enviado_cliente]'     role='dimension' type='nominal'/>
    <column caption='Segmento'             datatype='string'   name='[nombre_segmento]'     role='dimension' type='nominal'/>
    <column caption='Fecha Actualización'  datatype='datetime' name='[fecha_actualizacion]' role='dimension' type='ordinal'/>
    <column caption='Number of Records' datatype='integer' default-role='measure' formula='1' hidden='true' name='[Number of Records]' role='measure' type='quantitative'/>
  </datasource>"""


def ds_recencia():
    return """  <datasource hasconnection='true' inline='true' name='recencia' caption='Recomendaciones Recencia'>
    <connection class='textscan' filename='./Data/Datasources/recomendaciones_recencia.csv' locale='es_PY' separator=',' start-of-week='sunday'>
      <relation name='recomendaciones_recencia.csv' table='[recomendaciones_recencia#csv]' type='table' />
    </connection>
    <column caption='ID Cliente'                  datatype='string'   name='[cliente_id]'         role='dimension' type='nominal'/>
    <column caption='Razón Social'                datatype='string'   name='[razon_social]'        role='dimension' type='nominal'/>
    <column caption='RUC'                         datatype='string'   name='[ruc]'                 role='dimension' type='nominal'/>
    <column caption='Sub Sector'                  datatype='string'   name='[sub_sector]'          role='dimension' type='nominal'/>
    <column caption='Family ID'                   datatype='integer'  name='[family_id]'           role='dimension' type='ordinal'/>
    <column caption='Familia'                     datatype='string'   name='[familia]'             role='dimension' type='nominal'/>
    <column caption='Días desde Última Compra'    datatype='integer'  name='[recencia]'            role='measure'   type='quantitative'/>
    <column caption='Frecuencia Compra (días)'    datatype='real'     name='[frecuencia_compra]'   role='measure'   type='quantitative'/>
    <column caption='Nro. Ventas'                 datatype='integer'  name='[nro_ventas]'          role='measure'   type='quantitative'/>
    <column caption='Score Recencia'              datatype='real'     name='[score_recencia]'      role='measure'   type='quantitative'/>
    <column caption='Ranking'                     datatype='integer'  name='[ranking]'             role='dimension' type='ordinal'/>
    <column caption='Enviado al Cliente'          datatype='boolean'  name='[enviado_cliente]'     role='dimension' type='nominal'/>
    <column caption='Segmento'                    datatype='string'   name='[nombre_segmento]'     role='dimension' type='nominal'/>
    <column caption='Fecha Actualización'         datatype='datetime' name='[fecha_actualizacion]' role='dimension' type='ordinal'/>
    <column caption='Number of Records' datatype='integer' default-role='measure' formula='1' hidden='true' name='[Number of Records]' role='measure' type='quantitative'/>
  </datasource>"""


def ds_complementarios():
    return """  <datasource hasconnection='true' inline='true' name='complementarios' caption='Recomendaciones Complementarios'>
    <connection class='textscan' filename='./Data/Datasources/recomendaciones_complementarios.csv' locale='es_PY' separator=',' start-of-week='sunday'>
      <relation name='recomendaciones_complementarios.csv' table='[recomendaciones_complementarios#csv]' type='table' />
    </connection>
    <column caption='ID Cliente'                datatype='string'   name='[cliente_id]'         role='dimension' type='nominal'/>
    <column caption='Razón Social'              datatype='string'   name='[razon_social]'        role='dimension' type='nominal'/>
    <column caption='RUC'                       datatype='string'   name='[ruc]'                 role='dimension' type='nominal'/>
    <column caption='Sub Sector'                datatype='string'   name='[sub_sector]'          role='dimension' type='nominal'/>
    <column caption='Family ID'                 datatype='integer'  name='[family_id]'           role='dimension' type='ordinal'/>
    <column caption='Familia'                   datatype='string'   name='[familia]'             role='dimension' type='nominal'/>
    <column caption='Equipo Actual'             datatype='string'   name='[grupo_equipo]'        role='dimension' type='nominal'/>
    <column caption='Producto Complementario'   datatype='string'   name='[grupo_comp]'          role='dimension' type='nominal'/>
    <column caption='Confianza'                 datatype='real'     name='[confianza]'           role='measure'   type='quantitative'/>
    <column caption='Ranking'                   datatype='integer'  name='[ranking]'             role='dimension' type='ordinal'/>
    <column caption='Enviado al Cliente'        datatype='boolean'  name='[enviado_cliente]'     role='dimension' type='nominal'/>
    <column caption='Segmento'                  datatype='string'   name='[nombre_segmento]'     role='dimension' type='nominal'/>
    <column caption='Fecha Actualización'       datatype='datetime' name='[fecha_actualizacion]' role='dimension' type='ordinal'/>
    <column caption='Number of Records' datatype='integer' default-role='measure' formula='1' hidden='true' name='[Number of Records]' role='measure' type='quantitative'/>
  </datasource>"""


# ─── WORKSHEETS ─────────────────────────────────────────────────────────────

def sheet_bar_segmento(name, ds):
    return f"""  <worksheet name='{name}'>
    <table>
      <view>
        <datasources>
          <datasource name='{ds}'/>
        </datasources>
        <datasource-dependencies datasource='{ds}'>
          <column name='[Number of Records]'/>
          <column name='[nombre_segmento]'/>
          <column-instance column='[nombre_segmento]' derivation='None' name='[none:nombre_segmento:nk]' pivot='key' type='nominal'/>
          <column-instance column='[Number of Records]' derivation='Count' name='[cnt:Number of Records:qk]' pivot='key' type='quantitative'/>
        </datasource-dependencies>
        <shelf-sorts>
          <field-sort-spec column='[cnt:Number of Records:qk]' datasource='{ds}' direction='DESC'/>
        </shelf-sorts>
        <rows>[none:nombre_segmento:nk]</rows>
        <cols>[cnt:Number of Records:qk]</cols>
        <view-filters/>
        <slices>
          <column>[none:nombre_segmento:nk]</column>
        </slices>
        <lod>
          <level field='[none:nombre_segmento:nk]'/>
        </lod>
      </view>
      <style>
        <style-rule element='mark'>
          <encoding attr='type' value='bar'/>
          <encoding attr='color' field='[none:nombre_segmento:nk]' type='nominal'/>
        </style-rule>
      </style>
    </table>
  </worksheet>"""


def sheet_bar_familia(name, ds):
    return f"""  <worksheet name='{name}'>
    <table>
      <view>
        <datasources>
          <datasource name='{ds}'/>
        </datasources>
        <datasource-dependencies datasource='{ds}'>
          <column name='[Number of Records]'/>
          <column name='[familia]'/>
          <column-instance column='[familia]' derivation='None' name='[none:familia:nk]' pivot='key' type='nominal'/>
          <column-instance column='[Number of Records]' derivation='Count' name='[cnt:Number of Records:qk]' pivot='key' type='quantitative'/>
        </datasource-dependencies>
        <shelf-sorts>
          <field-sort-spec column='[cnt:Number of Records:qk]' datasource='{ds}' direction='DESC'/>
        </shelf-sorts>
        <rows>[none:familia:nk]</rows>
        <cols>[cnt:Number of Records:qk]</cols>
        <view-filters/>
        <slices>
          <column>[none:familia:nk]</column>
        </slices>
        <lod>
          <level field='[none:familia:nk]'/>
        </lod>
      </view>
      <style>
        <style-rule element='mark'>
          <encoding attr='type' value='bar'/>
          <encoding attr='color' field='[none:familia:nk]' type='nominal'/>
        </style-rule>
      </style>
    </table>
  </worksheet>"""


def sheet_tabla_upsell_comp(name, ds):
    return f"""  <worksheet name='{name}'>
    <table>
      <view>
        <datasources>
          <datasource name='{ds}'/>
        </datasources>
        <datasource-dependencies datasource='{ds}'>
          <column name='[razon_social]'/>
          <column name='[sub_sector]'/>
          <column name='[familia]'/>
          <column name='[grupo_equipo]'/>
          <column name='[grupo_comp]'/>
          <column name='[confianza]'/>
          <column name='[enviado_cliente]'/>
          <column name='[nombre_segmento]'/>
          <column-instance column='[razon_social]'     derivation='None' name='[none:razon_social:nk]'     pivot='key' type='nominal'/>
          <column-instance column='[sub_sector]'       derivation='None' name='[none:sub_sector:nk]'       pivot='key' type='nominal'/>
          <column-instance column='[familia]'          derivation='None' name='[none:familia:nk]'          pivot='key' type='nominal'/>
          <column-instance column='[grupo_equipo]'     derivation='None' name='[none:grupo_equipo:nk]'     pivot='key' type='nominal'/>
          <column-instance column='[grupo_comp]'       derivation='None' name='[none:grupo_comp:nk]'       pivot='key' type='nominal'/>
          <column-instance column='[confianza]'        derivation='Attr' name='[attr:confianza:qk]'        pivot='key' type='quantitative'/>
          <column-instance column='[enviado_cliente]'  derivation='None' name='[none:enviado_cliente:nk]'  pivot='key' type='nominal'/>
          <column-instance column='[nombre_segmento]'  derivation='None' name='[none:nombre_segmento:nk]'  pivot='key' type='nominal'/>
        </datasource-dependencies>
        <rows>[none:razon_social:nk][none:familia:nk][none:grupo_equipo:nk]</rows>
        <cols>[none:sub_sector:nk][none:nombre_segmento:nk][none:grupo_comp:nk][attr:confianza:qk][none:enviado_cliente:nk]</cols>
        <view-filters/>
      </view>
      <style>
        <style-rule element='mark'>
          <encoding attr='type' value='text'/>
        </style-rule>
      </style>
    </table>
  </worksheet>"""


def sheet_tabla_recencia(name, ds):
    return f"""  <worksheet name='{name}'>
    <table>
      <view>
        <datasources>
          <datasource name='{ds}'/>
        </datasources>
        <datasource-dependencies datasource='{ds}'>
          <column name='[razon_social]'/>
          <column name='[sub_sector]'/>
          <column name='[familia]'/>
          <column name='[recencia]'/>
          <column name='[nro_ventas]'/>
          <column name='[score_recencia]'/>
          <column name='[enviado_cliente]'/>
          <column name='[nombre_segmento]'/>
          <column-instance column='[razon_social]'     derivation='None' name='[none:razon_social:nk]'     pivot='key' type='nominal'/>
          <column-instance column='[sub_sector]'       derivation='None' name='[none:sub_sector:nk]'       pivot='key' type='nominal'/>
          <column-instance column='[familia]'          derivation='None' name='[none:familia:nk]'          pivot='key' type='nominal'/>
          <column-instance column='[recencia]'         derivation='Attr' name='[attr:recencia:qk]'         pivot='key' type='quantitative'/>
          <column-instance column='[nro_ventas]'       derivation='Attr' name='[attr:nro_ventas:qk]'       pivot='key' type='quantitative'/>
          <column-instance column='[score_recencia]'   derivation='Attr' name='[attr:score_recencia:qk]'   pivot='key' type='quantitative'/>
          <column-instance column='[enviado_cliente]'  derivation='None' name='[none:enviado_cliente:nk]'  pivot='key' type='nominal'/>
          <column-instance column='[nombre_segmento]'  derivation='None' name='[none:nombre_segmento:nk]'  pivot='key' type='nominal'/>
        </datasource-dependencies>
        <rows>[none:razon_social:nk][none:familia:nk]</rows>
        <cols>[none:sub_sector:nk][none:nombre_segmento:nk][attr:recencia:qk][attr:nro_ventas:qk][attr:score_recencia:qk][none:enviado_cliente:nk]</cols>
        <view-filters/>
      </view>
      <style>
        <style-rule element='mark'>
          <encoding attr='type' value='text'/>
        </style-rule>
      </style>
    </table>
  </worksheet>"""


# ─── DASHBOARDS ─────────────────────────────────────────────────────────────

def dashboard(name, s1, s2, s3):
    return f"""  <dashboard name='{name}'>
    <layout-options>
      <page>
        <zoom type='automatic'/>
      </page>
      <filter-show-all-value>true</filter-show-all-value>
    </layout-options>
    <zones>
      <zone h='100000' id='1' type='layout-basic' w='100000' x='0' y='0'>
        <zone h='100000' id='2' layout-style='ttb' type='layout-flow' w='100000' x='0' y='0'>
          <zone h='40000' id='3' layout-style='ltr' type='layout-flow' w='100000' x='0' y='0'>
            <zone h='40000' id='4' name='{s1}' param='{s1}' type='sheet' w='50000' x='0' y='0'/>
            <zone h='40000' id='5' name='{s2}' param='{s2}' type='sheet' w='50000' x='50000' y='0'/>
          </zone>
          <zone h='60000' id='6' name='{s3}' param='{s3}' type='sheet' w='100000' x='0' y='40000'/>
        </zone>
      </zone>
    </zones>
  </dashboard>"""


# ─── WORKBOOK ────────────────────────────────────────────────────────────────

def build_workbook():
    return f"""<?xml version='1.0' encoding='utf-8' ?>
<workbook source-build='2022.4.1' source-platform='win' version='18.1' xmlns:user='http://www.tableausoftware.com/xml/user'>
  <preferences>
    <color-palette name='Segmentos RFM' type='regular'>
      <color>#F5A623</color>
      <color>#D0021B</color>
      <color>#417505</color>
      <color>#7ED321</color>
      <color>#4A90E2</color>
      <color>#9013FE</color>
      <color>#F8E71C</color>
      <color>#8B572A</color>
      <color>#E94C4C</color>
    </color-palette>
  </preferences>
  <datasources>
{ds_upsell()}
{ds_recencia()}
{ds_complementarios()}
  </datasources>
  <worksheets>
{sheet_bar_segmento('Segmentos Upsell', 'upsell')}
{sheet_bar_familia('Familias Upsell', 'upsell')}
{sheet_tabla_upsell_comp('Tabla Upsell', 'upsell')}
{sheet_bar_segmento('Segmentos Recencia', 'recencia')}
{sheet_bar_familia('Familias Recencia', 'recencia')}
{sheet_tabla_recencia('Tabla Recencia', 'recencia')}
{sheet_bar_segmento('Segmentos Complementarios', 'complementarios')}
{sheet_bar_familia('Familias Complementarios', 'complementarios')}
{sheet_tabla_upsell_comp('Tabla Complementarios', 'complementarios')}
  </worksheets>
  <dashboards>
{dashboard('Recomendaciones Upsell', 'Segmentos Upsell', 'Familias Upsell', 'Tabla Upsell')}
{dashboard('Recomendaciones Recencia', 'Segmentos Recencia', 'Familias Recencia', 'Tabla Recencia')}
{dashboard('Recomendaciones Complementarios', 'Segmentos Complementarios', 'Familias Complementarios', 'Tabla Complementarios')}
  </dashboards>
</workbook>"""


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    twb = build_workbook()
    output_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)

    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('Tablero_Recomendaciones.twb', twb)
        zf.write(UPSELL_SRC,         f'Data/Datasources/{UPSELL_CSV}')
        zf.write(RECENCIA_SRC,       f'Data/Datasources/{RECENCIA_CSV}')
        zf.write(COMPLEMENTARIOS_SRC, f'Data/Datasources/{COMPLEMENTARIOS_CSV}')

    size_mb = os.path.getsize(output_path) / 1_000_000
    print(f'OK: {output_path}')
    print(f'Tamaño: {size_mb:.1f} MB')
    print('Contenido del ZIP:')
    with zipfile.ZipFile(output_path) as zf:
        for info in zf.infolist():
            print(f'  {info.filename} ({info.file_size:,} bytes)')


if __name__ == '__main__':
    main()
