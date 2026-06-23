"""
.. module:: projects.slug
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Project slug canonicalization for 2-projects.

.. moduleauthor:: Code Craft AI LLC

Project slugs are the public-facing URL identifier. They are lower-case,
hyphen-separated ASCII. The canonical regex is ``^[a-z][a-z0-9-]{1,62}``
per ``specs/2-projects/design.md`` (max length 63).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import re

from ccai.pychestrate.webservice.projects.exceptions import SlugValidationError


_SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,62}$")


def canonicalize_project_slug(*, raw_slug: str) -> str:
    """
        Normalize a caller-supplied slug and validate it.

        :param raw_slug: Slug as supplied by the caller.

        :returns: The canonicalized slug.
        :raises: SlugValidationError
    """
    if raw_slug is None:
        err_msg_lines = ["Cannot canonicalize project slug — value is None."]
        err_msg = os.linesep.join(err_msg_lines)
        raise SlugValidationError(err_msg)

    stripped = raw_slug.strip().lower()
    if len(stripped) == 0:
        err_msg_lines = ["Cannot canonicalize project slug — value is empty after trim."]
        err_msg = os.linesep.join(err_msg_lines)
        raise SlugValidationError(err_msg)

    if _SLUG_PATTERN.match(stripped) is None:
        err_msg_lines = ["Project slug does not match required pattern."]
        err_msg_lines.append("SLUG: {}".format(stripped))
        err_msg_lines.append("PATTERN: ^[a-z][a-z0-9-]{1,62}$")
        err_msg = os.linesep.join(err_msg_lines)
        raise SlugValidationError(err_msg)

    rtnval = stripped
    return rtnval
