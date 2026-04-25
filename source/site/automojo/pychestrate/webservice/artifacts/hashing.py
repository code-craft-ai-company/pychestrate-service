"""
.. module:: artifacts.hashing
    :synopsis: Streaming SHA-256 over a blob source.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib

from typing import IO, Iterable


HASH_CHUNK_BYTES: int = 1 << 20


def hash_blob_stream(
        *,
        stream: IO[bytes]
    ) -> str:
    """
        Compute the lowercase-hex SHA-256 of every byte read from
        ``stream`` until EOF. Stream is consumed; the caller
        re-opens or seeks back as needed.

        :param stream: Binary readable stream.

        :returns: Lowercase hex digest string.
    """
    hasher = hashlib.sha256()
    while True:
        chunk = stream.read(HASH_CHUNK_BYTES)
        if chunk is None or len(chunk) == 0:
            break
        hasher.update(chunk)
    rtnval = hasher.hexdigest()
    return rtnval


def hash_iterable_chunks(
        *,
        chunks: Iterable[bytes]
    ) -> str:
    """
        Convenience for callers that already have an iterable of
        chunk bytes.
    """
    hasher = hashlib.sha256()
    for chunk in chunks:
        if chunk is None or len(chunk) == 0:
            continue
        hasher.update(chunk)
    rtnval = hasher.hexdigest()
    return rtnval
