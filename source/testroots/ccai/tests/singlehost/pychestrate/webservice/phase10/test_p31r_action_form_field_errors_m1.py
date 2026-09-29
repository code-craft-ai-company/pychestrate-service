"""
.. module:: test_p31r_action_form_field_errors_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Action forms on a detail page show a refused value's
               error next to its input (ADM-11).

.. moduleauthor:: Code Craft AI LLC

The forms that create and edit things re-render with a 400. A form on a
detail page (check out an IP address, change a device's health status)
posts to its own address and redirects back to the page, as its
successes do, so a refusal cannot re-render a page it does not own. A
refusal that names an input now travels through the session: the page it
redirects to shows the message beside that input, lists it in the error
summary, keeps what was typed, and shows it once. A refusal about the
state of the thing (a device at capacity, an offline device) still shows
as a banner.
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
    get,
    merge_cookies,
    post_form,
    unique_name,
)


def _tag(page: str, *, element: str, field_id: str) -> str:
    match = re.search(r"<" + element + r'[^>]*\bid="' + re.escape(field_id) + r'"[^>]*>', page, re.S)
    rtnval = match.group(0) if match is not None else ""
    return rtnval


def _error_text(page: str, *, field_id: str) -> str:
    match = re.search(r'id="' + re.escape(field_id) + r'-error"[^>]*>(.*?)</div>', page, re.S)
    rtnval = html.unescape(match.group(1).strip()) if match is not None else ""
    return rtnval


def _created_id(response, *, prefix: str) -> int:
    location = response.header("Location") or ""
    match = re.search(re.escape(prefix) + r"/(\d+)", location)
    testbase.assert_true(match is not None, "no id in the redirect: {} {}".format(response.status_code, location))
    return int(match.group(1))


# ===========================================================================
# IP pool checkout
# ===========================================================================


def _pool_with_gateway() -> Tuple[int, str, str, Dict[str, str]]:
    """
        Create a /29 with a gateway; return ``(pool id, gateway, an
        address outside the pool, cookies)``.
    """
    cookies = admin_cookies()
    first = uuid.uuid4().int % 200 + 20
    second = uuid.uuid4().int % 200 + 20
    gateway = "10.{}.{}.1".format(first, second)
    created = post_form(
        path="/resources/ip-pools/create",
        fields={
            "name": unique_name(prefix="ipco"),
            "cidr": "10.{}.{}.0/29".format(first, second),
            "gateway": gateway,
            "dns_servers": "",
            "reserved_ips": "",
            "description": "",
        },
        cookies=cookies,
    )
    testbase.assert_equal(created.status_code, 303)
    pool_id = _created_id(created, prefix="/resources/ip-pools")
    outside = "10.{}.{}.200".format(first, second)
    rtnval = (pool_id, gateway, outside, cookies)
    return rtnval


def _refused_checkout(*, specific_ip: str, extra: Dict[str, str] = None):
    pool_id, gateway, outside, cookies = _pool_with_gateway()
    address = {"gateway": gateway, "outside": outside}[specific_ip]
    fields = {"count": "1", "specific_ip": address, "job_id": "job-kept", "timeout_minutes": "", "reason": "kept reason"}
    fields.update(extra or {})
    response = post_form(path="/resources/ip-pools/{}/checkout".format(pool_id), fields=fields, cookies=cookies)
    jar = merge_cookies(cookies=cookies, response=response)
    page = get(path="/resources/ip-pools/{}".format(pool_id), cookies=jar)
    # What the browser holds after the page it was redirected to.
    rtnval = (response, page, address, pool_id, merge_cookies(cookies=jar, response=page))
    return rtnval


def test_a_reserved_address_is_shown_next_to_the_specific_ip_input():
    """
    **Feature: action form field errors (ADM-11)**
    **Property: asking to check out the pool's gateway redirects back to
    the pool page, where the refusal sits beside the specific-IP input
    (aria-invalid, described by it), the summary links to it, and what
    was typed is still in the form.**
    """
    response, page, address, _pool_id, _cookies = _refused_checkout(specific_ip="gateway")
    tag = _tag(page.text, element="input", field_id="specific_ip")

    testbase.assert_equal(
        (response.status_code,
         len(_error_text(page.text, field_id="specific_ip")) > 0,
         'aria-invalid="true"' in tag and "specific_ip-error" in tag,
         'href="#specific_ip"' in page.text and 'data-role="error-summary"' in page.text,
         'value="{}"'.format(address) in tag,
         'value="job-kept"' in _tag(page.text, element="input", field_id="job_id"),
         'value="kept reason"' in _tag(page.text, element="input", field_id="reason")),
        (303, True, True, True, True, True, True),
    )
    return


def test_an_address_outside_the_pool_is_shown_next_to_the_specific_ip_input():
    """
    **Feature: action form field errors (ADM-11)**
    **Property: an address outside the pool's range is refused beside
    the specific-IP input.**
    """
    _response, page, _address, _pool_id, _cookies = _refused_checkout(specific_ip="outside")

    testbase.assert_equal(
        (len(_error_text(page.text, field_id="specific_ip")) > 0,
         'aria-invalid="true"' in _tag(page.text, element="input", field_id="specific_ip")),
        (True, True),
    )
    return


def test_the_refusal_is_shown_once():
    """
    **Feature: action form field errors (ADM-11)**
    **Property: opening the pool page again after the refusal was shown
    finds no error and an empty specific-IP input.**
    """
    _response, _page, _address, pool_id, cookies = _refused_checkout(specific_ip="gateway")
    again = get(path="/resources/ip-pools/{}".format(pool_id), cookies=cookies)

    testbase.assert_equal(
        ('data-role="error-summary"' in again.text, 'id="specific_ip-error"' in again.text,
         'value=""' in _tag(again.text, element="input", field_id="specific_ip")),
        (False, False, True),
    )
    return


# ===========================================================================
# Device health status
# ===========================================================================


def _device() -> Tuple[int, Dict[str, str]]:
    cookies = admin_cookies()
    created = post_form(
        path="/resources/create",
        fields={
            "name": unique_name(prefix="hstat"), "resource_type": "device", "pool_id": "",
            "description": "", "capacity": "1", "metadata": "{}",
        },
        cookies=cookies,
    )
    testbase.assert_equal(created.status_code, 303)
    rtnval = (_created_id(created, prefix="/resources"), cookies)
    return rtnval


def test_a_blank_reason_is_shown_next_to_the_reason_input_and_changes_nothing():
    """
    **Feature: action form field errors (ADM-11)**
    **Property: changing a device's health status with a reason that is
    only spaces redirects back to its health page, where the refusal
    sits beside the reason input; the status the person picked stays
    selected, and the device's status did not change.**
    """
    resource_id, cookies = _device()
    before = get(path="/resources/health/{}".format(resource_id), cookies=cookies)
    response = post_form(
        path="/resources/health/{}/update".format(resource_id),
        fields={"status": "maintenance", "reason": "   "},
        cookies=cookies,
    )
    jar = merge_cookies(cookies=cookies, response=response)
    page = get(path="/resources/health/{}".format(resource_id), cookies=jar)
    reason = _tag(page.text, element="input", field_id="reason")
    selected = re.search(r'<option value="maintenance"\s+selected', page.text)
    after = get(path="/resources/health/{}".format(resource_id), cookies=merge_cookies(cookies=jar, response=page))

    testbase.assert_equal(
        (response.status_code,
         len(_error_text(page.text, field_id="reason")) > 0,
         'aria-invalid="true"' in reason and "reason-error" in reason,
         'href="#reason"' in page.text and 'data-role="error-summary"' in page.text,
         selected is not None,
         'data-role="error-summary"' in after.text,
         'name="status"' in before.text),
        (303, True, True, True, True, False, True),
    )
    return
