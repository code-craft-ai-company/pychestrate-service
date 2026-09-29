"""
.. module:: resources.routes_import
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``GET`` / ``POST /resources/import`` -- register many
               devices from a spreadsheet, after a preview (RES-22).

.. moduleauthor:: Code Craft AI LLC

The page takes pasted CSV (or text pasted from a spreadsheet). "Preview"
reads it and checks every row against the lab (the pool must exist, and
its resources must not already have that name) and shows what would be
made and what is wrong, creating nothing. "Import" reads and checks the
same text again (the lab may have changed since the preview) and creates
the devices only when every row is fine, so an import is all of it or none
of it. Importing needs the resource-management permission, like adding
one device.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from typing import Any, Dict, List, Optional

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import Response

from ccai.pychestrate.webservice.webinterface.foundation import (
    auth_guard,
    flash,
    url_for as _url_for_module,
)
from ccai.pychestrate.webservice.webinterface.blueprints.config.routes import (
    _attach_session_to_response,
    _build_default_template_context,
    _parse_form_or_empty,
    _redirect_with_flash,
    _render,
    _require_permission_or_redirect,
    _resolve_authenticated_request,
)
from ccai.pychestrate.webservice.webinterface.blueprints.resources import resource_import
from ccai.pychestrate.webservice.webinterface.blueprints.resources.routes import (
    _ADMIN_PERMISSION,
    _build_resource_manager,
    _denial_message,
    _describe_resource_manager_error,
    _resources_permission_flags,
)


_LOGGER = logging.getLogger("pychestrate.ui.resources.import")

#: Pools read when checking a spreadsheet; a lab has nowhere near this many.
_POOL_LIMIT = 1000


def _read_and_check(*, resource_manager: Any, user_id: Any, text: str) -> resource_import.ImportPreview:
    """
        Parse the text and check every row against the lab as it is now.

        :param resource_manager: The resource manager.
        :param user_id: The signed-in person (for the pool list).
        :param text: What was pasted.

        :returns: The preview, with each row's problems filled in.
    """
    preview = resource_import.parse_import(text=text)
    if len(preview.file_problems) > 0 or len(preview.rows) == 0:
        return preview
    pools = resource_manager.list_pools(user_id, limit=_POOL_LIMIT).pools
    pool_ids_by_name: Dict[str, int] = {pool.name: pool.id for pool in pools}
    default_pool_id: Optional[int] = next((pool.id for pool in pools if pool.is_default), None)
    existing = resource_manager.find_existing_names([row.name for row in preview.rows if len(row.name) > 0])
    resource_import.check_against_lab(
        rows=preview.rows, pool_ids_by_name=pool_ids_by_name, default_pool_id=default_pool_id, existing=existing,
    )
    return preview


def _create_all(*, resource_manager: Any, user_id: Any, rows: List[resource_import.ImportRow]) -> Any:
    """
        Create the devices, in order.

        :returns: ``(created, stopped_at, message)``: how many were made, the
                  row it stopped at (None when all were made) and why.
    """
    from ccai.pychestrate.core.managers.resource_manager import ResourceCreateRequest  # noqa: E402

    created = 0
    for row in rows:
        try:
            resource_manager.create_resource(
                ResourceCreateRequest(
                    name=row.name, resource_type=row.resource_type, pool_id=row.pool_id,
                    description=row.description, metadata=dict(row.metadata), tags=list(row.tags),
                    capacity=row.capacity,
                ),
                user_id,
            )
        except Exception as exc:  # noqa: BLE001 -- report which row it was, and how far it got
            message = _describe_resource_manager_error(exc=exc)
            if message is None:
                _LOGGER.exception("Unexpected error importing resource row %s", row.number)
                message = "An unexpected error occurred. The problem has been logged."
            return (created, row.number, message)
        created += 1
    return (created, None, "")


def _render_page(
        *, auth: Any, text: str, preview: Optional[resource_import.ImportPreview], status_code: int = 200
    ) -> Response:
    flashes = flash.consume_flashes(session=auth.session)
    context = _build_default_template_context(
        session=auth.session,
        request_endpoint="resources.resource_import",
        flashes=flashes,
        csrf_token=auth.csrf_token,
    )
    context.update(_resources_permission_flags(auth=auth))
    context["import_text"] = text
    context["import_preview"] = preview
    context["documented_columns"] = resource_import.DOCUMENTED_COLUMNS
    context["example_text"] = resource_import.EXAMPLE_TEXT
    context["max_rows"] = resource_import.MAX_IMPORT_ROWS
    response = _render(
        template_name="resources/resources/import.html",
        context=context,
        status_code=status_code,
    )
    _attach_session_to_response(response=response, session=auth.session)
    return response


def handle_resource_import(request: Request) -> Response:
    """
        ``GET /resources/import`` shows the page; ``POST`` previews
        (``action=preview``) or imports (``action=import``) the pasted text.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        deny_response = _require_permission_or_redirect(
            auth=auth,
            permission=_ADMIN_PERMISSION,
            deny_message=_denial_message(action="import devices"),
            deny_redirect_url=_url_for_module.url_for("resources.dashboard"),
        )
        if deny_response is not None:
            return deny_response

        if request.method.upper() == "GET":
            return _render_page(auth=auth, text="", preview=None)

        single_form = _parse_form_or_empty(request=request)
        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for("resources.resource_import"),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(response=csrf_redirect, session=auth.session)
            return csrf_redirect

        text = str(single_form.get("csv_text", ""))
        action = str(single_form.get("action", "preview")).strip().lower()
        resource_manager = _build_resource_manager(db_session=db_session)
        preview = _read_and_check(resource_manager=resource_manager, user_id=auth.user_id, text=text)

        if action != "import":
            return _render_page(auth=auth, text=text, preview=preview)
        if not preview.importable:
            # Nothing is made when anything is wrong: the page shows what.
            return _render_page(auth=auth, text=text, preview=preview, status_code=400)

        created, stopped_at, message = _create_all(
            resource_manager=resource_manager, user_id=auth.user_id, rows=preview.rows,
        )
        if stopped_at is not None:
            flash.add_flash(
                session=auth.session,
                message=(
                    "Row {} could not be created: {} {} of {} devices were made before it stopped;"
                    " they are in the list. Fix the row and import the rest."
                ).format(stopped_at, message, created, len(preview.rows)),
                category=flash.CATEGORY_ERROR,
            )
            return _render_page(auth=auth, text=text, preview=preview, status_code=409)
        return _redirect_with_flash(
            session=auth.session,
            url=_url_for_module.url_for("resources.resource_list"),
            message="Imported {} resource{}.".format(created, "" if created == 1 else "s"),
            category=flash.CATEGORY_SUCCESS,
        )
    finally:
        try:
            db_session.close()
        except Exception:
            pass


__all__ = ["handle_resource_import"]
