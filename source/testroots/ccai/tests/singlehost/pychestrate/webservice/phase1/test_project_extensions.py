"""
.. module:: test_project_extensions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Extension-surface tests for 2-projects (TT-4).

.. moduleauthor:: Code Craft AI LLC

Exercises the :class:`ProjectMetadataFieldExtension` extension point:

- An out-of-tree ``ComplianceTierFieldExtension`` can be registered
  after :func:`reset_phase1_runtime`.
- The extension's ``validate_value`` classmethod is honored when a
  PATCH payload references its field.
- Duplicate ``field_name`` across two subclasses is rejected at
  freeze time with :class:`ConfigurationError`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, ClassVar, FrozenSet, Optional

from ccai import testbase

from ccai.errors.exceptions import ConfigurationError

from ccai.pychestrate.webservice.extensions.registry import register_resource_extension
from ccai.pychestrate.webservice.projects import service as project_service
from ccai.pychestrate.webservice.projects.exceptions import (
    MetadataFieldValidationError,
)
from ccai.pychestrate.webservice.projects.extensions.metadata_field import (
    ProjectMetadataFieldExtension,
)
from ccai.pychestrate.webservice.projects.metadata_registry import (
    freeze_registry,
    reset_for_testing as reset_projects_metadata_registry,
)

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
)


_COMPLIANCE_VALUES: FrozenSet[str] = frozenset({"public", "restricted", "confidential"})


class ComplianceTierFieldExtension(ProjectMetadataFieldExtension):
    """
        Out-of-tree sample extension: restricts ``compliance_tier``
        to the fixed enum.
    """
    resource_extension_name: ClassVar[str] = "project_metadata_field"
    field_name: ClassVar[str] = "compliance_tier"
    field_type: ClassVar[str] = "enum"
    required: ClassVar[bool] = False
    default_value: ClassVar[Any] = None
    enum_values: ClassVar[Optional[FrozenSet[str]]] = _COMPLIANCE_VALUES
    description: ClassVar[str] = "Sample compliance tier from pychestrate-ext-example."
    source_extension: ClassVar[str] = "pychestrate-ext-example"


class CollisionFieldExtension(ProjectMetadataFieldExtension):
    """
        Duplicate field_name collision test: uses 'cost_center' so
        freeze_registry must reject it.
    """
    resource_extension_name: ClassVar[str] = "project_metadata_field"
    field_name: ClassVar[str] = "cost_center"
    field_type: ClassVar[str] = "string"
    required: ClassVar[bool] = False
    default_value: ClassVar[Any] = None
    enum_values: ClassVar[Optional[FrozenSet[str]]] = None
    description: ClassVar[str] = "Colliding duplicate of the in-tree cost_center."
    source_extension: ClassVar[str] = "pychestrate-ext-test-collider"


def _install_out_of_tree_extension() -> None:
    """
        Reset the frozen metadata registry, register the out-of-tree
        extension, and re-freeze so :func:`load_registered_fields`
        picks it up alongside the in-tree pack.
    """
    reset_projects_metadata_registry()
    register_resource_extension(
        base_class=ProjectMetadataFieldExtension,
        extension=ComplianceTierFieldExtension,
    )
    freeze_registry()
    return


def test_out_of_tree_extension_accepts_valid_value():
    """
    **Feature: 2-projects TT-4**
    **Property: Registering an out-of-tree ComplianceTierFieldExtension
    lets patch_project accept values from the declared enum.**
    """
    reset_phase1_runtime()
    _install_out_of_tree_extension()

    _engine, session = build_in_memory_session()
    try:
        project_service.create_project(
            db_session=session,
            slug="tt4-accepted",
            display_name="Accepted",
            description="",
            owning_group_id=None,
            template_id=None,
            template_version=None,
            actor_user_id=None,
        )

        updated = project_service.patch_project(
            db_session=session,
            slug="tt4-accepted",
            display_name=None,
            description=None,
            extension_fields={"compliance_tier": "restricted"},
            actor_user_id=None,
        )

        testbase.assert_equal(
            updated.extension_fields.get("compliance_tier", None), "restricted",
        )
    finally:
        session.close()
    return


def test_out_of_tree_extension_rejects_invalid_enum_value():
    """
    **Feature: 2-projects TT-4**
    **Property: patch_project rejects enum values not in the declared
    set with MetadataFieldValidationError.**
    """
    reset_phase1_runtime()
    _install_out_of_tree_extension()

    _engine, session = build_in_memory_session()
    try:
        project_service.create_project(
            db_session=session,
            slug="tt4-rejected",
            display_name="Rejected",
            description="",
            owning_group_id=None,
            template_id=None,
            template_version=None,
            actor_user_id=None,
        )

        raised = False
        try:
            project_service.patch_project(
                db_session=session,
                slug="tt4-rejected",
                display_name=None,
                description=None,
                extension_fields={"compliance_tier": "platinum"},
                actor_user_id=None,
            )
        except MetadataFieldValidationError:
            raised = True

        testbase.assert_equal(raised, True)
    finally:
        session.close()
    return


def test_duplicate_field_name_collision_rejected_at_freeze():
    """
    **Feature: 2-projects M2 Extension collision (Requirement 4.3)**
    **Property: Registering two ProjectMetadataFieldExtension classes
    with the same field_name raises ConfigurationError during
    freeze_registry(), naming both offenders.**
    """
    reset_phase1_runtime()

    reset_projects_metadata_registry()
    register_resource_extension(
        base_class=ProjectMetadataFieldExtension,
        extension=CollisionFieldExtension,
    )

    raised = False
    err_text = ""
    try:
        freeze_registry()
    except ConfigurationError as xcpt:
        raised = True
        err_text = str(xcpt)

    testbase.assert_equal(raised, True)
    testbase.assert_equal("Duplicate field_name" in err_text, True)
    testbase.assert_equal("cost_center" in err_text, True)
    return
