#!/usr/bin/env python3
"""Genera Tableau Packaged Workbook (.twbx) — Tablero Recomendaciones Comerciales v4"""

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

def ds_col(caption, name, datatype, role, col_type):
    """Column definition in <datasource>."""
    return f"    <column caption='{caption}' datatype='{datatype}' name='[{name}]' role='{role}' type='{col_type}'/>"

def dep_col(name, datatype, role, col_type):
    """Column reference inside <datasource-dependencies> — needs role/type/datatype."""
    return f"          <column datatype='{datatype}' name='[{name}]' role='{role}' type='{col_type}'/>"

def col_inst(field, deriv, inst_name, inst_type):
    """Column-instance: only column/derivation/name/pivot/type — no role, no datatype."""
    return f"          <column-instance column='[{field}]' derivation='{deriv}' name='{inst_name}' pivot='key' type='{inst_type}'/>"


# ─── DATASOURCES ────────────────────────────────────────────────────────────

def ds_upsell():
    return f"""  <datasource hasconnection='true' inline='true' name='upsell' caption='Recomendaciones Upsell'>
    <connection class='textscan' filename='./Data/Datasources/{UPSELL_CSV}' locale='es_PY' separator=',' start-of-week='sunday'>
      <relation name='{UPSELL_CSV}' table='[recomendaciones_upsell#csv]' type='table' />
    </connection>
{ds_col('ID Cliente',          'cliente_id',         'string',   'dimension', 'nominal')}
{ds_col('Razón Social',        'razon_social',        'string',   'dimension', 'nominal')}
{ds_col('RUC',                 'ruc',                 'string',   'dimension', 'nominal')}
{ds_col('Sub Sector',          'sub_sector',          'string',   'dimension', 'nominal')}
{ds_col('Family ID',           'family_id',           'integer',  'dimension', 'ordinal')}
{ds_col('Familia',             'familia',             'string',   'dimension', 'nominal')}
{ds_col('Equipo Actual',       'grupo_equipo',        'string',   'dimension', 'nominal')}
{ds_col('Recomendación',       'grupo_comp',          'string',   'dimension', 'nominal')}
{ds_col('Confianza',           'confianza',           'real',     'measure',   'quantitative')}
{ds_col('Ranking',             'ranking',             'integer',  'dimension', 'ordinal')}
{ds_col('Enviado al Cliente',  'enviado_cliente',     'boolean',  'dimension', 'nominal')}
{ds_col('Segmento',            'nombre_segmento',     'string',   'dimension', 'nominal')}
{ds_col('Fecha Actualización', 'fecha_actualizacion', 'datetime', 'dimension', 'ordinal')}
    <column caption='Number of Records' datatype='integer' hidden='true' name='[Number of Records]' role='measure' type='quantitative'>
      <calculation class='tableau' formula='1'/>
    </column>
  </datasource>"""


def ds_recencia():
    return f"""  <datasource hasconnection='true' inline='true' name='recencia' caption='Recomendaciones Recencia'>
    <connection class='textscan' filename='./Data/Datasources/{RECENCIA_CSV}' locale='es_PY' separator=',' start-of-week='sunday'>
      <relation name='{RECENCIA_CSV}' table='[recomendaciones_recencia#csv]' type='table' />
    </connection>
{ds_col('ID Cliente',               'cliente_id',         'string',   'dimension', 'nominal')}
{ds_col('Razón Social',             'razon_social',        'string',   'dimension', 'nominal')}
{ds_col('RUC',                      'ruc',                 'string',   'dimension', 'nominal')}
{ds_col('Sub Sector',               'sub_sector',          'string',   'dimension', 'nominal')}
{ds_col('Family ID',                'family_id',           'integer',  'dimension', 'ordinal')}
{ds_col('Familia',                  'familia',             'string',   'dimension', 'nominal')}
{ds_col('Días sin Comprar',         'recencia',            'integer',  'measure',   'quantitative')}
{ds_col('Frecuencia Compra (días)', 'frecuencia_compra',   'real',     'measure',   'quantitative')}
{ds_col('Nro. Ventas',              'nro_ventas',          'integer',  'measure',   'quantitative')}
{ds_col('Score Recencia',           'score_recencia',      'real',     'measure',   'quantitative')}
{ds_col('Ranking',                  'ranking',             'integer',  'dimension', 'ordinal')}
{ds_col('Enviado al Cliente',       'enviado_cliente',     'boolean',  'dimension', 'nominal')}
{ds_col('Segmento',                 'nombre_segmento',     'string',   'dimension', 'nominal')}
{ds_col('Fecha Actualización',      'fecha_actualizacion', 'datetime', 'dimension', 'ordinal')}
    <column caption='Number of Records' datatype='integer' hidden='true' name='[Number of Records]' role='measure' type='quantitative'>
      <calculation class='tableau' formula='1'/>
    </column>
  </datasource>"""


