"""
.. module:: hardening.platform_wsgi
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The WSGI layers every pychestrate response passes
               through.

.. moduleauthor:: Code Craft AI LLC

Both entry points in :mod:`app_pychestrate_main` (the built-in server
and the gunicorn factory) wrap their WSGI application once with
:func:`wrap_platform_wsgi_application`. Working at the WSGI boundary
means the layers see every response -- including the dispatcher's own
404 / 405 / 500 answers and the setup-gate redirects -- not only the
ones a matched route produced.

Layers (outermost last):

* security headers + the per-response CSP nonce
  (:mod:`hardening.security_headers`).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Callable, Iterable

from ccai.pychestrate.webservice.hardening.security_headers import (
    wrap_wsgi_application_with_security_headers,
)


RUNTIME_ENVIRONMENT_PRODUCTION: str = "production"


def wrap_platform_wsgi_application(
        *,
        wsgi_app: Callable[..., Iterable[bytes]],
        runtime_environment: str
    ) -> Callable[..., Iterable[bytes]]:
    """
        Wrap the service's WSGI application with the platform layers.

        :param wsgi_app: The WSGI callable the entry point built.
        :param runtime_environment: ``PYCHESTRATE_RUNTIME_ENVIRONMENT``;
                                    HSTS is only sent in production.

        :returns: The wrapped WSGI callable.
    """
    wrapped = wrap_wsgi_application_with_security_headers(
        wsgi_app=wsgi_app,
        hsts_enabled=runtime_environment == RUNTIME_ENVIRONMENT_PRODUCTION,
    )
    rtnval = wrapped
    return rtnval


__all__ = [
    "wrap_platform_wsgi_application",
]
