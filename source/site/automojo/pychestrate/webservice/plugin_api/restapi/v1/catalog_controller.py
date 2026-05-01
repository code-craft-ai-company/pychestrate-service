"""
.. module:: plugin_api.restapi.v1.catalog_controller
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST controllers for ``GET /api/v1/plugin-api/_meta/catalog``.

.. moduleauthor:: Automation Mojo LLC

The controllers are read-only views over the cached
:class:`Catalog` exposed by ``plugin_api.runtime``. M2 layers in
``GET /api/v1/plugin-api/_meta/extensions`` listing loaded
extensions; M1 stops at the catalog itself.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from flask_restx import Namespace, Resource, fields

from automojo.pychestrate.webservice.plugin_api import runtime as plugin_api_runtime
from automojo.pychestrate.webservice.plugin_api.catalog_builder import (
    catalog_to_jsonable,
)


PLUGIN_API_NAMESPACE_PATH = "/plugin-api/_meta"


plugin_api_ns = Namespace(
    "Plugin API v1",
    description="Read-only published-surface catalog (8-plugin-api).",
)


catalog_entry_model = plugin_api_ns.model(
    "PluginApiCatalogEntry",
    {
        "name": fields.String(description="Protocol or resource base name."),
        "kind": fields.String(description="factory_protocol | resource_extension."),
        "protocol_schema_version": fields.Integer(),
        "min_schema_version": fields.Integer(),
        "status": fields.String(description="supported | deprecated | removed-in-next-major."),
        "deprecation_date": fields.String(description="ISO-8601 date or null."),
        "sunset_date": fields.String(description="ISO-8601 date or null."),
        "docs_url": fields.String(),
        "reference": fields.String(description="Dotted path to in-tree reference."),
        "declaring_class": fields.String(description="module.ClassName declaring the entry."),
    },
)


catalog_response_model = plugin_api_ns.model(
    "PluginApiCatalog",
    {
        "factory_protocols": fields.List(fields.Nested(catalog_entry_model)),
        "resource_extensions": fields.List(fields.Nested(catalog_entry_model)),
    },
)


@plugin_api_ns.route("/catalog")
class PluginApiCatalogResource(Resource):
    """
        ``GET /api/v1/plugin-api/_meta/catalog`` — full published-surface catalog.
    """

    @plugin_api_ns.marshal_with(catalog_response_model)
    def get(self):
        catalog = plugin_api_runtime.get_active_catalog()
        rtnval = catalog_to_jsonable(catalog=catalog)
        return rtnval


@plugin_api_ns.route("/catalog/<string:protocol_name>")
@plugin_api_ns.param("protocol_name", "Factory protocol name OR resource extension class name")
class PluginApiCatalogDetailResource(Resource):
    """
        ``GET /api/v1/plugin-api/_meta/catalog/{protocol_name}`` — single
        published-surface entry.
    """

    @plugin_api_ns.marshal_with(catalog_entry_model)
    def get(self, protocol_name: str):
        catalog = plugin_api_runtime.get_active_catalog()
        flat_entries = list(catalog.factory_entries) + list(catalog.resource_entries)

        matched = None
        for entry in flat_entries:
            if entry.name == protocol_name:
                matched = entry
                break

        if matched is None:
            plugin_api_ns.abort(404, "Plugin API catalog entry not found: {}".format(protocol_name))

        rendered = catalog_to_jsonable(catalog=catalog)
        for entry_dict in rendered["factory_protocols"] + rendered["resource_extensions"]:
            if entry_dict["name"] == protocol_name:
                rtnval = entry_dict
                return rtnval

        plugin_api_ns.abort(404, "Plugin API catalog entry not found: {}".format(protocol_name))
        return None


def publish_namespaces(version_prefix: str):
    """
        Return namespace registrations for the v1 API wiring.

        :param version_prefix: Version prefix string (``/1``).

        :returns: List of (namespace, path) tuples.
    """
    rtnval = [(plugin_api_ns, version_prefix + PLUGIN_API_NAMESPACE_PATH)]
    return rtnval
