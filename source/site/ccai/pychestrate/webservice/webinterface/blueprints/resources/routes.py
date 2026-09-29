"""
.. module:: webinterface.blueprints.resources.routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /resources
               (E1 slice -- dashboard + resources core).

.. moduleauthor:: Code Craft AI LLC

The resources blueprint owns the consumer-facing ``/resources``
surface. This module lands the dashboard + the seven core
``/resources/*`` routes (list / create / detail / edit / delete
/ checkout):

* ``GET  /resources/`` and ``/resources/dashboard`` -- summary
                                                       statistics
                                                       page.
* ``GET  /resources/list``                          -- list +
                                                       filters
                                                       (pool /
                                                       type / health
                                                       / tags /
                                                       search).
* ``GET  /resources/create``                        -- create form.
* ``POST /resources/create``                        -- create.
* ``GET  /resources/{resource_id}``                 -- detail +
                                                       active
                                                       allocations.
* ``GET  /resources/{resource_id}/edit``            -- edit form.
* ``POST /resources/{resource_id}/edit``            -- update.
* ``POST /resources/{resource_id}/delete``          -- delete.
* ``POST /resources/{resource_id}/checkout``        -- check out a
                                                       resource for
                                                       a job.

Pre-registers the URL patterns for the sibling resource
endpoints (pools / ip_pools / allocations / reservations /
health / tags) so the dashboard sidebar's
``url_for('resources.pool_list')`` etc. resolve at template
render time.

Foundation pieces consumed
--------------------------

The auth resolver, session cookie management, CSRF guard,
flash queue, jinja2 environment, ``url_for`` shim, multi-form
parsing, default-context builder, and the
``_require_permission_or_redirect`` admin guard all come from
:mod:`webinterface.blueprints.config.routes`.

Auth backend
------------

Every authenticated handler routes through
:class:`SecurityManager`. The
``check_permission(user_id, 'resources.manage')`` gate guards
the create / edit / delete handlers via the
``_require_permission_or_redirect`` helper; checkout is
login-required only.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import logging
import re

from typing import Any, Callable, Dict, List, Optional

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import (
    HTMLResponse,
    RedirectResponse,
    Response,
)

from ccai.pychestrate.webservice.webinterface.foundation import (
    auth_guard,
    csrf,
    flash,
    form_errors,
    url_for as _url_for_module,
)
from ccai.pychestrate.webservice.webinterface.blueprints.config.routes import (
    MultiFormView,
    _attach_session_to_response,
    _build_default_template_context,
    _has_permission,
    _parse_form_multi,
    _parse_form_or_empty,
    _redirect_with_flash,
    _render,
    _require_permission_or_redirect,
    _resolve_authenticated_request,
    _wrap_fragment_handler_in_shell,
)


RESOURCES_PATH = "/resources"

# Largest ``per_page`` any resources list honours; larger requests are
# served this many rows per page instead of loading the whole table.
RESOURCES_MAX_PER_PAGE = 100

_DEFAULT_RESOURCES_PAGE_TITLE = "Pychestrate"

# Second path segment (/resources/<segment>) -> tab label. Deeper
# paths inherit their section's label.
_RESOURCES_SECTION_TITLE_LABELS: Dict[str, str] = {
    "pools": "Resource Pools",
    "ip-pools": "IP Pools",
    "allocations": "Allocations",
    "reservations": "Reservations",
    "health": "Resource Health",
    "tags": "Tags",
    "create": "New Resource",
}


def _resolve_resources_page_title(*, path: str) -> str:
    """
        Resolve the shell document ``<title>`` for a resources page
        from the request path (``/resources/ip-pools/7`` ->
        ``"IP Pools · Pychestrate"``).

        :param path: Request path.

        :returns: Title string.
    """
    if path is None or len(path) == 0:
        return _DEFAULT_RESOURCES_PAGE_TITLE
    segments = [segment for segment in path.split("/") if len(segment) > 0]
    if len(segments) == 0 or segments[0] != "resources":
        return _DEFAULT_RESOURCES_PAGE_TITLE
    label = "Resources"
    if len(segments) >= 2:
        label = _RESOURCES_SECTION_TITLE_LABELS.get(segments[1], "Resource")
    rtnval = "{} · {}".format(label, _DEFAULT_RESOURCES_PAGE_TITLE)
    return rtnval


def _wrap_resources_handler_in_shell(handler: Any) -> Any:
    """
        Render a resources-blueprint handler's HTML inside the site
        shell (UI remediation Phase 2, finding R-1). The resources
        pages used to ship as standalone documents with their own
        header and sidebar; ``resources/base.html`` is now a fragment
        like the admin and projects bases.

        :param handler: The original handler.

        :returns: Shell-wrapping handler.
    """
    rtnval = _wrap_fragment_handler_in_shell(
        handler, title_resolver=_resolve_resources_page_title
    )
    return rtnval
_LOGGER = logging.getLogger("pychestrate.ui.resources")


_ROUTE_TABLE = (
    ("resources.dashboard_root", "/", ("GET",)),
    ("resources.dashboard", "/dashboard", ("GET",)),
    ("resources.resource_list", "/list", ("GET",)),
    ("resources.resource_create", "/create", ("GET", "POST")),
    ("resources.resource_detail", "/{resource_id}", ("GET",)),
    (
        "resources.resource_edit",
        "/{resource_id}/edit",
        ("GET", "POST"),
    ),
    (
        "resources.resource_delete",
        "/{resource_id}/delete",
        ("POST",),
    ),
    (
        "resources.resource_checkout",
        "/{resource_id}/checkout",
        ("POST",),
    ),
)


# All previously-stubbed resources endpoints have shipped. The
# tuple stays in the source as a hook for any post-E4 additions.
_FUTURE_ENDPOINT_PATTERNS: tuple = ()


_ADMIN_PERMISSION = "system:resources.manage"


def _denial_message(*, action: str) -> str:
    """
        The sentence shown when someone without the resource-management
        permission reaches a handler that needs it, naming what they
        tried instead of a page they cannot open.

        :param action: What they tried, e.g. ``"delete a resource pool"``.

        :returns: The message.
    """
    rtnval = "You need the resource-management permission to {}.".format(action)
    return rtnval


def _resources_permission_flags(*, auth: Any) -> Dict[str, Any]:
    """
        Template flags for the resources pages: ``can_manage`` is the
        same probe the write handlers gate on, so templates can hide
        Create / Edit / Delete / Force-checkin controls from users the
        gate would bounce (audit findings R-4, R-12).
        ``current_user_id`` lets a template show owner-only controls
        (checkin, cancel reservation) on the rows the user owns.

        :param auth: Resolution from ``_resolve_authenticated_request``.

        :returns: Dict to merge into the render context.
    """
    rtnval = {
        "can_manage": _has_permission(auth=auth, permission=_ADMIN_PERMISSION),
        "current_user_id": getattr(auth, "user_id", ""),
    }
    return rtnval
# ---------------------------------------------------------------------------
# Lazy-import builder seams (test-patchable)
# ---------------------------------------------------------------------------


def _build_resource_manager(*, db_session: Any) -> Any:
    """
        Construct a :class:`ResourceManager`. Lazy-imports the
        class so tests can patch this builder without importing
        the source module.
    """
    from ccai.pychestrate.core.managers.resource_manager import (  # noqa: E402
        ResourceManager,
    )
    rtnval = ResourceManager(db_session)
    return rtnval


def _build_allocation_manager(*, db_session: Any) -> Any:
    """
        Construct an :class:`AllocationManager`. Lazy-imports.
    """
    from ccai.pychestrate.core.managers.allocation_manager import (  # noqa: E402
        AllocationManager,
    )
    rtnval = AllocationManager(db_session)
    return rtnval


def _build_ip_pool_manager(*, db_session: Any) -> Any:
    """
        Construct an :class:`IPPoolManager`. Lazy-imports.
    """
    from ccai.pychestrate.core.managers.ip_pool_manager import (  # noqa: E402
        IPPoolManager,
    )
    rtnval = IPPoolManager(db_session)
    return rtnval


def _resolve_resource_type(*, resource_type_str: str) -> Any:
    """
        Resolve a ``resource_type`` form value to the manager's
        :class:`ResourceType` enum value. Raises ValueError on
        unknown.
    """
    from ccai.pychestrate.core.orm import (  # noqa: E402
        ResourceType,
    )
    rtnval = ResourceType(resource_type_str)
    return rtnval


def _resolve_health_status_or_none(
        *, health_status_str: Optional[str]
    ) -> Optional[Any]:
    """
        Resolve a ``health_status`` form value to the manager's
        :class:`HealthStatus` enum value. Returns ``None`` on
        empty / unknown so handlers can branch without try/except.
    """
    if health_status_str is None or len(health_status_str) == 0:
        return None
    try:
        from ccai.pychestrate.core.orm import (  # noqa: E402
            HealthStatus,
        )
        rtnval = HealthStatus(health_status_str)
        return rtnval
    except (ValueError, ImportError):
        return None


def _resolve_allocation_mode(*, mode_str: str) -> Any:
    """
        Resolve an ``allocation mode`` form value to the
        :class:`AllocationMode` enum value. Raises ValueError on
        unknown.
    """
    from ccai.pychestrate.core.orm import (  # noqa: E402
        AllocationMode,
    )
    rtnval = AllocationMode(mode_str)
    return rtnval


def _build_resource_create_request(
        *,
        name: str,
        resource_type: Any,
        pool_id: Optional[int],
        description: str,
        metadata: Dict[str, Any],
        tags: List[str],
        capacity: int
    ) -> Any:
    """
        Construct a :class:`ResourceCreateRequest`. Lazy-imports.
    """
    from ccai.pychestrate.core.managers.resource_manager import (  # noqa: E402
        ResourceCreateRequest,
    )
    rtnval = ResourceCreateRequest(
        name=name,
        resource_type=resource_type,
        pool_id=pool_id,
        description=description,
        metadata=metadata,
        tags=tags,
        capacity=capacity,
    )
    return rtnval


def _build_resource_update_request(
        *,
        description: Optional[str],
        metadata: Optional[Dict[str, Any]],
        tags: Optional[List[str]],
        capacity: Optional[int],
        health_status: Optional[Any]
    ) -> Any:
    """
        Construct a :class:`ResourceUpdateRequest`. Lazy-imports.
    """
    from ccai.pychestrate.core.managers.resource_manager import (  # noqa: E402
        ResourceUpdateRequest,
    )
    rtnval = ResourceUpdateRequest(
        description=description,
        metadata=metadata,
        tags=tags,
        capacity=capacity,
        health_status=health_status,
    )
    return rtnval


def _build_checkout_request(
        *,
        resource_id: int,
        job_id: Optional[str],
        mode: Any,
        timeout_minutes: Optional[int],
        reason: str
    ) -> Any:
    """
        Construct a :class:`CheckoutRequest`. Lazy-imports.
    """
    from ccai.pychestrate.core.managers.allocation_manager import (  # noqa: E402
        CheckoutRequest,
    )
    rtnval = CheckoutRequest(
        resource_id=resource_id,
        job_id=job_id,
        mode=mode,
        timeout_minutes=timeout_minutes,
        reason=reason,
    )
    return rtnval


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


def _coerce_int(*, raw: Any) -> Optional[int]:
    if raw is None:
        return None
    try:
        rtnval = int(raw)
    except (TypeError, ValueError):
        return None
    return rtnval


def _coerce_int_with_default(*, raw: Any, default: int) -> int:
    parsed = _coerce_int(raw=raw)
    if parsed is None:
        return default
    return parsed


def _parse_pagination_params(
        *, request: Request,
        default_per_page: int = 20
    ) -> Dict[str, Any]:
    page = _coerce_int_with_default(
        raw=request.query_params.get("page", None), default=1
    )
    if page < 1:
        page = 1

    per_page = _coerce_int_with_default(
        raw=request.query_params.get("per_page", None),
        default=default_per_page,
    )
    if per_page < 1:
        per_page = default_per_page
    if per_page > RESOURCES_MAX_PER_PAGE:
        per_page = RESOURCES_MAX_PER_PAGE

    rtnval = {"page": page, "per_page": per_page}
    return rtnval


def _parse_metadata_json_or_default(
        *, raw: str, default: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
    """
        Parse a JSON object string from the metadata textarea.
        Returns ``default`` when ``raw`` is empty. Raises
        ``ValueError`` (caught + flashed by the caller) on a
        decode failure -- mirrors the legacy handler's
        ``json.JSONDecodeError`` -> flash branch.

        :param raw: Form-submitted metadata string.
        :param default: Fallback (None) on empty input.

        :returns: Parsed dict on valid JSON; ``default`` on empty.
        :raises: ValueError when the input is non-empty but not
                 valid JSON.
    """
    if raw is None or len(raw) == 0:
        return default
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid JSON in metadata field.") from exc
    if not isinstance(parsed, dict):
        raise ValueError(
            "Metadata must be a JSON object, not a {}".format(
                type(parsed).__name__
            )
        )
    return parsed


def _calculate_total_pages(*, total: int, per_page: int) -> int:
    """
        Compute the real page count from a manager's total row
        count. Always at least 1 so templates can render a page
        indicator unconditionally.

        :param total: Total matching rows reported by the manager.
        :param per_page: Page size.

        :returns: Number of pages (>= 1).
    """
    if total <= 0:
        return 1
    rtnval = (total + per_page - 1) // per_page
    return rtnval


def _build_page_window(
        *, page: int, total_pages: int, width: int = 2
    ) -> List[int]:
    """
        Build the run of page numbers to render around the
        current page (first/last/prev/next are rendered
        separately by the pagination template block).

        :param page: Current page (1-based).
        :param total_pages: Real page count.
        :param width: Pages shown on each side of the current page.

        :returns: Contiguous list of page numbers.
    """
    start = page - width
    if start < 1:
        start = 1
    end = page + width
    if end > total_pages:
        end = total_pages
    rtnval = list(range(start, end + 1))
    return rtnval


def _describe_resource_manager_error(*, exc: Exception) -> Optional[str]:
    """
        Map a typed ResourceManager error to its deliberate,
        user-facing message. Returns None when ``exc`` is not one
        of the typed errors -- callers then log the exception and
        flash a generic sentence instead of the raw exception
        text. Lazy-imports so this module stays importable when
        the manager package is absent (test runtimes patch the
        manager builders).

        :param exc: The exception raised by a ResourceManager call.

        :returns: Specific user-facing message, or None.
    """
    try:
        from ccai.pychestrate.core.managers.resource_manager import (  # noqa: E402
            DuplicateResourceError,
            PoolHasResourcesError,
            PoolNotFoundError,
            ResourceHasAllocationsError,
            ResourceNotFoundError,
            ResourceValidationError,
            TagNotFoundError,
        )
    except ImportError:
        return None

    typed_errors = (
        DuplicateResourceError,
        PoolHasResourcesError,
        PoolNotFoundError,
        ResourceHasAllocationsError,
        ResourceNotFoundError,
        ResourceValidationError,
        TagNotFoundError,
    )
    if not isinstance(exc, typed_errors):
        return None

    # The manager's text (ids, codes) is for the log; the person
    # gets the copy below.
    _log_refusal(exc=exc)
    if isinstance(exc, ResourceHasAllocationsError):
        rtnval = (
            "This resource is checked out. Check it in, or force a"
            " check-in, before deleting it."
        )
        return rtnval
    if isinstance(exc, PoolHasResourcesError):
        rtnval = "{}. Move or delete them first.".format(exc.message)
        return rtnval
    copy = _RESOURCE_ERROR_COPY.get(getattr(exc, "error_code", ""), None)
    if copy is not None:
        return copy
    # Validation and duplicate-name messages are written for people.
    rtnval = _as_sentence(text=exc.message)
    return rtnval


#: Visible labels of the resource form fields, for the error summary.
RESOURCE_FIELD_LABELS: Dict[str, str] = {
    "name": "Resource Name",
    "resource_type": "Resource Type",
    "pool_id": "Resource Pool",
    "description": "Description",
    "capacity": "Capacity",
    "tags": "Tags",
    "new_tags": "New tags",
    "metadata": "Metadata (JSON)",
}


def _split_new_tags(*, raw: Any) -> List[str]:
    """
        The tag names typed into the "New tags" input: separated by
        commas or spaces, without repeats, in the order typed.

        :param raw: What was typed (or ``None``).

        :returns: The names, not yet validated.
    """
    rtnval: List[str] = []
    for piece in re.split(r"[\s,]+", str(raw or "")):
        name = piece.strip()
        if len(name) > 0 and name not in rtnval:
            rtnval.append(name)
    return rtnval


def _checked_new_tags(*, raw: Any) -> List[str]:
    """
        The names typed into the "New tags" input, refused when one is
        not a valid tag name.

        :param raw: What was typed.

        :returns: The valid names.
        :raises ValueError: Naming the first invalid one; the caller
                            shows it beside the input.
    """
    from ccai.pychestrate.core.managers.resource_manager import validate_tag_name  # noqa: E402

    names = _split_new_tags(raw=raw)
    for name in names:
        if validate_tag_name(name) is not True:
            raise ValueError(
                "'{}' is not a valid tag name. Use letters, digits, '_' and '-', starting with a"
                " letter or digit, at most 64 characters.".format(name)
            )
    return names


def _merged_tags(*, ticked: List[str], typed: List[str]) -> List[str]:
    """
        The ticked tags followed by the newly typed ones, without repeats.
    """
    rtnval = list(ticked)
    for name in typed:
        if name not in rtnval:
            rtnval.append(name)
    return rtnval


def _resource_field_errors(
        *, exc: BaseException, default_field: Optional[str] = None
    ) -> Dict[str, str]:
    """
        The ``{field: message}`` for a refused resource form, or an
        empty dict when the error is about no single input.

        A typed manager validation or duplicate error names its field
        (``exc.field``); its message is the one people are shown, not
        the manager's log text. A ``ValueError`` from parsing the typed
        text is about the input being parsed (``default_field``).

        :param exc: The error the manager or the parser raised.
        :param default_field: The field a ``ValueError`` is about.

        :returns: One entry, or an empty dict.
    """
    rtnval: Dict[str, str] = {}
    named = getattr(exc, "field", None)
    if isinstance(exc, ValueError) is True and default_field is not None:
        rtnval = {default_field: str(exc)}
    elif isinstance(named, str) is True and len(named) > 0:
        message = _describe_resource_manager_error(exc=exc)
        if message is not None:
            rtnval = {named: message}
    return rtnval


# User-facing copy for typed manager errors, by error code. The
# managers' own messages name ids, fields and statuses for the logs;
# these are what a person sees. A code not listed keeps the manager's
# message, which for the remaining codes is already written for
# people.
_RESOURCE_ERROR_COPY: Dict[str, str] = {
    "RESOURCE_NOT_FOUND": "That resource no longer exists.",
    "POOL_NOT_FOUND": "That pool no longer exists.",
    "TAG_NOT_FOUND": "That tag no longer exists.",
}

_ALLOCATION_ERROR_COPY: Dict[str, str] = {
    "TIMES_REQUIRED": "Enter both a start time and an end time.",
    "END_NOT_AFTER_START": "The end time must be after the start time.",
    "START_IN_PAST": "The start time has already passed. Choose a start time in the future.",
    "RESOURCE_NOT_FOUND": "That resource no longer exists.",
    "ALLOCATION_NOT_FOUND": "That allocation no longer exists.",
    "ALLOCATION_NOT_ACTIVE": "This allocation has already been checked in.",
    "NOT_ALLOCATION_OWNER": (
        "Only the person who checked this resource out can check it in."
        " An administrator can force a check-in from the allocation's page."
    ),
    "NOT_RESERVATION_OWNER": "Only the person who made this reservation can change or cancel it.",
    "RESERVATION_NOT_FOUND": "That reservation no longer exists.",
    "RESERVATION_NOT_CANCELLABLE": (
        "This reservation can no longer be cancelled: it has already"
        " started, finished or been cancelled."
    ),
    "RESERVATION_NOT_MODIFIABLE": (
        "Only upcoming reservations can be changed; this one has already"
        " started, finished or been cancelled."
    ),
}


def _log_refusal(*, exc: Exception) -> None:
    """
        Keep the manager's own wording of a refused request in the
        log, since the person sees friendlier copy instead.

        :param exc: The typed manager error.

        :returns: None.
    """
    _LOGGER.info(
        "Resources request refused [%s]: %s",
        getattr(exc, "error_code", type(exc).__name__),
        getattr(exc, "message", str(exc)),
    )
    return


def _as_sentence(*, text: str) -> str:
    """
        End a message passed through from a manager with a full stop,
        like every other flash on the resources pages.

        :param text: The message.

        :returns: The message ending in punctuation.
    """
    stripped = str(text).rstrip()
    if len(stripped) == 0 or stripped[-1] in ".!?":
        return stripped
    rtnval = stripped + "."
    return rtnval


def _format_utc(*, value: Any) -> str:
    """
        ``YYYY-MM-DD HH:MM UTC`` for a datetime in a message (the
        stored times are UTC; a naive one is taken to be UTC).

        :param value: The datetime.

        :returns: The formatted text.
    """
    from ccai.pychestrate.core.defaults import ensure_utc  # noqa: E402
    rtnval = "{} UTC".format(ensure_utc(value).strftime("%Y-%m-%d %H:%M"))
    return rtnval


_REMOVED_RECORD_LABELS = (
    ("reservations", "reservation", "reservations"),
    ("allocations", "allocation record", "allocation records"),
    ("health_check_configs", "health check setting", "health check settings"),
    ("health_transitions", "health status change", "health status changes"),
    ("metadata_history", "metadata change", "metadata changes"),
)


def _describe_resource_removal(*, removed: Any) -> str:
    """
        The success message for a resource deletion, naming the
        records removed with it ("Resource deleted, along with 3
        allocation records and 1 reservation.").

        :param removed: The counts ``delete_resource`` returned.

        :returns: User-facing message.
    """
    parts: List[str] = []
    if isinstance(removed, dict):
        for key, singular, plural in _REMOVED_RECORD_LABELS:
            count = removed.get(key, 0)
            if isinstance(count, int) and count > 0:
                parts.append("{} {}".format(count, singular if count == 1 else plural))
    if len(parts) == 0:
        return "Resource deleted successfully."
    if len(parts) == 1:
        listed = parts[0]
    else:
        listed = "{} and {}".format(", ".join(parts[:-1]), parts[-1])
    rtnval = "Resource deleted, along with {}.".format(listed)
    return rtnval


def _describe_allocation_error(*, exc: Exception) -> Optional[str]:
    """
        Map a typed AllocationManager error to a specific,
        user-facing message. ``ResourceUnavailableError`` includes
        who currently holds the resource and until when (from the
        ``current_allocation`` payload); capacity / conflict /
        lock errors get actionable guidance. Returns None when
        ``exc`` is not a typed allocation error.

        :param exc: The exception raised by an AllocationManager
                    call.

        :returns: Specific user-facing message, or None.
    """
    try:
        from ccai.pychestrate.core.managers.allocation_manager import (  # noqa: E402
            AllocationError,
            CapacityExceededError,
            ConcurrentModificationError,
            LockTimeoutError,
            ReservationConflictError,
            ResourceOfflineError,
            ResourceUnavailableError,
        )
    except ImportError:
        return None

    if not isinstance(exc, AllocationError):
        return None

    # The manager's text (ids, field names, statuses) is for the log;
    # the person gets the copy below.
    _log_refusal(exc=exc)

    if isinstance(exc, ResourceUnavailableError):
        msg_parts = ["{}.".format(exc.message)]
        current = exc.current_allocation
        if current is not None:
            if current.username is not None:
                holder = current.username
            else:
                holder = "another user"
            msg_parts.append(
                "Held by {} (allocation #{}).".format(holder, current.id)
            )
            if current.expected_checkin is not None:
                msg_parts.append(
                    "Expected check-in: {}.".format(
                        _format_utc(value=current.expected_checkin)
                    )
                )
            else:
                msg_parts.append("No expected check-in time is set.")
        rtnval = " ".join(msg_parts)
        return rtnval

    if isinstance(exc, CapacityExceededError):
        if exc.capacity is not None and exc.current_allocations is not None:
            rtnval = (
                "All {} allocation slots of this resource are in use ({}"
                " checked out). Check one in to free a slot.".format(
                    exc.capacity, exc.current_allocations
                )
            )
        else:
            rtnval = (
                "This resource is at capacity. Check an allocation in to"
                " free a slot."
            )
        return rtnval

    if isinstance(exc, ReservationConflictError) and getattr(exc, "error_code", "") == "RESERVED_FOR_OTHERS":
        first = exc.conflicting_reservations[0] if len(exc.conflicting_reservations) > 0 else None
        if first is None:
            return "Someone else has reserved this resource for part of that time."
        holder = getattr(first, "username", None) or "Someone else"
        rtnval = (
            "{} has reserved this from {} to {}. Check it out with a timeout"
            " that ends before then, or reserve a time of your own.".format(
                holder, _format_utc(value=first.start_time), _format_utc(value=first.end_time),
            )
        )
        return rtnval

    if isinstance(exc, ReservationConflictError):
        held = []
        for conflict in exc.conflicting_reservations[:3]:
            held.append(
                "reservation #{} from {} to {}".format(
                    conflict.id,
                    _format_utc(value=conflict.start_time),
                    _format_utc(value=conflict.end_time),
                )
            )
        if len(held) == 0:
            rtnval = "The resource is already reserved for part of that time."
        else:
            rtnval = (
                "The resource is already reserved for part of that time:"
                " {}.".format("; ".join(held))
            )
        return rtnval

    if isinstance(exc, ResourceOfflineError):
        status = getattr(exc, "health_status", None)
        described = "in maintenance" if status == "maintenance" else (status or "unavailable")
        rtnval = (
            "This resource is {} and cannot be checked out until it is"
            " back online.".format(described)
        )
        return rtnval

    if isinstance(exc, LockTimeoutError):
        rtnval = (
            "Another request is changing this resource right now. Please"
            " try again."
        )
        return rtnval

    if isinstance(exc, ConcurrentModificationError):
        rtnval = (
            "Someone else changed this at the same time. Refresh the page"
            " and try again."
        )
        return rtnval

    copy = _ALLOCATION_ERROR_COPY.get(getattr(exc, "error_code", ""), None)
    if copy is not None:
        return copy
    # Remaining typed errors (no matching resource, permission) carry
    # messages written for people.
    rtnval = _as_sentence(text=exc.message)
    return rtnval


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_dashboard(request: Request) -> Response:
    """
        ``GET /resources/`` and ``/resources/dashboard`` --
        summary statistics page.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        resource_manager = _build_resource_manager(db_session=db_session)
        allocation_manager = _build_allocation_manager(
            db_session=db_session
        )
        ip_pool_manager = _build_ip_pool_manager(db_session=db_session)

        # The summary cards use the managers' real totals -- the
        # ``*ListResponse`` dataclasses carry a ``total`` computed
        # by a count query, and the health cards come from a
        # dedicated aggregate query -- so the dashboard never
        # undercounts past a fetch limit.
        resource_count = resource_manager.list_resources(limit=1).total
        pool_count = resource_manager.list_pools(
            auth.user_id, limit=1
        ).total
        ip_pool_count = ip_pool_manager.list_pools(
            auth.user_id, limit=1
        ).total
        active_allocation_count = allocation_manager.list_allocations(
            status="active", limit=1
        ).total

        health_counts = resource_manager.count_resources_by_health_status()

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="resources.dashboard",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context.update(_resources_permission_flags(auth=auth))
        context["resource_count"] = resource_count
        context["pool_count"] = pool_count
        context["ip_pool_count"] = ip_pool_count
        context["active_allocation_count"] = active_allocation_count
        context["health_counts"] = health_counts

        response = _render(
            template_name="resources/dashboard.html",
            context=context,
        )
        _attach_session_to_response(
            response=response, session=auth.session
        )
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_resource_list(request: Request) -> Response:
    """
        ``GET /resources/list`` -- paginated list with optional
        ``?pool_id=`` / ``?resource_type=`` / ``?health_status=``
        / ``?search=`` / ``?tags=t1&tags=t2`` filters.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        params = _parse_pagination_params(request=request)
        offset = (params["page"] - 1) * params["per_page"]

        pool_id = _coerce_int(
            raw=request.query_params.get("pool_id", None)
        )
        resource_type_str = (
            request.query_params.get("resource_type", None) or None
        )
        health_status_str = (
            request.query_params.get("health_status", None) or None
        )
        search = request.query_params.get("search", "") or ""
        availability = request.query_params.get("availability", "") or ""
        if availability not in ("available", "in_use"):
            availability = ""
        # The list filter expects multi-valued ``tags`` -- the
        # query string can carry repeated ``?tags=…`` pairs.
        tag_query = []
        try:
            tag_query = list(request.query_params.getlist("tags"))
        except Exception:
            tag_query = []

        filter_kwargs: Dict[str, Any] = {
            "offset": offset,
            "limit": params["per_page"],
        }
        if pool_id is not None:
            filter_kwargs["pool_id"] = pool_id
        if resource_type_str is not None:
            try:
                filter_kwargs["resource_type"] = _resolve_resource_type(
                    resource_type_str=resource_type_str
                )
            except (ValueError, ImportError):
                pass
        if health_status_str is not None:
            resolved_status = _resolve_health_status_or_none(
                health_status_str=health_status_str
            )
            if resolved_status is not None:
                filter_kwargs["health_status"] = resolved_status
        if len(tag_query) > 0:
            filter_kwargs["tags"] = tag_query
        if len(search) > 0:
            filter_kwargs["search"] = search
        if len(availability) > 0:
            filter_kwargs["availability"] = availability

        resource_manager = _build_resource_manager(db_session=db_session)
        resources_response = resource_manager.list_resources(
            **filter_kwargs
        )
        resources = resources_response.resources
        holders = resource_manager.get_current_holders([item.id for item in resources])
        pools = resource_manager.list_pools(auth.user_id).pools
        all_tags = resource_manager.list_tags().tags

        total_pages = _calculate_total_pages(
            total=resources_response.total,
            per_page=params["per_page"],
        )
        page_window = _build_page_window(
            page=params["page"], total_pages=total_pages
        )

        filters_active = (
            pool_id is not None
            or resource_type_str is not None
            or health_status_str is not None
            or len(tag_query) > 0
            or len(search) > 0
            or len(availability) > 0
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="resources.resource_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context.update(_resources_permission_flags(auth=auth))
        context["resources"] = resources
        context["resource_total"] = resources_response.total
        context["pools"] = pools
        context["all_tags"] = all_tags
        context["page"] = params["page"]
        context["per_page"] = params["per_page"]
        context["total_pages"] = total_pages
        context["page_window"] = page_window
        context["filters_active"] = filters_active
        context["selected_pool_id"] = pool_id
        context["selected_resource_type"] = resource_type_str
        context["selected_health_status"] = health_status_str
        context["selected_tags"] = tag_query
        context["search"] = search
        context["selected_availability"] = availability
        context["holders"] = holders

        response = _render(
            template_name="resources/resources/list.html",
            context=context,
        )
        _attach_session_to_response(
            response=response, session=auth.session
        )
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def _render_resource_create_form(
        *,
        auth: Any,
        resource_manager: Any,
        form_data: Optional[MultiFormView],
        status_code: int = 200,
        errors: Optional[Dict[str, str]] = None
    ) -> HTMLResponse:
    """
        Helper to render the create-form template for both GET
        and the POST-error re-render path. Pulls the pool /
        all_tags lists out of the manager and merges them with
        the default context.
    """
    pools = resource_manager.list_pools(auth.user_id).pools
    all_tags = resource_manager.list_tags().tags

    flashes = flash.consume_flashes(session=auth.session)
    context = _build_default_template_context(
        session=auth.session,
        request_endpoint="resources.resource_create",
        flashes=flashes,
        csrf_token=auth.csrf_token,
    )
    context.update(_resources_permission_flags(auth=auth))
    context["pools"] = pools
    context["all_tags"] = all_tags
    context["form_data"] = form_data
    context["errors"] = errors if errors is not None else {}
    context["error_labels"] = RESOURCE_FIELD_LABELS
    response = _render(
        template_name="resources/resources/create.html",
        context=context,
        status_code=status_code,
    )
    _attach_session_to_response(
        response=response, session=auth.session
    )
    return response


def handle_resource_create(request: Request) -> Response:
    """
        ``GET /resources/create`` / ``POST /resources/create``.
        Admin-gated; checkout is on the detail page.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        deny_response = _require_permission_or_redirect(
            auth=auth,
            permission=_ADMIN_PERMISSION,
            deny_message=_denial_message(action="add a device or resource"),
            deny_redirect_url=_url_for_module.url_for(
                "resources.dashboard"
            ),
        )
        if deny_response is not None:
            return deny_response

        method = request.method.upper()
        resource_manager = _build_resource_manager(db_session=db_session)

        if method == "GET":
            # "Add Resource" from a pool page links here with
            # ?pool_id=; pre-select that pool in the form.
            preselect: Optional[MultiFormView] = None
            requested_pool_id = request.query_params.get("pool_id", None)
            if requested_pool_id is not None and len(str(requested_pool_id)) > 0:
                preselect = MultiFormView(data={
                    "pool_id": [str(requested_pool_id)],
                    "resource_type": ["generic"],
                })
            response = _render_resource_create_form(
                auth=auth,
                resource_manager=resource_manager,
                form_data=preselect,
            )
            return response

        # POST
        single_form = _parse_form_or_empty(request=request)
        multi_form = _parse_form_multi(request=request)
        form_view = MultiFormView(data=multi_form)

        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for(
                "resources.resource_create"
            ),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        name = str(single_form.get("name", "")).strip()
        resource_type_str = str(
            single_form.get("resource_type", "generic")
        )
        pool_id = _coerce_int(raw=single_form.get("pool_id", None))
        description = str(single_form.get("description", "")).strip()
        capacity = _coerce_int_with_default(
            raw=single_form.get("capacity", None), default=1
        )
        tags = list(multi_form.get("tags", []))
        metadata_str = str(single_form.get("metadata", "")).strip()
        errors: Dict[str, str] = {}
        parsing_field = "new_tags"

        try:
            tags = _merged_tags(ticked=tags, typed=_checked_new_tags(raw=single_form.get("new_tags", "")))
            parsing_field = "metadata"
            metadata = _parse_metadata_json_or_default(
                raw=metadata_str, default={}
            )
            if metadata is None:
                metadata = {}
            parsing_field = "resource_type"
            resource_type = _resolve_resource_type(
                resource_type_str=resource_type_str
            )
            parsing_field = "name"
            create_request = _build_resource_create_request(
                name=name,
                resource_type=resource_type,
                pool_id=pool_id,
                description=description,
                metadata=metadata,
                tags=tags,
                capacity=capacity,
            )
            created = resource_manager.create_resource(
                create_request, auth.user_id
            )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.resource_detail",
                    resource_id=created.id,
                ),
                message='Resource "{}" created successfully.'.format(
                    name
                ),
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            errors = _resource_field_errors(exc=exc, default_field=parsing_field)
            if len(errors) == 0:
                message = _describe_resource_manager_error(exc=exc)
                if message is None and isinstance(exc, ValueError) is True:
                    message = str(exc)
                if message is None:
                    _LOGGER.exception("Unexpected error creating resource")
                    message = (
                        "An unexpected error occurred while creating the"
                        " resource. The problem has been logged."
                    )
                flash.add_flash(
                    session=auth.session,
                    message=message,
                    category=flash.CATEGORY_ERROR,
                )

        # Re-render the form with the submitted values.
        response = _render_resource_create_form(
            auth=auth,
            resource_manager=resource_manager,
            form_data=form_view,
            status_code=400,
            errors=errors,
        )
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_resource_detail(request: Request) -> Response:
    """
        ``GET /resources/{resource_id}`` -- detail page including
        the active allocation list for the resource.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        resource_id = _coerce_int(
            raw=request.path_params.get("resource_id", None)
        )
        if resource_id is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("resources.resource_list"),
                message="Resource not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        resource_manager = _build_resource_manager(db_session=db_session)
        resource = resource_manager.get_resource(resource_id)
        if resource is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("resources.resource_list"),
                message="Resource not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        allocation_manager = _build_allocation_manager(
            db_session=db_session
        )
        active_allocations = allocation_manager.get_active_allocations(
            resource_id
        )
        upcoming_reservations = allocation_manager.list_reservations(
            resource_id=resource_id, status="pending", limit=20
        ).reservations

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="resources.resource_detail",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context.update(_resources_permission_flags(auth=auth))
        context["resource"] = resource
        context["active_allocations"] = active_allocations
        context["upcoming_reservations"] = upcoming_reservations
        # The first reservation of someone else: a check-out that runs into
        # it is refused, so the checkout card says so up front.
        context["next_reservation_by_other"] = next(
            (
                item for item in upcoming_reservations
                if str(getattr(item, "user_id", "")) != str(auth.user_id)
            ),
            None,
        )
        response = _render(
            template_name="resources/resources/detail.html",
            context=context,
        )
        _attach_session_to_response(
            response=response, session=auth.session
        )
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_resource_edit(request: Request) -> Response:
    """
        ``GET /resources/{resource_id}/edit`` /
        ``POST /resources/{resource_id}/edit``. Admin-gated.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        deny_response = _require_permission_or_redirect(
            auth=auth,
            permission=_ADMIN_PERMISSION,
            deny_message=_denial_message(action="edit a device or resource"),
            deny_redirect_url=_url_for_module.url_for(
                "resources.dashboard"
            ),
        )
        if deny_response is not None:
            return deny_response

        resource_id = _coerce_int(
            raw=request.path_params.get("resource_id", None)
        )
        if resource_id is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("resources.resource_list"),
                message="Resource not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        resource_manager = _build_resource_manager(db_session=db_session)
        resource = resource_manager.get_resource(resource_id)
        if resource is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("resources.resource_list"),
                message="Resource not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        method = request.method.upper()
        form_view: Optional[MultiFormView] = None
        errors: Dict[str, str] = {}
        status_code = 200

        if method == "POST":
            status_code = 400
            single_form = _parse_form_or_empty(request=request)
            multi_form = _parse_form_multi(request=request)
            form_view = MultiFormView(data=multi_form)

            csrf_redirect = auth_guard.enforce_csrf_or_redirect(
                form=single_form,
                session=auth.session,
                fallback_url=_url_for_module.url_for(
                    "resources.resource_edit",
                    resource_id=resource_id,
                ),
            )
            if csrf_redirect is not None:
                _attach_session_to_response(
                    response=csrf_redirect, session=auth.session
                )
                return csrf_redirect

            # A field the form submitted is an explicit value even when
            # it is empty: clearing the description, unticking every
            # tag or emptying the metadata saves exactly that. Only a
            # field the form did not send at all means "no change".
            description: Optional[str] = None
            if "description" in multi_form:
                description = str(
                    single_form.get("description", "")
                ).strip()
            capacity_raw: Optional[str] = None
            if "capacity" in multi_form:
                capacity_raw = str(
                    single_form.get("capacity", "")
                ).strip()
            # Unticked checkboxes are not submitted, so the form sends a
            # ``tags_present`` marker whenever it shows the tag list; with
            # the marker and no ``tags`` the resource ends up untagged.
            tags: Optional[List[str]] = None
            if "tags_present" in multi_form or "tags" in multi_form:
                tags = list(multi_form.get("tags", []))
            typed_tags = str(single_form.get("new_tags", "") or "")
            metadata_str: Optional[str] = None
            if "metadata" in multi_form:
                metadata_str = str(single_form.get("metadata", "")).strip()

            parsing_field = "new_tags"
            try:
                if tags is not None:
                    tags = _merged_tags(ticked=tags, typed=_checked_new_tags(raw=typed_tags))
                # Moving the resource to another pool is applied first: a
                # name that already exists in that pool stops the save
                # with the error beside the pool select.
                if "pool_id" in multi_form:
                    parsing_field = "pool_id"
                    chosen_pool = _coerce_int(raw=single_form.get("pool_id", None))
                    if chosen_pool is not None and chosen_pool != getattr(resource, "pool_id", None):
                        try:
                            resource_manager.assign_resource_to_pool(
                                resource_id, chosen_pool, auth.user_id
                            )
                        except Exception as move_exc:
                            if getattr(move_exc, "error_code", "") == "RESOURCE_NAME_EXISTS":
                                raise ValueError(
                                    "A resource with this name is already in that pool."
                                ) from None
                            raise
                parsing_field = "capacity"
                capacity: Optional[int] = None
                if capacity_raw is not None:
                    capacity = _coerce_int(raw=capacity_raw)
                    if capacity is None or capacity < 1:
                        raise ValueError(
                            "Capacity must be a whole number of at least 1."
                        )
                metadata: Optional[Dict[str, Any]] = None
                parsing_field = "metadata"
                if metadata_str is not None:
                    metadata = _parse_metadata_json_or_default(
                        raw=metadata_str, default={}
                    )
                parsing_field = "description"
                # Health status is deliberately NOT editable here:
                # status changes must go through the health page,
                # which records a reason in the audit trail.
                update_request = _build_resource_update_request(
                    description=description,
                    metadata=metadata,
                    tags=tags,
                    capacity=capacity,
                    health_status=None,
                )
                resource_manager.update_resource(
                    resource_id, update_request, auth.user_id
                )
                response = _redirect_with_flash(
                    session=auth.session,
                    url=_url_for_module.url_for(
                        "resources.resource_detail",
                        resource_id=resource_id,
                    ),
                    message="Resource updated successfully.",
                    category=flash.CATEGORY_SUCCESS,
                )
                return response
            except Exception as exc:
                errors = _resource_field_errors(exc=exc, default_field=parsing_field)
                if len(errors) == 0:
                    message = _describe_resource_manager_error(exc=exc)
                    if message is None and isinstance(exc, ValueError) is True:
                        message = str(exc)
                    if message is None:
                        _LOGGER.exception(
                            "Unexpected error updating resource %s",
                            resource_id,
                        )
                        message = (
                            "An unexpected error occurred while updating"
                            " the resource. The problem has been logged."
                        )
                    flash.add_flash(
                        session=auth.session,
                        message=message,
                        category=flash.CATEGORY_ERROR,
                    )

        # GET, or POST that fell through. Re-render the edit form
        # -- with the submitted values (``form_data``) when a POST
        # failed, so typed input is never reverted to the DB state.
        pools = resource_manager.list_pools(auth.user_id).pools
        all_tags = resource_manager.list_tags().tags

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="resources.resource_edit",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context.update(_resources_permission_flags(auth=auth))
        context["resource"] = resource
        context["pools"] = pools
        context["all_tags"] = all_tags
        context["form_data"] = form_view
        context["errors"] = errors
        context["error_labels"] = RESOURCE_FIELD_LABELS
        response = _render(
            template_name="resources/resources/edit.html",
            context=context,
            status_code=status_code,
        )
        _attach_session_to_response(
            response=response, session=auth.session
        )
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_resource_delete(request: Request) -> Response:
    """
        ``POST /resources/{resource_id}/delete``. Admin-gated.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        deny_response = _require_permission_or_redirect(
            auth=auth,
            permission=_ADMIN_PERMISSION,
            deny_message=_denial_message(action="delete a device or resource"),
            deny_redirect_url=_url_for_module.url_for(
                "resources.dashboard"
            ),
        )
        if deny_response is not None:
            return deny_response

        resource_id = _coerce_int(
            raw=request.path_params.get("resource_id", None)
        )
        single_form = _parse_form_or_empty(request=request)

        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for(
                "resources.resource_list"
            ),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        if resource_id is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("resources.resource_list"),
                message="Resource not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        resource_manager = _build_resource_manager(db_session=db_session)
        try:
            removed = resource_manager.delete_resource(resource_id, auth.user_id)
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("resources.resource_list"),
                message=_describe_resource_removal(removed=removed),
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            message = _describe_resource_manager_error(exc=exc)
            if message is None:
                _LOGGER.exception(
                    "Unexpected error deleting resource %s", resource_id
                )
                message = (
                    "An unexpected error occurred while deleting the"
                    " resource. The problem has been logged."
                )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("resources.resource_list"),
                message=message,
                category=flash.CATEGORY_ERROR,
            )
            return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_resource_checkout(request: Request) -> Response:
    """
        ``POST /resources/{resource_id}/checkout``. Login-gated
        (no admin requirement -- any user can check out).
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        resource_id = _coerce_int(
            raw=request.path_params.get("resource_id", None)
        )
        single_form = _parse_form_or_empty(request=request)

        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for(
                "resources.resource_list"
            ),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        if resource_id is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("resources.resource_list"),
                message="Resource not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        job_id_raw = str(single_form.get("job_id", "")).strip()
        mode_str = str(single_form.get("mode", "exclusive"))
        timeout_minutes = _coerce_int(
            raw=single_form.get("timeout_minutes", None)
        )
        reason = str(single_form.get("reason", "")).strip()

        allocation_manager = _build_allocation_manager(
            db_session=db_session
        )
        try:
            mode = _resolve_allocation_mode(mode_str=mode_str)
            checkout_request = _build_checkout_request(
                resource_id=resource_id,
                job_id=job_id_raw if len(job_id_raw) > 0 else None,
                mode=mode,
                timeout_minutes=timeout_minutes,
                reason=reason,
            )
            allocation = allocation_manager.checkout(
                checkout_request, auth.user_id
            )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.resource_detail",
                    resource_id=resource_id,
                ),
                message=(
                    "Resource checked out successfully."
                    " Allocation ID: {}".format(allocation.id)
                ),
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            message = _describe_allocation_error(exc=exc)
            if message is None:
                _LOGGER.exception(
                    "Unexpected error checking out resource %s",
                    resource_id,
                )
                message = (
                    "An unexpected error occurred while checking out"
                    " the resource. The problem has been logged."
                )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.resource_detail",
                    resource_id=resource_id,
                ),
                message=message,
                category=flash.CATEGORY_ERROR,
            )
            return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


