#!/usr/bin/env python3
"""Genera Tableau Packaged Workbook (.twbx) — Tablero Recomendaciones Comerciales v2"""

import zipfile
import os

UPLOAD_DIR = '/root/.claude/uploads/b93c094c-6396-4d3a-beb2-975e0f3decf5/'
OUTPUT_DIR = '/home/user/neighborhoods/'
OUTPUT_FILE = 'Tablero_Recomendaciones.twbx'

UPSELL_SRC         = UPLOAD_DIR + 'ed9fbd21-recomendaciones_upsell_202605291036.csv'
RECENCIA_SRC       = UPLOAD_DIR + '7894d62d-recomendaciones_recencia_202605291036.csv'
COMPLEMENTARIOS_SRC = UPLOAD_DIR + '319047f9-recomendaciones_complementarios_202605291035.csv'

UPSELL_CSV         = 'recomendaciones_upsell.csv'
RECENCIA_CSV       = 'recomendaciones_recencia.csv'
COMPLEMENTARIOS_CSV = 'recomendaciones_complementarios.csv'

# ─── HELPERS ────────────────────────────────────────────────────────────────

def col(caption, name, datatype, role, col_type):
    """Column definition in datasource"""
    return f"    <column caption='{caption}' datatype='{datatype}' name='[{name}]' role='{role}' type='{col_type}'/>"

def col_ref(name, datatype, role, col_type):
    """Column reference inside datasource-dependencies"""
    return f"          <column datatype='{datatype}' name='[{name}]' role='{role}' type='{col_type}'/>"

def col_inst(field, datatype, deriv, inst_name, role, col_type):
    """Column instance (aggregated field reference)"""
    return f"          <column-instance column='[{field}]' datatype='{datatype}' derivation='{deriv}' name='{inst_name}' pivot='key' role='{role}' type='{col_type}'/>"


# ─── DATASOURCES ────────────────────────────────────────────────────────────

def ds_upsell():
    return f"""  <datasource hasconnection='true' inline='true' name='upsell' caption='Recomendaciones Upsell'>
    <connection class='textscan' filename='./Data/Datasources/{UPSELL_CSV}' locale='es_PY' separator=',' start-of-week='sunday'>
      <relation name='{UPSELL_CSV}' table='[recomendaciones_upsell#csv]' type='table' />
    </connection>
{col('ID Cliente',          'cliente_id',         'string',   'dimension', 'nominal')}
{col('Razón Social',        'razon_social',        'string',   'dimension', 'nominal')}
{col('RUC',                 'ruc',                 'string',   'dimension', 'nominal')}
{col('Sub Sector',          'sub_sector',          'string',   'dimension', 'nominal')}
{col('Family ID',           'family_id',           'integer',  'dimension', 'ordinal')}
{col('Familia',             'familia',             'string',   'dimension', 'nominal')}
{col('Equipo Actual',       'grupo_equipo',        'string',   'dimension', 'nominal')}
{col('Recomendación',       'grupo_comp',          'string',   'dimension', 'nominal')}
{col('Confianza',           'confianza',           'real',     'measure',   'quantitative')}
{col('Ranking',             'ranking',             'integer',  'dimension', 'ordinal')}
{col('Enviado al Cliente',  'enviado_cliente',     'boolean',  'dimension', 'nominal')}
{col('Segmento',            'nombre_segmento',     'string',   'dimension', 'nominal')}
{col('Fecha Actualización', 'fecha_actualizacion', 'datetime', 'dimension', 'ordinal')}
    <column caption='Number of Records' datatype='integer' hidden='true' name='[Number of Records]' role='measure' type='quantitative'>
      <calculation class='tableau' formula='1'/>
    </column>
  </datasource>"""


def ds_recencia():
    return f"""  <datasource hasconnection='true' inline='true' name='recencia' caption='Recomendaciones Recencia'>
    <connection class='textscan' filename='./Data/Datasources/{RECENCIA_CSV}' locale='es_PY' separator=',' start-of-week='sunday'>
      <relation name='{RECENCIA_CSV}' table='[recomendaciones_recencia#csv]' type='table' />
    </connection>
{col('ID Cliente',                 'cliente_id',         'string',   'dimension', 'nominal')}
{col('Razón Social',               'razon_social',        'string',   'dimension', 'nominal')}
{col('RUC',                        'ruc',                 'string',   'dimension', 'nominal')}
{col('Sub Sector',                 'sub_sector',          'string',   'dimension', 'nominal')}
{col('Family ID',                  'family_id',           'integer',  'dimension', 'ordinal')}
{col('Familia',                    'familia',             'string',   'dimension', 'nominal')}
{col('Días sin Comprar',           'recencia',            'integer',  'measure',   'quantitative')}
{col('Frecuencia Compra (días)',   'frecuencia_compra',   'real',     'measure',   'quantitative')}
{col('Nro. Ventas',                'nro_ventas',          'integer',  'measure',   'quantitative')}
{col('Score Recencia',             'score_recencia',      'real',     'measure',   'quantitative')}
{col('Ranking',                    'ranking',             'integer',  'dimension', 'ordinal')}
{col('Enviado al Cliente',         'enviado_cliente',     'boolean',  'dimension', 'nominal')}
{col('Segmento',                   'nombre_segmento',     'string',   'dimension', 'nominal')}
{col('Fecha Actualización',        'fecha_actualizacion', 'datetime', 'dimension', 'ordinal')}
    <column caption='Number of Records' datatype='integer' hidden='true' name='[Number of Records]' role='measure' type='quantitative'>
      <calculation class='tableau' formula='1'/>
    </column>
  </datasource>"""


