"""
.. module:: security.auth.oidc
    :synopsis: 1-authentication M2 OIDC primitives.

The OIDC subpackage hosts the M2 building blocks for the
authorization-code-with-PKCE flow:

* :mod:`pkce` — PKCE S256 verifier + challenge generation.
* :mod:`state` — one-shot ``auth_oidc_state`` row helpers.
* :mod:`flow` — orchestration entry points
  (``begin_oidc_login``, M3 wiring lands the matching
  ``complete_oidc_callback`` and ``refresh_oidc_session``).

Each module is thin and pure-ish so the test surface stays
mock-free.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"
