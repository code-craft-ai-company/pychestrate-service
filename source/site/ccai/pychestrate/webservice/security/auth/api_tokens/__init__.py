"""
.. module:: security.auth.api_tokens
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Machine identity -- API tokens (personal access tokens)
               and service accounts.

.. moduleauthor:: Code Craft AI LLC

* :mod:`models` -- the ``auth_api_tokens`` table.
* :mod:`service` -- issue / list / revoke / authenticate tokens,
  create / list service accounts.
* :mod:`audit_events` -- audit kinds for token creation, revocation,
  and use.

The session middleware authenticates ``Authorization: Bearer pyc_...``
through :func:`service.authenticate_api_token` (see
:func:`middleware_webworks.default_resolve_api_token`); the REST
surface lives in :mod:`security.auth.restapi.v1.api_tokens_routes`
and the admin / account pages in
:mod:`webinterface.blueprints.config.routes_tokens`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


# Side-effect import: registers ``auth_api_tokens`` on
# ``PychestratePhase1Base.metadata`` whenever the auth package loads,
# so ``create_all`` (dev / tests) and alembic both see the table.
from ccai.pychestrate.webservice.security.auth.api_tokens import models as _models  # noqa: F401


def register_builtin_extensions() -> None:
    """
        Register the API-token audit kinds so the audit bus subscriber
        captures token creation, revocation, and use. Idempotent.

        :returns: None.
    """
    from ccai.pychestrate.webservice.audit.extensions.event_type import (  # noqa: E402
        AuditEventTypeExtension,
    )
    from ccai.pychestrate.webservice.extensions.registry import (  # noqa: E402
        register_resource_extension,
    )
    from ccai.pychestrate.webservice.security.auth.api_tokens.audit_events import (  # noqa: E402
        API_TOKEN_AUDIT_EVENT_TYPES,
    )

    for event_type in API_TOKEN_AUDIT_EVENT_TYPES:
        register_resource_extension(
            base_class=AuditEventTypeExtension, extension=event_type
        )
    return
