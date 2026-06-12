"""
.. module:: dbconnection
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Contains helper functions for working with specific databases

.. moduleauthor:: Myron Walker <myron.walker@gmail.com>
"""

__author__ = "Myron Walker"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"

from typing import Optional

import logging
import os

from sqlalchemy import create_engine
from sqlalchemy.engine.base import Engine as SqlEngine

from ccai.errors.exceptions import ConfigurationError, NotOverloadedError

from ccai.credentials.basecredential import BaseCredential
from ccai.credentials.basiccredential import BasicCredential
from ccai.credentials.credentialmanager import CredentialManager

from ccai.dataprofiles.databasebasicsocketprofile import DatabaseBasicSocketProfile
from ccai.dataprofiles.databasebasictcpprofile import DatabaseBasicTcpProfile


logger = logging.getLogger()


class DatabaseConnectionFactory:

    def __init__(self, profile_name: str, *, dbprofile: DatabaseBasicSocketProfile, credential: BaseCredential):
        self._profile_name = profile_name
        self._dbprofile = dbprofile
        self._credential = credential
        return
    
    @property
    def credential(self) -> BaseCredential:
        return self._credential
    
    @property
    def dbprofile(self) -> DatabaseBasicSocketProfile:
        return self._dbprofile
    
    @property
    def profile_name(self) -> str:
        return self._profile_name

    def create_engine(self, *, dbname=None, echo=True) -> SqlEngine:
        errmsg = "The 'create_engine' method must be overloaded by 'DatabaseConnectionFactory' derived types."
        raise NotImplementedError(errmsg)
    
    def format_connection_string() -> str:
        errmsg = "The 'format_connection_string' method must be overloaded by 'DatabaseConnectionFactory' derived types."
        raise NotImplementedError(errmsg)


class BasicSocketDatabaseConnectionFactory(DatabaseConnectionFactory):

    def __init__(self, profile_name: str, *, dbprofile: DatabaseBasicSocketProfile, credential: BaseCredential):
        super().__init__(profile_name, dbprofile=dbprofile, credential=credential)
        return

    def create_engine(self, *, dbname=None, echo=True) -> SqlEngine:
        """Create a SQLAlchemy engine using pipe based connectivity."""

        socket_path: str = self.dbprofile.socket

        if dbname is None and self.dbprofile.dbname is not None:
            dbname = self.dbprofile.dbname

        if dbname is None:
            warnmsg = "BasicSocketDatabaseConnectionFactory.create_engine: dbname was None."
            logger.warn(warnmsg)

        if isinstance(self.credential, BasicCredential):
            connstr = self.format_connection_string(dbname=dbname)
            dbengine = create_engine(connstr, echo=echo)
        else:
            errmsg = (
                "BasicSocketDatabaseConnectionFactory requires a BasicCredential to "
                "create an engine."
            )
            raise ConfigurationError(errmsg)

        return dbengine

    def get_connection_scheme(self):
        """Return the SQLAlchemy connection scheme for the profile."""

        conn_scheme = None

        if self.dbprofile.dbtype == "postgresql":
            try:
                import psycopg2  # noqa: F401
            except ImportError:
                errmsg_lines = [
                    "In order to create a postgresql database engine, you must install the following dependencies.",
                    "DEPENDENCIES",
                    "    psycopg2",
                ]
                errmsg = os.linesep.join(errmsg_lines)
                raise ConfigurationError(errmsg)

            conn_scheme = "postgresql+psycopg2"

        return conn_scheme

    def format_connection_string(self, dbname: Optional[str] = None) -> str:
        """Build a connection string for pipe based access."""

        conn_scheme: str = self.get_connection_scheme()

        socket_path: str = self.dbprofile.socket

        if not isinstance(self.credential, BasicCredential):
            errmsg = (
                "BasicSocketDatabaseConnectionFactory requires a BasicCredential to "
                "format the connection string."
            )
            raise ConfigurationError(errmsg)

        credobj: BasicCredential = self.credential

        username = credobj.username
        password = credobj.password

        if dbname is None:
            dbname = self.dbprofile.dbname

        conn_str = f"{conn_scheme}://{username}:{password}@/{dbname}?host={socket_path}"

        return conn_str


