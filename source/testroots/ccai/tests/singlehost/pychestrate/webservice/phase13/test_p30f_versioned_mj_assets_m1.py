"""
.. module:: test_p30f_versioned_mj_assets_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The component-library assets under /mj are linked with a
               content hash, like every other static asset.

.. moduleauthor:: Code Craft AI LLC

Audit finding XC-20: the shell document linked ``/mj/styles/tokens.css``
and ``/mj/styles/base.css`` without a version, so they were served
``Cache-Control: no-cache`` and revalidated on every page while every
``?v=`` asset was cached immutably. ``build_mj_static_url`` (the
``mj_static_url`` template global) now versions them. No database,
browser, or server needed.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import re
import tempfile

from ccai import testbase

from ccai.pychestrate.webservice.webinterface.foundation import static_files
from ccai.pychestrate.webservice.webinterface.site_shell.shell_document import (
    SHELL_TEMPLATE_NAME,
)

from ccai.tests.singlehost.pychestrate.webservice.phase13._template_harness import (
    strict_environment,
)


def _mj_root_with_tokens(content: bytes) -> str:
    root = tempfile.mkdtemp(prefix="pyc-mj-static-")
    os.makedirs(os.path.join(root, "styles"))
    with open(os.path.join(root, "styles", "tokens.css"), "wb") as fh:
        fh.write(content)
    return root


def _render_shell_document() -> str:
    template = strict_environment().get_template(SHELL_TEMPLATE_NAME)
    rtnval = template.render(
        page_title="Pychestrate",
        initial_route="/",
        bundle_names=["pyc-site-shell"],
        bundle_stylesheets=[],
        content_html="",
        csrf_token="",
        user_display_name="",
        user_login_name="",
        service_version="",
        user_guide_url="",
    )
    return rtnval


def test_mj_static_url_appends_a_content_hash():
    """
    **Feature: versioned component-library assets**
    **Property: build_mj_static_url returns /mj/<path>?v=<hash> for a
    file that exists under the /mj root.**
    """
    root = _mj_root_with_tokens(b":root{}")
    static_files.configure_mj_static_url_root(static_root=root)
    try:
        url = static_files.build_mj_static_url("styles/tokens.css")
        testbase.assert_true(re.match(r"^/mj/styles/tokens\.css\?v=[0-9a-f]{12}$", url) is not None, url)
    finally:
        static_files.configure_mj_static_url_root(static_root=None)
    return


def test_mj_static_url_hash_follows_the_file_content():
    """
    **Feature: versioned component-library assets**
    **Property: the /mj URL's hash changes when the file content
    changes, so a library upgrade busts the browser cache.**
    """
    root = _mj_root_with_tokens(b":root{}")
    static_files.configure_mj_static_url_root(static_root=root)
    try:
        first = static_files.build_mj_static_url("styles/tokens.css")
        with open(os.path.join(root, "styles", "tokens.css"), "wb") as fh:
            fh.write(b":root{--mj-accent:red}")
        os.utime(os.path.join(root, "styles", "tokens.css"), (1, 1))
        second = static_files.build_mj_static_url("styles/tokens.css")
        testbase.assert_true(first != second, "hash did not change with content")
    finally:
        static_files.configure_mj_static_url_root(static_root=None)
    return


def test_mj_static_url_leaves_a_missing_file_unversioned():
    """
    **Feature: versioned component-library assets**
    **Property: a path with no file behind it is returned un-versioned
    so the page still links it.**
    """
    root = _mj_root_with_tokens(b":root{}")
    static_files.configure_mj_static_url_root(static_root=root)
    try:
        url = static_files.build_mj_static_url("styles/missing.css")
        testbase.assert_equal(url, "/mj/styles/missing.css")
    finally:
        static_files.configure_mj_static_url_root(static_root=None)
    return


def test_mj_static_url_defaults_to_the_installed_webworks_assets():
    """
    **Feature: versioned component-library assets**
    **Property: without configuration, build_mj_static_url hashes the
    installed codecraftai-webworks static/ directory -- the one the
    bootstrap mounts at /mj.**
    """
    static_files.configure_mj_static_url_root(static_root=None)
    url = static_files.build_mj_static_url("styles/base.css")
    testbase.assert_true(url.startswith("/mj/styles/base.css?v="), url)
    return


def test_mj_static_url_is_a_template_global():
    """
    **Feature: versioned component-library assets**
    **Property: the consumer-UI jinja environment exposes
    mj_static_url alongside static_url.**
    """
    environment = strict_environment()
    testbase.assert_true(environment.globals.get("mj_static_url") is static_files.build_mj_static_url)
    return


def test_shell_document_links_versioned_mj_stylesheets():
    """
    **Feature: versioned component-library assets**
    **Property: the shell document links /mj/styles/tokens.css and
    /mj/styles/base.css with a ?v= content hash.**
    """
    html = _render_shell_document()
    linked = re.findall(r'href="(/mj/[^"]+)"', html)
    unversioned = [href for href in linked if "?v=" not in href]
    testbase.assert_equal(len(linked), 2)
    testbase.assert_equal(unversioned, [])
    return
