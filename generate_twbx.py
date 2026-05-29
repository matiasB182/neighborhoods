#!/usr/bin/env python3
"""Genera Tableau Packaged Workbook (.twbx) — Tablero Recomendaciones Comerciales v3"""

import zipfile
import os

UPLOAD_DIR = '/root/.claude/uploads/b93c094c-6396-4d3a-beb2-975e0f3decf5/'
OUTPUT_DIR = '/home/user/neighborhoods/'
OUTPUT_FILE = 'Tablero_Recomendaciones.twbx'

UPSELL_SRC          = UPLOAD_DIR + 'ed9fbd21-recomendaciones_upsell_202605291036.csv'
RECENCIA_SRC        = UPLOAD_DIR + '7894d62d-recomendaciones_recencia_202605291036.csv'
COMPLEMENTARIOS_SRC = UPLOAD_DIR + '319047f9-recomendaciones_complementarios_202605291035.csv'

UPSELL_CSV          = 'recomendaciones_upsell.csv'
RECENCIA_CSV        = 'recomendaciones_recencia.csv'
COMPLEMENTARIOS_CSV = 'recomendaciones_complementarios.csv'

# ─── HELPERS ────────────────────────────────────────────────────────────────

def col(caption, name, datatype, role, col_type):
    """Column definition in datasource."""
    return f"    <column caption='{caption}' datatype='{datatype}' name='[{name}]' role='{role}' type='{col_type}'/>"

def col_ref(name):
    """Bare column reference inside datasource-dependencies (no extra attrs needed)."""
    return f"          <column name='[{name}]'/>"

def col_inst(field, deriv, inst_name, inst_type):
    """Column instance: only column, derivation, name, pivot, type — no role/datatype."""
    return f"          <column-instance column='[{field}]' derivation='{deriv}' name='{inst_name}' pivot='key' type='{inst_type}'/>"

