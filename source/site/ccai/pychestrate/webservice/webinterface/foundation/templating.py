"""
.. module:: webinterface.foundation.templating
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Jinja2 templating helpers for the webworks-side
               consumer web UI.

.. moduleauthor:: Code Craft AI LLC

The blueprints under ``webinterface/blueprints/`` ship their
templates in per-blueprint ``templates/`` subdirectories. This
module supplies the render-call shape that lets webworks
handlers reuse those templates unchanged:

* :func:`build_jinja_environment` -- one-time builder that wires
  a ``ChoiceLoader`` over every per-blueprint ``templates/``
  directory plus an optional shared ``templates/`` root. Returns
  a :class:`jinja2.Environment` ready for handlers to consume.

* :func:`render_template_response` -- the one call a webworks
  handler makes to convert ``(template_name, context)`` into a
  :class:`HTMLResponse`.

* :func:`get_default_environment` -- module-level singleton
  pattern. The bootstrap calls
  :func:`set_default_environment` once at startup with the
  configured environment; handlers call
  ``render_template_response(...)`` without threading the env
  through.

Test seam: every public function accepts an optional
``environment`` kwarg so tests can pass a stub
:class:`jinja2.Environment` without touching the module-level
singleton.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import enum
import math
import os

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import jinja2

from ccai.webworks.routing.response import HTMLResponse


_default_environment: Optional[jinja2.Environment] = None


def build_jinja_environment(
        *,
        template_search_paths: List[str],
        autoescape: bool = True,
        cache_size: int = 400,
        strict_undefined: bool = False
    ) -> jinja2.Environment:
    """
        Construct a configured :class:`jinja2.Environment`.

        :param template_search_paths: Ordered list of filesystem
                                      directories jinja searches
                                      for templates. Earlier paths
                                      win on collision (per
                                      :class:`jinja2.ChoiceLoader`
                                      semantics).
        :param autoescape: When True, autoescape HTML / XML / SVG
                           extensions. The web UI is HTML so this
                           is the safe default.
        :param cache_size: Number of compiled templates to cache
                           in-process. Set to 0 to disable caching
                           (development convenience).
        :param strict_undefined: When True, install
                                 :class:`jinja2.StrictUndefined` so a
                                 template that reads a variable or
                                 attribute the handler never supplied
                                 raises :class:`jinja2.UndefinedError`
                                 instead of rendering an empty string.
                                 The render-smoke tests always enable
                                 this; production enables it through
                                 the ``PYCHESTRATE_TEMPLATE_STRICT_UNDEFINED``
                                 environment variable.

        :returns: Configured :class:`jinja2.Environment`.
        :raises: ValueError on an empty path list.
    """
    if template_search_paths is None or len(template_search_paths) == 0:
        raise ValueError(
            "build_jinja_environment requires at least one"
            " template search path"
        )

    loaders = []
    for path in template_search_paths:
        loaders.append(jinja2.FileSystemLoader(path))
    combined_loader = jinja2.ChoiceLoader(loaders)

    autoescape_callable = jinja2.select_autoescape(
        enabled_extensions=("html", "htm", "xml", "svg"),
    ) if autoescape is True else False

    if strict_undefined is True:
        undefined_class = jinja2.StrictUndefined
    else:
        undefined_class = jinja2.Undefined

    rtnval = jinja2.Environment(
        loader=combined_loader,
        autoescape=autoescape_callable,
        cache_size=cache_size,
        keep_trailing_newline=True,
        undefined=undefined_class,
    )
    return rtnval


def install_template_globals(*, environment: jinja2.Environment) -> None:
    """
        Install every global the consumer-UI templates rely on:
        ``url_for`` (route registry shim), ``static_url``
        (content-hashed static asset URLs), ``ui_profile`` and
        ``csp_nonce`` (the response's Content-Security-Policy script
        nonce). Production bootstrap and the test harnesses all call
        this one function so the set of globals can never drift
        between them.

        :param environment: Configured jinja2 environment.

        :returns: None.
    """
    from ccai.pychestrate.webservice.webinterface.foundation.url_for import (  # noqa: E402
        install_url_for_global,
    )
    from ccai.pychestrate.webservice.webinterface.foundation.static_files import (  # noqa: E402
        install_static_url_global,
    )
    from ccai.pychestrate.webservice.webinterface.site_shell.ui_profile import (  # noqa: E402
        install_ui_profile_global,
    )
    from ccai.pychestrate.webservice.hardening.security_headers import (  # noqa: E402
        install_csp_nonce_global,
    )
    install_url_for_global(environment=environment)
    install_static_url_global(environment=environment)
    install_ui_profile_global(environment=environment)
    # ``csp_nonce()`` -- inline <script> blocks must carry the
    # response's Content-Security-Policy nonce to run.
    install_csp_nonce_global(environment=environment)
    environment.filters["format_datetime"] = format_datetime_filter
    environment.filters["input_datetime"] = input_datetime_filter
    environment.filters["humanize_count"] = humanize_count_filter
    environment.filters["display"] = display_filter
    environment.filters["status_tone"] = status_tone_filter
    environment.filters["enum_value"] = enum_value_filter
    return


# ---------------------------------------------------------------------------
# Template filters shared by every fragment
# ---------------------------------------------------------------------------

DISPLAY_PLACEHOLDER: str = "\u2014"

# Status vocabulary -> badge tone. Every status the managers emit maps
# here so the same value renders the same colour on every page.
_STATUS_TONES: Dict[str, str] = {
    "succeeded": "success", "success": "success", "passed": "success",
    "completed": "success", "published": "success", "online": "success",
    "enabled": "success", "active": "success", "healthy": "success",
    "approved": "success", "available": "success",
    "failed": "danger", "failure": "danger", "error": "danger",
    "errored": "danger", "offline": "danger", "cancelled": "danger",
    "canceled": "danger", "timeout": "danger", "timed_out": "danger",
    "deprecated": "danger", "rejected": "danger", "revoked": "danger",
    "expired": "danger", "unhealthy": "danger",
    "running": "info", "in_progress": "info", "started": "info",
    "provisioning": "info", "checked_out": "info", "allocated": "info",
    "pending": "warning", "queued": "warning", "scheduled": "warning",
    "degraded": "warning", "draft": "warning", "maintenance": "warning",
    "waiting_approval": "warning", "reserved": "warning",
    "exclusive": "info", "shared": "secondary",
    "skipped": "secondary", "disabled": "secondary", "unknown": "secondary",
    "inactive": "secondary", "destroyed": "secondary", "released": "secondary",
}


def enum_value_filter(value: Any) -> Any:
    """
        Return ``value.value`` for an Enum member and ``value`` itself
        otherwise, so templates can render a field that is an Enum on
        one response type and a plain string on another.
    """
    if isinstance(value, enum.Enum):
        return value.value
    return value


def status_tone_filter(value: Any) -> str:
    """
        Map a status value (Enum or string) to a badge tone:
        ``success`` / ``danger`` / ``info`` / ``warning`` /
        ``secondary``.
    """
    raw = enum_value_filter(value)
    key = str(raw).strip().lower() if raw is not None else ""
    rtnval = _STATUS_TONES.get(key, "secondary")
    return rtnval


def display_filter(value: Any, placeholder: str = DISPLAY_PLACEHOLDER) -> Any:
    """
        Render ``None`` (and empty strings) as an em dash instead of
        the literal word ``None``.
    """
    if value is None:
        return placeholder
    if isinstance(value, str) and len(value.strip()) == 0:
        return placeholder
    return value


def format_datetime_filter(
        value: Any,
        fmt: str = "%Y-%m-%d %H:%M",
        placeholder: str = DISPLAY_PLACEHOLDER
    ) -> Any:
    """
        Render a datetime as a ``<time>`` element: the visible text in
        ``fmt`` with an explicit UTC marker, the machine-readable ISO
        value in ``datetime=``, and the full timestamp as the title.
        ``None`` renders the placeholder.
    """
    if value is None:
        return placeholder
    if isinstance(value, str):
        return value
    try:
        iso_value = value.isoformat()
        display_value = value.strftime(fmt)
    except Exception:
        return str(value)
    zone_label = "UTC"
    tzinfo = getattr(value, "tzinfo", None)
    if tzinfo is not None:
        try:
            name = value.tzname()
            if name:
                zone_label = name
        except Exception:
            pass
    rtnval = jinja2.Markup(
        '<time datetime="{}" title="{}">{} {}</time>'.format(
            jinja2.escape(iso_value),
            jinja2.escape(iso_value),
            jinja2.escape(display_value),
            jinja2.escape(zone_label),
        )
    ) if hasattr(jinja2, "Markup") else _markup_time(iso_value, display_value, zone_label)
    return rtnval


def input_datetime_filter(value: Any, zone_name: Optional[str] = "UTC") -> str:
    """
        Render a datetime as the ``value`` of an ``<input
        type="datetime-local">``: plain ``YYYY-MM-DDTHH:MM`` text in
        ``zone_name`` (an IANA zone; UTC when empty or unknown). A
        naive value is taken to be UTC. ``None`` and anything that is
        not a datetime render as an empty string, so the input shows
        blank instead of markup (``format_datetime`` returns a
        ``<time>`` element, which does not belong inside ``value=""``).

        :param value: The datetime to render.
        :param zone_name: IANA zone the input is filled in.

        :returns: The input value, or an empty string.
    """
    if not isinstance(value, datetime):
        return ""
    zone: Any = timezone.utc
    name = str(zone_name or "").strip()
    if len(name) > 0 and name != "UTC":
        try:
            zone = ZoneInfo(name)
        except (KeyError, ValueError, OSError):
            zone = timezone.utc
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)
    rtnval = value.astimezone(zone).strftime("%Y-%m-%dT%H:%M")
    return rtnval


_SUPERSCRIPT_DIGITS = str.maketrans("0123456789", "\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079")

_COUNT_SCALES = (
    (10 ** 12, "trillion"),
    (10 ** 9, "billion"),
    (10 ** 6, "million"),
)


def humanize_count_filter(value: Any) -> Any:
    """
        Render a count people can read at a glance: exact with
        thousands separators below a million (``65,534``), in words up
        to the trillions (``16.8 million``), and beyond that as the
        power of two it is within 1% of (``≈ 2⁶⁴`` for an IPv6 /64's
        18446744073709551615 addresses) or else in scientific notation
        (``≈ 1.4 × 10¹⁹``). Anything that is not an integer is returned
        as is.

        :param value: The count.

        :returns: The readable count.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return value
    magnitude = abs(value)
    if magnitude < 10 ** 6:
        rtnval = "{:,}".format(value)
        return rtnval
    sign = "-" if value < 0 else ""
    if magnitude < 10 ** 15:
        for scale, word in _COUNT_SCALES:
            if magnitude >= scale:
                rtnval = "{}{:.1f} {}".format(sign, magnitude / scale, word)
                return rtnval
    exponent = round(math.log2(magnitude))
    power = 1 << exponent
    if abs(magnitude - power) * 100 <= power:
        shown = "2" + str(exponent).translate(_SUPERSCRIPT_DIGITS)
    else:
        decimal_exponent = len(str(magnitude)) - 1
        shown = "{:.1f} \u00d7 10{}".format(
            magnitude / (10 ** decimal_exponent),
            str(decimal_exponent).translate(_SUPERSCRIPT_DIGITS),
        )
    rtnval = "\u2248 {}{}".format(sign, shown)
    return rtnval


