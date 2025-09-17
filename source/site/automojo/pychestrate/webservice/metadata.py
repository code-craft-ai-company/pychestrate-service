
from typing import Any, Dict

import os

from sqlalchemy.engine.base import Engine
from sqlalchemy.orm.session import Session

from automojo.credentials.secrettokencredential import SecretTokenCredential
from automojo.credentials.basiccredential import BasicCredential


LOOKUP_CONTENT_TYPE_TO_ROLE_REQUIREMENTS = {
}


class RUNTIME_ENVIRONMENTS:
    DEVELOPMENT = 'development'
    PRODUCTION = 'production'
    STAGING = 'staging'
    TESTING = 'testing'


# API routes that use token authentication
API_PREFIXES = [
    '/api/',
    '/webhook/'
]


# Routes that don't require authentication
PUBLIC_ROUTES = {
}

DIR_THIS = os.path.dirname(__file__)


class SITE_DIRECTORIES:

    DIR_BLUEPRINTS = os.path.join(DIR_THIS, "webinterface", "blueprints")
    DIR_STATIC = os.path.join(DIR_THIS, "webinterface", "static")
    DIR_STATIC_IMAGES = os.path.join(DIR_THIS, "webinterface", "static", "images")


class SITE_SHARED_GLOBALS:

    HOST = "pychestrate.local"
    OAUTH_CONFIGURATIONS: Dict[str, Dict[str, Any]] = None
    DATABASE_ENGINE: Engine = None
    DATABASE_SESSION_FACTORY: Session = None
    HCAPTCHA_CREDENTIAL: SecretTokenCredential = None
    SMTP_HOST: str = None
    SMTP_PORT: int = None
    SMTP_CREDENTIAL: BasicCredential = None