def ds_complementarios():
    return f"""  <datasource hasconnection='true' inline='true' name='complementarios' caption='Recomendaciones Complementarios'>
    <connection class='textscan' filename='./Data/Datasources/{COMPLEMENTARIOS_CSV}' locale='es_PY' separator=',' start-of-week='sunday'>
      <relation name='{COMPLEMENTARIOS_CSV}' table='[recomendaciones_complementarios#csv]' type='table' />
    </connection>
{col('ID Cliente',                 'cliente_id',         'string',   'dimension', 'nominal')}
{col('Razón Social',               'razon_social',        'string',   'dimension', 'nominal')}
{col('RUC',                        'ruc',                 'string',   'dimension', 'nominal')}
{col('Sub Sector',                 'sub_sector',          'string',   'dimension', 'nominal')}
{col('Family ID',                  'family_id',           'integer',  'dimension', 'ordinal')}
{col('Familia',                    'familia',             'string',   'dimension', 'nominal')}
{col('Equipo Actual',              'grupo_equipo',        'string',   'dimension', 'nominal')}
{col('Producto Complementario',    'grupo_comp',          'string',   'dimension', 'nominal')}
{col('Confianza',                  'confianza',           'real',     'measure',   'quantitative')}
{col('Ranking',                    'ranking',             'integer',  'dimension', 'ordinal')}
{col('Enviado al Cliente',         'enviado_cliente',     'boolean',  'dimension', 'nominal')}
{col('Segmento',                   'nombre_segmento',     'string',   'dimension', 'nominal')}
{col('Fecha Actualización',        'fecha_actualizacion', 'datetime', 'dimension', 'ordinal')}
    <column caption='Number of Records' datatype='integer' hidden='true' name='[Number of Records]' role='measure' type='quantitative'>
      <calculation class='tableau' formula='1'/>
    </column>
  </datasource>"""


# ─── WORKSHEETS ─────────────────────────────────────────────────────────────

def sheet_bar_segmento(name, ds):
    """Bar chart: Segmentos (rows) vs Count (cols)"""
    return f"""  <worksheet name='{name}'>
    <table>
      <view>
        <datasources>
          <datasource name='{ds}'/>
        </datasources>
        <datasource-dependencies datasource='{ds}'>
{col_ref('nombre_segmento', 'string',  'dimension', 'nominal')}
{col_ref('Number of Records', 'integer', 'measure', 'quantitative')}
{col_inst('nombre_segmento', 'string',  'None',  '[none:nombre_segmento:nk]', 'dimension', 'nominal')}
{col_inst('Number of Records', 'integer', 'Count', '[cnt:Number of Records:qk]', 'measure', 'quantitative')}
        </datasource-dependencies>
      </view>
      <style/>
      <panes>
        <pane>
          <view>
            <datasource name='{ds}'/>
          </view>
          <mark class='Bar'/>
        </pane>
      </panes>
      <rows>[none:nombre_segmento:nk]</rows>
      <cols>[cnt:Number of Records:qk]</cols>
    </table>
  </worksheet>"""


def sheet_bar_familia(name, ds):
    """Bar chart: Familia (rows) vs Count (cols)"""
    return f"""  <worksheet name='{name}'>
    <table>
      <view>
        <datasources>
          <datasource name='{ds}'/>
        </datasources>
        <datasource-dependencies datasource='{ds}'>
{col_ref('familia', 'string',  'dimension', 'nominal')}
{col_ref('Number of Records', 'integer', 'measure', 'quantitative')}
{col_inst('familia', 'string',  'None',  '[none:familia:nk]', 'dimension', 'nominal')}
{col_inst('Number of Records', 'integer', 'Count', '[cnt:Number of Records:qk]', 'measure', 'quantitative')}
        </datasource-dependencies>
      </view>
      <style/>
      <panes>
        <pane>
          <view>
            <datasource name='{ds}'/>
          </view>
          <mark class='Bar'/>
        </pane>
      </panes>
      <rows>[none:familia:nk]</rows>
      <cols>[cnt:Number of Records:qk]</cols>
    </table>
  </worksheet>"""


