"""
.. module:: test_tag_service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for 2-tagging M1 service surface.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo import testbase

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.extensions.registry import register_resource_extension
from automojo.pychestrate.webservice.tagging import service as tag_service
from automojo.pychestrate.webservice.tagging.exceptions import (
    TagAssignmentNotFoundError,
    TagValueValidationError,
    TaxonomyNotFoundError,
)
from automojo.pychestrate.webservice.tagging.extensions.taxonomy import (
    TagTaxonomyExtension,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)
from automojo.tests.singlehost.pychestrate.webservice.phase2.fixtures import (
    reset_phase2_runtime,
)


class _TestEnvironmentTaxonomy(TagTaxonomyExtension):
    """
        Test-only taxonomy distinct from the in-tree ``env`` pack.
    """
    resource_extension_name: str = "tag_taxonomy"
    taxonomy_name: str = "test_env"
    case_sensitive_value: bool = False
    allowed_values: frozenset = frozenset({"dev", "stage", "prod"})
    color_hex: str = "#aabbcc"
    description: str = "Test-only environment taxonomy."


def _register_env_taxonomy() -> None:
    """
        Helper that registers the test taxonomy on top of the Phase-2
        runtime reset.
    """
    register_resource_extension(
        base_class=TagTaxonomyExtension,
        extension=_TestEnvironmentTaxonomy,
    )
    return


def test_assign_tag_round_trip():
    """
    **Feature: 2-tagging (M1)**
    **Property: assign_tag persists a row visible via list_tags.**
    """
    reset_phase2_runtime()
    _register_env_taxonomy()
    _engine, session = build_in_memory_session()

    project_id = new_uuid()
    tag_service.assign_tag(
        db_session=session,
        entity_kind="project",
        entity_id=project_id,
        raw_tag="test_env:prod",
        actor_user_id=None,
    )

    rows = tag_service.list_tags(
        db_session=session, entity_kind="project", entity_id=project_id,
    )
    testbase.assert_equal(len(rows), 1)
    testbase.assert_equal(rows[0].taxonomy_name, "test_env")
    testbase.assert_equal(rows[0].canonical_value, "prod")
    return


def test_assign_tag_disallowed_value_raises():
    """
    **Feature: 2-tagging (M1)**
    **Property: A value outside the taxonomy's allowed_values raises
    TagValueValidationError.**
    """
    reset_phase2_runtime()
    _register_env_taxonomy()
    _engine, session = build_in_memory_session()

    project_id = new_uuid()
    raised = False
    try:
        tag_service.assign_tag(
            db_session=session,
            entity_kind="project",
            entity_id=project_id,
            raw_tag="test_env:canary",
            actor_user_id=None,
        )
    except TagValueValidationError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_assign_tag_unknown_taxonomy_raises():
    """
    **Feature: 2-tagging (M1)**
    **Property: Unknown taxonomy raises TaxonomyNotFoundError.**
    """
    reset_phase2_runtime()
    _engine, session = build_in_memory_session()

    raised = False
    try:
        tag_service.assign_tag(
            db_session=session,
            entity_kind="project",
            entity_id=new_uuid(),
            raw_tag="unknown:value",
            actor_user_id=None,
        )
    except TaxonomyNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_remove_tag_round_trip():
    """
    **Feature: 2-tagging (M1)**
    **Property: remove_tag removes the row; a second call raises
    TagAssignmentNotFoundError.**
    """
    reset_phase2_runtime()
    _register_env_taxonomy()
    _engine, session = build_in_memory_session()

    project_id = new_uuid()
    tag_service.assign_tag(
        db_session=session, entity_kind="project", entity_id=project_id,
        raw_tag="test_env:dev", actor_user_id=None,
    )

    tag_service.remove_tag(
        db_session=session, entity_kind="project", entity_id=project_id,
        raw_tag="test_env:dev",
    )

    rows = tag_service.list_tags(
        db_session=session, entity_kind="project", entity_id=project_id,
    )
    testbase.assert_equal(len(rows), 0)

    raised = False
    try:
        tag_service.remove_tag(
            db_session=session, entity_kind="project", entity_id=project_id,
            raw_tag="test_env:dev",
        )
    except TagAssignmentNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return
