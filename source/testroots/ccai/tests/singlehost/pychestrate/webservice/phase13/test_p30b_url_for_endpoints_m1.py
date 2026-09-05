"""
.. module:: test_p30b_url_for_endpoints_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Every ``url_for`` endpoint literal in a template
               resolves against the route registry.

.. moduleauthor:: Code Craft AI LLC

``url_for`` raises ``KeyError`` for an unregistered endpoint, so a
typo in a template becomes a 500 on the page that renders it. The
audit found no dead endpoints today; this test keeps it that way
by checking the string literals in every template (and its bases)
against the registry the four blueprint registrars populate.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import sys

from typing import Callable

from ccai import testbase

from ccai.pychestrate.webservice.webinterface.foundation import url_for as url_for_module

from ccai.tests.singlehost.pychestrate.webservice.phase13._template_harness import (
    ensure_routes_registered,
    enumerate_templates,
    slugify,
    url_for_endpoints_in_template,
)


def _make_endpoint_test(template_name: str) -> Callable[[], None]:
    def _test() -> None:
        ensure_routes_registered()
        registry = url_for_module.get_registry_snapshot()
        referenced = url_for_endpoints_in_template(template_name=template_name)
        unknown = [name for name in referenced if name not in registry]
        testbase.assert_equal(
            unknown,
            [],
            "{} links to unregistered endpoints: {}".format(template_name, unknown),
        )
        return

    _test.__doc__ = (
        "**Feature: ui-remediation guardrails**\n"
        "**Property: every url_for endpoint literal in `{}` is"
        " registered by a blueprint route table.**".format(template_name)
    )
    return _test


def _install_generated_tests() -> None:
    module = sys.modules[__name__]
    for template_name in enumerate_templates():
        func = _make_endpoint_test(template_name)
        func_name = "test_endpoints_{}".format(slugify(template_name))
        func.__name__ = func_name
        func.__qualname__ = func_name
        func.__module__ = __name__
        setattr(module, func_name, func)
    return


_install_generated_tests()
