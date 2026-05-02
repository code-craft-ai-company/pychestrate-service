"""
.. module:: plugin_api.restapi.v1.catalog_controller
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST controllers for ``GET /api/v1/plugin-api/_meta/*``.

.. moduleauthor:: Automation Mojo LLC

The controllers are read-only views over the cached
:class:`Catalog` exposed by ``plugin_api.runtime`` plus the
:class:`MountManifest` produced by
``extensions.ext_router.mount_extension_routes``. The catalog
endpoint enumerates the published-surface contract; the mounts
endpoint reports which concrete subclasses the host has discovered
at startup so operators can answer "which extensions are live?"
without SSH access.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from flask_restx import Namespace, Resource, fields

from automojo.pychestrate.webservice.extensions.ext_router import (
    manifest_to_jsonable,
    mount_extension_routes,
)
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


mount_entry_model = plugin_api_ns.model(
    "PluginApiExtMount",
    {
        "ext_name": fields.String(description="Owning extension's ext_name."),
        "method": fields.String(description="HTTP method."),
        "path_suffix": fields.String(description="Per-extension suffix."),
        "full_path": fields.String(description="/api/v1/ext/<ext-name><suffix>."),
        "handler_class": fields.String(description="Fully qualified handler class."),
        "required_permissions": fields.List(fields.String()),
        "required_capabilities": fields.List(fields.String()),
        "description": fields.String(description="Operator-facing summary."),
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


@plugin_api_ns.route("/mounts")
class PluginApiMountsResource(Resource):
    """
        ``GET /api/v1/plugin-api/_meta/mounts`` — concrete extension
        routes the host has discovered. Mirrors the in-process
        :class:`MountManifest` produced by
        ``extensions.ext_router.mount_extension_routes`` so operators
        can enumerate live extensions without SSH access.
    """

    @plugin_api_ns.marshal_list_with(mount_entry_model)
    def get(self):
        manifest = mount_extension_routes(extensions=None)
        rtnval = manifest_to_jsonable(manifest=manifest)
        return rtnval


def publish_namespaces(version_prefix: str):
    """
        Return namespace registrations for the v1 API wiring.

        :param version_prefix: Version prefix string (``/1``).

        :returns: List of (namespace, path) tuples.
    """
    rtnval = [(plugin_api_ns, version_prefix + PLUGIN_API_NAMESPACE_PATH)]
    return rtnval
