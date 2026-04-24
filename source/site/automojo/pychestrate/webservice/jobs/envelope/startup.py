"""
.. module:: jobs.envelope.startup
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Service-startup hook that installs the envelope signing key.

.. moduleauthor:: Automation Mojo LLC

The M1 bootstrap path loads the Ed25519 signing key from either an
operator-supplied config (file / env) or — in dev mode — generates
an ephemeral key so the service can come up without the operator
having staged anything. Production deployers override this with a
``1-secrets-vault`` fetch once the vault wiring lands.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass
from typing import Optional

from automojo.errors.exceptions import ConfigurationError

from automojo.pychestrate.webservice.jobs.envelope import signer


DEV_MODE_ENV_VAR: str = "PYCHESTRATE_DEV_MODE"
DEV_KEY_ID_DEFAULT: str = "pychestrate-dev-ed25519"


@dataclass(frozen=True)
class EnvelopeSignerBootstrapConfig:
    """
        Operator-supplied configuration for the envelope signing
        startup hook.

        :param source: ``"file"``, ``"env"``, or ``"dev"``. ``"dev"``
                       generates an ephemeral key in-process and is
                       only honored when the
                       ``PYCHESTRATE_DEV_MODE`` env var is set to
                       ``"1"`` / ``"true"`` (case-insensitive).
        :param file_path: Path to the base64 Ed25519 seed when
                          ``source="file"``.
        :param env_var: Environment variable holding the seed when
                        ``source="env"``.
        :param key_id: Operator-assigned identifier to publish on
                       signed envelopes.
    """
    source: str
    file_path: Optional[str]
    env_var: Optional[str]
    key_id: str


def install_envelope_signer(*, config: EnvelopeSignerBootstrapConfig) -> None:
    """
        Load the Ed25519 signing key according to ``config`` and
        install it as the active key. In ``"dev"`` mode the caller
        must also set ``PYCHESTRATE_DEV_MODE=1`` so the ephemeral
        path cannot be accidentally taken in production.

        :param config: :class:`EnvelopeSignerBootstrapConfig`.

        :returns: None.
        :raises: ConfigurationError on misconfiguration.
    """
    if config.source == "dev":
        if _dev_mode_active() is False:
            err_lines = [
                "Envelope signer source 'dev' requires "
                "PYCHESTRATE_DEV_MODE=1 in the environment.",
            ]
            err_lines.append("HINT: stage a real signing key and re-run with source='file' or 'env'.")
            err_msg = os.linesep.join(err_lines)
            raise ConfigurationError(err_msg) from None

        handle = signer.generate_dev_signing_key(key_id=config.key_id)
        signer.set_active_signing_key(handle=handle)
        return

    handle = signer.load_signing_key_at_startup(
        source=config.source,
        file_path=config.file_path,
        env_var=config.env_var,
        key_id=config.key_id,
    )
    signer.set_active_signing_key(handle=handle)
    return


def _dev_mode_active() -> bool:
    """
        Check the ``PYCHESTRATE_DEV_MODE`` environment variable.

        :returns: True when set to ``"1"`` or ``"true"``
                  (case-insensitive).
    """
    raw = os.environ.get(DEV_MODE_ENV_VAR, "")
    if raw is None:
        return False
    normalized = raw.strip().lower()
    if normalized in ("1", "true", "yes"):
        return True
    return False
