"""
.. module:: webservice.embed.key_provider
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Process-local embed signing key provider.

.. moduleauthor:: Automation Mojo LLC

The full key store lives in ``1-secrets-vault`` (a follow-up wires
that path). Until then the REST surface needs a stable HMAC key so
``POST .../:sign`` can mint URLs the ``GET /embed/...`` serving route
can verify within the same process lifetime.

This module derives a single deterministic :class:`EmbedSigningKey`
from the ``PYCHESTRATE_EMBED_SIGNING_SECRET`` environment variable
when present, or a process-stable random key otherwise. The
``key_id`` is a stable base32 fingerprint of the key material so the
issuer and the resolver agree without external state.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import base64
import hashlib
import os
import threading

from typing import Optional

from automojo.pychestrate.webservice.embed.signing import EmbedSigningKey


EMBED_SIGNING_SECRET_ENV_VAR: str = "PYCHESTRATE_EMBED_SIGNING_SECRET"


_LOCK = threading.RLock()
_ACTIVE_KEY: Optional[EmbedSigningKey] = None


def _fingerprint_key_id(*, key_bytes: bytes) -> str:
    """
        Derive a stable 12-byte base32 key id from raw key material.

        :param key_bytes: Raw HMAC key material.

        :returns: Uppercase base32 key-id string (no padding).
    """
    digest = hashlib.sha256(key_bytes).digest()
    encoded = base64.b32encode(digest[:12]).decode("ascii")
    rtnval = encoded.rstrip("=")
    return rtnval


def _derive_key() -> EmbedSigningKey:
    """
        Build the process signing key from the configured secret, or
        a process-stable random key when the env var is absent.

        :returns: A fresh :class:`EmbedSigningKey`.
    """
    configured_secret = os.environ.get(EMBED_SIGNING_SECRET_ENV_VAR, None)
    if configured_secret is not None and len(configured_secret) > 0:
        key_bytes = hashlib.sha256(configured_secret.encode("utf-8")).digest()
    else:
        key_bytes = os.urandom(32)

    key_id = _fingerprint_key_id(key_bytes=key_bytes)
    rtnval = EmbedSigningKey(key_id=key_id, key_bytes=key_bytes)
    return rtnval


def get_active_signing_key() -> EmbedSigningKey:
    """
        Return the process-active embed signing key, deriving it on
        first use.

        :returns: The cached :class:`EmbedSigningKey`.
    """
    global _ACTIVE_KEY
    with _LOCK:
        cached = _ACTIVE_KEY
        if cached is not None:
            rtnval = cached
            return rtnval
        derived = _derive_key()
        _ACTIVE_KEY = derived
    rtnval = derived
    return rtnval


def resolve_signing_key(key_id: str) -> Optional[EmbedSigningKey]:
    """
        Resolver callable for :func:`embed.signing.verify_signed_url`.

        :param key_id: Key id parsed from the embed URL.

        :returns: The :class:`EmbedSigningKey` when ``key_id`` matches
                  the process-active key, else ``None``.
    """
    active = get_active_signing_key()
    if key_id == active.key_id:
        rtnval: Optional[EmbedSigningKey] = active
        return rtnval
    rtnval = None
    return rtnval


def reset_for_testing() -> None:
    """
        Clear the cached signing key. Test helper.

        :returns: None.
    """
    global _ACTIVE_KEY
    with _LOCK:
        _ACTIVE_KEY = None
    return


__all__ = [
    "EMBED_SIGNING_SECRET_ENV_VAR",
    "get_active_signing_key",
    "resolve_signing_key",
    "reset_for_testing",
]