def _markup_time(iso_value: str, display_value: str, zone_label: str) -> Any:
    from markupsafe import Markup, escape  # noqa: E402
    rtnval = Markup(
        '<time datetime="{}" title="{}">{} {}</time>'.format(
            escape(iso_value), escape(iso_value), escape(display_value), escape(zone_label)
        )
    )
    return rtnval


def set_default_environment(*, environment: jinja2.Environment) -> None:
    """
        Install the supplied environment as the module-level
        default. Subsequent calls to
        :func:`render_template_response` without an explicit
        ``environment=`` use this one.

        :param environment: Configured jinja2 environment.

        :returns: None.
    """
    global _default_environment
    _default_environment = environment
    return


def get_default_environment() -> jinja2.Environment:
    """
        Return the module-level default environment.

        :returns: Configured :class:`jinja2.Environment`.
        :raises: RuntimeError when no default environment has been
                 installed.
    """
    if _default_environment is None:
        raise RuntimeError(
            "No default jinja2 environment configured. Call"
            " set_default_environment(environment=...) once at"
            " startup, or pass environment= to"
            " render_template_response(...)."
        )
    rtnval = _default_environment
    return rtnval


def reset_default_environment_for_testing() -> None:
    """
        Clear the module-level default. Tests call this in
        cleanup so cross-test state never bleeds.

        :returns: None.
    """
    global _default_environment
    _default_environment = None
    return


