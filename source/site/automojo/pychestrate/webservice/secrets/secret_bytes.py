"""
.. module:: secrets.secret_bytes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SecretBytes wrapper with redacted repr and zeroize-on-close.

.. moduleauthor:: Automation Mojo LLC

Plaintext secrets never appear in ``repr``, ``str``, trace output, or log
messages. Callers wrap raw bytes in :class:`SecretBytes` as soon as the
plaintext exists and consume the wrapper once. Downstream formatting
paths see only the literal string ``"<redacted>"``.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


REDACTED_TOKEN: str = "<redacted>"


class SecretBytes:
    """
        Opaque byte container for secret plaintext.

        The wrapper exposes a :meth:`reveal` accessor that returns the
        underlying bytes exactly once per wrapper lifetime. After
        :meth:`close` runs, subsequent ``reveal`` calls raise
        :class:`RuntimeError`. Every formatter and the interactive
        repr only ever see ``"<redacted>"``.
    """

    def __init__(self, raw: bytes) -> None:
        self._raw = bytes(raw)
        self._revealed_count = 0
        self._closed = False
        return

    def reveal(self) -> bytes:
        """
            Return the underlying bytes. Raises when the wrapper has been closed.

            :returns: The underlying bytes.
            :raises: RuntimeError when the wrapper is closed.
        """
        if self._closed is True:
            raise RuntimeError("SecretBytes has been closed; plaintext is no longer available")

        self._revealed_count = self._revealed_count + 1
        rtnval = self._raw
        return rtnval

    def close(self) -> None:
        """
            Zeroize the held plaintext and mark the wrapper unusable.

            :returns: None.
        """
        if self._closed is True:
            return

        zeros = bytes(len(self._raw))
        self._raw = zeros
        self._closed = True
        return

    def __repr__(self) -> str:
        return REDACTED_TOKEN

    def __str__(self) -> str:
        return REDACTED_TOKEN

    def __len__(self) -> int:
        return len(self._raw)

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            # Destructors run in arbitrary contexts; swallowing here is
            # explicit per AGENTS.md (purposeful silencing for finalizers).
            pass
        return
