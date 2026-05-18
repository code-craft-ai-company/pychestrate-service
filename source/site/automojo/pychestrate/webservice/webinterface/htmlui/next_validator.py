"""
.. module:: webinterface.htmlui.next_validator
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Same-origin guard for the post-login ``next`` query
               parameter (Requirement 5 + NFR-2 of
               1-authentication).

.. moduleauthor:: Automation Mojo LLC

When an unauthenticated browser is bounced to ``/login`` from a
protected page the dispatcher carries the original target in the
``?next=<percent-encoded-path>`` query string. After successful
authentication the login handler redirects the browser to that
target, but only if it passes the same-origin safety check
defined by NFR-2 of ``1-authentication/requirements.md``.

The accepted shape is intentionally narrow: a server-local
absolute path. Anything that smells of an open-redirect attempt
(absolute URLs, protocol-relative ``//host/...`` strings,
backslash-escaped variants, embedded newlines / control
characters, credential markers) is rejected; the caller falls
back to ``/`` per spec.

The validator emits no log line; the calling handler is
responsible for the ``auth.login.next_rejected`` event (it owns
the request context needed to hash the offending value for
forensics).
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Optional


# Maximum length of a candidate ``next`` value. Real same-origin
# paths are well under this; a 4 KiB ceiling stops a pathological
# value from forcing the validator to scan an arbitrarily large
# string before rejecting it.
MAX_NEXT_LENGTH: int = 4096


# Control character set that disqualifies a ``next`` value
# regardless of any other property. NUL through ASCII 0x1F plus
# DEL (0x7F). Newlines / carriage returns are included in this
# range and are also called out by NFR-2 directly.
_CONTROL_CHARS: tuple = tuple(chr(i) for i in range(0x20)) + ("\x7f",)


class NextValidator:
    """
        Stateless validator for the post-login ``next`` query
        parameter. The flask-era code inlined the same checks
        across two handlers; consolidating them in a class keeps
        the contract self-documenting (every accept / reject
        condition lives in one place) and lets future provider-
        specific login flows reuse the same primitive.

        Usage:

        ::

            validator = NextValidator()
            target = validator.resolve_safe_target(
                candidate=request.query_params.get("next", ""),
                fallback="/",
            )

        :param fallback_target: Default URL returned when the
                                candidate is rejected. Callers
                                that want a different fallback
                                (e.g. ``"/admin"``) override per
                                call site.
    """

    def __init__(self, *, fallback_target: str = "/") -> None:
        """
            Construct a validator with a default fallback.

            :param fallback_target: URL to return when the
                                    candidate ``next`` value fails
                                    validation.
        """
        if fallback_target is None or len(fallback_target) == 0:
            self._fallback_target: str = "/"
        else:
            self._fallback_target = fallback_target
        return

    def is_safe_same_origin_target(
            self, *, candidate: Optional[str]
        ) -> bool:
        """
            Return True when ``candidate`` is a server-local
            absolute path that is safe to use as a redirect
            target after a successful login.

            A candidate is accepted only when every condition
            below holds:

            * Not ``None`` and not empty.
            * Length under :data:`MAX_NEXT_LENGTH` characters.
            * Contains no ASCII control character (NUL through
              0x1F, plus DEL 0x7F) -- this rejects CRLF
              injection attempts.
            * Contains no backslash character (``\\``) -- some
              browsers + intermediaries normalise ``\\`` to
              ``/``, which would let ``\\\\evil.example/`` defeat
              the leading-``//`` check.
            * Starts with a single ``/`` (so it is an absolute
              path on our own origin) AND does NOT start with
              ``//`` (which would be a protocol-relative URL
              addressing another host).
            * Contains no ``://`` (which would indicate an
              absolute URL with a scheme).
            * Contains no ``@`` character (which would indicate a
              ``user:pass@host`` style credential / authority).

            :param candidate: Raw ``next`` value lifted from the
                              request query string (callers
                              should pass the percent-decoded
                              form -- webworks decodes
                              ``query_params`` for us).

            :returns: ``True`` when the candidate is safe to use
                      as a redirect target, ``False`` otherwise.
        """
        if candidate is None:
            return False
        if not isinstance(candidate, str):
            return False
        if len(candidate) == 0:
            return False
        if len(candidate) > MAX_NEXT_LENGTH:
            return False

        for ch in _CONTROL_CHARS:
            if ch in candidate:
                return False

        if "\\" in candidate:
            return False

        if candidate.startswith("/") is False:
            return False
        if candidate.startswith("//") is True:
            return False

        if "://" in candidate:
            return False
        if "@" in candidate:
            return False

        return True

    def resolve_safe_target(
            self,
            *,
            candidate: Optional[str],
            fallback: Optional[str] = None
        ) -> str:
        """
            Return either ``candidate`` (when it passes
            :meth:`is_safe_same_origin_target`) or the fallback
            target.

            :param candidate: Raw ``next`` value from the request.
            :param fallback: Optional per-call override of the
                             instance's default fallback target.

            :returns: The URL the caller should redirect to.
        """
        if fallback is None or len(fallback) == 0:
            resolved_fallback = self._fallback_target
        else:
            resolved_fallback = fallback

        if self.is_safe_same_origin_target(candidate=candidate) is True:
            rtnval = candidate
            return rtnval

        rtnval = resolved_fallback
        return rtnval


__all__ = [
    "MAX_NEXT_LENGTH",
    "NextValidator",
]
