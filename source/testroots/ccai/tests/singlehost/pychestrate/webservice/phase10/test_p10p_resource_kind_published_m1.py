"""
.. module:: test_p10p_resource_kind_published_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Promotes ``resource_kind`` to the published catalog.

.. moduleauthor:: Code Craft AI LLC

8-plugin-api Requirement 2 advertises this surface as
``ResourceKindExtension`` (resource-extension shape). The in-tree
implementation took the factory-protocol shape — same semantic
surface (a discoverable set of typed kinds), different extension
mechanism. The catalog publishes the actual implementation under
``factory: resource_kind``; the spec naming will be reconciled in a
future doc pass. Tests confirm the catalog now includes the
factory entry pointing at ``DeviceResourceKind`` as the reference.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai import testbase

from ccai.pychestrate.webservice.plugin_api import build_catalog, is_class_published
from ccai.pychestrate.webservice.plugin_api.catalog_validator import (
    validate_catalog_against_code,
)
from ccai.pychestrate.webservice.resources.inventory.kinds.kind_protocol import (
    ResourceKindProtocol,
)


def test_resource_kind_protocol_is_published():
    """
    **Feature: 8-plugin-api integration**
    **Property: is_class_published returns True for ResourceKindProtocol.**
    """
    rtnval = is_class_published(target_class=ResourceKindProtocol)
    testbase.assert_equal(rtnval, True)
    return


def test_catalog_includes_resource_kind_factory_entry():
    """
    **Feature: 8-plugin-api integration**
    **Property: build_catalog now lists a ``resource_kind`` factory
    entry pointing at DeviceResourceKind.**
    """
    catalog = build_catalog()
    matched = None
    for entry in catalog.factory_entries:
        if entry.name == "resource_kind":
            matched = entry
            break
    testbase.assert_equal(matched is not None, True)
    testbase.assert_equal(
        matched.metadata.reference.endswith(".DeviceResourceKind"), True
    )
    return


def test_catalog_validator_resolves_resource_kind_reference():
    """
    **Feature: 8-plugin-api integration**
    **Property: validate_catalog_against_code resolves the
    DeviceResourceKind dotted path without raising.**
    """
    catalog = build_catalog()
    validate_catalog_against_code(catalog=catalog)
    return


def test_resource_kind_published_docs_url_is_documented_path():
    """
    **Feature: 8-plugin-api integration**
    **Property: The published docs URL is the guide's own catalog page,
    /docs/extensions/protocols/resource_kind.html (DOC-20).**
    """
    testbase.assert_equal(
        ResourceKindProtocol.published_docs_url,
        "/docs/extensions/protocols/resource_kind.html",
    )
    return
