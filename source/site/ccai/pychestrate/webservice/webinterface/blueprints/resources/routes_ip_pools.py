"""
.. module:: webinterface.blueprints.resources.routes_ip_pools
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /resources/ip-pools
               (E2 slice -- IP pool management).

.. moduleauthor:: Code Craft AI LLC

The seven IP pool routes served under the resources blueprint:

* ``GET  /resources/ip-pools``                            -- list.
* ``GET  /resources/ip-pools/create``                     -- form.
* ``POST /resources/ip-pools/create``                     -- create
                                                             (admin).
* ``GET  /resources/ip-pools/{pool_id}``                  -- detail
                                                             (with
                                                             active
                                                             allocations
                                                             and
                                                             available
                                                             IPs).
* ``GET  /resources/ip-pools/{pool_id}/edit``             -- form
                                                             (admin).
* ``POST /resources/ip-pools/{pool_id}/edit``             -- update
                                                             (admin).
* ``POST /resources/ip-pools/{pool_id}/delete``           -- delete
                                                             (admin).
* ``POST /resources/ip-pools/{pool_id}/checkout``         -- check
                                                             out one
                                                             or more
                                                             IPs.
* ``POST /resources/ip-pools/{pool_id}/checkin``          -- check in
                                                             a single
                                                             allocation
                                                             OR every
                                                             allocation
                                                             for a job.

The create-form's ``dns_servers`` / ``reserved_ips`` fields are
split on commas via :func:`_parse_csv_string`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

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
    url_for as _url_for_module,
)
from ccai.pychestrate.webservice.webinterface.blueprints.config.routes import (
    MultiFormView,
    _attach_session_to_response,
    _build_default_template_context,
    _parse_form_multi,
    _parse_form_or_empty,
    _redirect_with_flash,
    _render,
    _require_permission_or_redirect,
    _resolve_authenticated_request,
)
from ccai.pychestrate.webservice.webinterface.blueprints.resources.routes import (
    RESOURCES_MAX_PER_PAGE,
    RESOURCES_PATH,
    _resources_permission_flags,
    _wrap_resources_handler_in_shell,
    _build_page_window,
    _calculate_total_pages,
)


_LOGGER = logging.getLogger("pychestrate.ui.resources.ip_pools")


def _build_ip_pool_manager(*, db_session: Any) -> Any:
    """
        Construct an :class:`IPPoolManager`. Defined locally so
        each per-feature module owns its own test-patch surface
        -- see the equivalent note in routes_pools.py.
    """
    from ccai.pychestrate.core.managers.ip_pool_manager import (  # noqa: E402
        IPPoolManager,
    )
    rtnval = IPPoolManager(db_session)
    return rtnval


_ROUTE_TABLE = (
    ("resources.ip_pool_list", "/ip-pools", ("GET",)),
    (
        "resources.ip_pool_create",
        "/ip-pools/create",
        ("GET", "POST"),
    ),
    ("resources.ip_pool_detail", "/ip-pools/{pool_id}", ("GET",)),
    (
        "resources.ip_pool_edit",
        "/ip-pools/{pool_id}/edit",
        ("GET", "POST"),
    ),
    (
        "resources.ip_pool_delete",
        "/ip-pools/{pool_id}/delete",
        ("POST",),
    ),
    (
        "resources.ip_pool_checkout",
        "/ip-pools/{pool_id}/checkout",
        ("POST",),
    ),
    (
        "resources.ip_pool_checkin",
        "/ip-pools/{pool_id}/checkin",
        ("POST",),
    ),
)


_ADMIN_PERMISSION = "system:resources.manage"


# ---------------------------------------------------------------------------
# Lazy-import builder seams
# ---------------------------------------------------------------------------


def _build_ip_pool_create_request(
        *,
        name: str,
        cidr: str,
        gateway: Optional[str],
        dns_servers: List[str],
        description: str,
        reserved_ips: List[str]
    ) -> Any:
    """
        Construct an :class:`IPPoolCreateRequest`. Lazy-imports.
    """
    from ccai.pychestrate.core.managers.ip_pool_manager import (  # noqa: E402
        IPPoolCreateRequest,
    )
    rtnval = IPPoolCreateRequest(
        name=name,
        cidr=cidr,
        gateway=gateway,
        dns_servers=dns_servers,
        description=description,
        reserved_ips=reserved_ips,
    )
    return rtnval


def _build_ip_pool_update_request(
        *,
        description: Optional[str],
        gateway: Optional[str],
        dns_servers: Optional[List[str]],
        reserved_ips: Optional[List[str]]
    ) -> Any:
    """
        Construct an :class:`IPPoolUpdateRequest`. Lazy-imports.
    """
    from ccai.pychestrate.core.managers.ip_pool_manager import (  # noqa: E402
        IPPoolUpdateRequest,
    )
    rtnval = IPPoolUpdateRequest(
        description=description,
        gateway=gateway,
        dns_servers=dns_servers,
        reserved_ips=reserved_ips,
    )
    return rtnval


def _build_ip_allocation_request(
        *,
        pool_id: int,
        count: int,
        specific_ip: Optional[str],
        job_id: Optional[str],
        timeout_minutes: Optional[int],
        reason: str
    ) -> Any:
    """
        Construct an :class:`IPAllocationRequest`. Lazy-imports.
    """
    from ccai.pychestrate.core.managers.ip_pool_manager import (  # noqa: E402
        IPAllocationRequest,
    )
    rtnval = IPAllocationRequest(
        pool_id=pool_id,
        count=count,
        specific_ip=specific_ip,
        job_id=job_id,
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


def _describe_ip_pool_error(*, exc: Exception) -> Optional[str]:
    """
        Map a typed IPPoolManager error to its deliberate,
        user-facing message. Returns None when ``exc`` is not one
        of the typed errors -- callers then log the exception and
        flash a generic sentence instead of the raw exception
        text. Lazy-imports so this module stays importable when
        the manager package is absent (test runtimes patch the
        manager builders).

        :param exc: The exception raised by an IPPoolManager call.

        :returns: Specific user-facing message, or None.
    """
    try:
        from ccai.pychestrate.core.managers.ip_pool_manager import (  # noqa: E402
            CIDROverlapError,
            DuplicateIPPoolError,
            IPAllocationNotFoundError,
            IPNotAvailableError,
            IPNotInPoolError,
            IPPoolExhaustedError,
            IPPoolHasAllocationsError,
            IPPoolNotFoundError,
            IPPoolValidationError,
            IPReservedError,
            NotIPAllocationOwnerError,
        )
    except ImportError:
        return None

    if isinstance(exc, CIDROverlapError):
        msg_parts = ["{}.".format(exc.message)]
        if len(exc.overlapping_pools) > 0:
            msg_parts.append(
                "Overlapping pools: {}.".format(
                    ", ".join(exc.overlapping_pools)
                )
            )
        rtnval = " ".join(msg_parts)
        return rtnval

    typed_errors = (
        DuplicateIPPoolError,
        IPAllocationNotFoundError,
        IPNotAvailableError,
        IPNotInPoolError,
        IPPoolExhaustedError,
        IPPoolHasAllocationsError,
        IPPoolNotFoundError,
        IPPoolValidationError,
        IPReservedError,
        NotIPAllocationOwnerError,
    )
    if isinstance(exc, typed_errors):
        rtnval = exc.message
        return rtnval
    return None


def _parse_csv_string(*, raw: str) -> List[str]:
    """
        Split a comma-separated string into a list of trimmed
        non-empty entries. Mirrors the legacy
        ``[s.strip() for s in raw.split(',') if s.strip()]``
        pattern used for both ``dns_servers`` and
        ``reserved_ips`` form fields.

        :param raw: Form-submitted CSV string.

        :returns: List of trimmed entries (may be empty).
    """
    if raw is None or len(raw) == 0:
        return []
    rtnval: List[str] = []
    for chunk in raw.split(","):
        trimmed = chunk.strip()
        if len(trimmed) > 0:
            rtnval.append(trimmed)
    return rtnval


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_ip_pool_list(request: Request) -> Response:
    """
        ``GET /resources/ip-pools``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        params = _parse_pagination_params(request=request)
        offset = (params["page"] - 1) * params["per_page"]

        ip_pool_manager = _build_ip_pool_manager(db_session=db_session)
        pools_response = ip_pool_manager.list_pools(
            auth.user_id, offset=offset, limit=params["per_page"]
        )
        pools = pools_response.pools

        total_pages = _calculate_total_pages(
            total=pools_response.total,
            per_page=params["per_page"],
        )
        page_window = _build_page_window(
            page=params["page"], total_pages=total_pages
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="resources.ip_pool_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context.update(_resources_permission_flags(auth=auth))
        context["pools"] = pools
        context["page"] = params["page"]
        context["per_page"] = params["per_page"]
        context["total_pages"] = total_pages
        context["page_window"] = page_window
        response = _render(
            template_name="resources/ip_pools/list.html",
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


def handle_ip_pool_create(request: Request) -> Response:
    """
        ``GET /resources/ip-pools/create`` /
        ``POST /resources/ip-pools/create`` (admin-gated).
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        deny_response = _require_permission_or_redirect(
            auth=auth,
            permission=_ADMIN_PERMISSION,
            deny_redirect_url=_url_for_module.url_for(
                "resources.dashboard"
            ),
        )
        if deny_response is not None:
            return deny_response

        method = request.method.upper()
        ip_pool_manager = _build_ip_pool_manager(db_session=db_session)

        if method == "GET":
            flashes = flash.consume_flashes(session=auth.session)
            context = _build_default_template_context(
                session=auth.session,
                request_endpoint="resources.ip_pool_create",
                flashes=flashes,
                csrf_token=auth.csrf_token,
            )
            context.update(_resources_permission_flags(auth=auth))
            context["form_data"] = None
            response = _render(
                template_name="resources/ip_pools/create.html",
                context=context,
            )
            _attach_session_to_response(
                response=response, session=auth.session
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
                "resources.ip_pool_create"
            ),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        name = str(single_form.get("name", "")).strip()
        cidr = str(single_form.get("cidr", "")).strip()
        gateway = str(single_form.get("gateway", "")).strip()
        dns_servers_str = str(
            single_form.get("dns_servers", "")
        ).strip()
        description = str(single_form.get("description", "")).strip()
        reserved_ips_str = str(
            single_form.get("reserved_ips", "")
        ).strip()

        dns_servers = _parse_csv_string(raw=dns_servers_str)
        reserved_ips = _parse_csv_string(raw=reserved_ips_str)

        try:
            create_request = _build_ip_pool_create_request(
                name=name,
                cidr=cidr,
                gateway=gateway if len(gateway) > 0 else None,
                dns_servers=dns_servers,
                description=description,
                reserved_ips=reserved_ips,
            )
            pool = ip_pool_manager.create_pool(
                create_request, auth.user_id
            )
            message = 'IP Pool "{}" created successfully.'.format(name)
            stored_cidr = getattr(pool, "cidr", cidr)
            if isinstance(stored_cidr, str) and stored_cidr != cidr:
                # The manager stores the canonical network
                # (10.50.0.5/29 -> 10.50.0.0/29); say so.
                message = (
                    'IP Pool "{}" created with range {} (entered as'
                    " {}).".format(name, stored_cidr, cidr)
                )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.ip_pool_detail", pool_id=pool.id
                ),
                message=message,
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            message = _describe_ip_pool_error(exc=exc)
            if message is None:
                _LOGGER.exception("Unexpected error creating IP pool")
                message = (
                    "An unexpected error occurred while creating the"
                    " IP pool. The problem has been logged."
                )
            flash.add_flash(
                session=auth.session,
                message=message,
                category=flash.CATEGORY_ERROR,
            )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="resources.ip_pool_create",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context.update(_resources_permission_flags(auth=auth))
        context["form_data"] = form_view
        response = _render(
            template_name="resources/ip_pools/create.html",
            context=context,
            status_code=400,
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


def handle_ip_pool_detail(request: Request) -> Response:
    """
        ``GET /resources/ip-pools/{pool_id}`` -- detail page with
        active allocations and an "available IPs" preview list.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        pool_id = _coerce_int(
            raw=request.path_params.get("pool_id", None)
        )
        if pool_id is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.ip_pool_list"
                ),
                message="IP Pool not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        ip_pool_manager = _build_ip_pool_manager(db_session=db_session)
        pool = ip_pool_manager.get_pool(pool_id)
        if pool is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.ip_pool_list"
                ),
                message="IP Pool not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        allocations = ip_pool_manager.list_allocations(
            pool_id=pool_id, status="active"
        ).allocations
        available_ips = ip_pool_manager.get_available_ips(
            pool_id, count=10
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="resources.ip_pool_detail",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context.update(_resources_permission_flags(auth=auth))
        context["pool"] = pool
        context["allocations"] = allocations
        context["available_ips"] = available_ips
        response = _render(
            template_name="resources/ip_pools/detail.html",
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


def handle_ip_pool_edit(request: Request) -> Response:
    """
        ``GET /resources/ip-pools/{pool_id}/edit`` /
        ``POST /resources/ip-pools/{pool_id}/edit``
        (admin-gated).
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        deny_response = _require_permission_or_redirect(
            auth=auth,
            permission=_ADMIN_PERMISSION,
            deny_redirect_url=_url_for_module.url_for(
                "resources.dashboard"
            ),
        )
        if deny_response is not None:
            return deny_response

        pool_id = _coerce_int(
            raw=request.path_params.get("pool_id", None)
        )
        if pool_id is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.ip_pool_list"
                ),
                message="IP Pool not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        ip_pool_manager = _build_ip_pool_manager(db_session=db_session)
        pool = ip_pool_manager.get_pool(pool_id)
        if pool is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.ip_pool_list"
                ),
                message="IP Pool not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        method = request.method.upper()
        form_view: Optional[MultiFormView] = None

        if method == "POST":
            single_form = _parse_form_or_empty(request=request)
            multi_form = _parse_form_multi(request=request)
            form_view = MultiFormView(data=multi_form)

            csrf_redirect = auth_guard.enforce_csrf_or_redirect(
                form=single_form,
                session=auth.session,
                fallback_url=_url_for_module.url_for(
                    "resources.ip_pool_edit", pool_id=pool_id
                ),
            )
            if csrf_redirect is not None:
                _attach_session_to_response(
                    response=csrf_redirect, session=auth.session
                )
                return csrf_redirect

            gateway = str(single_form.get("gateway", "")).strip()
            dns_servers_str = str(
                single_form.get("dns_servers", "")
            ).strip()
            description = str(
                single_form.get("description", "")
            ).strip()
            reserved_ips_str = str(
                single_form.get("reserved_ips", "")
            ).strip()

            # Legacy semantics: empty CSV input passes None
            # (don't update), non-empty passes the parsed list.
            if len(dns_servers_str) > 0:
                dns_servers: Optional[List[str]] = _parse_csv_string(
                    raw=dns_servers_str
                )
            else:
                dns_servers = None
            if len(reserved_ips_str) > 0:
                reserved_ips: Optional[List[str]] = _parse_csv_string(
                    raw=reserved_ips_str
                )
            else:
                reserved_ips = None

            try:
                update_request = _build_ip_pool_update_request(
                    description=(
                        description if len(description) > 0 else None
                    ),
                    gateway=gateway if len(gateway) > 0 else None,
                    dns_servers=dns_servers,
                    reserved_ips=reserved_ips,
                )
                ip_pool_manager.update_pool(
                    pool_id, update_request, auth.user_id
                )
                response = _redirect_with_flash(
                    session=auth.session,
                    url=_url_for_module.url_for(
                        "resources.ip_pool_detail", pool_id=pool_id
                    ),
                    message="IP Pool updated successfully.",
                    category=flash.CATEGORY_SUCCESS,
                )
                return response
            except Exception as exc:
                message = _describe_ip_pool_error(exc=exc)
                if message is None:
                    _LOGGER.exception(
                        "Unexpected error updating IP pool %s",
                        pool_id,
                    )
                    message = (
                        "An unexpected error occurred while updating"
                        " the IP pool. The problem has been logged."
                    )
                flash.add_flash(
                    session=auth.session,
                    message=message,
                    category=flash.CATEGORY_ERROR,
                )

        # GET, or POST that fell through -- re-render with the
        # submitted values (``form_data``) when a POST failed so
        # typed input is never reverted to the stored pool state.
        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="resources.ip_pool_edit",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context.update(_resources_permission_flags(auth=auth))
        context["pool"] = pool
        context["form_data"] = form_view
        response = _render(
            template_name="resources/ip_pools/edit.html",
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


def handle_ip_pool_delete(request: Request) -> Response:
    """
        ``POST /resources/ip-pools/{pool_id}/delete``
        (admin-gated).
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        deny_response = _require_permission_or_redirect(
            auth=auth,
            permission=_ADMIN_PERMISSION,
            deny_redirect_url=_url_for_module.url_for(
                "resources.dashboard"
            ),
        )
        if deny_response is not None:
            return deny_response

        pool_id = _coerce_int(
            raw=request.path_params.get("pool_id", None)
        )
        single_form = _parse_form_or_empty(request=request)

        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for(
                "resources.ip_pool_list"
            ),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        if pool_id is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.ip_pool_list"
                ),
                message="IP Pool not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        ip_pool_manager = _build_ip_pool_manager(db_session=db_session)
        try:
            ip_pool_manager.delete_pool(pool_id, auth.user_id)
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.ip_pool_list"
                ),
                message="IP Pool deleted successfully.",
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            message = _describe_ip_pool_error(exc=exc)
            if message is None:
                _LOGGER.exception(
                    "Unexpected error deleting IP pool %s", pool_id
                )
                message = (
                    "An unexpected error occurred while deleting the"
                    " IP pool. The problem has been logged."
                )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.ip_pool_list"
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


