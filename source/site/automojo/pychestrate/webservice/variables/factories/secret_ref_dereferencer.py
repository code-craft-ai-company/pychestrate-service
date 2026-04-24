"""
.. module:: variables.factories.secret_ref_dereferencer
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``secret_ref_dereferencer`` factory protocol + reference impl.

.. moduleauthor:: Automation Mojo LLC

A variable whose ``value_type`` is ``SECRET_REF`` stores a string like
``secret://my-secret#v3``. When :func:`variable_service.resolve_effective`
is invoked with ``dereference_secrets=True`` it walks the registered
implementations of this factory protocol in PRECEDENCE order, returning
the first payload produced.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, ClassVar

from automojo.pychestrate.webservice.extensions.factory_protocol import FactoryProtocolBase


class SecretRefDereferencerProtocol(FactoryProtocolBase):
    """
        Contract implemented by secret-reference dereferencers.
    """

    factory_protocol_name: ClassVar[str] = "secret_ref_dereferencer"
    protocol_schema_version: ClassVar[int] = 1

    @classmethod
    def dereference(cls, *, secret_ref: str) -> Any:
        """
            Resolve ``secret_ref`` to its payload.

            :param secret_ref: String in ``secret://name#version`` form.

            :returns: The resolved payload.
            :raises: NotImplementedError when this impl cannot handle ``secret_ref``.
        """
        raise NotImplementedError("Subclasses must implement dereference()")


class VaultSecretRefDereferencer(SecretRefDereferencerProtocol):
    """
        Reference dereferencer that resolves ``secret://name#version``
        against the in-tree :mod:`secrets` vault.
    """

    factory_protocol_name: ClassVar[str] = "secret_ref_dereferencer"
    PRECEDENCE: ClassVar[int] = 1000

    @classmethod
    def dereference(cls, *, secret_ref: str) -> Any:
        """
            Parse ``secret://name#version`` and return a placeholder
            resolution summary. Real vault dereferencing requires the
            caller-bound identity + session; this M2 reference impl
            returns a structured stub that callers can use for routing
            until the fully wired SecretsBackend integration lands.

            :param secret_ref: ``secret://<name>[#<version>]`` reference.

            :returns: Dict with ``name`` and optional ``version`` keys.
            :raises: NotImplementedError when ``secret_ref`` is not in
                     the ``secret://…`` form.
        """
        if secret_ref is None or secret_ref.startswith("secret://") is False:
            raise NotImplementedError("Not a secret:// reference")

        remainder = secret_ref[len("secret://"):]
        if "#" in remainder:
            name, _, version = remainder.partition("#")
        else:
            name = remainder
            version = ""

        rtnval = {
            "kind": "secret_ref",
            "name": name.strip(),
            "version": version.strip() if len(version.strip()) > 0 else None,
            "resolved_via": "VaultSecretRefDereferencer",
        }
        return rtnval
