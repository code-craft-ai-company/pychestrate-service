"""
.. module:: test_p30a_template_render_smoke_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Render every consumer-UI template under
               StrictUndefined against dataclass-shaped fixtures.

.. moduleauthor:: Code Craft AI LLC

The UI audit found nine feature areas whose templates read
attributes that do not exist on the manager response dataclasses
the handlers pass (``watch.event_type``, ``job.passed_count``,
``pool.reserved_ips`` ...). Under jinja's default ``Undefined``
those render as blanks, zeros, or the literal ``None``; two of
them call ``.value`` on the missing attribute and raise a 500.

This module generates one test per template per fixture mode:

* ``populated`` -- every Optional set, every list holding rows.
  Any attribute the dataclass does not define raises
  ``UndefinedError`` and fails the test.
* ``sparse`` -- Optionals ``None``, lists empty. Exercises the
  empty-state branches and asserts the literal word ``None`` does
  not leak into the rendered HTML.

A template that reads a variable the fixture registry does not
know about fails with a ``KeyError`` naming the variable; the fix
is to register it in
:mod:`ccai.testshared.factories.webui.template_contexts` with the
type the handler passes.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re
import sys

from typing import Callable

from ccai import testbase

from ccai.testshared.factories.webui.dataclass_fixtures import (
    MODE_POPULATED,
    MODE_SPARSE,
)
from ccai.testshared.factories.webui.template_contexts import (
    build_template_context,
)

from ccai.tests.singlehost.pychestrate.webservice.phase13._template_harness import (
    enumerate_templates,
    slugify,
    strict_environment,
    undeclared_variables,
)


# The literal word "None" (or "Nones", from ``{{ seconds }}s``)
# not embedded in a longer identifier is what an un-guarded
# ``{{ optional_field }}`` produces.
_NONE_LEAK_PATTERN = re.compile(r"(?<![A-Za-z0-9_\-.])None(?:s\b|(?![A-Za-z0-9_\-]))")


def render_template(*, template_name: str, mode: str) -> str:
    """
        Render ``template_name`` with a context built for exactly the
        variables it reads.

        :param template_name: Loader-relative template name.
        :param mode: Fixture mode.

        :returns: Rendered HTML.
    """
    env = strict_environment()
    variables = undeclared_variables(template_name=template_name)
    context = build_template_context(
        template_name=template_name, variable_names=variables, mode=mode
    )
    template = env.get_template(template_name)
    rtnval = template.render(context)
    return rtnval


def _is_macro_library(template_name: str) -> bool:
    """
        Templates whose basename starts with an underscore
        (``config/_pagination.html``) only define macros and render
        to whitespace on their own.
    """
    basename = template_name.rsplit("/", 1)[-1]
    rtnval = basename.startswith("_")
    return rtnval


def _make_populated_test(template_name: str) -> Callable[[], None]:
    def _test() -> None:
        rendered = render_template(template_name=template_name, mode=MODE_POPULATED)
        if _is_macro_library(template_name) is False:
            testbase.assert_true(
                len(rendered.strip()) > 0,
                "{} rendered an empty document".format(template_name),
            )
        return

    _test.__doc__ = (
        "**Feature: ui-remediation guardrails**\n"
        "**Property: `{}` renders under StrictUndefined with every"
        " Optional populated and every list holding rows, so every"
        " attribute it reads exists on the handler-supplied"
        " dataclasses.**".format(template_name)
    )
    return _test


def _make_sparse_test(template_name: str) -> Callable[[], None]:
    def _test() -> None:
        rendered = render_template(template_name=template_name, mode=MODE_SPARSE)
        if _is_macro_library(template_name) is False:
            testbase.assert_true(
                len(rendered.strip()) > 0,
                "{} rendered an empty document".format(template_name),
            )
        leak = _NONE_LEAK_PATTERN.search(rendered)
        testbase.assert_true(
            leak is None,
            "{} leaks the literal 'None' into the page when Optional"
            " fields are unset (around: {!r})".format(
                template_name,
                rendered[max(0, (leak.start() if leak else 0) - 60):(leak.end() if leak else 0) + 20],
            ),
        )
        return

    _test.__doc__ = (
        "**Feature: ui-remediation guardrails**\n"
        "**Property: `{}` renders under StrictUndefined with every"
        " Optional unset and every list empty, and never prints the"
        " literal word None.**".format(template_name)
    )
    return _test


def _install_generated_tests() -> None:
    module = sys.modules[__name__]
    for template_name in enumerate_templates():
        slug = slugify(template_name)
        for suffix, factory in (
            ("populated", _make_populated_test),
            ("sparse", _make_sparse_test),
        ):
            func = factory(template_name)
            func_name = "test_render_{}__{}".format(slug, suffix)
            func.__name__ = func_name
            func.__qualname__ = func_name
            func.__module__ = __name__
            setattr(module, func_name, func)
    return


_install_generated_tests()
