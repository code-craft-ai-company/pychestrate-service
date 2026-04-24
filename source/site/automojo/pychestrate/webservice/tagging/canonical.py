"""
.. module:: tagging.canonical
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Canonicalization of tag input values for 2-tagging.

.. moduleauthor:: Automation Mojo LLC

The canonical form is ``taxonomy_name:value``. The taxonomy name is
lower-cased and the value is lower-cased only when the taxonomy
declares ``case_sensitive_value=False``. Validation against the
taxonomy's ``allowed_values`` set (if present) is enforced here.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import re

from typing import Tuple

from automojo.pychestrate.webservice.tagging.exceptions import (
    TagValueValidationError,
    TaxonomyNotFoundError,
)


_TAXONOMY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


def canonicalize_tag(*, raw_tag: str, taxonomy) -> Tuple[str, str]:
    """
        Split a ``taxonomy:value`` tag into canonical components.

        :param raw_tag: Input string in ``taxonomy_name:value`` form.
        :param taxonomy: The registered taxonomy extension class.

        :returns: Tuple ``(taxonomy_name, canonical_value)``.
        :raises: TagValueValidationError
    """
    if raw_tag is None or len(raw_tag.strip()) == 0:
        err_msg_lines = ["Cannot canonicalize tag — value is empty."]
        err_msg = os.linesep.join(err_msg_lines)
        raise TagValueValidationError(err_msg)

    stripped = raw_tag.strip()
    if ":" not in stripped:
        err_msg_lines = ["Tag is not in ``taxonomy:value`` form."]
        err_msg_lines.append("TAG: {}".format(stripped))
        err_msg = os.linesep.join(err_msg_lines)
        raise TagValueValidationError(err_msg)

    name_part, _, value_part = stripped.partition(":")
    name_norm = name_part.strip().lower()

    if _TAXONOMY_PATTERN.match(name_norm) is None:
        err_msg_lines = ["Taxonomy name does not match required pattern."]
        err_msg_lines.append("TAXONOMY: {}".format(name_norm))
        err_msg_lines.append("PATTERN: ^[a-z][a-z0-9_]{0,31}$")
        err_msg = os.linesep.join(err_msg_lines)
        raise TagValueValidationError(err_msg)

    declared_name = getattr(taxonomy, "taxonomy_name", "")
    if declared_name != name_norm:
        err_msg_lines = ["Taxonomy mismatch between input tag and registered taxonomy."]
        err_msg_lines.append("INPUT: {}".format(name_norm))
        err_msg_lines.append("REGISTERED: {}".format(declared_name))
        err_msg = os.linesep.join(err_msg_lines)
        raise TaxonomyNotFoundError(err_msg)

    value_trimmed = value_part.strip()
    if len(value_trimmed) == 0:
        err_msg_lines = ["Tag value is empty."]
        err_msg_lines.append("TAG: {}".format(stripped))
        err_msg = os.linesep.join(err_msg_lines)
        raise TagValueValidationError(err_msg)

    case_sensitive = bool(getattr(taxonomy, "case_sensitive_value", False))
    canonical_value = value_trimmed if case_sensitive is True else value_trimmed.lower()

    allowed = getattr(taxonomy, "allowed_values", None)
    if allowed is not None:
        if canonical_value not in allowed:
            err_msg_lines = ["Tag value is not in the taxonomy's allowed_values."]
            err_msg_lines.append("TAXONOMY: {}".format(name_norm))
            err_msg_lines.append("VALUE: {}".format(canonical_value))
            err_msg = os.linesep.join(err_msg_lines)
            raise TagValueValidationError(err_msg)

    rtnval = (name_norm, canonical_value)
    return rtnval
