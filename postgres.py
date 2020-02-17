#!/usr/bin/python3

import logging

import psycopg2

from config import DB_NAME


def get_pg():
    '''
    Return *the* common psycopg connection to the database
    based on config
    '''
    global __pg_connection
    try:
        return __pg_connection
    except NameError:
        logger = logging.getLogger(__name__)
        logger.debug('Opening new connection to postgres')
        __pg_connection = psycopg2.connect("dbname={}".format(DB_NAME))
        return __pg_connection
