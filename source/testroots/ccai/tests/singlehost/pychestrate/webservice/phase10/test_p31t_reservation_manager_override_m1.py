"""
.. module:: test_p31t_reservation_manager_override_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A lab manager can change or cancel another person's
               reservation, giving a reason that is audited (RES-18).

.. moduleauthor:: Code Craft AI LLC

A reservation could only be changed or cancelled by its owner, so a lab
manager who needed a device could not free it, and the refusal named
raw ids. The refusal already says "Only the person who made this
reservation can change or cancel it", and the controls are hidden from
people who cannot use them. A person holding the resource-management
permission may now act for the owner: cancelling gives a reason next to
the button, changing the times gives a reason in the form, and the
reason goes into the audit log with the owner's name, as a record of its
own. Anyone else is refused as before. The owner is not notified: nothing
in the product sends notifications yet.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import html
import re
import uuid

from typing import Dict, Tuple

from ccai import testbase

from ccai.tests.singlehost.pychestrate.webservice.phase10._adm_helpers import (
    admin_cookies,
    app,
    audit_records_for,
    ensure_audit_wiring,
    get,
    latest_audit_sequence,
    merge_cookies,
    post_form,
    unique_name,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    ensure_seeded_admin,
    ensure_seeded_viewer,
    login_via_post,
)


ADMIN_NEEDS_A_REASON = "Give a reason to cancel someone else's reservation; it is recorded in the audit log."
OWNER_ONLY = "Only the person who made this reservation can change or cancel it."


def _viewer_cookies() -> Tuple[Dict[str, str], str]:
    viewer = ensure_seeded_viewer()
    _response, cookies = login_via_post(wsgi_app=app(), login=viewer.login, password=viewer.password)
    return (cookies, str(viewer.user_id))


def _reservation_owned_by_the_viewer() -> Tuple[str, Dict[str, str], Dict[str, str], str]:
    """
        A device and a pending reservation of the viewer's on it.
        Returns ``(reservation id, admin cookies, viewer cookies, the
        viewer's user id)``.
    """
    admin = admin_cookies()
    viewer_cookies, viewer_id = _viewer_cookies()
    device = post_form(
        path="/resources/create",
        fields={"name": unique_name(prefix="ovr"), "resource_type": "device", "pool_id": "",
                "description": "", "capacity": "1", "metadata": "{}"},
        cookies=admin,
    )
    device_id = re.search(r"/resources/(\d+)", device.header("Location") or "").group(1)
    year = 2040 + uuid.uuid4().int % 50
    created = post_form(
        path="/resources/reservations/create",
        fields={"resource_id": device_id, "start_time": "{}-03-01T10:00".format(year),
                "end_time": "{}-03-01T11:00".format(year), "tz": "UTC", "mode": "exclusive",
                "job_id": "", "reason": ""},
        cookies=viewer_cookies,
    )
    testbase.assert_equal(created.status_code, 303)
    reservation_id = re.search(r"/resources/reservations/(\d+)", created.header("Location") or "").group(1)
    return (reservation_id, admin, viewer_cookies, viewer_id)


def _status(reservation_id: str, cookies: Dict[str, str]) -> str:
    page = get(path="/resources/reservations/{}".format(reservation_id), cookies=cookies).text
    match = re.search(r'badge badge-[a-z]+">(Pending|Active|Completed|Cancelled)<', page)
    return match.group(1) if match is not None else ""


def _flash_after(response, cookies: Dict[str, str]) -> str:
    followed = get(path=response.header("Location") or "/", cookies=merge_cookies(cookies=cookies, response=response))
    return html.unescape(followed.text).replace("&rsquo;", "'")


def test_a_manager_cancels_someone_elses_reservation_with_a_reason_that_is_audited():
    """
    **Feature: reservation manager override (RES-18)**
    **Property: the administrator cancels a reservation the viewer made,
    giving a reason; it is cancelled, the message says the reason is
    recorded, and one audit record names the administrator, the owner,
    the reservation and the reason.**
    """
    ensure_audit_wiring()
    reservation_id, admin, viewer_cookies, viewer_id = _reservation_owned_by_the_viewer()
    mark = latest_audit_sequence()
    response = post_form(
        path="/resources/reservations/{}/cancel".format(reservation_id),
        fields={"reason": "Rack needed for the audit"}, cookies=admin,
    )
    message = _flash_after(response, admin)
    rows = audit_records_for(kind="audit.reservation.overridden", since_sequence=mark)
    payload = rows[0].payload_json if len(rows) == 1 else {}

    testbase.assert_equal(
        (response.status_code, "Your reason was recorded in the audit log." in message,
         _status(reservation_id, admin), len(rows),
         str(rows[0].actor_user_id) if rows else "", payload.get("owner_user_id"), payload.get("reason"),
         payload.get("action"), str(payload.get("reservation_id"))),
        (303, True, "Cancelled", 1, str(ensure_seeded_admin().user_id), viewer_id,
         "Rack needed for the audit", "cancelled", reservation_id),
    )
    return


def test_a_manager_needs_a_reason_to_cancel_someone_elses_reservation():
    """
    **Feature: reservation manager override (RES-18)**
    **Property: cancelling the viewer's reservation with no reason is
    refused with a message asking for one; the reservation stays
    pending and nothing is audited.**
    """
    ensure_audit_wiring()
    reservation_id, admin, _viewer_cookies_, _viewer_id = _reservation_owned_by_the_viewer()
    mark = latest_audit_sequence()
    response = post_form(
        path="/resources/reservations/{}/cancel".format(reservation_id), fields={"reason": "  "}, cookies=admin,
    )

    testbase.assert_equal(
        (ADMIN_NEEDS_A_REASON in _flash_after(response, admin), _status(reservation_id, admin),
         len(audit_records_for(kind="audit.reservation.overridden", since_sequence=mark))),
        (True, "Pending", 0),
    )
    return


def test_a_person_who_is_not_a_manager_still_cannot_cancel_someone_elses_reservation():
    """
    **Feature: reservation manager override (RES-18)**
    **Property: the viewer, who is not a manager, cannot cancel the
    administrator's reservation even when giving a reason; the message
    says only its owner can, and it stays pending.**
    """
    reservation_id, admin, viewer_cookies, _viewer_id = _reservation_owned_by_the_viewer()
    # A reservation the administrator owns.
    device = post_form(
        path="/resources/create",
        fields={"name": unique_name(prefix="ovr2"), "resource_type": "device", "pool_id": "",
                "description": "", "capacity": "1", "metadata": "{}"},
        cookies=admin,
    )
    device_id = re.search(r"/resources/(\d+)", device.header("Location") or "").group(1)
    year = 2040 + uuid.uuid4().int % 50
    made = post_form(
        path="/resources/reservations/create",
        fields={"resource_id": device_id, "start_time": "{}-06-01T10:00".format(year),
                "end_time": "{}-06-01T11:00".format(year), "tz": "UTC", "mode": "exclusive",
                "job_id": "", "reason": ""},
        cookies=admin,
    )
    admins_id = re.search(r"/resources/reservations/(\d+)", made.header("Location") or "").group(1)
    response = post_form(
        path="/resources/reservations/{}/cancel".format(admins_id),
        fields={"reason": "I would like it"}, cookies=viewer_cookies,
    )

    testbase.assert_equal(
        (OWNER_ONLY in _flash_after(response, viewer_cookies), _status(admins_id, admin)),
        (True, "Pending"),
    )
    return


def test_a_manager_changes_someone_elses_reservation_with_a_reason_that_is_audited():
    """
    **Feature: reservation manager override (RES-18)**
    **Property: the administrator moves the viewer's reservation, giving
    a reason; the times change and one audit record says it was changed
    for its owner, and why.**
    """
    ensure_audit_wiring()
    reservation_id, admin, _viewer_cookies_, viewer_id = _reservation_owned_by_the_viewer()
    mark = latest_audit_sequence()
    year = 2040 + uuid.uuid4().int % 50
    response = post_form(
        path="/resources/reservations/{}/edit".format(reservation_id),
        fields={"start_time": "{}-09-01T14:00".format(year), "end_time": "{}-09-01T15:00".format(year),
                "tz": "UTC", "override_reason": "Moved for maintenance"},
        cookies=admin,
    )
    rows = audit_records_for(kind="audit.reservation.overridden", since_sequence=mark)
    detail = get(path="/resources/reservations/{}".format(reservation_id), cookies=admin).text

    testbase.assert_equal(
        (response.status_code, len(rows), rows[0].payload_json.get("action") if rows else "",
         rows[0].payload_json.get("reason") if rows else "", rows[0].payload_json.get("owner_user_id") if rows else "",
         "{}-09-01".format(year) in detail),
        (303, 1, "changed", "Moved for maintenance", viewer_id, True),
    )
    return


def test_changing_someone_elses_reservation_without_a_reason_is_shown_next_to_the_reason():
    """
    **Feature: reservation manager override (RES-18)**
    **Property: submitting the edit form for the viewer's reservation
    with no reason answers 400 with the message beside the reason
    input, the typed times kept, and nothing changed or audited.**
    """
    ensure_audit_wiring()
    reservation_id, admin, _viewer_cookies_, _viewer_id = _reservation_owned_by_the_viewer()
    mark = latest_audit_sequence()
    year = 2040 + uuid.uuid4().int % 50
    response = post_form(
        path="/resources/reservations/{}/edit".format(reservation_id),
        fields={"start_time": "{}-09-01T14:00".format(year), "end_time": "{}-09-01T15:00".format(year),
                "tz": "UTC", "override_reason": ""},
        cookies=admin,
    )
    reason_tag = re.search(r'<input[^>]*\bid="override_reason"[^>]*>', response.text, re.S)

    testbase.assert_equal(
        (response.status_code, 'id="override_reason-error"' in response.text,
         reason_tag is not None and 'aria-invalid="true"' in reason_tag.group(0),
         "{}-09-01T14:00".format(year) in response.text,
         len(audit_records_for(kind="audit.reservation.overridden", since_sequence=mark))),
        (400, True, True, True, 0),
    )
    return


def test_the_manager_is_offered_the_controls_and_the_owner_is_not_asked_for_a_reason():
    """
    **Feature: reservation manager override (RES-18)**
    **Property: on the viewer's reservation the administrator's page has
    Edit and a Cancel that asks for a reason; the owner's own page has
    Edit and a Cancel with no reason field; the edit form asks the
    owner for no reason.**
    """
    reservation_id, admin, viewer_cookies, _viewer_id = _reservation_owned_by_the_viewer()
    manager_page = get(path="/resources/reservations/{}".format(reservation_id), cookies=admin).text
    owner_page = get(path="/resources/reservations/{}".format(reservation_id), cookies=viewer_cookies).text
    manager_edit = get(path="/resources/reservations/{}/edit".format(reservation_id), cookies=admin).text
    owner_edit = get(path="/resources/reservations/{}/edit".format(reservation_id), cookies=viewer_cookies).text
    edit_link = "reservations/{}/edit".format(reservation_id)

    testbase.assert_equal(
        (edit_link in manager_page and 'name="reason"' in manager_page,
         edit_link in owner_page and 'name="reason"' not in owner_page,
         'name="override_reason"' in manager_edit, 'name="override_reason"' in owner_edit),
        (True, True, True, False),
    )
    return
