"""
.. module:: cli.builtin_operations
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The commands ``pyc`` knows without the server's OpenAPI
               document.

.. moduleauthor:: Code Craft AI LLC

``pyc`` builds its API commands from the server's
``/api/v1/_meta/openapi.json``. When that document cannot be fetched
(an older server, a proxy that blocks it, no network yet) and no
cached copy exists, the CLI falls back to this small built-in
document so the everyday commands still work and the real request
reports the real problem (unreachable, 401, ...).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict


_SLUG_PARAM: Dict[str, Any] = {
    "name": "slug", "in": "path", "required": True, "schema": {"type": "string"},
}
_RUN_ID_PARAM: Dict[str, Any] = {
    "name": "run_id", "in": "path", "required": True, "schema": {"type": "string"},
}
_PAGE_PARAMS = [
    {"name": "page", "in": "query", "required": False, "schema": {"type": "integer"}},
    {"name": "per_page", "in": "query", "required": False, "schema": {"type": "integer"}},
]

#: Minimal OpenAPI document (same shape and operation ids as the
#: server's) used when the real one is unavailable.
FALLBACK_OPENAPI_DOCUMENT: Dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"title": "Pychestrate (pyc built-in fallback)", "version": "pyc-builtin"},
    "servers": [{"url": "/api/v1"}],
    "paths": {
        "/me": {
            "get": {
                "operationId": "me_get_identity", "tags": ["me"],
                "summary": "Who the caller is and how the request authenticated.",
            },
        },
        "/projects": {
            "get": {
                "operationId": "projects_list", "tags": ["projects"],
                "summary": "List projects.", "parameters": list(_PAGE_PARAMS),
            },
            "post": {
                "operationId": "projects_create", "tags": ["projects"],
                "summary": "Create a project.", "requestBody": {"required": True},
            },
        },
        "/projects/{slug}": {
            "get": {
                "operationId": "projects_get_by_slug", "tags": ["projects"],
                "summary": "Read a project by slug.", "parameters": [_SLUG_PARAM],
            },
        },
        "/runs": {
            "get": {
                "operationId": "runs_list", "tags": ["runs"],
                "summary": "List runs.", "parameters": list(_PAGE_PARAMS),
            },
        },
        "/runs/{run_id}": {
            "get": {
                "operationId": "runs_get_by_id", "tags": ["runs"],
                "summary": "Read one run.", "parameters": [_RUN_ID_PARAM],
            },
        },
    },
}


__all__ = [
    "FALLBACK_OPENAPI_DOCUMENT",
]
