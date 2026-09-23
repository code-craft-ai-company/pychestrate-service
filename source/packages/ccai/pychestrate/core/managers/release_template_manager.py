"""
.. module:: release_template_manager
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Contains the :class:`ReleaseTemplateManager` for
               project-scoped release-template CRUD.

.. moduleauthor:: Code Craft AI LLC

This module provides the :class:`ReleaseTemplateManager` class
which handles project-scoped release-template CRUD operations.

A release template captures the default values used when creating
a new release inside a project: default channel, default version
pattern, default repository IDs, default pipeline blob, and
default schedule blob.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import re

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import utc_now


# =============================================================================
# Validation constants
# =============================================================================

# Template name validation: alphanumeric, underscore, hyphen, period.
# Must start with alphanumeric, 1-128 characters.
TEMPLATE_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.\-]{0,127}\Z')


# =============================================================================
# Request / Response dataclasses
# =============================================================================


@dataclass
class ReleaseTemplateResponse:
    """Response dataclass for a release-template row."""
    id: int
    project_id: int
    name: str
    description: str
    default_channel: Optional[str]
    version_pattern: Optional[str]
    default_repo_ids: List[int]
    default_pipeline: Optional[Dict[str, Any]]
    default_schedule: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime


@dataclass
class ReleaseTemplateListResponse:
    """Paginated list of :class:`ReleaseTemplateResponse`."""
    templates: List[ReleaseTemplateResponse] = field(default_factory=list)
    total: int = 0
    offset: int = 0
    limit: int = 0


# =============================================================================
# Exceptions
# =============================================================================


class ReleaseTemplateNotFoundError(Exception):
    """Raised when a release template cannot be found."""

    def __init__(
            self,
            message: str,
            error_code: str = "RELEASE_TEMPLATE_NOT_FOUND"
        ) -> None:
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)
        return


class DuplicateReleaseTemplateError(Exception):
    """Raised when a release template name already exists in the project."""

    def __init__(
            self,
            message: str,
            field_name: Optional[str] = None,
            error_code: str = "RELEASE_TEMPLATE_NAME_EXISTS"
        ) -> None:
        self.message = message
        self.field = field_name
        self.error_code = error_code
        super().__init__(self.message)
        return


class ReleaseTemplateValidationError(Exception):
    """Raised when release-template validation fails."""

    def __init__(
            self,
            message: str,
            field_name: Optional[str] = None,
            error_code: str = "RELEASE_TEMPLATE_VALIDATION_ERROR"
        ) -> None:
        self.message = message
        self.field = field_name
        self.error_code = error_code
        super().__init__(self.message)
        return


class ReleaseTemplateProjectNotFoundError(Exception):
    """Raised when the parent project cannot be found."""

    def __init__(
            self,
            message: str,
            error_code: str = "PROJECT_NOT_FOUND"
        ) -> None:
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)
        return


# =============================================================================
# Validation helpers
# =============================================================================


def validate_template_name(name: str) -> bool:
    """
        Validate that ``name`` conforms to the template-name pattern.

        :param name: Candidate template name.

        :returns: ``True`` when valid, ``False`` otherwise.
    """
    if name is None:
        return False

    if len(name) == 0:
        return False

    match = TEMPLATE_NAME_PATTERN.match(name)
    if match is None:
        return False

    rtnval = True
    return rtnval


def validate_default_repo_ids(repo_ids: Any) -> List[str]:
    """
        Validate that ``repo_ids`` is a list of non-negative
        integers.

        :param repo_ids: Candidate repository-id list.

        :returns: List of validation error messages (empty when valid).
    """
    errors: List[str] = []

    if repo_ids is None:
        return errors

    if not isinstance(repo_ids, list):
        errors.append("default_repo_ids must be a list.")
        return errors

    for index, candidate in enumerate(repo_ids):
        if not isinstance(candidate, int):
            errors.append(
                "default_repo_ids[{}]: must be an integer.".format(index)
            )
            continue
        if candidate < 0:
            errors.append(
                "default_repo_ids[{}]: must be >= 0.".format(index)
            )

    return errors


# =============================================================================
# Manager
# =============================================================================


class ReleaseTemplateManager:
    """
        Manager class for project-scoped release-template CRUD.

        Provides:

        * ``list_for_project``  -- paginated list scoped to a project.
        * ``create``            -- create a template inside a project.
        * ``get``               -- read a template by id.
        * ``update``            -- patch one or more fields on a template.
        * ``delete``            -- delete a template by id.

        All methods route through the ORM and emit audit events
        when an ``audit_logger`` is supplied.
    """

    def __init__(
            self,
            db_session: DbSession,
            audit_logger: Any = None
        ) -> None:
        """
            Initialize the manager.

            :param db_session: SQLAlchemy session.
            :param audit_logger: Optional ``AuditLogger`` instance for
                                 audit event emission.
        """
        self._db_session = db_session
        self._audit_logger = audit_logger
        return

    # -------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------

    def _template_to_response(
            self, template: Any
        ) -> ReleaseTemplateResponse:
        """
            Convert a :class:`ProjectReleaseTemplate` ORM row to a
            :class:`ReleaseTemplateResponse` dataclass.

            :param template: ORM row.

            :returns: Dataclass response.
        """
        repo_ids_raw = template.default_repo_ids
        if repo_ids_raw is None:
            repo_ids = []
        else:
            repo_ids = list(repo_ids_raw)

        description = template.description
        if description is None:
            description = ""

        rtnval = ReleaseTemplateResponse(
            id=template.id,
            project_id=template.project_id,
            name=template.name,
            description=description,
            default_channel=template.default_channel,
            version_pattern=template.version_pattern,
            default_repo_ids=repo_ids,
            default_pipeline=template.default_pipeline,
            default_schedule=template.default_schedule,
            created_at=template.created_at,
            updated_at=template.updated_at,
        )
        return rtnval

    def _verify_project_exists(self, project_id: int) -> None:
        """
            Ensure a :class:`Project` row exists with the given id.

            :param project_id: Candidate project id.

            :raises ReleaseTemplateProjectNotFoundError: When the
                project does not exist.
        """
        from ccai.pychestrate.core.orm import Project  # noqa: E402

        project = self._db_session.query(Project).filter(
            Project.id == project_id
        ).first()

        if project is None:
            err_msg_lines = ["Project not found."]
            err_msg_lines.append(
                "PROJECT_ID: {}".format(project_id)
            )
            err_msg = os.linesep.join(err_msg_lines)
            raise ReleaseTemplateProjectNotFoundError(err_msg) from None

        return

    def _validate_inputs(
            self,
            *,
            name: Optional[str],
            default_repo_ids: Any,
            require_name: bool
        ) -> None:
        """
            Validate the writable fields shared by ``create`` and
            ``update``.

            :param name: Candidate template name (may be ``None`` on
                         update).
            :param default_repo_ids: Candidate repository-id list (may
                                     be ``None`` on update).
            :param require_name: ``True`` to require ``name`` to be
                                 non-None and valid (create path).

            :raises ReleaseTemplateValidationError: On any validation
                error.
        """
        if require_name is True:
            if validate_template_name(name) is False:
                err_msg_lines = [
                    "Release template name failed validation."
                ]
                err_msg_lines.append("NAME: {!r}".format(name))
                err_msg_lines.append(
                    "RULE: must be 1-128 chars, start with alphanumeric, "
                    "and contain only alphanumeric, underscore, hyphen, "
                    "or period."
                )
                err_msg = os.linesep.join(err_msg_lines)
                raise ReleaseTemplateValidationError(
                    err_msg, field_name="name", error_code="INVALID_NAME"
                ) from None
        else:
            if name is not None:
                if validate_template_name(name) is False:
                    err_msg_lines = [
                        "Release template name failed validation."
                    ]
                    err_msg_lines.append("NAME: {!r}".format(name))
                    err_msg = os.linesep.join(err_msg_lines)
                    raise ReleaseTemplateValidationError(
                        err_msg,
                        field_name="name",
                        error_code="INVALID_NAME",
                    ) from None

        repo_errors = validate_default_repo_ids(default_repo_ids)
        if len(repo_errors) > 0:
            err_msg_lines = [
                "Release template default_repo_ids failed validation."
            ]
            err_msg_lines.extend(repo_errors)
            err_msg = os.linesep.join(err_msg_lines)
            raise ReleaseTemplateValidationError(
                err_msg,
                field_name="default_repo_ids",
                error_code="INVALID_DEFAULT_REPO_IDS",
            ) from None

        return

    # -------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------

    def list_for_project(
            self,
            project_id: int,
            *,
            offset: int = 0,
            limit: int = 50
        ) -> ReleaseTemplateListResponse:
        """
            List release templates scoped to a single project.

            :param project_id: The project the templates belong to.
            :param offset: Pagination offset.
            :param limit: Pagination page size.

            :returns: :class:`ReleaseTemplateListResponse`.
        """
        from ccai.pychestrate.core.orm import (  # noqa: E402
            ProjectReleaseTemplate,
        )

        query = self._db_session.query(ProjectReleaseTemplate).filter(
            ProjectReleaseTemplate.project_id == project_id
        )
        total = query.count()

        rows = query.order_by(ProjectReleaseTemplate.name.asc()).offset(
            offset
        ).limit(limit).all()

        items: List[ReleaseTemplateResponse] = []
        for row in rows:
            items.append(self._template_to_response(row))

        rtnval = ReleaseTemplateListResponse(
            templates=items,
            total=int(total),
            offset=int(offset),
            limit=int(limit),
        )
        return rtnval

    def create(
            self,
            project_id: int,
            *,
            name: str,
            description: str = "",
            default_channel: Optional[str] = None,
            version_pattern: Optional[str] = None,
            default_repo_ids: Optional[List[int]] = None,
            default_pipeline: Optional[Dict[str, Any]] = None,
            default_schedule: Optional[Dict[str, Any]] = None,
            created_by: Optional[str] = None
        ) -> ReleaseTemplateResponse:
        """
            Create a new release template inside a project.

            :param project_id: Project the template belongs to.
            :param name: Template name (unique inside the project).
            :param description: Optional human description.
            :param default_channel: Optional default channel name.
            :param version_pattern: Optional version pattern.
            :param default_repo_ids: Optional list of default
                                     repository ids.
            :param default_pipeline: Optional default pipeline blob.
            :param default_schedule: Optional default schedule blob.
            :param created_by: Optional actor id for audit logging.

            :returns: :class:`ReleaseTemplateResponse` for the new
                      template.

            :raises ReleaseTemplateProjectNotFoundError: Project
                does not exist.
            :raises ReleaseTemplateValidationError: Validation
                failed.
            :raises DuplicateReleaseTemplateError: A template with
                the same name already exists inside the project.
        """
        from ccai.pychestrate.core.orm import (  # noqa: E402
            ProjectReleaseTemplate,
        )

        if default_repo_ids is None:
            repo_ids_value: List[int] = []
        else:
            repo_ids_value = list(default_repo_ids)

        self._validate_inputs(
            name=name,
            default_repo_ids=repo_ids_value,
            require_name=True,
        )
        self._verify_project_exists(project_id=project_id)

        existing = self._db_session.query(ProjectReleaseTemplate).filter(
            ProjectReleaseTemplate.project_id == project_id,
            ProjectReleaseTemplate.name == name,
        ).first()
        if existing is not None:
            err_msg_lines = [
                "Release template with this name already exists in project."
            ]
            err_msg_lines.append("PROJECT_ID: {}".format(project_id))
            err_msg_lines.append("NAME: {}".format(name))
            err_msg = os.linesep.join(err_msg_lines)
            raise DuplicateReleaseTemplateError(
                err_msg, field_name="name"
            ) from None

        now = utc_now()
        template = ProjectReleaseTemplate(
            project_id=project_id,
            name=name,
            description=description if len(description) > 0 else None,
            default_channel=default_channel,
            version_pattern=version_pattern,
            default_repo_ids=repo_ids_value,
            default_pipeline=default_pipeline,
            default_schedule=default_schedule,
            created_at=now,
            updated_at=now,
        )
        self._db_session.add(template)
        self._db_session.commit()
        self._db_session.refresh(template)

        if self._audit_logger is not None:
            self._audit_logger.log_event(
                event_type='release_template_created',
                user_id=str(created_by) if created_by is not None else None,
                details={
                    "project_id": project_id,
                    "template_id": template.id,
                    "template_name": template.name,
                },
            )

        rtnval = self._template_to_response(template)
        return rtnval

    def get(self, template_id: int) -> Optional[ReleaseTemplateResponse]:
        """
            Fetch a release template by id.

            :param template_id: Template id.

            :returns: :class:`ReleaseTemplateResponse` or ``None`` when
                      no row matches.
        """
        from ccai.pychestrate.core.orm import (  # noqa: E402
            ProjectReleaseTemplate,
        )

        template = self._db_session.query(ProjectReleaseTemplate).filter(
            ProjectReleaseTemplate.id == template_id
        ).first()

        if template is None:
            return None

        rtnval = self._template_to_response(template)
        return rtnval

    def update(
            self,
            template_id: int,
            *,
            name: Optional[str] = None,
            description: Optional[str] = None,
            default_channel: Optional[str] = None,
            version_pattern: Optional[str] = None,
            default_repo_ids: Optional[List[int]] = None,
            default_pipeline: Optional[Dict[str, Any]] = None,
            default_schedule: Optional[Dict[str, Any]] = None,
            updated_by: Optional[str] = None
        ) -> ReleaseTemplateResponse:
        """
            Update one or more fields on a release template.

            All keyword arguments are optional. Fields set to ``None``
            are left untouched.

            :param template_id: Template id.
            :param name: New template name.
            :param description: New description.
            :param default_channel: New default channel.
            :param version_pattern: New version pattern.
            :param default_repo_ids: New default repository ids.
            :param default_pipeline: New default pipeline blob.
            :param default_schedule: New default schedule blob.
            :param updated_by: Optional actor id for audit logging.

            :returns: :class:`ReleaseTemplateResponse` for the updated
                      template.

            :raises ReleaseTemplateNotFoundError: Template not found.
            :raises ReleaseTemplateValidationError: Validation failed.
            :raises DuplicateReleaseTemplateError: ``name`` collides
                with another template in the project.
        """
        from ccai.pychestrate.core.orm import (  # noqa: E402
            ProjectReleaseTemplate,
        )

        template = self._db_session.query(ProjectReleaseTemplate).filter(
            ProjectReleaseTemplate.id == template_id
        ).first()

        if template is None:
            err_msg_lines = ["Release template not found."]
            err_msg_lines.append("TEMPLATE_ID: {}".format(template_id))
            err_msg = os.linesep.join(err_msg_lines)
            raise ReleaseTemplateNotFoundError(err_msg) from None

        self._validate_inputs(
            name=name,
            default_repo_ids=default_repo_ids,
            require_name=False,
        )

        if name is not None and name != template.name:
            existing = self._db_session.query(
                ProjectReleaseTemplate
            ).filter(
                ProjectReleaseTemplate.project_id == template.project_id,
                ProjectReleaseTemplate.name == name,
                ProjectReleaseTemplate.id != template_id,
            ).first()
            if existing is not None:
                err_msg_lines = [
                    "Release template with this name already exists in "
                    "project."
                ]
                err_msg_lines.append(
                    "PROJECT_ID: {}".format(template.project_id)
                )
                err_msg_lines.append("NAME: {}".format(name))
                err_msg = os.linesep.join(err_msg_lines)
                raise DuplicateReleaseTemplateError(
                    err_msg, field_name="name"
                ) from None
            template.name = name

        if description is not None:
            if len(description) == 0:
                template.description = None
            else:
                template.description = description

        if default_channel is not None:
            template.default_channel = default_channel

        if version_pattern is not None:
            template.version_pattern = version_pattern

        if default_repo_ids is not None:
            template.default_repo_ids = list(default_repo_ids)

        if default_pipeline is not None:
            template.default_pipeline = default_pipeline

        if default_schedule is not None:
            template.default_schedule = default_schedule

        template.updated_at = utc_now()
        self._db_session.commit()
        self._db_session.refresh(template)

        if self._audit_logger is not None:
            self._audit_logger.log_event(
                event_type='release_template_updated',
                user_id=str(updated_by) if updated_by is not None else None,
                details={
                    "project_id": template.project_id,
                    "template_id": template.id,
                    "template_name": template.name,
                },
            )

        rtnval = self._template_to_response(template)
        return rtnval

    def delete(
            self,
            template_id: int,
            *,
            deleted_by: Optional[str] = None
        ) -> None:
        """
            Delete a release template by id.

            :param template_id: Template id.
            :param deleted_by: Optional actor id for audit logging.

            :raises ReleaseTemplateNotFoundError: Template not found.
        """
        from ccai.pychestrate.core.orm import (  # noqa: E402
            ProjectReleaseTemplate,
        )

        template = self._db_session.query(ProjectReleaseTemplate).filter(
            ProjectReleaseTemplate.id == template_id
        ).first()

        if template is None:
            err_msg_lines = ["Release template not found."]
            err_msg_lines.append("TEMPLATE_ID: {}".format(template_id))
            err_msg = os.linesep.join(err_msg_lines)
            raise ReleaseTemplateNotFoundError(err_msg) from None

        project_id = template.project_id
        template_name = template.name

        self._db_session.delete(template)
        self._db_session.commit()

        if self._audit_logger is not None:
            self._audit_logger.log_event(
                event_type='release_template_deleted',
                user_id=str(deleted_by) if deleted_by is not None else None,
                details={
                    "project_id": project_id,
                    "template_id": template_id,
                    "template_name": template_name,
                },
            )

        return

    # -------------------------------------------------------------------
    # Releases from a template
    # -------------------------------------------------------------------

    def build_release_request(
            self,
            template: ReleaseTemplateResponse,
            *,
            version: str,
            name: Optional[str] = None,
            description: Optional[str] = None,
            metadata: Optional[Dict[str, Any]] = None
        ) -> Any:
        """
            Fold a template's defaults into a ``ReleaseCreateRequest``.

            ``version`` is required -- there is no sane template default
            for an exact release version -- and must match the
            template's ``version_pattern`` when it has one. ``name`` and
            ``description`` fall back to the template's. The release
            metadata records where the release came from
            (``template_id`` / ``template_name``) and the template's
            ``channel``, ``version_pattern``, ``repository_ids``,
            ``pipeline`` and ``schedule`` defaults; keys in ``metadata``
            overwrite them.

            :param template: The template to apply.
            :param version: Release version (e.g. ``1.4.0``).
            :param name: Optional release name.
            :param description: Optional release description.
            :param metadata: Optional metadata overrides.

            :returns: ``ReleaseCreateRequest`` for
                      :meth:`ReleaseManager.create_release`.

            :raises ReleaseTemplateValidationError: missing version, or
                a version that does not match the template's pattern.
        """
        from ccai.pychestrate.core.managers.release_manager import (  # noqa: E402
            ReleaseCreateRequest,
        )

        effective_version = version.strip() if isinstance(version, str) else ""
        if len(effective_version) == 0:
            raise ReleaseTemplateValidationError(
                "Enter the release version, for example 1.4.0.",
                field_name="version",
                error_code="MISSING_VERSION",
            ) from None

        pattern = template.version_pattern
        if pattern is not None and len(pattern) > 0:
            try:
                matches = re.fullmatch(pattern, effective_version) is not None
            except re.error:
                matches = False
            if matches is False:
                raise ReleaseTemplateValidationError(
                    "Version {} does not match this template's version "
                    "pattern {}.".format(effective_version, pattern),
                    field_name="version",
                    error_code="VERSION_PATTERN_MISMATCH",
                ) from None

        if isinstance(name, str) and len(name.strip()) > 0:
            effective_name = name.strip()
        else:
            effective_name = "{0} {1}".format(template.name, effective_version)

        if isinstance(description, str):
            effective_description = description
        else:
            effective_description = template.description

        merged_metadata: Dict[str, Any] = {}
        if template.default_channel is not None and len(template.default_channel) > 0:
            merged_metadata["channel"] = template.default_channel
        if template.version_pattern is not None and len(template.version_pattern) > 0:
            merged_metadata["version_pattern"] = template.version_pattern
        if template.default_repo_ids is not None and len(template.default_repo_ids) > 0:
            merged_metadata["repository_ids"] = list(template.default_repo_ids)
        if template.default_pipeline is not None:
            merged_metadata["pipeline"] = template.default_pipeline
        if template.default_schedule is not None:
            merged_metadata["schedule"] = template.default_schedule
        merged_metadata["template_id"] = template.id
        merged_metadata["template_name"] = template.name

        if isinstance(metadata, dict):
            for key, value in metadata.items():
                merged_metadata[key] = value

        rtnval = ReleaseCreateRequest(
            version=effective_version,
            name=effective_name,
            description=effective_description,
            metadata=merged_metadata,
        )
        return rtnval

    def create_release_from_template(
            self,
            project_id: int,
            template_id: int,
            *,
            version: str,
            name: Optional[str] = None,
            description: Optional[str] = None,
            metadata: Optional[Dict[str, Any]] = None,
            user_id: Optional[str] = None,
            release_manager: Any = None
        ) -> Any:
        """
            Create a draft release in ``project_id`` from one of the
            project's release templates (see
            :meth:`build_release_request` for how the defaults apply).

            :param project_id: Project the release goes into.
            :param template_id: Template to apply; must belong to the
                                project.
            :param version: Release version.
            :param name: Optional release name.
            :param description: Optional release description.
            :param metadata: Optional metadata overrides.
            :param user_id: Acting user, for the audit trail.
            :param release_manager: Optional ``ReleaseManager`` (built
                                    on this manager's session when
                                    omitted).

            :returns: The ``ReleaseResponse`` of the new release.

            :raises ReleaseTemplateNotFoundError: the template does not
                exist in the project.
            :raises ReleaseTemplateValidationError: see
                :meth:`build_release_request`.
            :raises ReleaseVersionValidationError: the version is not a
                semantic version.
            :raises DuplicateReleaseVersionError: the project already has
                a release with that version.
        """
        template = self.get(template_id)
        if template is None or template.project_id != project_id:
            err_msg_lines = ["Release template not found in this project."]
            err_msg_lines.append("TEMPLATE_ID: {}".format(template_id))
            err_msg = os.linesep.join(err_msg_lines)
            raise ReleaseTemplateNotFoundError(err_msg) from None

        release_request = self.build_release_request(
            template,
            version=version,
            name=name,
            description=description,
            metadata=metadata,
        )

        if release_manager is None:
            from ccai.pychestrate.core.managers.release_manager import (  # noqa: E402
                ReleaseManager,
            )
            release_manager = ReleaseManager(self._db_session)

        rtnval = release_manager.create_release(
            project_id=project_id,
            request=release_request,
            user_id=user_id,
        )
        return rtnval
