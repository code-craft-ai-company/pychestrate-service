"""
.. module:: security.auth.saml
    :synopsis: SAML 2.0 primitives package marker.

The SAML feature ships in three slices:

* P20a — :mod:`saml_metadata` cache (this slice).
* P20b — :mod:`saml_id` (assertion validator).
* P20c — :mod:`replay_cache` + :class:`SamlAuthProvider`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"