def ds_complementarios():
    return f"""  <datasource hasconnection='true' inline='true' name='complementarios' caption='Recomendaciones Complementarios'>
    <connection class='textscan' filename='./Data/Datasources/{COMPLEMENTARIOS_CSV}' locale='es_PY' separator=',' start-of-week='sunday'>
      <relation name='{COMPLEMENTARIOS_CSV}' table='[recomendaciones_complementarios#csv]' type='table' />
    </connection>
{ds_col('ID Cliente',              'cliente_id',         'string',   'dimension', 'nominal')}
{ds_col('Razón Social',            'razon_social',        'string',   'dimension', 'nominal')}
{ds_col('RUC',                     'ruc',                 'string',   'dimension', 'nominal')}
{ds_col('Sub Sector',              'sub_sector',          'string',   'dimension', 'nominal')}
{ds_col('Family ID',               'family_id',           'integer',  'dimension', 'ordinal')}
{ds_col('Familia',                 'familia',             'string',   'dimension', 'nominal')}
{ds_col('Equipo Actual',           'grupo_equipo',        'string',   'dimension', 'nominal')}
{ds_col('Prod. Complementario',    'grupo_comp',          'string',   'dimension', 'nominal')}
{ds_col('Confianza',               'confianza',           'real',     'measure',   'quantitative')}
{ds_col('Ranking',                 'ranking',             'integer',  'dimension', 'ordinal')}
{ds_col('Enviado al Cliente',      'enviado_cliente',     'boolean',  'dimension', 'nominal')}
{ds_col('Segmento',                'nombre_segmento',     'string',   'dimension', 'nominal')}
{ds_col('Fecha Actualización',     'fecha_actualizacion', 'datetime', 'dimension', 'ordinal')}
    <column caption='Number of Records' datatype='integer' hidden='true' name='[Number of Records]' role='measure' type='quantitative'>
      <calculation class='tableau' formula='1'/>
    </column>
  </datasource>"""


# ─── WORKSHEETS ─────────────────────────────────────────────────────────────
# Pane structure (from schema): (view, mark, mark-sizing?, encodings?, ...)
# view inside pane has content model (breakdown) → <view/> empty is valid.
# filter inside view requires class + column attrs → use pass-all wildcard per dim field.
# sort requires class + column + direction → use unspecified class.

def _view_tail(filter_col, sort_col):
    """Required elements at end of <view>: filter, sort, perspectives, aggregation."""
    return f"""\
      <filter class='wildcard' column='{filter_col}' required='false'>
        <wildcard-matches>
          <wildcard-match match='' type='match-all'/>
        </wildcard-matches>
      </filter>
      <sort class='unspecified' column='{sort_col}' direction='ASC'/>
      <perspectives/>
      <aggregation value='true'/>"""


def sheet_bar_segmento(name, ds):
    inst_seg = '[none:nombre_segmento:nk]'
    inst_cnt = '[cnt:Number of Records:qk]'
    return f"""  <worksheet name='{name}'>
    <table>
      <view>
        <datasources>
          <datasource name='{ds}'/>
        </datasources>
        <datasource-dependencies datasource='{ds}'>
{dep_col('nombre_segmento',  'string',  'dimension', 'nominal')}
{dep_col('Number of Records','integer', 'measure',   'quantitative')}
{col_inst('nombre_segmento',  'None',  inst_seg, 'nominal')}
{col_inst('Number of Records','Count', inst_cnt, 'quantitative')}
        </datasource-dependencies>
{_view_tail(inst_seg, inst_seg)}
      </view>
      <style/>
      <panes>
        <pane>
          <view/>
          <mark class='Bar'/>
        </pane>
      </panes>
      <rows>{inst_seg}</rows>
      <cols>{inst_cnt}</cols>
    </table>
  </worksheet>"""


def sheet_bar_familia(name, ds):
    inst_fam = '[none:familia:nk]'
    inst_cnt = '[cnt:Number of Records:qk]'
    return f"""  <worksheet name='{name}'>
    <table>
      <view>
        <datasources>
          <datasource name='{ds}'/>
        </datasources>
        <datasource-dependencies datasource='{ds}'>
{dep_col('familia',          'string',  'dimension', 'nominal')}
{dep_col('Number of Records','integer', 'measure',   'quantitative')}
{col_inst('familia',          'None',  inst_fam, 'nominal')}
{col_inst('Number of Records','Count', inst_cnt, 'quantitative')}
        </datasource-dependencies>
{_view_tail(inst_fam, inst_fam)}
      </view>
      <style/>
      <panes>
        <pane>
          <view/>
          <mark class='Bar'/>
        </pane>
      </panes>
      <rows>{inst_fam}</rows>
      <cols>{inst_cnt}</cols>
    </table>
  </worksheet>"""


