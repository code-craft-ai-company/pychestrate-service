"""
.. module:: restapi.versions.v1.phase3
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Aggregates the Layer-3 REST namespaces into v1.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.agents.restapi.v1.agents_controller import (
    publish_namespaces as agents_publish_namespaces,
)
from automojo.pychestrate.webservice.pods.restapi.v1.pods_controller import (
    publish_namespaces as pods_publish_namespaces,
)


def publish_namespaces(version_prefix: str):
    """
        Return (namespace, path) tuples for every Phase-3 feature controller.
    """
    rtnval = []
    rtnval.extend(pods_publish_namespaces(version_prefix))
    rtnval.extend(agents_publish_namespaces(version_prefix))
    return rtnval
