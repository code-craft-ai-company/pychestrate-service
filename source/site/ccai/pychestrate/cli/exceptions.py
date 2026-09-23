"""
.. module:: cli.exceptions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: CLI-side exception types.

.. moduleauthor:: Code Craft AI LLC

Every exception here maps to one documented exit code (see
:mod:`cli.exit_codes` and ``entry._map_exception_to_exit_code``);
their messages are written for the person at the terminal.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class CredentialsFileNotFoundError(Exception):
    """
        Raised when the credentials file is absent and no token is
        otherwise sourced.
    """


class CredentialsFilePermissionError(Exception):
    """
        Raised when the credentials file's mode is wider than ``0600``.
    """


class CredentialsFileInvalidError(Exception):
    """
        Raised when the credentials file cannot be read or parsed.
    """


class NotConfiguredError(Exception):
    """
        Raised when no server URL is configured anywhere (no profile,
        no ``--server-url``, no ``PYC_SERVER_URL``).
    """


class ProfileNotFoundError(Exception):
    """
        Raised when the named profile is missing from the credentials
        file.
    """


class CliUsageError(Exception):
    """
        Raised for a malformed command line (unknown command, missing
        argument, invalid ``--data``).
    """


class BadRequestError(Exception):
    """
        Raised when the server returns 400 or 422: the request was
        understood but its arguments were rejected.
    """


class AuthenticationError(Exception):
    """
        Raised when the server returns 401 / 403.
    """


class PermissionDeniedError(AuthenticationError):
    """
        Raised when the server returns 403: the caller is known but
        lacks a permission.
    """


class NotFoundError(Exception):
    """
        Raised when the server returns 404.
    """


class ConflictError(Exception):
    """
        Raised when the server returns 409.
    """


class RateLimitedError(Exception):
    """
        Raised when the server returns 429.
    """


class ServerError(Exception):
    """
        Raised when the server returns >= 500.
    """


class UnexpectedResponseError(ServerError):
    """
        Raised when the answer is not the API's: a redirect (usually
        to the sign-in page), an HTML page, or a status the CLI does
        not expect. The message names the likely cause.
    """


class ServerUnreachableError(Exception):
    """
        Raised when no HTTP answer arrives: connection refused, DNS
        failure, TLS failure, timeout, or a malformed URL.
    """


class RunFailedError(Exception):
    """
        Raised by ``--wait`` when the run reached a terminal state
        other than success.
    """


class WaitTimeoutError(Exception):
    """
        Raised by ``--wait`` when the run did not finish in time.
    """


class OpenApiUnavailableError(Exception):
    """
        Raised when the OpenAPI document cannot be loaded from cache or
        fetched from the server.
    """


class CommandTreeBuildError(Exception):
    """
        Raised when ``parser.build_command_tree`` cannot construct a
        coherent argparse tree from the supplied OpenAPI document.
    """
