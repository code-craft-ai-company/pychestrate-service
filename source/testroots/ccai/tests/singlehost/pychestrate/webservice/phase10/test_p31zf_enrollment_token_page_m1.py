"""
.. module:: test_p31zf_enrollment_token_page_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The minted-token screen can be copied from, does not clip
               the command, quotes its arguments and survives a reload
               (ADM-40).

.. moduleauthor:: Code Craft AI LLC

The screen that shows a new enrollment token once had a clipped command
line, no way to copy either the secret or the command, arguments that were
pasted unquoted (a pod label with a space became several arguments), and a
reload minted a second token whose secret nobody saw. The list under it
showed full UUIDs, microsecond ISO timestamps and one colour for every
status. The secret is still shown only once and never rides in the session
cookie, so a reload cannot be turned into a redirect; a second mint of the
same project and pod within thirty seconds is refused instead, saying it
looks like a reload.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import html
import os
import re
import uuid

from typing import Dict, Tuple

from ccai import testbase

import ccai.pychestrate.webservice.webinterface as webinterface_package
from ccai.pychestrate.webservice.webinterface.foundation.templating import status_tone_filter

from ccai.tests.singlehost.pychestrate.webservice.phase10._adm_helpers import (
    admin_cookies,
    get,
    open_db_session,
    post_form,
    unique_name,
)


def _api_project() -> str:
    """A registry project; returns its UUID."""
    from ccai.pychestrate.webservice.projects.models import Project, ProjectState  # noqa: E402

    slug = unique_name(prefix="tokproj")
    project_uuid = uuid.uuid4()
    db_session = open_db_session()
    try:
        db_session.add(Project(project_id=project_uuid, slug=slug, display_name="API {}".format(slug), description="",
                               state=ProjectState.ACTIVE, extension_fields={}))
        db_session.commit()
    finally:
        db_session.close()
    return str(project_uuid)


def _mint(cookies: Dict[str, str], project_id: str, pod_name: str) -> Tuple[int, str]:
    response = post_form(
        path="/admin/enrollment-tokens/mint",
        fields={"project_id": project_id, "pod_name": pod_name, "one_shot": "1"}, cookies=cookies,
    )
    return (response.status_code, html.unescape(response.text))


def _token_count(pod_name: str) -> int:
    from ccai.pychestrate.webservice.clients.models import EnrollmentToken  # noqa: E402

    db_session = open_db_session()
    try:
        return db_session.query(EnrollmentToken).filter(EnrollmentToken.pod_name == pod_name).count()
    finally:
        db_session.close()


def _pre(page: str, element_id: str) -> str:
    match = re.search(r'<pre[^>]*\bid="' + re.escape(element_id) + r'"[^>]*>(.*?)</pre>', page, re.S)
    return match.group(1) if match is not None else ""


def test_the_result_panel_has_copy_buttons_for_the_secret_and_the_commands():
    """
    **Feature: minted token screen (ADM-40)**
    **Property: after a mint the panel has a Copy secret and a Copy
    commands button, each naming the block it copies, the blocks carry the
    secret and the commands, and the copy script is on the page.**
    """
    admin = admin_cookies()
    status, page = _mint(admin, _api_project(), unique_name(prefix="pod"))
    secret = _pre(page, "mint-secret").strip()
    commands = _pre(page, "mint-commands")

    testbase.assert_equal(
        (status, len(secret) > 20, 'data-copy-from="#mint-secret"' in page, 'data-copy-from="#mint-commands"' in page,
         "--token " + secret in commands, "pychestrate-client run" in commands, 'button[data-copy-from]' in page),
        (200, True, True, True, True, True, True),
    )
    return


def test_the_enroll_command_quotes_a_pod_label_with_spaces_and_punctuation():
    """
    **Feature: minted token screen (ADM-40)**
    **Property: a pod label "lab pod 01 !!" is written into the enroll
    command as one quoted argument, so pasting the command into a shell
    passes it as one value.**
    """
    admin = admin_cookies()
    label = "lab pod 01 !! " + uuid.uuid4().hex[:6]
    status, page = _mint(admin, _api_project(), label)
    commands = _pre(page, "mint-commands")

    testbase.assert_equal((status, "--name '{}'".format(label) in commands), (200, True))
    return


def test_a_repeated_mint_is_refused_and_makes_no_second_token():
    """
    **Feature: minted token screen (ADM-40)**
    **Property: sending the same mint form again straight away (a reload
    of the result page, or a double click) answers 409, says it looks like
    a reload, shows no secret and leaves one token for the pod.**
    """
    admin = admin_cookies()
    project = _api_project()
    pod = unique_name(prefix="pod")
    first_status, _first = _mint(admin, project, pod)
    second_status, second = _mint(admin, project, pod)

    testbase.assert_equal(
        (first_status, second_status, "looks like a reload or a double click" in second, "Shown once" in second, _token_count(pod)),
        (200, 409, True, False, 1),
    )
    return


def test_a_second_token_for_another_pod_or_project_is_still_made():
    """
    **Feature: minted token screen (ADM-40)**
    **Property: the guard is only for the same project and pod: a token
    for another pod of the same project, and one for the same pod label in
    another project, are each minted.**
    """
    admin = admin_cookies()
    project, other_project = _api_project(), _api_project()
    pod, other_pod = unique_name(prefix="pod"), unique_name(prefix="pod")
    results = [_mint(admin, project, pod)[0], _mint(admin, project, other_pod)[0], _mint(admin, other_project, pod)[0]]

    testbase.assert_equal((results, _token_count(pod), _token_count(other_pod)), ([200, 200, 200], 2, 1))
    return


def test_the_list_shows_short_ids_local_times_a_status_colour_and_the_newest_first():
    """
    **Feature: minted token screen (ADM-40)**
    **Property: in the list the token id is shortened (the full id is its
    tooltip), issue and expiry are <time> elements for the viewer's zone,
    a pending token's badge has the pending tone, and a token minted later
    is listed above an earlier one.**
    """
    admin = admin_cookies()
    project = _api_project()
    earlier, later = unique_name(prefix="pod"), unique_name(prefix="pod")
    _mint(admin, project, earlier)
    _status, page = _mint(admin, project, later)
    row = re.search(r"<tr>\s*<td><code[^>]*>[^<]*</code></td>\s*<td>[^<]*</td>\s*<td>" + re.escape(later) + r"</td>.*?</tr>", page, re.S)
    row_text = row.group(0) if row is not None else ""

    testbase.assert_equal(
        (row is not None, re.search(r'<code class="mono" title="[0-9a-f-]{36}">[0-9a-f]{8}…</code>', row_text) is not None,
         row_text.count("<time data-pyc-local"), 'class="badge badge-warning">Pending<' in row_text,
         page.index(later) < page.index(earlier) if page.count(later) and page.count(earlier) else None),
        (True, True, 2, True, True),
    )
    return


def test_a_redeemed_token_gets_the_success_colour():
    """
    **Feature: minted token screen (ADM-40)**
    **Property: the shared status tones know "redeemed" (success), and the
    other token statuses keep distinct tones: pending warns, revoked and
    expired are danger.**
    """
    testbase.assert_equal(
        [status_tone_filter(value) for value in ("REDEEMED", "PENDING", "REVOKED", "EXPIRED")],
        ["success", "warning", "danger", "danger"],
    )
    return


def test_the_command_box_wraps_instead_of_scrolling_sideways():
    """
    **Feature: minted token screen (ADM-40)**
    **Property: the stylesheet's command box breaks long lines (pre-wrap,
    anywhere) and no longer hides the end of the enroll command behind a
    horizontal scroll.**
    """
    root = os.path.dirname(os.path.abspath(webinterface_package.__file__))
    with open(os.path.join(root, "static", "styles", "pyc-fragment.css"), encoding="utf-8") as handle:
        css = handle.read()
    rule = re.search(r"\.command-box\s*\{[^}]*\}", css).group(0)

    testbase.assert_equal(
        ("white-space: pre-wrap" in rule, "overflow-wrap: anywhere" in rule, "overflow-x: auto" in rule),
        (True, True, False),
    )
    return
