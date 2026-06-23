"""
.. module:: test_tag_m2
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for 2-tagging M2 behaviour (boolean search + taxonomies).

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai import testbase

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.tagging import service as tag_service
from ccai.pychestrate.webservice.tagging.expression import compile_tag_expression

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)
from ccai.tests.singlehost.pychestrate.webservice.phase2.fixtures import (
    reset_phase2_runtime,
)


def test_compile_tag_expression_truth_table():
    """
    **Feature: 2-tagging (M2)**
    **Property: compile_tag_expression produces correct predicates for
    AND, OR, NOT, parentheses.**
    """
    pred = compile_tag_expression(expression="env:prod AND platform:linux")
    testbase.assert_equal(pred(frozenset({"env:prod", "platform:linux"})), True)
    testbase.assert_equal(pred(frozenset({"env:prod"})), False)

    pred_or = compile_tag_expression(expression="env:dev OR env:stage")
    testbase.assert_equal(pred_or(frozenset({"env:dev"})), True)
    testbase.assert_equal(pred_or(frozenset({"env:prod"})), False)

    pred_not = compile_tag_expression(expression="!env:prod")
    testbase.assert_equal(pred_not(frozenset({"env:dev"})), True)
    testbase.assert_equal(pred_not(frozenset({"env:prod"})), False)

    pred_complex = compile_tag_expression(
        expression="(env:prod OR env:stage) AND !compliance:restricted",
    )
    testbase.assert_equal(
        pred_complex(frozenset({"env:prod", "compliance:public"})),
        True,
    )
    testbase.assert_equal(
        pred_complex(frozenset({"env:prod", "compliance:restricted"})),
        False,
    )
    return


def test_search_entities_via_registered_taxonomy():
    """
    **Feature: 2-tagging (M2)**
    **Property: search_entities returns entity ids whose tag set matches.**
    """
    reset_phase2_runtime()
    _engine, session = build_in_memory_session()

    p_a = new_uuid()
    p_b = new_uuid()

    tag_service.assign_tag(
        db_session=session, entity_kind="project", entity_id=p_a,
        raw_tag="env:prod", actor_user_id=None,
    )
    tag_service.assign_tag(
        db_session=session, entity_kind="project", entity_id=p_b,
        raw_tag="env:dev", actor_user_id=None,
    )

    matched = tag_service.search_entities(
        db_session=session, entity_kind="project", expression="env:prod",
    )
    testbase.assert_equal(p_a in matched, True)
    testbase.assert_equal(p_b in matched, False)
    return


def test_resource_entity_kind_is_supported():
    """
    **Feature: 2-tagging (M2)**
    **Property: ``resource`` / ``pod`` / ``job`` / ``artifact`` kinds are
    valid targets alongside ``project``.**
    """
    reset_phase2_runtime()
    _engine, session = build_in_memory_session()

    resource_id = new_uuid()
    tag_service.assign_tag(
        db_session=session, entity_kind="resource", entity_id=resource_id,
        raw_tag="env:prod", actor_user_id=None,
    )

    rows = tag_service.list_tags(
        db_session=session, entity_kind="resource", entity_id=resource_id,
    )
    testbase.assert_equal(len(rows), 1)
    return
