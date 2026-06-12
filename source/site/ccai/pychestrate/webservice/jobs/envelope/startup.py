"""
.. module:: jobs.envelope.startup
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Service-startup hook that installs the envelope signing key.

.. moduleauthor:: Code Craft AI LLC

The M1 bootstrap path loads the Ed25519 signing key from either an
operator-supplied config (file / env) or — in dev mode — generates
an ephemeral key so the service can come up without the operator
having staged anything. Production deployers override this with a
``1-secrets-vault`` fetch once the vault wiring lands.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import os

from dataclasses import dataclass
from typing import Optional

from ccai.errors.exceptions import ConfigurationError

from ccai.pychestrate.webservice.jobs.envelope import signer


DEV_MODE_ENV_VAR: str = "PYCHESTRATE_DEV_MODE"
DEV_KEY_ID_DEFAULT: str = "pychestrate-dev-ed25519"

#: Documented env-var names for the deploy-time signing-key wiring.
#: Mirrors the ``PYCHESTRATE_KEK_*`` naming so operators can grep the
#: deploy environment for a uniform ``PYCHESTRATE_*`` surface.
ENV_SIGNING_KEY_SOURCE: str = "PYCHESTRATE_ENVELOPE_SIGNING_KEY_SOURCE"
ENV_SIGNING_KEY_ID: str = "PYCHESTRATE_ENVELOPE_SIGNING_KEY_ID"
ENV_SIGNING_KEY_FILE_PATH: str = "PYCHESTRATE_ENVELOPE_SIGNING_KEY_FILE_PATH"
ENV_SIGNING_KEY_ENV_VAR: str = "PYCHESTRATE_ENVELOPE_SIGNING_KEY_ENV_VAR"

_module_logger = logging.getLogger(__name__)


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


def build_bootstrap_config_from_environment() -> EnvelopeSignerBootstrapConfig:
    """
        Build an :class:`EnvelopeSignerBootstrapConfig` from the
        ``PYCHESTRATE_ENVELOPE_SIGNING_KEY_*`` environment variables.

        When ``PYCHESTRATE_ENVELOPE_SIGNING_KEY_SOURCE`` is unset the
        config defaults to ``"dev"`` -- a non-production deploy that
        sets ``PYCHESTRATE_DEV_MODE=1`` then gets an ephemeral
        in-process key without staging any material. A production
        deploy must set ``SOURCE`` to ``"file"`` or ``"env"`` and
        stage a real key.

        :returns: Populated :class:`EnvelopeSignerBootstrapConfig`.
    """
    source = os.environ.get(ENV_SIGNING_KEY_SOURCE, "")
    if source is None or len(source.strip()) == 0:
        source = "dev"
    else:
        source = source.strip()

    key_id = os.environ.get(ENV_SIGNING_KEY_ID, "")
    if key_id is None or len(key_id.strip()) == 0:
        key_id = DEV_KEY_ID_DEFAULT
    else:
        key_id = key_id.strip()

    file_path = os.environ.get(ENV_SIGNING_KEY_FILE_PATH, None)
    env_var = os.environ.get(ENV_SIGNING_KEY_ENV_VAR, None)

    rtnval = EnvelopeSignerBootstrapConfig(
        source=source,
        file_path=file_path,
        env_var=env_var,
        key_id=key_id,
    )
    return rtnval


def install_envelope_signer_from_environment() -> bool:
    """
        Best-effort install of the envelope signing key from the
        deploy environment. Called from the service entrypoints after
        the runtime bootstrap loads the KEK.

        A misconfiguration is logged and swallowed rather than crashing
        the whole service -- the ``GET /envelope-signing-keys`` endpoint
        and the envelope codec already fail closed (503 /
        :class:`EnvelopeSigningKeyMissingError`) when no key is
        installed, so a missing signing key degrades the dispatch
        feature without taking down login or the rest of the API.

        :returns: True when a signing key was installed, False when
                  installation was skipped or failed.
    """
    config = build_bootstrap_config_from_environment()
    try:
        install_envelope_signer(config=config)
    except ConfigurationError as xcpt:
        _module_logger.warning(
            "pychestrate.envelope.signer.not_installed source=%s reason=%s",
            config.source,
            str(xcpt),
        )
        rtnval = False
        return rtnval

    _module_logger.info(
        "pychestrate.envelope.signer.installed source=%s key_id=%s",
        config.source,
        config.key_id,
    )
    rtnval = True
    return rtnval


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
