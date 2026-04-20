"""
.. module:: restapi.versions.v1.phase1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Aggregates the Phase-1 spec-shaped REST namespaces into v1.

.. moduleauthor:: Automation Mojo LLC

The Phase-1 controllers live next to the feature modules under
``source/site/automojo/pychestrate/webservice/{identity,security,secrets,audit}/``
per the feature specs. This aggregator pulls their ``publish_namespaces``
exports together and exposes a single entry point for ``wkpackets.py``
to consume. The legacy ``restapi/versions/v1/config/*`` controllers stay
untouched during the Phase-1 parallel-run.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.identity.users.restapi.v1.users_controller import (
    publish_namespaces as users_publish_namespaces,
)
from automojo.pychestrate.webservice.security.auth.restapi.v1.auth_controller import (
    publish_namespaces as auth_publish_namespaces,
)
from automojo.pychestrate.webservice.security.rbac.restapi.v1.rbac_controller import (
    publish_namespaces as rbac_publish_namespaces,
)
from automojo.pychestrate.webservice.secrets.restapi.v1.secrets_controller import (
    publish_namespaces as secrets_publish_namespaces,
)
from automojo.pychestrate.webservice.audit.restapi.v1.audit_controller import (
    publish_namespaces as audit_publish_namespaces,
)
from automojo.pychestrate.webservice.identity.flags.restapi.v1.flags_controller import (
    publish_namespaces as flags_publish_namespaces,
)
from automojo.pychestrate.webservice.clients.restapi.v1.clients_controller import (
    publish_namespaces as clients_publish_namespaces,
)
from automojo.pychestrate.webservice.clients.restapi.v1.enrollment_controller import (
    publish_namespaces as enrollment_publish_namespaces,
)


def publish_namespaces(version_prefix: str):
    """
        Return the list of (namespace, path) registrations for every
        Phase-1 and Phase-2 feature controller.

        :param version_prefix: Version prefix string (``/1``).

        :returns: List of (namespace, path) tuples.
    """
    rtnval = []
    rtnval.extend(users_publish_namespaces(version_prefix))
    rtnval.extend(auth_publish_namespaces(version_prefix))
    rtnval.extend(rbac_publish_namespaces(version_prefix))
    rtnval.extend(secrets_publish_namespaces(version_prefix))
    rtnval.extend(audit_publish_namespaces(version_prefix))
    rtnval.extend(flags_publish_namespaces(version_prefix))
    rtnval.extend(clients_publish_namespaces(version_prefix))
    rtnval.extend(enrollment_publish_namespaces(version_prefix))
    return rtnval