def render_template_response(
        *,
        template_name: str,
        context: Optional[Dict[str, Any]] = None,
        status_code: int = 200,
        headers: Optional[Dict[str, str]] = None,
        environment: Optional[jinja2.Environment] = None
    ) -> HTMLResponse:
    """
        Render a template with the supplied context and return a
        webworks :class:`HTMLResponse`. Typical handler usage::

            return render_template_response(
                template_name="foo.html", context=ctx)

        :param template_name: Template path relative to the search
                              paths (e.g. ``config/users/list.html``).
        :param context: Dict of values made available inside the
                        template. ``None`` becomes an empty dict.
        :param status_code: HTTP status code (default 200).
        :param headers: Optional additional response headers. The
                        ``Content-Type`` header is set by
                        :class:`HTMLResponse`.
        :param environment: Optional environment override
                            (test seam). Defaults to the module-
                            level singleton.

        :returns: :class:`HTMLResponse` carrying the rendered HTML.
        :raises: jinja2.TemplateNotFound when the template is not
                 found by the loader chain. RuntimeError when no
                 environment is available (neither passed in nor
                 set as default).
    """
    if environment is None:
        env = get_default_environment()
    else:
        env = environment

    if context is None:
        render_context: Dict[str, Any] = {}
    else:
        render_context = context

    template = env.get_template(template_name)
    rendered_html = template.render(render_context)
    rtnval = HTMLResponse(
        content=rendered_html,
        status_code=status_code,
        headers=headers,
    )
    return rtnval


