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

Layers (innermost first):

* security headers + the per-response CSP nonce
  (:mod:`hardening.security_headers`);
* request metrics -- count and latency per method / status class,
  exposed on ``/metrics`` (:mod:`system.operations`).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import time

from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Tuple

from ccai.pychestrate.webservice.hardening.security_headers import (
    wrap_wsgi_application_with_security_headers,
)


RUNTIME_ENVIRONMENT_PRODUCTION: str = "production"


class _MeasuredBody:
    """
        Response iterable that records the request's metrics once the
        server finishes with it (exhaustion or ``close()``), for
        applications that only call ``start_response`` while being
        iterated.
    """

    def __init__(self, *, inner: Iterable[bytes], on_done: Callable[[], None]) -> None:
        self._inner = inner
        self._on_done = on_done
        self._done = False
        return

    def __iter__(self) -> Iterator[bytes]:
        for chunk in self._inner:
            yield chunk
        self._finish()
        return

    def close(self) -> None:
        """
            WSGI ``close()``: close the inner iterable, then record.

            :returns: None.
        """
        try:
            closer = getattr(self._inner, "close", None)
            if callable(closer):
                closer()
        finally:
            self._finish()
        return

    def _finish(self) -> None:
        if self._done is False:
            self._done = True
            self._on_done()
        return


def wrap_wsgi_application_with_request_metrics(
        *,
        wsgi_app: Callable[..., Iterable[bytes]]
    ) -> Callable[..., Iterable[bytes]]:
    """
        Count every response by method and status class and observe
        how long it took to produce.

        :param wsgi_app: WSGI callable.

        :returns: WSGI callable.
    """
    from ccai.pychestrate.webservice.system.operations import record_http_request

    def _application(environ: Dict[str, Any], start_response: Callable[..., Any]) -> Iterable[bytes]:
        started = time.perf_counter()
        method = str(environ.get("REQUEST_METHOD", "GET") or "GET")
        captured: Dict[str, Optional[int]] = {"status": None}

        def _start_response(status: str, headers: List[Tuple[str, str]], exc_info: Any = None) -> Any:
            try:
                captured["status"] = int(str(status).split(" ", 1)[0])
            except ValueError:
                captured["status"] = None
            if exc_info is None:
                rtnval = start_response(status, headers)
            else:
                rtnval = start_response(status, headers, exc_info)
            return rtnval

        def _record() -> None:
            status = captured["status"] if captured["status"] is not None else 500
            record_http_request(method=method, status_code=status, duration_seconds=time.perf_counter() - started)
            return

        try:
            body = wsgi_app(environ, _start_response)
        except BaseException:
            captured["status"] = 500
            _record()
            raise
        if captured["status"] is not None:
            _record()
            return body
        rtnval = _MeasuredBody(inner=body, on_done=_record)
        return rtnval

    rtnval = _application
    return rtnval


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
    wrapped = wrap_wsgi_application_with_request_metrics(wsgi_app=wrapped)
    rtnval = wrapped
    return rtnval


__all__ = [
    "wrap_platform_wsgi_application",
    "wrap_wsgi_application_with_request_metrics",
]