def sheet_tabla_upsell_comp(name, ds):
    """Text table: razon_social, familia, grupo_equipo | sub_sector, segmento, grupo_comp, confianza, enviado"""
    return f"""  <worksheet name='{name}'>
    <table>
      <view>
        <datasources>
          <datasource name='{ds}'/>
        </datasources>
        <datasource-dependencies datasource='{ds}'>
{col_ref('razon_social',    'string',  'dimension', 'nominal')}
{col_ref('sub_sector',      'string',  'dimension', 'nominal')}
{col_ref('familia',         'string',  'dimension', 'nominal')}
{col_ref('grupo_equipo',    'string',  'dimension', 'nominal')}
{col_ref('grupo_comp',      'string',  'dimension', 'nominal')}
{col_ref('confianza',       'real',    'measure',   'quantitative')}
{col_ref('enviado_cliente', 'boolean', 'dimension', 'nominal')}
{col_ref('nombre_segmento', 'string',  'dimension', 'nominal')}
{col_inst('razon_social',    'string',  'None',    '[none:razon_social:nk]',    'dimension', 'nominal')}
{col_inst('sub_sector',      'string',  'None',    '[none:sub_sector:nk]',      'dimension', 'nominal')}
{col_inst('familia',         'string',  'None',    '[none:familia:nk]',         'dimension', 'nominal')}
{col_inst('grupo_equipo',    'string',  'None',    '[none:grupo_equipo:nk]',    'dimension', 'nominal')}
{col_inst('grupo_comp',      'string',  'None',    '[none:grupo_comp:nk]',      'dimension', 'nominal')}
{col_inst('confianza',       'real',    'Average', '[avg:confianza:qk]',        'measure',   'quantitative')}
{col_inst('enviado_cliente', 'boolean', 'None',    '[none:enviado_cliente:nk]', 'dimension', 'nominal')}
{col_inst('nombre_segmento', 'string',  'None',    '[none:nombre_segmento:nk]', 'dimension', 'nominal')}
        </datasource-dependencies>
      </view>
      <style/>
      <panes>
        <pane>
          <view>
            <datasource name='{ds}'/>
          </view>
          <mark class='Text'/>
        </pane>
      </panes>
      <rows>[none:razon_social:nk][none:familia:nk][none:grupo_equipo:nk]</rows>
      <cols>[none:sub_sector:nk][none:nombre_segmento:nk][none:grupo_comp:nk][avg:confianza:qk][none:enviado_cliente:nk]</cols>
    </table>
  </worksheet>"""


def sheet_tabla_recencia(name, ds):
    """Text table: razon_social, familia | sub_sector, segmento, recencia, nro_ventas, score, enviado"""
    return f"""  <worksheet name='{name}'>
    <table>
      <view>
        <datasources>
          <datasource name='{ds}'/>
        </datasources>
        <datasource-dependencies datasource='{ds}'>
{col_ref('razon_social',    'string',  'dimension', 'nominal')}
{col_ref('sub_sector',      'string',  'dimension', 'nominal')}
{col_ref('familia',         'string',  'dimension', 'nominal')}
{col_ref('recencia',        'integer', 'measure',   'quantitative')}
{col_ref('nro_ventas',      'integer', 'measure',   'quantitative')}
{col_ref('score_recencia',  'real',    'measure',   'quantitative')}
{col_ref('enviado_cliente', 'boolean', 'dimension', 'nominal')}
{col_ref('nombre_segmento', 'string',  'dimension', 'nominal')}
{col_inst('razon_social',    'string',  'None',    '[none:razon_social:nk]',    'dimension', 'nominal')}
{col_inst('sub_sector',      'string',  'None',    '[none:sub_sector:nk]',      'dimension', 'nominal')}
{col_inst('familia',         'string',  'None',    '[none:familia:nk]',         'dimension', 'nominal')}
{col_inst('recencia',        'integer', 'Average', '[avg:recencia:qk]',         'measure',   'quantitative')}
{col_inst('nro_ventas',      'integer', 'Sum',     '[sum:nro_ventas:qk]',       'measure',   'quantitative')}
{col_inst('score_recencia',  'real',    'Average', '[avg:score_recencia:qk]',   'measure',   'quantitative')}
{col_inst('enviado_cliente', 'boolean', 'None',    '[none:enviado_cliente:nk]', 'dimension', 'nominal')}
{col_inst('nombre_segmento', 'string',  'None',    '[none:nombre_segmento:nk]', 'dimension', 'nominal')}
        </datasource-dependencies>
      </view>
      <style/>
      <panes>
        <pane>
          <view>
            <datasource name='{ds}'/>
          </view>
          <mark class='Text'/>
        </pane>
      </panes>
      <rows>[none:razon_social:nk][none:familia:nk]</rows>
      <cols>[none:sub_sector:nk][none:nombre_segmento:nk][avg:recencia:qk][sum:nro_ventas:qk][avg:score_recencia:qk][none:enviado_cliente:nk]</cols>
    </table>
  </worksheet>"""