VIEW_REQUIRED_TAIL = """\
      <filter/>
      <sort/>
      <perspectives/>
      <aggregation value='true'/>"""


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
{col('ID Cliente',               'cliente_id',         'string',   'dimension', 'nominal')}
{col('Razón Social',             'razon_social',        'string',   'dimension', 'nominal')}
{col('RUC',                      'ruc',                 'string',   'dimension', 'nominal')}
{col('Sub Sector',               'sub_sector',          'string',   'dimension', 'nominal')}
{col('Family ID',                'family_id',           'integer',  'dimension', 'ordinal')}
{col('Familia',                  'familia',             'string',   'dimension', 'nominal')}
{col('Días sin Comprar',         'recencia',            'integer',  'measure',   'quantitative')}
{col('Frecuencia Compra (días)', 'frecuencia_compra',   'real',     'measure',   'quantitative')}
{col('Nro. Ventas',              'nro_ventas',          'integer',  'measure',   'quantitative')}
{col('Score Recencia',           'score_recencia',      'real',     'measure',   'quantitative')}
{col('Ranking',                  'ranking',             'integer',  'dimension', 'ordinal')}
{col('Enviado al Cliente',       'enviado_cliente',     'boolean',  'dimension', 'nominal')}
{col('Segmento',                 'nombre_segmento',     'string',   'dimension', 'nominal')}
{col('Fecha Actualización',      'fecha_actualizacion', 'datetime', 'dimension', 'ordinal')}
    <column caption='Number of Records' datatype='integer' hidden='true' name='[Number of Records]' role='measure' type='quantitative'>
      <calculation class='tableau' formula='1'/>
    </column>
  </datasource>"""


def ds_complementarios():
    return f"""  <datasource hasconnection='true' inline='true' name='complementarios' caption='Recomendaciones Complementarios'>
    <connection class='textscan' filename='./Data/Datasources/{COMPLEMENTARIOS_CSV}' locale='es_PY' separator=',' start-of-week='sunday'>
      <relation name='{COMPLEMENTARIOS_CSV}' table='[recomendaciones_complementarios#csv]' type='table' />
    </connection>
{col('ID Cliente',              'cliente_id',         'string',   'dimension', 'nominal')}
{col('Razón Social',            'razon_social',        'string',   'dimension', 'nominal')}
{col('RUC',                     'ruc',                 'string',   'dimension', 'nominal')}
{col('Sub Sector',              'sub_sector',          'string',   'dimension', 'nominal')}
{col('Family ID',               'family_id',           'integer',  'dimension', 'ordinal')}
{col('Familia',                 'familia',             'string',   'dimension', 'nominal')}
{col('Equipo Actual',           'grupo_equipo',        'string',   'dimension', 'nominal')}
{col('Prod. Complementario',    'grupo_comp',          'string',   'dimension', 'nominal')}
{col('Confianza',               'confianza',           'real',     'measure',   'quantitative')}
{col('Ranking',                 'ranking',             'integer',  'dimension', 'ordinal')}
{col('Enviado al Cliente',      'enviado_cliente',     'boolean',  'dimension', 'nominal')}
{col('Segmento',                'nombre_segmento',     'string',   'dimension', 'nominal')}
{col('Fecha Actualización',     'fecha_actualizacion', 'datetime', 'dimension', 'ordinal')}
    <column caption='Number of Records' datatype='integer' hidden='true' name='[Number of Records]' role='measure' type='quantitative'>
      <calculation class='tableau' formula='1'/>
    </column>
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
{col_ref('nombre_segmento')}
{col_ref('Number of Records')}
{col_inst('nombre_segmento',  'None',  '[none:nombre_segmento:nk]',  'nominal')}
{col_inst('Number of Records','Count', '[cnt:Number of Records:qk]', 'quantitative')}
        </datasource-dependencies>
{VIEW_REQUIRED_TAIL}
      </view>
      <style/>
      <panes>
        <pane selectable='true'>
          <mark class='Bar'/>
        </pane>
      </panes>
      <rows>[none:nombre_segmento:nk]</rows>
      <cols>[cnt:Number of Records:qk]</cols>
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
{col_ref('familia')}
{col_ref('Number of Records')}
{col_inst('familia',          'None',  '[none:familia:nk]',          'nominal')}
{col_inst('Number of Records','Count', '[cnt:Number of Records:qk]', 'quantitative')}
        </datasource-dependencies>
{VIEW_REQUIRED_TAIL}
      </view>
      <style/>
      <panes>
        <pane selectable='true'>
          <mark class='Bar'/>
        </pane>
      </panes>
      <rows>[none:familia:nk]</rows>
      <cols>[cnt:Number of Records:qk]</cols>
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
{col_ref('razon_social')}
{col_ref('sub_sector')}
{col_ref('familia')}
{col_ref('grupo_equipo')}
{col_ref('grupo_comp')}
{col_ref('confianza')}
{col_ref('enviado_cliente')}
{col_ref('nombre_segmento')}
{col_inst('razon_social',    'None', '[none:razon_social:nk]',    'nominal')}
{col_inst('sub_sector',      'None', '[none:sub_sector:nk]',      'nominal')}
{col_inst('familia',         'None', '[none:familia:nk]',         'nominal')}
{col_inst('grupo_equipo',    'None', '[none:grupo_equipo:nk]',    'nominal')}
{col_inst('grupo_comp',      'None', '[none:grupo_comp:nk]',      'nominal')}
{col_inst('confianza',       'Avg',  '[avg:confianza:qk]',        'quantitative')}
{col_inst('enviado_cliente', 'None', '[none:enviado_cliente:nk]', 'nominal')}
{col_inst('nombre_segmento', 'None', '[none:nombre_segmento:nk]', 'nominal')}
        </datasource-dependencies>
{VIEW_REQUIRED_TAIL}
      </view>
      <style/>
      <panes>
        <pane selectable='true'>
          <mark class='Text'/>
        </pane>
      </panes>
      <rows>[none:razon_social:nk][none:familia:nk][none:grupo_equipo:nk]</rows>
      <cols>[none:sub_sector:nk][none:nombre_segmento:nk][none:grupo_comp:nk][avg:confianza:qk][none:enviado_cliente:nk]</cols>
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
{col_ref('razon_social')}
{col_ref('sub_sector')}
{col_ref('familia')}
{col_ref('recencia')}
{col_ref('nro_ventas')}
{col_ref('score_recencia')}
{col_ref('enviado_cliente')}
{col_ref('nombre_segmento')}
{col_inst('razon_social',   'None', '[none:razon_social:nk]',    'nominal')}
{col_inst('sub_sector',     'None', '[none:sub_sector:nk]',      'nominal')}
{col_inst('familia',        'None', '[none:familia:nk]',         'nominal')}
{col_inst('recencia',       'Avg',  '[avg:recencia:qk]',         'quantitative')}
{col_inst('nro_ventas',     'Sum',  '[sum:nro_ventas:qk]',       'quantitative')}
{col_inst('score_recencia', 'Avg',  '[avg:score_recencia:qk]',   'quantitative')}
{col_inst('enviado_cliente','None', '[none:enviado_cliente:nk]', 'nominal')}
{col_inst('nombre_segmento','None', '[none:nombre_segmento:nk]', 'nominal')}
        </datasource-dependencies>
{VIEW_REQUIRED_TAIL}
      </view>
      <style/>
      <panes>
        <pane selectable='true'>
          <mark class='Text'/>
        </pane>
      </panes>
      <rows>[none:razon_social:nk][none:familia:nk]</rows>
      <cols>[none:sub_sector:nk][none:nombre_segmento:nk][avg:recencia:qk][sum:nro_ventas:qk][avg:score_recencia:qk][none:enviado_cliente:nk]</cols>
    </table>
  </worksheet>"""


# ─── DASHBOARDS ─────────────────────────────────────────────────────────────

_zone_id = [10]

def _id():
    _zone_id[0] += 1
    return _zone_id[0]


def dashboard(name, s1, s2, s3):
    """
    Layout: 2 bar charts side-by-side (top 40%), detail table full-width (bottom 60%).
    Worksheet zones have no 'type' attribute — layout containers keep type.
    """
    i1, i2, i3 = _id(), _id(), _id()
    i4, i5, i6 = _id(), _id(), _id()
    return f"""  <dashboard name='{name}'>
    <layout-options/>
    <zones>
      <zone h='100000' id='{i1}' type='layout-basic' w='100000' x='0' y='0'>
        <zone h='100000' id='{i2}' layout-style='ttb' type='layout-flow' w='100000' x='0' y='0'>
          <zone h='40000' id='{i3}' layout-style='ltr' type='layout-flow' w='100000' x='0' y='0'>
            <zone h='40000' id='{i4}' name='{s1}' param='{s1}' w='50000' x='0' y='0'/>
            <zone h='40000' id='{i5}' name='{s2}' param='{s2}' w='50000' x='50000' y='0'/>
          </zone>
          <zone h='60000' id='{i6}' name='{s3}' param='{s3}' w='100000' x='0' y='40000'/>
        </zone>
      </zone>
    </zones>
  </dashboard>"""


# ─── WORKBOOK ────────────────────────────────────────────────────────────────

def build_workbook():
    sheets = "\n".join([
        sheet_bar_segmento('Segmentos Upsell',          'upsell'),
        sheet_bar_familia ('Familias Upsell',            'upsell'),
        sheet_tabla_upsell_comp('Tabla Upsell',          'upsell'),
        sheet_bar_segmento('Segmentos Recencia',         'recencia'),
        sheet_bar_familia ('Familias Recencia',          'recencia'),
        sheet_tabla_recencia('Tabla Recencia',           'recencia'),
        sheet_bar_segmento('Segmentos Complementarios',  'complementarios'),
        sheet_bar_familia ('Familias Complementarios',   'complementarios'),
        sheet_tabla_upsell_comp('Tabla Complementarios', 'complementarios'),
    ])
    dashboards = "\n".join([
        dashboard('Recomendaciones Upsell',
                  'Segmentos Upsell', 'Familias Upsell', 'Tabla Upsell'),
        dashboard('Recomendaciones Recencia',
                  'Segmentos Recencia', 'Familias Recencia', 'Tabla Recencia'),
        dashboard('Recomendaciones Complementarios',
                  'Segmentos Complementarios', 'Familias Complementarios', 'Tabla Complementarios'),
    ])
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
        + sheets + "\n"
        "  </worksheets>\n"
        "  <dashboards>\n"
        + dashboards + "\n"
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
    with zipfile.ZipFile(output_path) as zf:
        for info in zf.infolist():
            print(f'  {info.filename}  ({info.file_size:,} bytes)')


if __name__ == '__main__':
    main()
