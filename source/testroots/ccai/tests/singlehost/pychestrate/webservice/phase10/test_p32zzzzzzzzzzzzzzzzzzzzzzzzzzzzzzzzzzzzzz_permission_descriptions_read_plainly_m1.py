"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz_permission_descriptions_read_plainly_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The catalog's permission descriptions describe what a permission allows, not how it is reached (ADM-06).

.. moduleauthor:: Code Craft AI LLC

Fifty-odd of the 73 core permission descriptions ended "... via the REST surface", an implementation detail that told a person building a role
nothing. The role form cleaned the words at display time, but the catalog itself, the REST catalog (``GET /api/v1/rbac/permissions``) and the
permission-denied page still carried them. The descriptions are now written plainly at the source; the display-time cleaning stays as a safety
net for a pack that is installed later.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import List

from ccai import testbase

from ccai.pychestrate.webservice.extensions.registry import list_resource_extensions
from ccai.pychestrate.webservice.security.rbac.extensions.core_permissions import (
    _CORE_PERMISSION_DESCRIPTIONS,
    CorePermissionExtension,
)
from ccai.pychestrate.webservice.security.rbac.extensions.permission_extension import PermissionExtension
from ccai.pychestrate.webservice.webinterface.foundation.permission_presentation import plain_description


#: Words a finished description does not end on (a cut-off phrase does: "... via the").
DANGLING_ENDINGS = (" via", " the", " and", " of", ",")


def test_no_core_description_mentions_the_rest_surface_or_ends_mid_sentence():
    """
    **Feature: plain permission descriptions (ADM-06)**
    **Property: none of the 73 core descriptions contains "REST surface", each is a non-empty sentence fragment that starts with a capital
    and does not end on a joining word, and cleaning them for display changes none of them.**
    """
    problems: List[str] = []
    for key, text in _CORE_PERMISSION_DESCRIPTIONS.items():
        if "REST surface" in text:
            problems.append(key + ": mentions it")
        if len(text.strip()) == 0 or text.strip()[0].isupper() is False:
            problems.append(key + ": not a sentence")
        if text.rstrip().endswith(DANGLING_ENDINGS):
            problems.append(key + ": ends mid-sentence")
    unchanged = [key for key, text in _CORE_PERMISSION_DESCRIPTIONS.items() if plain_description(text) != text.strip()]

    testbase.assert_equal((problems, unchanged, len(_CORE_PERMISSION_DESCRIPTIONS) >= 73), ([], [], True))
    return


def test_the_descriptors_the_catalog_serves_are_plain_too():
    """
    **Feature: plain permission descriptions (ADM-06)**
    **Property: the descriptor the core pack returns for each of its keys carries the plain text, and so does every descriptor of every
    registered permission pack (what the REST catalog and the permission-denied page serve).**
    """
    served = {key: CorePermissionExtension.describe(permission_key=key).description for key in CorePermissionExtension.permission_keys}
    registered: List[str] = []
    for pack in list_resource_extensions(base_class=PermissionExtension):
        for key in pack.permission_keys:
            if "REST surface" in pack.describe(permission_key=key).description:
                registered.append(key)

    testbase.assert_equal(
        (served == dict(_CORE_PERMISSION_DESCRIPTIONS), [key for key, text in served.items() if "REST surface" in text], registered),
        (True, [], []),
    )
    return
