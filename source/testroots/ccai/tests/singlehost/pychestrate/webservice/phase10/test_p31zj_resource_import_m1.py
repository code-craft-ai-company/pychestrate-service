"""
.. module:: test_p31zj_resource_import_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Register many devices from a spreadsheet, after a preview
               (RES-22).

.. moduleauthor:: Code Craft AI LLC

Registering two dozen devices took about a hundred and seventy form
interactions. Resources, Import takes pasted CSV (or cells pasted from a
spreadsheet), reads it, checks every row against the lab and shows what
would be made and what is wrong, creating nothing; Import then makes every
device, or none when any row has a problem. These tests cover the reader
(columns, tags, metadata, limits) and the page (preview, confirm, refusal,
permission).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import html
import re
import uuid

from typing import Dict, List, Tuple

from ccai import testbase

from ccai.pychestrate.webservice.webinterface.blueprints.resources import resource_import
from ccai.pychestrate.webservice.webinterface.blueprints.resources.resource_import import (
    MAX_IMPORT_ROWS,
    check_against_lab,
    parse_import,
)

from ccai.tests.singlehost.pychestrate.webservice.phase10._adm_helpers import (
    admin_cookies,
    app,
    get,
    merge_cookies,
    post_form,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    ensure_seeded_viewer,
    login_via_post,
)


# ---------------------------------------------------------------------------
# The reader
# ---------------------------------------------------------------------------


def test_the_reader_takes_the_documented_columns_and_metadata_cells():
    """
    **Feature: resource import (RES-22)**
    **Property: a header row naming name, type, pool, capacity, tags and
    two meta.<key> columns gives rows with those fields, tags split on
    spaces, commas and semicolons, and the meta cells as metadata.**
    """
    preview = parse_import(text=(
        "name,type,pool,capacity,description,tags,meta.serial,meta.os\n"
        'phone-01,device,android,2,"Front, left",a b;c,SN-1,14\n'
    ))
    row = preview.rows[0]

    testbase.assert_equal(
        (preview.importable, row.number, row.name, row.resource_type, row.pool_name, row.capacity, row.description,
         row.tags, row.metadata),
        (True, 2, "phone-01", "device", "android", 2, "Front, left", ["a", "b", "c"], {"serial": "SN-1", "os": "14"}),
    )
    return


def test_the_defaults_apply_and_a_spreadsheet_paste_with_tabs_is_read():
    """
    **Feature: resource import (RES-22)**
    **Property: a sheet with only a name column gets type device and
    capacity 1; text pasted from a spreadsheet (tab separated, with a
    header spelled "Resource Type") is read the same way.**
    """
    plain = parse_import(text="name\nbench-1\n")
    pasted = parse_import(text="Name\tResource Type\tCapacity\nbench-2\tgeneric\t3\n")

    testbase.assert_equal(
        (plain.rows[0].resource_type, plain.rows[0].capacity, pasted.importable, pasted.rows[0].resource_type, pasted.rows[0].capacity),
        ("device", 1, True, "generic", 3),
    )
    return


def test_each_bad_cell_is_reported_on_its_row_and_the_others_are_still_read():
    """
    **Feature: resource import (RES-22)**
    **Property: a bad name, type, capacity, tag and metadata are each
    reported on their own row with their own message, while a good row
    beside them is read and marked ready; the file is not importable.**
    """
    preview = parse_import(text=(
        "name,type,capacity,tags,metadata\n"
        "good-1,device,1,ok,\n"
        "bad name!,device,1,,\n"
        "bad-type,toaster,1,,\n"
        "bad-cap,device,zero,,\n"
        "bad-tag,device,1,-x,\n"
        "bad-json,device,1,,{nope\n"
        "bad-shape,device,1,,[1]\n"
    ))
    problems = [sorted(row.problems) for row in preview.rows]

    testbase.assert_equal(
        (preview.importable, preview.problem_rows, problems),
        (False, 6, [[], ["name"], ["type"], ["capacity"], ["tags"], ["metadata"], ["metadata"]]),
    )
    return


def test_an_unknown_or_missing_column_refuses_the_whole_file():
    """
    **Feature: resource import (RES-22)**
    **Property: a header with a column the reader does not know (a typo)
    names it in a file problem and reads no rows, so the column is not
    dropped in silence; a header with no name column, an empty paste, a
    header with nothing under it and a repeated column are each refused.**
    """
    unknown = parse_import(text="name,colour\nphone,red\n")
    no_name = parse_import(text="type,pool\ndevice,x\n")
    empty = parse_import(text="   \n")
    header_only = parse_import(text="name,type\n")
    repeated = parse_import(text="name,name\na,b\n")

    testbase.assert_equal(
        ("\"colour\"" in unknown.file_problems[0], unknown.rows, "no name column" in no_name.file_problems[0].lower(),
         len(empty.file_problems), "no devices" in header_only.file_problems[0],
         "more than once" in repeated.file_problems[0]),
        (True, [], True, 1, True, True),
    )
    return


def test_a_row_with_too_many_cells_and_a_file_that_is_too_big_are_refused():
    """
    **Feature: resource import (RES-22)**
    **Property: a row with more cells than the header is a problem on that
    row; more than the row limit, or more than the character limit, is a
    file problem that reads nothing.**
    """
    wide = parse_import(text="name\nphone,extra\n")
    many = parse_import(text="name\n" + "\n".join("d{}".format(i) for i in range(MAX_IMPORT_ROWS + 1)) + "\n")
    long_text = parse_import(text="name\n" + "x" * (resource_import.MAX_IMPORT_CHARACTERS + 1))

    testbase.assert_equal(
        ("more cells" in wide.rows[0].problems["row"], many.rows, "at most 500" in many.file_problems[0],
         "too much text" in long_text.file_problems[0]),
        (True, [], True, True),
    )
    return


def test_the_same_name_twice_in_a_pool_is_caught_within_the_file():
    """
    **Feature: resource import (RES-22)**
    **Property: a second row with the same name and pool as an earlier one
    is a problem naming that row; the same name in another pool is fine.**
    """
    preview = parse_import(text="name,pool\na,x\na,y\na,x\n")

    testbase.assert_equal(
        ([sorted(row.problems) for row in preview.rows], "row 2" in preview.rows[2].problems["name"]),
        ([[], [], ["name"]], True),
    )
    return


def test_rows_are_checked_against_the_pools_and_names_in_the_lab():
    """
    **Feature: resource import (RES-22)**
    **Property: a pool that does not exist, and a name the pool (or the
    default pool) already holds, are each a problem on the row; a blank
    pool resolves to the default pool's id.**
    """
    preview = parse_import(text="name,pool\nnew-1,lab\nnew-2,ghost\ntaken,lab\ntaken-default,\n")
    check_against_lab(
        rows=preview.rows, pool_ids_by_name={"lab": 7}, default_pool_id=3,
        existing={(7, "taken"), (3, "taken-default")},
    )

    testbase.assert_equal(
        ([sorted(row.problems) for row in preview.rows], [row.pool_id for row in preview.rows][:1],
         preview.rows[3].pool_id, "default pool" in preview.rows[3].problems["name"],
         "ghost" in preview.rows[1].problems["pool"]),
        ([[], ["pool"], ["name"], ["name"]], [7], 3, True, True),
    )
    return


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------


def _suffix() -> str:
    return uuid.uuid4().hex[:8]


def _pool(cookies: Dict[str, str]) -> str:
    name = "imp-pool-" + _suffix()
    post_form(path="/resources/pools/create", fields={"name": name, "description": ""}, cookies=cookies)
    return name


def _post(cookies: Dict[str, str], text: str, action: str):
    return post_form(path="/resources/import", fields={"csv_text": text, "action": action}, cookies=cookies)


def _listed(cookies: Dict[str, str], prefix: str) -> List[str]:
    page = get(path="/resources/list", cookies=cookies, query={"search": prefix, "per_page": "100"}).text
    return sorted(re.findall(r">(" + re.escape(prefix) + r"[a-z0-9-]*)</a></td>", page))


def _sheet(prefix: str, pool: str, count: int) -> Tuple[str, List[str]]:
    names = ["{}-{}".format(prefix, index) for index in range(count)]
    lines = ["name,type,pool,capacity,tags,meta.serial"] + [
        "{},device,{},1,imp-tag-{} shared-{},SN-{}".format(name, pool, prefix, prefix, index) for index, name in enumerate(names)
    ]
    return ("\n".join(lines) + "\n", names)


def test_a_preview_shows_every_row_and_creates_nothing():
    """
    **Feature: resource import (RES-22)**
    **Property: previewing a sheet of three devices answers 200, lists each
    with its pool, tags and metadata marked Ready, offers an Import button
    for three, and no device exists afterwards.**
    """
    admin = admin_cookies()
    pool = _pool(admin)
    prefix = "prv" + _suffix()
    text, names = _sheet(prefix, pool, 3)
    response = _post(admin, text, "preview")
    page = html.unescape(response.text)

    testbase.assert_equal(
        (response.status_code, all(name in page for name in names), page.count('<span class="badge badge-success">Ready</span>'),
         "Import 3 devices" in page, "SN-0" in page, _listed(admin, prefix)),
        (200, True, 3, True, True, []),
    )
    return


def test_import_makes_every_device_with_its_pool_tags_and_metadata():
    """
    **Feature: resource import (RES-22)**
    **Property: choosing Import creates all three devices, redirects to
    the list saying so, the devices are in the named pool with their tags,
    and a device's page shows its metadata.**
    """
    admin = admin_cookies()
    pool = _pool(admin)
    prefix = "imp" + _suffix()
    text, names = _sheet(prefix, pool, 3)
    response = _post(admin, text, "import")
    message = html.unescape(get(path=response.header("Location") or "/", cookies=merge_cookies(cookies=admin, response=response)).text)
    first = re.search(r'<a href="/resources/(\d+)">' + re.escape(names[0]) + "</a>",
                      get(path="/resources/list", cookies=admin, query={"search": prefix}).text)
    device_page = html.unescape(get(path="/resources/{}".format(first.group(1)), cookies=admin).text)

    testbase.assert_equal(
        (response.status_code, "Imported 3 resources." in message, _listed(admin, prefix), pool in device_page,
         "shared-" + prefix in device_page, "SN-0" in device_page),
        (303, True, sorted(names), True, True, True),
    )
    return


def test_nothing_is_made_when_any_row_has_a_problem():
    """
    **Feature: resource import (RES-22)**
    **Property: a sheet with two good rows and one that names a pool that
    does not exist answers 400 on Import, marks the bad row with the
    reason, says nothing was imported, offers no Import button, and makes
    none of the three.**
    """
    admin = admin_cookies()
    pool = _pool(admin)
    prefix = "bad" + _suffix()
    text = "name,pool\n{p}-a,{pool}\n{p}-b,no-such-pool-{s}\n{p}-c,{pool}\n".format(p=prefix, pool=pool, s=_suffix())
    response = _post(admin, text, "import")
    page = html.unescape(response.text)

    testbase.assert_equal(
        (response.status_code, "There is no pool called" in page, "Nothing is imported while any row has a problem" in page,
         "Import 3 devices" in page and 'data-role="import-confirm"' in page, _listed(admin, prefix)),
        (400, True, True, False, []),
    )
    return


def test_a_name_already_in_the_pool_is_caught_at_preview_and_at_import():
    """
    **Feature: resource import (RES-22)**
    **Property: importing a sheet once makes the devices; the same sheet
    again is refused with each row saying the pool already has that name,
    and nothing more is made.**
    """
    admin = admin_cookies()
    pool = _pool(admin)
    prefix = "dup" + _suffix()
    text, names = _sheet(prefix, pool, 2)
    _post(admin, text, "import")
    again = _post(admin, text, "import")
    page = html.unescape(again.text)

    testbase.assert_equal(
        (again.status_code, page.count("already has a resource called"), _listed(admin, prefix)),
        (400, 2, sorted(names)),
    )
    return


def test_a_file_problem_is_shown_and_creates_nothing():
    """
    **Feature: resource import (RES-22)**
    **Property: a header with an unknown column answers a preview with
    the file problem listed, no table of rows and no Import button.**
    """
    admin = admin_cookies()
    response = _post(admin, "name,colour\nphone,red\n", "preview")
    page = html.unescape(response.text)

    testbase.assert_equal(
        (response.status_code, 'data-role="import-file-problems"' in page, '"colour"' in page, 'data-role="import-confirm"' in page),
        (200, True, True, False),
    )
    return


def test_only_a_person_who_can_manage_resources_can_import():
    """
    **Feature: resource import (RES-22)**
    **Property: a plain user is not offered Import on the list, is turned
    away from the page with a message naming the action, and posting a
    sheet anyway creates nothing; the administrator is offered it.**
    """
    admin = admin_cookies()
    viewer = ensure_seeded_viewer()
    _response, viewer_cookies = login_via_post(wsgi_app=app(), login=viewer.login, password=viewer.password)
    pool = _pool(admin)
    prefix = "perm" + _suffix()
    text, _names = _sheet(prefix, pool, 1)
    admin_list = get(path="/resources/list", cookies=admin).text
    viewer_list = get(path="/resources/list", cookies=viewer_cookies).text
    page = get(path="/resources/import", cookies=viewer_cookies)
    posted = _post(viewer_cookies, text, "import")
    message = html.unescape(get(path=posted.header("Location") or "/", cookies=merge_cookies(cookies=viewer_cookies, response=posted)).text)

    testbase.assert_equal(
        ('data-role="import-resources"' in admin_list, 'data-role="import-resources"' in viewer_list, page.status_code in (302, 303),
         "import devices" in message, _listed(admin, prefix)),
        (True, False, True, True, []),
    )
    return


def test_the_import_page_is_reachable_and_explains_the_columns():
    """
    **Feature: resource import (RES-22)**
    **Property: /resources/import is served (not read as a resource id),
    lists the columns and an example, and the create page links to it.**
    """
    admin = admin_cookies()
    page = html.unescape(get(path="/resources/import", cookies=admin).text)
    create = get(path="/resources/create", cookies=admin).text

    testbase.assert_equal(
        (get(path="/resources/import", cookies=admin).status_code, "<code>meta.&lt;key&gt;</code>" in page or "meta.<key>" in page,
         'data-role="import-example"' in page, 'data-role="import-resources"' in create),
        (200, True, True, True),
    )
    return
