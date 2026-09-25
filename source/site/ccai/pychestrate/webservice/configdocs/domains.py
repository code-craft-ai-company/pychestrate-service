"""
.. module:: configdocs.domains
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The fixed configuration-document domain vocabulary.

.. moduleauthor:: Code Craft AI LLC

0-config-formats Requirement 1.1 fixes the domain set at four. A
document domain names one *kind* of externally-authored input --
never a file format and never a storage location. The format that
expresses a domain is pluggable (``config_document_format``); the
domain vocabulary is not.

Each domain owns exactly one file (or one ``.d`` directory) beneath
``<presence_dir>/config``. Requirement 4.2 forbids two domains
sharing a file even when a format could express both, which is why
the stem is a property of the domain rather than of the format.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import enum

from typing import Dict, Tuple


class ConfigDocumentDomain(str, enum.Enum):
    """
        The four externally-authored document domains.
    """
    RESOURCE_SPEC = "resource_spec"
    LANDSCAPE = "landscape"
    TOPOLOGY = "topology"
    CREDENTIALS = "credentials"


#: Sub-directory of the presence directory that holds every
#: configuration document (Requirement 4.1).
CONFIG_SUBDIR: str = "config"


#: Format selected when a deployment expresses no preference
#: (Requirement 3.7). M3 reads the per-domain override from the
#: ``config.format.<domain>`` global variable.
DEFAULT_FORMAT_NAME: str = "codecraftai"


#: Per-domain filename stem. The concrete extension is the format's
#: business (``file_basenames``); the stem is the domain's, so that
#: switching format does not rename the operator's file.
DOMAIN_STEMS: Dict[ConfigDocumentDomain, str] = {
    ConfigDocumentDomain.RESOURCE_SPEC: "resource-specs",
    ConfigDocumentDomain.LANDSCAPE: "landscape",
    ConfigDocumentDomain.TOPOLOGY: "topology",
    ConfigDocumentDomain.CREDENTIALS: "credentials",
}


#: Suffix marking the directory form of a domain's document
#: (Requirement 4.6): ``landscape.d/`` instead of ``landscape.yaml``.
DIRECTORY_SUFFIX: str = ".d"


def domain_values() -> Tuple[str, ...]:
    """
        Every declared domain value, sorted.

        :returns: Tuple of domain string values.
    """
    rtnval = tuple(sorted([member.value for member in ConfigDocumentDomain]))
    return rtnval


def coerce_domain(*, domain: object) -> ConfigDocumentDomain:
    """
        Normalize a domain expressed as a string or enum member.

        :param domain: A :class:`ConfigDocumentDomain` or its string value.

        :returns: The matching :class:`ConfigDocumentDomain`.
        :raises: ValueError when ``domain`` names no declared domain.
    """
    if isinstance(domain, ConfigDocumentDomain) is True:
        return domain

    text = str(domain).strip()
    for member in ConfigDocumentDomain:
        if member.value == text:
            return member

    err_msg = "Unknown configuration-document domain '{}'. DECLARED: {}".format(
        text, list(domain_values()),
    )
    raise ValueError(err_msg) from None


def stem_for_domain(*, domain: ConfigDocumentDomain) -> str:
    """
        The filename stem this domain's document uses.

        :param domain: The domain.

        :returns: The stem, e.g. ``landscape``.
    """
    rtnval = DOMAIN_STEMS[domain]
    return rtnval


def env_var_for_domain(*, domain: ConfigDocumentDomain) -> str:
    """
        The per-domain absolute-path override variable
        (Requirement 4.7), e.g. ``PYCHESTRATE_CONFIG_LANDSCAPE_PATH``.

        :param domain: The domain.

        :returns: The environment variable name.
    """
    rtnval = "PYCHESTRATE_CONFIG_{}_PATH".format(domain.value.upper())
    return rtnval


def format_variable_for_domain(*, domain: ConfigDocumentDomain) -> str:
    """
        The global-variable key that selects this domain's format
        (Requirement 5.1). Read by M3; named here so the domain
        vocabulary owns the key shape.

        :param domain: The domain.

        :returns: The variable key, e.g. ``config.format.landscape``.
    """
    rtnval = "config.format.{}".format(domain.value)
    return rtnval