def render_template_to_string(
        *,
        template_name: str,
        context: Optional[Dict[str, Any]] = None,
        environment: Optional[jinja2.Environment] = None
    ) -> str:
    """
        Render a template with the supplied context and return the
        rendered HTML as a string (no HTTP response wrapping).

        Used by the site-shell integration in PR4 to render an
        admin page as a content fragment, which is then injected
        into the shell document via
        ``render_shell_document(content_html=...)``.

        :param template_name: Template path relative to the search
                              paths.
        :param context: Optional render context dict.
        :param environment: Optional environment override. Defaults
                            to the module-level singleton.

        :returns: Rendered HTML as a unicode string.
        :raises: jinja2.TemplateNotFound when the template is not
                 found. RuntimeError when no environment is
                 available.
    """
    if environment is None:
        env = get_default_environment()
    else:
        env = environment

    if context is None:
        render_context: Dict[str, Any] = {}
    else:
        render_context = context

    template = env.get_template(template_name)
    rtnval = template.render(render_context)
    return rtnval


def discover_blueprint_template_paths(
        *, blueprints_root: str
    ) -> List[str]:
    """
        Walk a blueprints root directory and return the ordered
        list of ``<blueprint>/templates`` subdirectories that
        exist on disk. Convention: each blueprint package owns its
        own ``templates/`` subfolder.

        :param blueprints_root: Filesystem path to the blueprints
                                root (e.g.
                                ``webinterface/blueprints``).

        :returns: List of template directory paths in alphabetical
                  blueprint order. Empty list when the root does
                  not exist.
    """
    rtnval: List[str] = []
    if blueprints_root is None or len(blueprints_root) == 0:
        return rtnval
    if os.path.isdir(blueprints_root) is False:
        return rtnval

    for entry in sorted(os.listdir(blueprints_root)):
        candidate = os.path.join(blueprints_root, entry, "templates")
        if os.path.isdir(candidate) is True:
            rtnval.append(candidate)
    return rtnval


__all__ = [
    "build_jinja_environment",
    "install_template_globals",
    "set_default_environment",
    "get_default_environment",
    "reset_default_environment_for_testing",
    "render_template_response",
    "discover_blueprint_template_paths",
]
