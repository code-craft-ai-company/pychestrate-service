"""
.. module:: tagging.service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Public internal API for 2-tagging.

.. moduleauthor:: Code Craft AI LLC

M1 only supports the ``project`` entity kind. Other kinds (resource, pod,
job, artifact) gain wiring in M2. No bus events are published — tagging
is deliberately high-volume and subscribers rely on the target entity's
own lifecycle topics for orphan cleanup in M3.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.errors.exceptions import SemanticError

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.tagging.canonical import canonicalize_tag
from ccai.pychestrate.webservice.tagging.exceptions import (
    TagAssignmentNotFoundError,
)
from ccai.pychestrate.webservice.tagging.models import TagAssignment
from ccai.pychestrate.webservice.tagging.registry import get_taxonomy
from ccai.pychestrate.webservice.tagging import repository as tag_repository


_SUPPORTED_ENTITY_KINDS = frozenset({"project", "resource", "pod", "job", "artifact"})


def assign_tag(
        *,
        db_session: DbSession,
        entity_kind: str,
        entity_id: str,
        raw_tag: str,
        actor_user_id: Optional[str]
    ) -> TagAssignment:
    """
        Assign a tag (``taxonomy:value``) to an entity.

        :param db_session: Active SQLAlchemy session.
        :param entity_kind: Entity kind (``project`` at M1).
        :param entity_id: Entity id.
        :param raw_tag: Caller input in ``taxonomy:value`` form.
        :param actor_user_id: Acting principal; attributed on the row.

        :returns: The persisted :class:`TagAssignment`.
        :raises: SemanticError, TagValueValidationError, TaxonomyNotFoundError
    """
    _require_supported_kind(entity_kind=entity_kind)

    taxonomy_name_guess, _, _ = raw_tag.partition(":")
    taxonomy_name_guess = taxonomy_name_guess.strip().lower()

    taxonomy = get_taxonomy(taxonomy_name=taxonomy_name_guess)
    (taxonomy_name, canonical_value) = canonicalize_tag(raw_tag=raw_tag, taxonomy=taxonomy)

    taxonomy.validate_value(canonical_value=canonical_value)

    existing = tag_repository.get_assignment(
        db_session=db_session,
        entity_kind=entity_kind,
        entity_id=entity_id,
        taxonomy_name=taxonomy_name,
        canonical_value=canonical_value,
    )
    if existing is not None:
        rtnval = existing
        return rtnval

    assignment = TagAssignment(
        assignment_id=new_uuid(),
        entity_kind=entity_kind,
        entity_id=entity_id,
        taxonomy_name=taxonomy_name,
        canonical_value=canonical_value,
        assigned_by_user_id=actor_user_id,
        assigned_at=utc_now(),
    )
    tag_repository.insert_assignment(db_session=db_session, assignment=assignment)

    db_session.commit()

    rtnval = assignment
    return rtnval


def remove_tag(
        *,
        db_session: DbSession,
        entity_kind: str,
        entity_id: str,
        raw_tag: str
    ) -> None:
    """
        Remove a previously assigned tag.

        :param db_session: Active SQLAlchemy session.
        :param entity_kind: Entity kind.
        :param entity_id: Entity id.
        :param raw_tag: ``taxonomy:value`` tag to remove.

        :returns: None.
        :raises: TagAssignmentNotFoundError
    """
    _require_supported_kind(entity_kind=entity_kind)

    taxonomy_name_guess, _, _ = raw_tag.partition(":")
    taxonomy_name_guess = taxonomy_name_guess.strip().lower()
    taxonomy = get_taxonomy(taxonomy_name=taxonomy_name_guess)

    (taxonomy_name, canonical_value) = canonicalize_tag(raw_tag=raw_tag, taxonomy=taxonomy)

    existing = tag_repository.get_assignment(
        db_session=db_session,
        entity_kind=entity_kind,
        entity_id=entity_id,
        taxonomy_name=taxonomy_name,
        canonical_value=canonical_value,
    )
    if existing is None:
        err_msg_lines = ["Cannot remove tag — no matching assignment."]
        err_msg_lines.append("ENTITY: {}/{}".format(entity_kind, entity_id))
        err_msg_lines.append("TAG: {}:{}".format(taxonomy_name, canonical_value))
        err_msg = os.linesep.join(err_msg_lines)
        raise TagAssignmentNotFoundError(err_msg) from None

    tag_repository.delete_assignment(db_session=db_session, assignment=existing)
    db_session.commit()
    return


def search_entities(
        *,
        db_session: DbSession,
        entity_kind: str,
        expression: str
    ) -> List[str]:
    """
        Return entity ids whose tag set satisfies ``expression``.

        :param db_session: Active SQLAlchemy session.
        :param entity_kind: Entity kind to search.
        :param expression: Boolean tag expression.

        :returns: List of entity id strings.
        :raises: SemanticError, TagValueValidationError
    """
    from ccai.pychestrate.webservice.tagging.expression import compile_tag_expression

    _require_supported_kind(entity_kind=entity_kind)
    predicate = compile_tag_expression(expression=expression)

    rows = tag_repository.list_for_kind(db_session=db_session, entity_kind=entity_kind)

    by_entity = {}
    for row in rows:
        eid = str(row.entity_id)
        bucket = by_entity.setdefault(eid, set())
        term = "{}:{}".format(row.taxonomy_name, row.canonical_value).lower()
        bucket.add(term)

    rtnval: List[str] = []
    for eid, tag_set in by_entity.items():
        if predicate(frozenset(tag_set)) is True:
            rtnval.append(eid)

    rtnval.sort()
    return rtnval


def list_tags(
        *,
        db_session: DbSession,
        entity_kind: str,
        entity_id: str
    ) -> List[TagAssignment]:
    """
        Return every tag assigned to the given entity.

        :param db_session: Active SQLAlchemy session.
        :param entity_kind: Entity kind.
        :param entity_id: Entity id.

        :returns: List of :class:`TagAssignment` rows.
    """
    _require_supported_kind(entity_kind=entity_kind)

    rtnval = tag_repository.list_for_entity(
        db_session=db_session,
        entity_kind=entity_kind,
        entity_id=entity_id,
    )
    return rtnval


def _require_supported_kind(*, entity_kind: str) -> None:
    """
        Raise :class:`SemanticError` when ``entity_kind`` is not supported.

        :param entity_kind: The candidate entity kind.

        :returns: None.
        :raises: SemanticError
    """
    if entity_kind is None or entity_kind not in _SUPPORTED_ENTITY_KINDS:
        err_msg_lines = ["Tagging for this entity kind is not supported at M1."]
        err_msg_lines.append("ENTITY_KIND: {}".format(entity_kind))
        err_msg_lines.append("SUPPORTED: {}".format(sorted(_SUPPORTED_ENTITY_KINDS)))
        err_msg = os.linesep.join(err_msg_lines)
        raise SemanticError(err_msg)

    return
