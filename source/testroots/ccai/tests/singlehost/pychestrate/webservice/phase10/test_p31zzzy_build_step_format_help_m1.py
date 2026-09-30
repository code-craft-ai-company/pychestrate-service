"""
.. module:: test_p31zzzy_build_step_format_help_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The build specification form says what a step looks like (PRJ-16).

.. moduleauthor:: Code Craft AI LLC

The Build Steps box took JSON and said only "JSON array of build step definitions";
the step types were revealed only by the error a wrong one produced, and that
error listed them in a different order on each run (it printed a set). The create
and edit forms now carry a "Step format and example" section that names the
fields and the types the validator accepts (read from the validator's own list,
so they cannot drift), and shows the example, and the error lists the types in
alphabetical order. These tests drive the whole application.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re
import uuid

from typing import Any, Dict, Tuple

from ccai import testbase

from ccai.pychestrate.core.managers.build_manager import validate_build_steps

from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    ensure_app,
    logged_in_cookies,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._test_repository import (
    add_repository,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._projects_ui_helpers import (
    create_project_via_ui,
    get_page,
    post_form,
)


def _format_section(html: str) -> Tuple[bool, list, str]:
    """``(present, the step types named, the example as text)`` of the step-format section."""
    section = re.search(r'<details[^>]*data-role="step-format".*?</details>', html, re.S)
    if section is None:
        return (False, [], "")
    types = re.findall(r"<code>([a-z]+)</code>", section.group(0).split("optionally")[0])
    example = re.search(r'data-role="step-example">(.*?)</pre>', section.group(0), re.S)
    return (True, [name for name in types if name not in ("name", "type")], example.group(1) if example else "")


def _spec(*, wsgi_app: Any, cookies: Dict[str, str], project_id: int) -> int:
    repo_id = add_repository(wsgi_app=wsgi_app, cookies=cookies, project_id=project_id, name="specrepo" + uuid.uuid4().hex[:4])
    response = post_form(
        wsgi_app=wsgi_app, path="/projects/{}/builds/specs/create".format(project_id), cookies=cookies,
        fields={"name": "spec-" + uuid.uuid4().hex[:6], "repository_id": str(repo_id), "branch": "main", "timeout_minutes": "60", "steps": "[]", "environment": "{}", "description": ""},
    )
    found = re.search(r"/builds/specs/(\d+)", response.header("Location") or "")
    if found is None:
        raise AssertionError("spec create did not redirect to the spec: {} {} {}".format(response.status_code, response.header("Location"), response.text[:300]))
    return int(found.group(1))


def test_the_create_and_edit_forms_show_the_step_types_and_an_example():
    """
    **Feature: choices, not guesses (PRJ-16)**
    **Property: the build specification create form and edit form both carry a
    "Step format and example" section naming the four step types the validator
    accepts (artifact, checkout, notification, script) and showing an example
    with a checkout step and a script step.**
    """
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)
    project_id = create_project_via_ui(wsgi_app=handle.wsgi_app, cookies=cookies, prefix="bsf" + uuid.uuid4().hex[:4])
    spec_id = _spec(wsgi_app=handle.wsgi_app, cookies=cookies, project_id=project_id)

    create = get_page(wsgi_app=handle.wsgi_app, path="/projects/{}/builds/specs/create".format(project_id), cookies=cookies).text
    edit = get_page(wsgi_app=handle.wsgi_app, path="/projects/{}/builds/specs/{}/edit".format(project_id, spec_id), cookies=cookies).text

    outcomes = {}
    for name, html in (("create", create), ("edit", edit)):
        present, types, example = _format_section(html)
        outcomes[name] = (present, types, '"type": "checkout"' in example, '"type": "script"' in example)

    expected = (True, ["artifact", "checkout", "notification", "script"], True, True)
    testbase.assert_equal(outcomes, {"create": expected, "edit": expected})
    return


def test_a_wrong_step_type_is_reported_with_the_types_in_alphabetical_order():
    """
    **Feature: choices, not guesses (PRJ-16)**
    **Property: the validator's message for an unknown type lists the valid
    types alphabetically, the same on every run (it used to print a set).**
    """
    errors = validate_build_steps([{"name": "x", "type": "nope"}])

    testbase.assert_equal(errors, ["Step 0: invalid type 'nope'. Must be one of: artifact, checkout, notification, script"])
    return