def sheet_tabla_upsell_comp(name, ds):
    i_rs  = '[none:razon_social:nk]'
    i_ss  = '[none:sub_sector:nk]'
    i_fam = '[none:familia:nk]'
    i_ge  = '[none:grupo_equipo:nk]'
    i_gc  = '[none:grupo_comp:nk]'
    i_con = '[avg:confianza:qk]'
    i_env = '[none:enviado_cliente:nk]'
    i_seg = '[none:nombre_segmento:nk]'
    return f"""  <worksheet name='{name}'>
    <table>
      <view>
        <datasources>
          <datasource name='{ds}'/>
        </datasources>
        <datasource-dependencies datasource='{ds}'>
{dep_col('razon_social',    'string',  'dimension', 'nominal')}
{dep_col('sub_sector',      'string',  'dimension', 'nominal')}
{dep_col('familia',         'string',  'dimension', 'nominal')}
{dep_col('grupo_equipo',    'string',  'dimension', 'nominal')}
{dep_col('grupo_comp',      'string',  'dimension', 'nominal')}
{dep_col('confianza',       'real',    'measure',   'quantitative')}
{dep_col('enviado_cliente', 'boolean', 'dimension', 'nominal')}
{dep_col('nombre_segmento', 'string',  'dimension', 'nominal')}
{col_inst('razon_social',    'None', i_rs,  'nominal')}
{col_inst('sub_sector',      'None', i_ss,  'nominal')}
{col_inst('familia',         'None', i_fam, 'nominal')}
{col_inst('grupo_equipo',    'None', i_ge,  'nominal')}
{col_inst('grupo_comp',      'None', i_gc,  'nominal')}
{col_inst('confianza',       'Avg',  i_con, 'quantitative')}
{col_inst('enviado_cliente', 'None', i_env, 'nominal')}
{col_inst('nombre_segmento', 'None', i_seg, 'nominal')}
        </datasource-dependencies>
{_view_tail(i_rs, i_rs)}
      </view>
      <style/>
      <panes>
        <pane>
          <view/>
          <mark class='Text'/>
        </pane>
      </panes>
      <rows>{i_rs}{i_fam}{i_ge}</rows>
      <cols>{i_ss}{i_seg}{i_gc}{i_con}{i_env}</cols>
    </table>
  </worksheet>"""


def sheet_tabla_recencia(name, ds):
    i_rs  = '[none:razon_social:nk]'
    i_ss  = '[none:sub_sector:nk]'
    i_fam = '[none:familia:nk]'
    i_rec = '[avg:recencia:qk]'
    i_nv  = '[sum:nro_ventas:qk]'
    i_scr = '[avg:score_recencia:qk]'
    i_env = '[none:enviado_cliente:nk]'
    i_seg = '[none:nombre_segmento:nk]'
    return f"""  <worksheet name='{name}'>
    <table>
      <view>
        <datasources>
          <datasource name='{ds}'/>
        </datasources>
        <datasource-dependencies datasource='{ds}'>
{dep_col('razon_social',   'string',  'dimension', 'nominal')}
{dep_col('sub_sector',     'string',  'dimension', 'nominal')}
{dep_col('familia',        'string',  'dimension', 'nominal')}
{dep_col('recencia',       'integer', 'measure',   'quantitative')}
{dep_col('nro_ventas',     'integer', 'measure',   'quantitative')}
{dep_col('score_recencia', 'real',    'measure',   'quantitative')}
{dep_col('enviado_cliente','boolean', 'dimension', 'nominal')}
{dep_col('nombre_segmento','string',  'dimension', 'nominal')}
{col_inst('razon_social',   'None', i_rs,  'nominal')}
{col_inst('sub_sector',     'None', i_ss,  'nominal')}
{col_inst('familia',        'None', i_fam, 'nominal')}
{col_inst('recencia',       'Avg',  i_rec, 'quantitative')}
{col_inst('nro_ventas',     'Sum',  i_nv,  'quantitative')}
{col_inst('score_recencia', 'Avg',  i_scr, 'quantitative')}
{col_inst('enviado_cliente','None', i_env, 'nominal')}
{col_inst('nombre_segmento','None', i_seg, 'nominal')}
        </datasource-dependencies>
{_view_tail(i_rs, i_rs)}
      </view>
      <style/>
      <panes>
        <pane>
          <view/>
          <mark class='Text'/>
        </pane>
      </panes>
      <rows>{i_rs}{i_fam}</rows>
      <cols>{i_ss}{i_seg}{i_rec}{i_nv}{i_scr}{i_env}</cols>
    </table>
  </worksheet>"""


# ─── DASHBOARDS ─────────────────────────────────────────────────────────────

_zone_id = [10]

def _id():
    _zone_id[0] += 1
    return _zone_id[0]


def dashboard(name, s1, s2, s3):
    i1, i2, i3, i4, i5, i6 = _id(), _id(), _id(), _id(), _id(), _id()
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
