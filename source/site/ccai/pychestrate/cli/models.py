"""
.. module:: cli.models
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Frozen dataclasses describing CLI runtime state.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Optional, Tuple


DEFAULT_PROFILE_NAME: str = "default"


@dataclass(frozen=True)
class CliProfile:
    """
        Resolved authentication / endpoint configuration for one
        invocation.

        :param profile_name: ``[default]`` / ``[<name>]`` section header.
        :param server_url: Fully qualified server URL.
        :param bearer_token: Optional bearer token. ``None`` when only
                             mTLS is configured.
        :param bearer_token_expires_at: Token expiry timestamp.
        :param mtls_cert_path: Filesystem path to a client certificate
                               PEM, or ``None``.
        :param mtls_key_path: Filesystem path to the matching private
                              key PEM, or ``None``.
        :param verify_tls: Whether to verify the server certificate.
    """
    profile_name: str
    server_url: str
    bearer_token: Optional[str]
    bearer_token_expires_at: Optional[datetime]
    mtls_cert_path: Optional[str]
    mtls_key_path: Optional[str]
    verify_tls: bool


@dataclass(frozen=True)
class RestOperation:
    """
        Subset of an OpenAPI operation needed to drive a request.

        :param operation_id: ``operationId`` declared on the path item.
        :param method: HTTP method (uppercase).
        :param path_template: Raw OpenAPI path template (e.g.,
                              ``/projects/{slug}``).
        :param path_param_names: Tuple of path-parameter names.
        :param query_param_names: Tuple of query-parameter names.
        :param required_query_param_names: Tuple of required query
                                            parameters.
        :param required_path_param_names: Tuple of required path
                                          parameters.
    """
    operation_id: str
    method: str
    path_template: str
    path_param_names: Tuple[str, ...] = field(default_factory=tuple)
    query_param_names: Tuple[str, ...] = field(default_factory=tuple)
    required_query_param_names: Tuple[str, ...] = field(default_factory=tuple)
    required_path_param_names: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CommandDescriptor:
    """
        Single ``pyc <noun> <verb>`` mapping built from an OpenAPI
        operation. Stored under :class:`CommandTree`.

        :param noun: Top-level noun (e.g., ``project``).
        :param verb: Action verb (e.g., ``list``, ``get``).
        :param operation: The OpenAPI operation backing this command.
    """
    noun: str
    verb: str
    operation: RestOperation


@dataclass(frozen=True)
class CommandTree:
    """
        Frozen view of every parseable ``pyc <noun> <verb>`` invocation.

        :param commands: Mapping ``(noun, verb)`` -> :class:`CommandDescriptor`.
    """
    commands: Mapping[Tuple[str, str], CommandDescriptor]


@dataclass(frozen=True)
class RestResponse:
    """
        Outcome of a single REST round-trip.

        :param status_code: HTTP status returned by the server.
        :param headers: Lowercased header dict.
        :param body: Decoded JSON body or ``None`` on empty / non-JSON
                     responses.
        :param raw_text: Original response text (for diagnostics).
    """
    status_code: int
    headers: Mapping[str, str]
    body: Optional[Any]
    raw_text: str
