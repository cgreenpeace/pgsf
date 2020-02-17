#!/usr/bin/python3

import argparse
import logging

import config
from tabledesc import TableDesc


def postgres_type_raw(field):
    sftype = field['type']
    if sftype in (
            'email', 'encryptedstring', 'id', 'multipicklist',
            'picklist', 'phone', 'reference', 'string', 'textarea', 'url'):
        return 'VARCHAR({})'.format(field['byteLength'])
    elif sftype == 'int':
        return 'INTEGER'
    elif sftype == 'date':
        return 'DATE'
    elif sftype == 'datetime':
        return 'TIMESTAMP'
    elif sftype == 'boolean':
        return 'BOOLEAN'
    elif sftype in ('currency', 'double', 'percent'):
        return 'DOUBLE PRECISION'
    else:
        return '"{}" NOT IMPLEMENTED '.format(sftype)


def postgres_json_to_csv(field, value):
    '''
    Given a field, this converts a json value returned by SF query into a csv
    compatible value.
    '''
    def csv_quote(value):
        # return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'
        return '"' + value.replace('"', '""') + '"'

    sftype = field['type']
    if value is None:
        return ''
    if sftype in (
            'email', 'encryptedstring', 'id', 'multipicklist',
            'picklist', 'phone', 'reference', 'string', 'textarea', 'url'):
        return csv_quote(value)
    elif sftype == 'int':
        return str(value)
    elif sftype == 'date':
        return str(value)
    elif sftype == 'datetime':
        return str(value)  # 2019-11-18T15:28:14.000Z TODO check
    elif sftype == 'boolean':
        return 't' if value else 'f'
    elif sftype in ('currency', 'double', 'percent'):
        return str(value)
    else:
        return '"{}" NOT IMPLEMENTED '.format(sftype)


def postgres_escape_str(s):
    return "'" + s.replace("'", "''") + "'"


def postgres_escape_name(name):
    assert '"' not in name
    if config.DB_QUOTE_NAMES:
        return '"' + name + '"'
    else:
        return name


def postgres_table_name(name):
    if config.DB_SCHEMA is not None:
        result = postgres_escape_name(config.DB_SCHEMA)
        result += '.'
    else:
        result = ''
    result += postgres_escape_name(name)
    return result


def postgres_const(value):
    if type(value) == str:
        return postgres_escape_str(value)
    elif type(value) == bool:
        return 'TRUE' if value else 'FALSE'
    elif type(value) in (int, float):
        return str(value)
    else:
        return 'NOTIMPLEMENTED'


def postgres_coldef_from_sffield(field):
    field_name = field['name']
    field_type = field['type']

    if field_type == 'address':
        base_name = field_name
        if base_name.endswith('Address'):
            base_name = base_name[:-7]  # remove suffix
        return [
            ' {} {}'.format(postgres_escape_name(base_name+'Street'),
                            'VARCHAR(255)'),
            ' {} {}'.format(postgres_escape_name(base_name+'City'),
                            'VARCHAR(40)'),
            ' {} {}'.format(postgres_escape_name(base_name+'State'),
                            'VARCHAR(80)'),
            ' {} {}'.format(postgres_escape_name(base_name+'PostalCode'),
                            'VARCHAR(20)'),
            ' {} {}'.format(postgres_escape_name(base_name+'Country'),
                            'VARCHAR(80)'),
            ' {} {}'.format(postgres_escape_name(base_name+'Latitude'),
                            'DOUBLE PRECISION'),
            ' {} {}'.format(postgres_escape_name(base_name+'Longitude'),
                            'DOUBLE PRECISION'),
            ]
    pgtype = postgres_type_raw(field)
    if field_name == 'Id':
        if config.DB_RENAME_ID:
            field_name = 'SfId'  # Can be NULL during inserts
        else:
            pgtype += ' PRIMARY KEY'
    else:
        if not field['nillable']:
            pgtype += ' NOT NULL'
        if field['defaultValue']:
            pgtype += ' DEFAULT ' + postgres_const(field['defaultValue'])
        if field['unique']:
                pgtype += ' UNIQUE'
    return [' {} {}'.format(postgres_escape_name(field_name), pgtype)]


def get_pgsql_create(table_name):
    logger = logging.getLogger(__name__)
    logger.debug('Analyzing %s', table_name)

    tabledesc = TableDesc(table_name)

    if config.DB_RENAME_ID:
        lines = [' id SERIAL PRIMARY KEY']
    else:
        lines = []
    sync_fields = tabledesc.get_sync_fields()
    for field_name, field in sync_fields.items():
        if field['calculated']:
            logger.warning('Field %s should be calculated locally',
                           field_name)
        if tabledesc.is_field_compound(field_name):
            logger.warning('Field %s should be composed/aggregated locally',
                           field_name)
        lines += postgres_coldef_from_sffield(field)
    statements = [
        'CREATE TABLE {} (\n{}\n);'.format(
            postgres_table_name(table_name),
            ',\n'.join(lines))
        ]

    indexed_fields_names = tabledesc.get_indexed_sync_field_names()
    for field_name, field in sync_fields.items():
        if field_name == 'Id' and not config.DB_RENAME_ID:
            continue  # primary key already there
        if field_name not in indexed_fields_names:
            continue
        if field.get('IsIndexed'):
            statements.append(
                'CREATE INDEX {} ON {} ({});'.format(
                    postgres_escape_name('{}_{}_idx'.format(
                            table_name, field_name)),
                    postgres_table_name(table_name),
                    postgres_escape_name(field_name)))
    return statements


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='make sql create table statements')
    parser.add_argument(
            '--dry-run',
            default=False, action='store_true',
            help='only print the statement to stdout')
    parser.add_argument(
            'table',
            help='table to create in postgres')
    args = parser.parse_args()

    logging.basicConfig(
            filename=config.LOGFILE,
            format=config.LOGFORMAT,
            level=config.LOGLEVEL)

    sql = get_pgsql_create(args.table)
    if args.dry_run:
        for line in sql:
            print(line)
    else:
        from postgres import get_pg
        pg = get_pg()
        cursor = pg.cursor()
        for line in sql:
            cursor.execute(line)
        pg.commit()
