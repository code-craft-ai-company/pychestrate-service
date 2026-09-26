"""
.. module:: projects.legacy_identity
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The registry UUID a web-UI (legacy integer id) project is
               given.

.. moduleauthor:: Code Craft AI LLC

Before the project bridge (:mod:`projects.bridge`) linked the two
project systems, the RPA pipeline and the enrollment page mapped a web-UI
project's integer id onto a UUID5 in a fixed namespace so the UUID-typed
run, dispatch and client tables could refer to it. A web-UI project's
registry row keeps exactly that UUID, so rows written under it before the
bridge belong to the project. Kept dependency-free so any module can
import it.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import uuid


#: Namespace of the UUID5 derived from a web-UI project's integer id.
LEGACY_PROJECT_NAMESPACE = uuid.UUID("7f4b6a2e-5c8d-4e1f-9a3b-2d6c8e0f1a5b")


def derived_project_uuid(legacy_proj_id: object) -> str:
    """
        :param legacy_proj_id: A web-UI project's integer id (or its text).

        :returns: The UUID5 ``consumer-project:<id>`` in
                  :data:`LEGACY_PROJECT_NAMESPACE`, as text.
    """
    rtnval = str(uuid.uuid5(LEGACY_PROJECT_NAMESPACE, "consumer-project:{}".format(str(legacy_proj_id).strip())))
    return rtnval


__all__ = [
    "LEGACY_PROJECT_NAMESPACE",
    "derived_project_uuid",
]