_HANDLERS_BY_ENDPOINT: Dict[str, Callable[[Request], Response]] = {
    "resources.dashboard_root": handle_dashboard,
    "resources.dashboard": handle_dashboard,
    "resources.resource_list": handle_resource_list,
    "resources.resource_create": handle_resource_create,
    "resources.resource_detail": handle_resource_detail,
    "resources.resource_edit": handle_resource_edit,
    "resources.resource_delete": handle_resource_delete,
    "resources.resource_checkout": handle_resource_checkout,
}


def register_resources_routes(*, app: Any) -> None:
    """
        Attach the E1 resources core routes to a webworks app
        and register their endpoint names with the url_for shim.

        Also pre-registers the URL patterns for E2/E3/E4
        endpoints so the dashboard sidebar template's
        ``url_for('resources.pool_list')`` / ``ip_pool_list`` /
        ``allocation_list`` / ``reservation_list`` /
        ``health_dashboard`` / ``tag_list`` calls all resolve
        before those handlers ship.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.

        :returns: None.
    """
    for endpoint_name, relative_path, methods in _ROUTE_TABLE:
        full_path = RESOURCES_PATH + relative_path
        if full_path.endswith("/") and full_path != "/":
            full_path = (
                RESOURCES_PATH if relative_path == "/" else full_path
            )

        _url_for_module.register_endpoint(
            endpoint=endpoint_name, pattern=full_path
        )
        handler = _HANDLERS_BY_ENDPOINT[endpoint_name]
        wrapped_handler = _wrap_resources_handler_in_shell(handler)
        app.attach_route(full_path, methods=list(methods))(wrapped_handler)
    for endpoint_name, relative_path in _FUTURE_ENDPOINT_PATTERNS:
        full_path = RESOURCES_PATH + relative_path
        _url_for_module.register_endpoint(
            endpoint=endpoint_name, pattern=full_path
        )

    # E2 features -- pools + ip pools. Lazy-imported so this
    # module remains importable when a per-feature module fails
    # to load (matches the config/routes.py register_*_routes
    # dispatch pattern from D2-D4).
    from ccai.pychestrate.webservice.webinterface.blueprints.resources.routes_pools import (  # noqa: E402
        register_pools_routes,
    )
    from ccai.pychestrate.webservice.webinterface.blueprints.resources.routes_ip_pools import (  # noqa: E402
        register_ip_pools_routes,
    )
    register_pools_routes(app=app)
    register_ip_pools_routes(app=app)

    # E3 features -- allocations + reservations.
    from ccai.pychestrate.webservice.webinterface.blueprints.resources.routes_allocations import (  # noqa: E402
        register_allocations_routes,
    )
    from ccai.pychestrate.webservice.webinterface.blueprints.resources.routes_reservations import (  # noqa: E402
        register_reservations_routes,
    )
    register_allocations_routes(app=app)
    register_reservations_routes(app=app)

    # E4 features -- health + tags.
    from ccai.pychestrate.webservice.webinterface.blueprints.resources.routes_health import (  # noqa: E402
        register_health_routes,
    )
    from ccai.pychestrate.webservice.webinterface.blueprints.resources.routes_tags import (  # noqa: E402
        register_tags_routes,
    )
    register_health_routes(app=app)
    register_tags_routes(app=app)

    return


__all__ = [
    "RESOURCES_MAX_PER_PAGE",
    "RESOURCES_PATH",
    "register_resources_routes",
    "handle_dashboard",
    "handle_resource_list",
    "handle_resource_create",
    "handle_resource_detail",
    "handle_resource_edit",
    "handle_resource_delete",
    "handle_resource_checkout",
]
