"""
.. module:: artifacts.cas_layout
    :synopsis: CAS key construction for hot / cold tiers.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from ccai.pychestrate.webservice.artifacts.errors import ArtifactError


HOT_TIER_PREFIX: str = "cas/hot"
COLD_TIER_PREFIX: str = "cas/cold"


def build_cas_key(
        *,
        digest: str,
        tier: str = "hot"
    ) -> str:
    """
        Produce the object-store key for a CAS blob.

        Layout: ``cas/<tier>/<digest[0:2]>/<digest[2:4]>/<digest>``

        :param digest: Lowercase-hex SHA-256.
        :param tier: ``"hot"`` or ``"cold"``.

        :returns: Slash-separated key.
        :raises: ArtifactError for unknown tier or malformed
                 digest.
    """
    if digest is None or len(digest) != 64:
        err_lines = ["CAS digest must be a 64-char lowercase-hex string."]
        err_lines.append("RECEIVED: {}".format(digest))
        err_msg = os.linesep.join(err_lines)
        raise ArtifactError(err_msg) from None
    if tier == "hot":
        prefix = HOT_TIER_PREFIX
    elif tier == "cold":
        prefix = COLD_TIER_PREFIX
    else:
        err_lines = ["Unknown CAS tier."]
        err_lines.append("TIER: {}".format(tier))
        err_lines.append("SUPPORTED: (hot, cold)")
        err_msg = os.linesep.join(err_lines)
        raise ArtifactError(err_msg) from None
    rtnval = "{}/{}/{}/{}".format(prefix, digest[0:2], digest[2:4], digest)
    return rtnval