# ─── DASHBOARDS ─────────────────────────────────────────────────────────────

_zone_id = [10]

def next_id():
    _zone_id[0] += 1
    return _zone_id[0]


def dashboard(name, s1, s2, s3):
    """Dashboard: 2 charts on top (40%), detail table on bottom (60%)"""
    i1, i2, i3, i4, i5, i6 = next_id(), next_id(), next_id(), next_id(), next_id(), next_id()
    return f"""  <dashboard name='{name}'>
    <layout-options/>
    <zones>
      <zone h='100000' id='{i1}' type='layout-basic' w='100000' x='0' y='0'>
        <zone h='100000' id='{i2}' layout-style='ttb' type='layout-flow' w='100000' x='0' y='0'>
          <zone h='40000' id='{i3}' layout-style='ltr' type='layout-flow' w='100000' x='0' y='0'>
            <zone h='40000' id='{i4}' name='{s1}' param='{s1}' type='view' w='50000' x='0' y='0'/>
            <zone h='40000' id='{i5}' name='{s2}' param='{s2}' type='view' w='50000' x='50000' y='0'/>
          </zone>
          <zone h='60000' id='{i6}' name='{s3}' param='{s3}' type='view' w='100000' x='0' y='40000'/>
        </zone>
      </zone>
    </zones>
  </dashboard>"""


# ─── WORKBOOK ────────────────────────────────────────────────────────────────

def build_workbook():
    sheets = [
        sheet_bar_segmento('Segmentos Upsell',           'upsell'),
        sheet_bar_familia ('Familias Upsell',             'upsell'),
        sheet_tabla_upsell_comp('Tabla Upsell',           'upsell'),
        sheet_bar_segmento('Segmentos Recencia',          'recencia'),
        sheet_bar_familia ('Familias Recencia',           'recencia'),
        sheet_tabla_recencia('Tabla Recencia',            'recencia'),
        sheet_bar_segmento('Segmentos Complementarios',   'complementarios'),
        sheet_bar_familia ('Familias Complementarios',    'complementarios'),
        sheet_tabla_upsell_comp('Tabla Complementarios',  'complementarios'),
    ]
    dashboards = [
        dashboard('Recomendaciones Upsell',
                  'Segmentos Upsell', 'Familias Upsell', 'Tabla Upsell'),
        dashboard('Recomendaciones Recencia',
                  'Segmentos Recencia', 'Familias Recencia', 'Tabla Recencia'),
        dashboard('Recomendaciones Complementarios',
                  'Segmentos Complementarios', 'Familias Complementarios', 'Tabla Complementarios'),
    ]
    return (
        "<?xml version='1.0' encoding='utf-8' ?>\n"
        "<workbook source-build='2022.4.1' source-platform='win' version='18.1' "
        "xmlns:user='http://www.tableausoftware.com/xml/user'>\n"
        "  <datasources>\n"
        + ds_upsell() + "\n"
        + ds_recencia() + "\n"
        + ds_complementarios() + "\n"
        "  </datasources>\n"
        "  <worksheets>\n"
        + "\n".join(sheets) + "\n"
        "  </worksheets>\n"
        "  <dashboards>\n"
        + "\n".join(dashboards) + "\n"
        "  </dashboards>\n"
        "</workbook>\n"
    )


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    twb = build_workbook()
    output_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)

    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('Tablero_Recomendaciones.twb', twb)
        zf.write(UPSELL_SRC,          f'Data/Datasources/{UPSELL_CSV}')
        zf.write(RECENCIA_SRC,        f'Data/Datasources/{RECENCIA_CSV}')
        zf.write(COMPLEMENTARIOS_SRC, f'Data/Datasources/{COMPLEMENTARIOS_CSV}')

    size_mb = os.path.getsize(output_path) / 1_000_000
    print(f'OK: {output_path}  ({size_mb:.1f} MB)')
    print('Contenido:')
    with zipfile.ZipFile(output_path) as zf:
        for info in zf.infolist():
            print(f'  {info.filename}  ({info.file_size:,} bytes)')


if __name__ == '__main__':
    main()