class BasicTcpDatabaseConnectionFactory(DatabaseConnectionFactory):

    def __init__(self, profile_name: str, *, dbprofile: DatabaseBasicTcpProfile, credential: BaseCredential):
        super().__init__(profile_name, dbprofile=dbprofile, credential=credential)
        return

    @property
    def dbprofile(self) -> DatabaseBasicTcpProfile:
        return self._dbprofile

    def create_engine(self, *, dbname=None, echo=True) -> SqlEngine:

        conn_scheme = None

        # If the database type we are creating an engine for is postgresql, make sure
        # we can import all of the postgresql dependencies.
        if self.dbprofile.dbtype == 'postgresql':
            try:
                import psycopg2
            except ImportError:
                errmsg_lines = [
                    "In order to create a postgresql database engine, you must install the following dependencies.",
                    "DEPENDENCIES",
                    "    psycopg2"
                ]
                errmsg = os.linesep.join(errmsg_lines)
                raise ConfigurationError(errmsg)
            
            conn_scheme = "postgresql+psycopg2"

        if dbname is None and self.dbprofile.dbname is not None:
            dbname = self.dbprofile.dbname

        if dbname is None:
            warnmsg = "BasicTcpDatabaseConnectionFactory.create_engine: dbname was None."
            logger.warn(warnmsg)

        if isinstance(self.credential, BasicCredential):
            credobj: BasicCredential = self.credential

            passwd = credobj.password

            connstr = self.format_connection_string(dbname=dbname)
            
            dbengine = create_engine(connstr, echo=echo)

        return dbengine
    
    def get_connection_scheme(self):

        conn_scheme = None

        # If the database type we are creating an engine for is postgresql, make sure
        # we can import all of the postgresql dependencies.
        if self.dbprofile.dbtype == 'postgresql':
            try:
                import psycopg2
            except ImportError:
                errmsg_lines = [
                    "In order to create a postgresql database engine, you must install the following dependencies.",
                    "DEPENDENCIES",
                    "    psycopg2"
                ]
                errmsg = os.linesep.join(errmsg_lines)
                raise ConfigurationError(errmsg)
            
            conn_scheme = "postgresql+psycopg2"

        return conn_scheme

    def format_connection_string(self, dbname: Optional[str]=None) -> str:
        
        conn_str = None

        conn_scheme: str = self.get_connection_scheme()
        host: str = self.dbprofile.host
        port: str = self.dbprofile.port
        
        if isinstance(self.credential, BasicCredential):
            credobj: BasicCredential = self.credential

            username = credobj.username
            password = credobj.password

            conn_str = f"{conn_scheme}://{username}:{password}@{host}:{port}"

            if dbname is not None:
                conn_str += f"/{dbname}"
            else:
                conn_str += f"/{self.dbprofile.dbname}"

        return conn_str



DATABASE_CONNECTION_FACTORIES = {}


def create_database_connection_factory(dbprofile: DatabaseBasicSocketProfile, cred_manager: CredentialManager) -> DatabaseConnectionFactory:

    global DATABASE_CONNECTION_FACTORIES

    conn_factory = None

    profile_name = dbprofile.identifier

    if profile_name in DATABASE_CONNECTION_FACTORIES:
        conn_factory = DATABASE_CONNECTION_FACTORIES[profile_name]
    
    else:

        credential_name = dbprofile.credential

        credential: BaseCredential = cred_manager.credentials[credential_name]

        category = dbprofile.category
        if category == "basic-socket":
            conn_factory = BasicSocketDatabaseConnectionFactory(profile_name, dbprofile=dbprofile, credential=credential)
        elif category == "basic-tcp":
            conn_factory = BasicTcpDatabaseConnectionFactory(profile_name, dbprofile=dbprofile, credential=credential)
        else:
            errmsg = "Unknown database connection type. profile_name={} category={}".format(
                profile_name, category)
            raise ConfigurationError(errmsg)

        DATABASE_CONNECTION_FACTORIES[profile_name] = conn_factory

    return conn_factory
