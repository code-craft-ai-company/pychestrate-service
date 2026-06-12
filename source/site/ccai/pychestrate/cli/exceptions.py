"""
.. module:: cli.exceptions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: CLI-side exception types.

.. moduleauthor:: Code Craft AI LLC
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


class ProfileNotFoundError(Exception):
    """
        Raised when the named profile is missing from the credentials
        file.
    """


class AuthenticationError(Exception):
    """
        Raised when the server returns 401 / 403.
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
