"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz_dashboard_attention_wording_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: How the projects dashboard words a project's attention count (PRJ-21).

.. moduleauthor:: Code Craft AI LLC

The count is a badge in the project's last-run cell: "1 needs attention", "3 need attention". The note that such projects come first shows only
when some project has a count. The template is rendered in the strict environment with the registry's fixtures.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re

from typing import Any, Dict

from ccai import testbase

from ccai.testshared.factories.webui.template_contexts import (
    MODE_POPULATED,
    build_template_context,
)

from ccai.tests.singlehost.pychestrate.webservice.phase13._template_harness import (
    strict_environment,
    undeclared_variables,
)


TEMPLATE = "projects/dashboard.html"


def _render(**overrides: Any) -> str:
    context = build_template_context(template_name=TEMPLATE, variable_names=undeclared_variables(template_name=TEMPLATE), mode=MODE_POPULATED)
    context.update(overrides)
    return strict_environment().get_template(TEMPLATE).render(context)


def _badges(page: str) -> list:
    return [" ".join(text.split()) for text in re.findall(r'data-role="project-attention">([^<]*)<', page)]


def test_one_needs_and_several_need_and_none_draws_nothing():
    """
    **Feature: projects dashboard health (PRJ-21)**
    **Property: a count of 1 reads "1 needs attention" and 3 reads "3 need attention" on the project's row (once per listed row with that id);
    with no counts there is no badge and no ordering note; with a count the note is shown once.**
    """
    context = build_template_context(template_name=TEMPLATE, variable_names=undeclared_variables(template_name=TEMPLATE), mode=MODE_POPULATED)
    project_id = list(context["projects"])[0].id
    shown = sum(1 for project in context["projects"] if project.id == project_id)
    one = _render(dashboard_attention_counts={project_id: 1})
    many = _render(dashboard_attention_counts={project_id: 3})
    none = _render(dashboard_attention_counts={})

    testbase.assert_equal(
        (
            _badges(one), _badges(many), _badges(none),
            one.count('data-role="projects-order"'), many.count('data-role="projects-order"'), none.count('data-role="projects-order"'),
        ),
        (["1 needs attention"] * shown, ["3 need attention"] * shown, [], 1, 1, 0),
    )
    return
