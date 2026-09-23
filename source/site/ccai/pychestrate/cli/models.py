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
        :param timeout_seconds: Per-request timeout, or ``None`` for
                                the transport default.
    """
    profile_name: str
    server_url: str
    bearer_token: Optional[str]
    bearer_token_expires_at: Optional[datetime]
    mtls_cert_path: Optional[str]
    mtls_key_path: Optional[str]
    verify_tls: bool
    timeout_seconds: Optional[float] = None


@dataclass(frozen=True)
class OperationParameter:
    """
        One path or query parameter of an operation, as the OpenAPI
        document declares it.

        :param name: Parameter name, as the server expects it.
        :param location: ``"path"`` or ``"query"``.
        :param required: Whether the server requires it.
        :param description: One-line description (``""`` when the
                            document has none).
        :param value_type: JSON-schema type: ``string``, ``integer``,
                           ``number``, ``boolean`` or ``array``.
        :param choices: The allowed values (``enum``); empty when any
                        value is accepted.
        :param default: The server-side default as text, or ``None``.
    """
    name: str
    location: str
    required: bool = False
    description: str = ""
    value_type: str = "string"
    choices: Tuple[str, ...] = field(default_factory=tuple)
    default: Optional[str] = None


@dataclass(frozen=True)
class BodyField:
    """
        One top-level field of an operation's JSON request body.

        :param name: Field name.
        :param required: Whether the body schema requires it.
        :param value_type: JSON-schema type (``""`` when unspecified).
        :param description: One-line description.
    """
    name: str
    required: bool = False
    value_type: str = ""
    description: str = ""


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
        :param summary: One-line summary from the OpenAPI document.
        :param has_request_body: Whether the operation takes a JSON
                                 body.
        :param parameters: Every path and query parameter with its
                           description, type, choices and default.
        :param body_fields: The request body's top-level fields.
        :param body_required: Whether the request body is required.
        :param description: The operation's longer description.
    """
    operation_id: str
    method: str
    path_template: str
    path_param_names: Tuple[str, ...] = field(default_factory=tuple)
    query_param_names: Tuple[str, ...] = field(default_factory=tuple)
    required_query_param_names: Tuple[str, ...] = field(default_factory=tuple)
    required_path_param_names: Tuple[str, ...] = field(default_factory=tuple)
    summary: str = ""
    has_request_body: bool = False
    parameters: Tuple[OperationParameter, ...] = field(default_factory=tuple)
    body_fields: Tuple[BodyField, ...] = field(default_factory=tuple)
    body_required: bool = False
    description: str = ""

    def find_parameter(self, name: str) -> Optional[OperationParameter]:
        """
            The declared parameter called ``name``.

            :param name: Parameter name.

            :returns: :class:`OperationParameter` or ``None``.
        """
        for parameter in self.parameters:
            if parameter.name == name:
                return parameter
        return None


@dataclass(frozen=True)
class CommandDescriptor:
    """
        Single ``pyc <noun> <verb>`` mapping built from an OpenAPI
        operation. Stored under :class:`CommandTree`.

        :param noun: Top-level noun (e.g., ``projects``).
        :param verb: Action verb (e.g., ``list``, ``get``).
        :param operation: The OpenAPI operation backing this command.
        :param aliases: Other ``(noun, verb)`` spellings that reach
                        this command (the name derived from the tag
                        and ``operationId``).
    """
    noun: str
    verb: str
    operation: RestOperation
    aliases: Tuple[Tuple[str, str], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CommandTree:
    """
        Frozen view of every parseable ``pyc <noun> <verb>`` invocation.

        :param commands: Mapping ``(noun, verb)`` -> :class:`CommandDescriptor`,
                         keyed by the canonical names.
        :param aliases: Mapping of alias ``(noun, verb)`` -> canonical
                        ``(noun, verb)``.
    """
    commands: Mapping[Tuple[str, str], CommandDescriptor]
    aliases: Mapping[Tuple[str, str], Tuple[str, str]] = field(default_factory=dict)


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
