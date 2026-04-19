"""
.. module:: dbio
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Contains helper functions for working with specific databases

.. moduleauthor:: Myron Walker <myron.walker@gmail.com>
"""

__author__ = "Myron Walker"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Optional


import contextlib
import logging

from sqlalchemy.engine.base import Engine as SqlEngine
from sqlalchemy.sql.schema import MetaData

from sqlalchemy_utils import database_exists as sqlutils_database_exists
from sqlalchemy_utils import create_database as sqlutils_create_database
from sqlalchemy_utils import drop_database as sqlutils_drop_database

from automojo.errors.exceptions import ConfigurationError

from automojo.credentials.credentialmanager import CredentialManager

from automojo.dataprofiles.databasebasicsocketprofile import DatabaseBasicSocketProfile

from automojo.pychestrate.core.storage.orm import PychestrateModelBase

from automojo.pychestrate.core.storage.dbconnection import DatabaseConnectionFactory, create_database_connection_factory


logger = logging.getLogger()


def database_exists(conn_factory: DatabaseConnectionFactory, dbname: Optional[str]=None) -> bool:
    """
        Checks to see if the specified database exists.
    """
    conn_str = conn_factory.format_connection_string(dbname=dbname)

    exists = sqlutils_database_exists(conn_str)

    return exists


def database_create(conn_factory: DatabaseConnectionFactory, dbname: Optional[str]=None, dbmetadata: Optional[MetaData]=None):
    """ 
        Creates the specified database.
    """

    conn_str = conn_factory.format_connection_string(dbname=dbname)

    sqlutils_create_database(conn_str)

    if dbmetadata is not None:
        engine = conn_factory.create_engine(dbname=dbname)
        dbmetadata.create_all(engine)

    return


def create_network_attached_database(db_profile: DatabaseBasicSocketProfile, cred_manager: CredentialManager, orm_metadata: MetaData, *, reset: bool = False):
    """
        Creates the 'pychestrate' database.
    
        :param db_profile: The database profile configuration.
        :param cred_manager: Credential manager instance for obtaining credentials.
        :param orm_metadata: The Object Relational Model to use when creating the database. 
        :param reset: When ``True`` delete the existing database before creation.
    """
    db_name = db_profile.dbname

    conn_factory = create_database_connection_factory(db_profile, cred_manager)
    if conn_factory is None:
        db_profile_name = db_profile["name"]
        errmsg = "'create_automojo_enterprise_database' could not get a connection factory for profile={}".format(
            db_profile_name
        )
        raise ConfigurationError(errmsg)

    if reset and database_exists(conn_factory, db_name):
        conn_str = conn_factory.format_connection_string(dbname=db_name)
        sqlutils_drop_database(conn_str)

    if not database_exists(conn_factory, db_name):
        database_create(conn_factory, db_name)

    engine = conn_factory.create_engine(dbname=db_name, echo=True)

    orm_metadata.create_all(engine, checkfirst=True)

    return


def open_network_attached_database(db_profile: DatabaseBasicSocketProfile, cred_manager: CredentialManager) -> SqlEngine:
    """
        Opens the postgresql database.

        :param db_profile: The database profile configuration.
        :param cred_manager: Credential manager instance for obtaining credentials.
        :param orm_metadata: The Object Relational Model to use when creating the database. 
        :param reset: When ``True`` delete the existing database before creation.

        :returns: A :class:`SqlEngine` object that can be used to interoperate with the specified database.
    """
    dbname = db_profile.dbname

    conn_factory = create_database_connection_factory(db_profile, cred_manager)
    if conn_factory is None:
        db_profile_name = db_profile["name"]
        errmsg = "'open_pychestrate_database' could not get a connection factory for profile={}".format(
            db_profile_name
        )
        raise ConfigurationError(errmsg)

    engine = conn_factory.create_engine(dbname=dbname, echo=True)

    return engine


def reset_network_attached_database(db_profile: DatabaseBasicSocketProfile, cred_manager: CredentialManager, orm_metadata: MetaData):
    """
        Reset a network attached database database.

        :param db_profile: The database profile configuration.
        :param cred_manager: Credential manager instance for obtaining credentials.
        :param orm_metadata: The Object Relational Model to use when creating the database. 
        :param reset: When ``True`` delete the existing database before creation.
    """
    dbname = db_profile.dbname

    conn_factory = create_database_connection_factory(db_profile, cred_manager)
    if conn_factory is None:
        db_profile_name = db_profile["name"]
        errmsg = "'reset_pychestrate_database' could not get a connection factory for profile={}".format(
            db_profile_name
        )
        raise ConfigurationError(errmsg)

    if database_exists(conn_factory, dbname):
    
        engine = conn_factory.create_engine(dbname=dbname, echo=True)

        with contextlib.closing(engine.connect()) as con:
            trans = con.begin()
            con.execute('TRUNCATE {} RESTART IDENTITY;'.format(
                ','.join(table.name 
                        for table in reversed(orm_metadata.sorted_tables))))
            trans.commit()

    return