def handle_ip_pool_checkout(request: Request) -> Response:
    """
        ``POST /resources/ip-pools/{pool_id}/checkout``. Login-only
        (any authenticated user can check out IPs). Supports
        single-IP via ``checkout_ip`` AND bulk via ``checkout_ips``
        when ``count > 1``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        pool_id = _coerce_int(
            raw=request.path_params.get("pool_id", None)
        )
        single_form = _parse_form_or_empty(request=request)

        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for(
                "resources.ip_pool_list"
            ),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        if pool_id is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.ip_pool_list"
                ),
                message="IP Pool not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        count = _coerce_int_with_default(
            raw=single_form.get("count", None), default=1
        )
        specific_ip = str(single_form.get("specific_ip", "")).strip()
        job_id = str(single_form.get("job_id", "")).strip()
        timeout_minutes = _coerce_int(
            raw=single_form.get("timeout_minutes", None)
        )
        reason = str(single_form.get("reason", "")).strip()

        ip_pool_manager = _build_ip_pool_manager(db_session=db_session)
        try:
            alloc_request = _build_ip_allocation_request(
                pool_id=pool_id,
                count=count,
                specific_ip=(
                    specific_ip if len(specific_ip) > 0 else None
                ),
                job_id=job_id if len(job_id) > 0 else None,
                timeout_minutes=timeout_minutes,
                reason=reason,
            )

            if count == 1:
                allocation = ip_pool_manager.checkout_ip(
                    alloc_request, auth.user_id
                )
                message = "IP {} checked out successfully.".format(
                    allocation.ip_address
                )
            else:
                result = ip_pool_manager.checkout_ips(
                    alloc_request, auth.user_id
                )
                message = "{} IPs checked out successfully.".format(
                    len(result.allocations)
                )

            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.ip_pool_detail", pool_id=pool_id
                ),
                message=message,
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            message = _describe_ip_pool_error(exc=exc)
            if message is None:
                _LOGGER.exception(
                    "Unexpected error checking out IP from pool %s",
                    pool_id,
                )
                message = (
                    "An unexpected error occurred while checking out"
                    " the IP. The problem has been logged."
                )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.ip_pool_detail", pool_id=pool_id
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


def handle_ip_pool_checkin(request: Request) -> Response:
    """
        ``POST /resources/ip-pools/{pool_id}/checkin``. Login-only.
        Supports single-allocation checkin via ``allocation_id``
        OR a bulk job-checkin via ``job_id`` -- mirrors the
        legacy handler's two branches exactly.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        pool_id = _coerce_int(
            raw=request.path_params.get("pool_id", None)
        )
        single_form = _parse_form_or_empty(request=request)

        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for(
                "resources.ip_pool_list"
            ),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        if pool_id is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "resources.ip_pool_list"
                ),
                message="IP Pool not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        allocation_id = _coerce_int(
            raw=single_form.get("allocation_id", None)
        )
        job_id = str(single_form.get("job_id", "")).strip()

        redirect_url = _url_for_module.url_for(
            "resources.ip_pool_detail", pool_id=pool_id
        )

        ip_pool_manager = _build_ip_pool_manager(db_session=db_session)
        try:
            if allocation_id is not None:
                ip_pool_manager.checkin_ip(
                    allocation_id, auth.user_id
                )
                response = _redirect_with_flash(
                    session=auth.session,
                    url=redirect_url,
                    message="IP checked in successfully.",
                    category=flash.CATEGORY_SUCCESS,
                )
                return response
            if len(job_id) > 0:
                count = ip_pool_manager.checkin_job_ips(
                    job_id, auth.user_id
                )
                response = _redirect_with_flash(
                    session=auth.session,
                    url=redirect_url,
                    message=(
                        "{} IPs checked in for job {}.".format(
                            count, job_id
                        )
                    ),
                    category=flash.CATEGORY_SUCCESS,
                )
                return response

            response = _redirect_with_flash(
                session=auth.session,
                url=redirect_url,
                message="No allocation ID or job ID provided.",
                category=flash.CATEGORY_ERROR,
            )
            return response
        except Exception as exc:
            message = _describe_ip_pool_error(exc=exc)
            if message is None:
                _LOGGER.exception(
                    "Unexpected error checking in IP for pool %s",
                    pool_id,
                )
                message = (
                    "An unexpected error occurred while checking in"
                    " the IP. The problem has been logged."
                )
            response = _redirect_with_flash(
                session=auth.session,
                url=redirect_url,
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
    "resources.ip_pool_list": handle_ip_pool_list,
    "resources.ip_pool_create": handle_ip_pool_create,
    "resources.ip_pool_detail": handle_ip_pool_detail,
    "resources.ip_pool_edit": handle_ip_pool_edit,
    "resources.ip_pool_delete": handle_ip_pool_delete,
    "resources.ip_pool_checkout": handle_ip_pool_checkout,
    "resources.ip_pool_checkin": handle_ip_pool_checkin,
}


def register_ip_pools_routes(*, app: Any) -> None:
    """
        Attach the IP pool routes to a webworks app and register
        their endpoint names with the url_for shim.
    """
    for endpoint_name, relative_path, methods in _ROUTE_TABLE:
        full_path = RESOURCES_PATH + relative_path
        _url_for_module.register_endpoint(
            endpoint=endpoint_name, pattern=full_path
        )
        handler = _HANDLERS_BY_ENDPOINT[endpoint_name]
        wrapped_handler = _wrap_resources_handler_in_shell(handler)
        app.attach_route(full_path, methods=list(methods))(wrapped_handler)
    return


__all__ = [
    "register_ip_pools_routes",
    "handle_ip_pool_list",
    "handle_ip_pool_create",
    "handle_ip_pool_detail",
    "handle_ip_pool_edit",
    "handle_ip_pool_delete",
    "handle_ip_pool_checkout",
    "handle_ip_pool_checkin",
]
