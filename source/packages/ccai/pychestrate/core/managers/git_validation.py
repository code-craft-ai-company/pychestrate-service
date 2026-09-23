"""
.. module:: git_validation
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Checks for the Git names and patterns project forms accept:
               branch and tag names, commit SHAs, repository URLs and
               regular expressions.

.. moduleauthor:: Code Craft AI LLC

Each check returns a sentence for the user when the value is not
acceptable, or None when it is, so managers can raise their validation
errors with it and the pages can show it next to the field.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re

from typing import Optional
from urllib.parse import urlsplit


# Characters git refuses in a ref name (git check-ref-format), plus
# whitespace and control characters.
_REF_FORBIDDEN = re.compile(r'[\x00-\x20\x7f~^:?*\[\\]')

# A full or abbreviated commit SHA (SHA-1 or SHA-256; git abbreviates to
# no fewer than 4 hexadecimal digits).
_COMMIT_SHA = re.compile(r'^[0-9a-fA-F]{4,64}\Z')

# scp-like SSH URL: git@host:path or user@host:path
_SCP_LIKE_URL = re.compile(r'^[A-Za-z0-9._-]+@[A-Za-z0-9.-]+:[^\s]+\Z')

# Longest branch or tag name accepted (the columns hold 128 characters).
MAX_REF_NAME_LENGTH: int = 128


def ref_name_problem(*, name: str, kind: str = "branch") -> Optional[str]:
    """
    Why ``name`` is not a valid branch or tag name, following git's
    check-ref-format rules.

    :param name: The name to check (without refs/heads/ or refs/tags/)
    :param kind: "branch" or "tag", for the message
    :returns: A sentence for the user, or None when the name is valid
    """
    value = name or ""
    rtnval: Optional[str] = None
    if len(value) == 0:
        rtnval = "Enter a {} name.".format(kind)
    elif len(value) > MAX_REF_NAME_LENGTH:
        rtnval = "A {} name can be at most {} characters.".format(kind, MAX_REF_NAME_LENGTH)
    elif (
        _REF_FORBIDDEN.search(value) is not None
        or ".." in value
        or "@{" in value
        or "//" in value
        or value == "@"
        or value.startswith(("-", "/", "."))
        or value.endswith(("/", ".", ".lock"))
        or "/." in value
    ):
        rtnval = (
            "'{}' is not a valid {} name: it cannot contain spaces, '..', '~', '^', ':', "
            "'?', '*', '[' or '\\', or start or end with '/' or '.'.".format(value, kind)
        )
    return rtnval


def commit_sha_problem(*, value: str) -> Optional[str]:
    """
    Why ``value`` is not a commit SHA.

    :param value: The value to check
    :returns: A sentence for the user, or None when it is 4 to 64
              hexadecimal characters
    """
    rtnval: Optional[str] = None
    if _COMMIT_SHA.match(value or "") is None:
        rtnval = (
            "'{}' is not a commit SHA: use 4 to 40 hexadecimal characters "
            "(or leave it empty for the latest commit on the branch).".format(value)
        )
    return rtnval


def repository_url_problem(*, url: str, ssh_only: bool = False) -> Optional[str]:
    """
    Why ``url`` is not a Git repository URL.

    :param url: The URL to check
    :param ssh_only: True when the repository authenticates with an SSH
                     key, which needs an SSH URL
    :returns: A sentence for the user, or None when the URL is usable
    """
    value = (url or "").strip()
    is_scp = _SCP_LIKE_URL.match(value) is not None
    try:
        parts = urlsplit(value)
    except ValueError:
        parts = None
    scheme = (parts.scheme if parts is not None else "").lower()
    has_host = parts is not None and bool(parts.hostname)
    has_space = any(ch.isspace() for ch in value)

    rtnval: Optional[str] = None
    if ssh_only is True:
        if has_space or not (is_scp or (scheme == "ssh" and has_host)):
            rtnval = (
                "SSH key authentication needs an SSH URL, for example "
                "git@github.com:org/repo.git or ssh://git@host/org/repo.git."
            )
    elif has_space or not (is_scp or (scheme in ("http", "https", "ssh") and has_host)):
        rtnval = (
            "Enter the repository's Git URL, for example "
            "https://github.com/org/repo.git or git@github.com:org/repo.git."
        )
    return rtnval


def regex_problem(*, pattern: str, what: str = "pattern") -> Optional[str]:
    """
    Why ``pattern`` is not a regular expression Python can use.

    :param pattern: The pattern to check (empty means "no pattern")
    :param what: What the pattern is for, for the message
    :returns: A sentence for the user, or None when it compiles
    """
    rtnval: Optional[str] = None
    if pattern:
        try:
            re.compile(pattern)
        except re.error as error:
            rtnval = "The {} is not a valid regular expression: {}.".format(what, error)
    return rtnval


__all__ = [
    "MAX_REF_NAME_LENGTH",
    "ref_name_problem",
    "commit_sha_problem",
    "repository_url_problem",
    "regex_problem",
]
