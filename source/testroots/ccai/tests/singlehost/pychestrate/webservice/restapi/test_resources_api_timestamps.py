"""
.. module:: test_resources_api_timestamps
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The resources REST API serialises every datetime as RFC 3339
               with an explicit UTC offset (audit finding RES-20).

.. moduleauthor:: Code Craft AI LLC

The resource-pools and resources endpoints returned ``created_at`` and friends
as naive ISO text on SQLite (``2026-09-22T23:34:26.123456``). Browsers read an
offset-less date-time as local time, so the pool detail view showed a pool
created at 4:34 PM PDT as "11:34:26 PM" in Los Angeles. The timestamps now
always carry the UTC offset, and the models hand back aware UTC values.

**Feature: resources (RES-20 REST timestamps)**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import uuid

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base
from ccai.pychestrate.webservice.resources.pools.models import ResourcePool
from ccai.pychestrate.webservice.resources.restapi.v1 import (
    resource_pools_routes,
    resources_routes,
)


class _Query:
    def __init__(self) -> None:
        return

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return default


class _Request:
    def __init__(self, *, path: str, path_params: Dict[str, Any], db_session: Any) -> None:
        self.path = path
        self.path_params = path_params
        self.query_params = _Query()
        self.db_session = db_session
        self.auth_principal = type("Principal", (), {"user_id": "user-1"})()
        return


class _Allowed:
    allowed = True
    reason = ""


def _stored_pool(*, created_at: datetime) -> Any:
    """
        A SQLite database holding one resource pool created at
        ``created_at``. Returns ``(session_factory, pool_id)``.
    """
    engine = sa.create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False},
    )
    PychestratePhase1Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    pool_id = uuid.uuid4()
    session.add(ResourcePool(
        pool_id=pool_id, project_id=uuid.uuid4(), name="android-phones", description="",
        capability_tags=[], created_at=created_at, updated_at=created_at,
    ))
    session.commit()
    session.close()
    rtnval = (factory, str(pool_id))
    return rtnval


def _read_pool_body(*, factory: Any, pool_id: str) -> Dict[str, Any]:
    patch = create_module_patch(resource_pools_routes.rbac_evaluator, "check_permission")
    mock = patch.activate()
    mock.configure(side_effect=lambda **kwargs: _Allowed())
    try:
        response = resource_pools_routes.handle_read_resource_pool(_Request(
            path="/api/v1/resource-pools/" + pool_id,
            path_params={"pool_id": pool_id},
            db_session=factory(),
        ))
    finally:
        patch.deactivate()
    rtnval = json.loads(response.body.decode("utf-8"))
    return rtnval


def test_pool_created_at_is_sent_with_a_utc_offset():
    """
    **Feature: resources (RES-20 REST timestamps)**
    **Property: GET /api/v1/resource-pools/{id} on SQLite returns
    created_at as RFC 3339 with the +00:00 offset.**
    """
    factory, pool_id = _stored_pool(created_at=datetime(2026, 9, 22, 23, 34, 26, tzinfo=timezone.utc))

    body = _read_pool_body(factory=factory, pool_id=pool_id)

    testbase.assert_equal(body["created_at"], "2026-09-22T23:34:26+00:00")
    return


def test_pool_created_in_another_zone_is_sent_as_the_same_instant():
    """
    **Feature: resources (RES-20 REST timestamps)**
    **Property: a pool stored with 16:34 at UTC-7 is returned as
    23:34 UTC, the same instant.**
    """
    pacific = timezone(timedelta(hours=-7))
    factory, pool_id = _stored_pool(created_at=datetime(2026, 9, 22, 16, 34, 26, tzinfo=pacific))

    body = _read_pool_body(factory=factory, pool_id=pool_id)

    testbase.assert_equal(body["created_at"], "2026-09-22T23:34:26+00:00")
    return


def test_resource_pool_models_read_back_aware_utc():
    """
    **Feature: resources (RES-20 REST timestamps)**
    **Property: the resource-pool model reads its timestamps back from
    SQLite as timezone-aware UTC values.**
    """
    factory, pool_id = _stored_pool(created_at=datetime(2026, 9, 22, 23, 34, 26, tzinfo=timezone.utc))
    session = factory()

    row = session.query(ResourcePool).filter(ResourcePool.pool_id == uuid.UUID(pool_id)).one()

    testbase.assert_equal(row.created_at.utcoffset(), timedelta(0))
    return


def test_resources_serializer_sends_a_naive_value_as_utc():
    """
    **Feature: resources (RES-20 REST timestamps)**
    **Property: the per-resource endpoints' serializer sends a naive
    datetime (as SQLite returns them) as UTC with an explicit offset.**
    """
    serialized = resources_routes._iso_or_none(datetime(2026, 9, 22, 23, 34, 26))

    testbase.assert_equal(serialized, "2026-09-22T23:34:26+00:00")
    return


def test_pools_serializer_sends_a_naive_value_as_utc():
    """
    **Feature: resources (RES-20 REST timestamps)**
    **Property: the resource-pools serializer sends a naive datetime as
    UTC with an explicit offset.**
    """
    serialized = resource_pools_routes._iso_or_none(datetime(2026, 9, 22, 23, 34, 26))

    testbase.assert_equal(serialized, "2026-09-22T23:34:26+00:00")
    return
