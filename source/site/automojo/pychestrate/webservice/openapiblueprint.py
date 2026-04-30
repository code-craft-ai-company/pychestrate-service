"""
.. module:: pychestrate.webservice.openapiblueprint
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Live OpenAPI specification served at /openapi.json.

.. moduleauthor:: Automation Mojo LLC

Mounts a single GET endpoint that serializes the live
:class:`EndpointRegistry` snapshot to an OpenAPI 3.0.3 document via
:class:`automojo.webworks.openapi.generator.OpenAPIGenerator`.
The spec is built once on first request and cached for subsequent
calls; restart the service to refresh after adding new endpoints.

Public by design — the descriptor metadata exposed here is the same
information that already appears in
``usersguide/apireference.md`` and discovering the API surface is a
pre-requisite for the login flow.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import threading

from typing import Any, Dict, Optional

from automojo.webworks.endpoints.doc import Doc
from automojo.webworks.endpoints.registry import EndpointRegistry
from automojo.webworks.endpoints.restblueprint import RestBlueprint
from automojo.webworks.openapi.configuration import OpenAPIInfo
from automojo.webworks.openapi.generator import OpenAPIGenerator
from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse


_OPENAPI_TITLE = "Pychestrate Service"
_OPENAPI_VERSION = "1.0.0"
_OPENAPI_DESCRIPTION = (
    "Pychestrate orchestration service — identity, RBAC, projects, "
    "pods, agents, and taskplus flow orchestration. See "
    "usersguide/apireference.md for the curated reference."
)


_SPEC_LOCK = threading.Lock()
_CACHED_SPEC: Optional[Dict[str, Any]] = None


def _build_spec() -> Dict[str, Any]:
    """
        Build (and cache) the OpenAPI spec dictionary.
    """
    global _CACHED_SPEC
    with _SPEC_LOCK:
        if _CACHED_SPEC is not None:
            return _CACHED_SPEC
        info = OpenAPIInfo(
            title=_OPENAPI_TITLE,
            version=_OPENAPI_VERSION,
            description=_OPENAPI_DESCRIPTION,
        )
        generator = OpenAPIGenerator(
            registry=EndpointRegistry,
            info=info,
            rest_only=True,
        )
        spec = generator.generate()
        _CACHED_SPEC = spec
        return spec


def _reset_spec_cache_for_testing() -> None:
    """
        Drop the cached spec so tests can re-build against a fresh
        registry snapshot.
    """
    global _CACHED_SPEC
    with _SPEC_LOCK:
        _CACHED_SPEC = None
    return


class OpenAPIBlueprint(RestBlueprint):
    """
        Serves the live OpenAPI 3.0.3 specification.
    """

    base_path = "/openapi.json"
    tags = ["openapi"]

    @RestBlueprint.attach_at(
        path="/openapi.json",
        methods=["GET"],
        doc=Doc(
            summary="OpenAPI 3.0.3 specification",
            description=(
                "Returns the live OpenAPI document derived from the "
                "EndpointRegistry. Cached per process; restart the "
                "service to refresh after adding new endpoints."
            ),
        ),
    )
    def openapi_json(request: Request) -> JSONResponse:
        """
            Return the OpenAPI document.
        """
        spec = _build_spec()
        rtnval = JSONResponse(content=spec, status_code=200)
        return rtnval
