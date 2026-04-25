"""
.. module:: test_p5a_matrix_sharding_m1
    :synopsis: Tests for P5a — 6-matrix-sharding M1.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import List

from automojo import testbase

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.extensions.registry import (
    reset_registry_for_testing,
)
from automojo.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    reset_for_testing as reset_event_bus,
    subscribe,
)
from automojo.pychestrate.webservice.orchestration.pipelines.sharding import (
    CartesianShardingStrategy,
    ExpandAspects,
    FailFastCartesianStrategy,
    MatrixDimensionFilter,
    MatrixSpec,
    MatrixSpecInvalidError,
    ShardSetNotFoundError,
    ShardSetState,
    ShardState,
    ShardingEventTopics,
    ShardingStrategyNotFoundError,
    bind_shard_to_run,
    canonicalize_matrix_spec,
    compute_shard_id,
    expand_matrix,
    get_shard_set,
    list_shards_for_set,
    register_builtin_extensions as sharding_register,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


PROJECT_UUID = "00000000-0000-4000-8000-0000000000d5"
PARENT_UUID = "00000000-0000-4000-8000-0000000000d6"
RUN_UUID = "00000000-0000-4000-8000-0000000000d7"


def _prepare_runtime() -> None:
    """
        Reset cross-test globals + register the in-tree
        sharding strategies.
    """
    reset_registry_for_testing()
    reset_event_bus()
    sharding_register()
    return


# -------------------------------------
# expansion primitives
# -------------------------------------

def test_compute_shard_id_is_deterministic_and_short():
    """
    **Feature: 6-matrix-sharding (M1)**
    **Property: compute_shard_id returns a 16-char hex digest
    that depends only on the dimension-tuple, regardless of key
    ordering at call time.**
    """
    a = compute_shard_id(
        dimension_values={"os": "linux", "py": "3.12"},
    )
    b = compute_shard_id(
        dimension_values={"py": "3.12", "os": "linux"},
    )
    c = compute_shard_id(
        dimension_values={"os": "darwin", "py": "3.12"},
    )
    testbase.assert_equal(len(a), 16)
    testbase.assert_equal(a, b)
    testbase.assert_equal(a == c, False)
    return


def test_canonical_matrix_spec_is_stable():
    """
    **Feature: 6-matrix-sharding (M1)**
    **Property: canonicalize_matrix_spec produces identical
    output regardless of dictionary ordering.**
    """
    spec_a = MatrixSpec(
        dimensions={"os": ["linux", "darwin"], "py": ["3.11", "3.12"]},
    )
    spec_b = MatrixSpec(
        dimensions={"py": ["3.11", "3.12"], "os": ["linux", "darwin"]},
    )
    canon_a = canonicalize_matrix_spec(matrix_spec=spec_a)
    canon_b = canonicalize_matrix_spec(matrix_spec=spec_b)
    testbase.assert_equal(canon_a, canon_b)
    return


# -------------------------------------
# CartesianShardingStrategy
# -------------------------------------

def test_cartesian_strategy_emits_full_product_in_lex_order():
    """
    **Feature: 6-matrix-sharding (M1)**
    **Property: CartesianShardingStrategy.expand returns the
    full cartesian product, lex-ordered by canonical
    dimension-values JSON, with a stable sequence_in_group on
    every shard.**
    """
    _prepare_runtime()
    spec = MatrixSpec(
        dimensions={"os": ["linux", "darwin"], "py": ["3.11", "3.12"]},
    )
    expanded = CartesianShardingStrategy.expand(matrix_spec=spec)
    testbase.assert_equal(len(expanded), 4)
    # Sequence is contiguous starting at 0.
    sequences = sorted(s.sequence_in_group for s in expanded)
    testbase.assert_equal(sequences, [0, 1, 2, 3])
    # Each shard id is unique.
    ids = {s.shard_id for s in expanded}
    testbase.assert_equal(len(ids), 4)
    return


def test_cartesian_strategy_honors_excludes():
    """
    **Feature: 6-matrix-sharding (M1)**
    **Property: excludes drop matching cartesian tuples; the
    sequence-in-group is still contiguous after the drop.**
    """
    _prepare_runtime()
    spec = MatrixSpec(
        dimensions={"os": ["linux", "darwin"], "py": ["3.11", "3.12"]},
        excludes=[
            MatrixDimensionFilter(values={"os": "darwin", "py": "3.11"}),
        ],
    )
    expanded = CartesianShardingStrategy.expand(matrix_spec=spec)
    testbase.assert_equal(len(expanded), 3)
    seqs = sorted(s.sequence_in_group for s in expanded)
    testbase.assert_equal(seqs, [0, 1, 2])
    # The dropped tuple does not appear.
    surviving = {dict(s.dimension_values).get("os") + "/" + dict(s.dimension_values).get("py") for s in expanded}
    testbase.assert_equal("darwin/3.11" in surviving, False)
    return


def test_cartesian_strategy_appends_includes_outside_product():
    """
    **Feature: 6-matrix-sharding (M1)**
    **Property: includes that already match the cartesian
    product are coalesced; includes outside the product are
    appended.**
    """
    _prepare_runtime()
    spec = MatrixSpec(
        dimensions={"os": ["linux"], "py": ["3.12"]},
        includes=[
            MatrixDimensionFilter(values={"os": "linux", "py": "3.12"}),
            MatrixDimensionFilter(values={"os": "windows", "py": "3.13"}),
        ],
    )
    expanded = CartesianShardingStrategy.expand(matrix_spec=spec)
    testbase.assert_equal(len(expanded), 2)
    return


def test_cartesian_strategy_rejects_empty_dimensions():
    """
    **Feature: 6-matrix-sharding (M1)**
    **Property: an empty dimensions dict raises
    MatrixSpecInvalidError before persistence runs.**
    """
    _prepare_runtime()
    spec = MatrixSpec(dimensions={})
    raised = False
    try:
        CartesianShardingStrategy.expand(matrix_spec=spec)
    except MatrixSpecInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_cartesian_strategy_rejects_empty_dimension_value_list():
    """
    **Feature: 6-matrix-sharding (M1)**
    **Property: a dimension with no values raises
    MatrixSpecInvalidError naming the dimension.**
    """
    _prepare_runtime()
    spec = MatrixSpec(dimensions={"os": ["linux"], "py": []})
    raised = False
    try:
        CartesianShardingStrategy.expand(matrix_spec=spec)
    except MatrixSpecInvalidError as xcpt:
        raised = True
        testbase.assert_equal("py" in str(xcpt), True)
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# FailFastCartesianStrategy
# -------------------------------------

def test_fail_fast_strategy_advertises_cancel_on_failure():
    """
    **Feature: 6-matrix-sharding (M1)**
    **Property: FailFastCartesianStrategy.describe declares
    should_cancel_on_failure=True; CartesianShardingStrategy
    declares False.**
    """
    fast_desc = FailFastCartesianStrategy.describe()
    cart_desc = CartesianShardingStrategy.describe()
    testbase.assert_equal(fast_desc.should_cancel_on_failure, True)
    testbase.assert_equal(cart_desc.should_cancel_on_failure, False)
    testbase.assert_equal(fast_desc.strategy_name, "cartesian-fail-fast")
    testbase.assert_equal(cart_desc.strategy_name, "cartesian")
    return


# -------------------------------------
# expand_matrix service
# -------------------------------------

def test_expand_matrix_persists_and_emits():
    """
    **Feature: 6-matrix-sharding (M1)**
    **Property: expand_matrix persists a ShardSet + ShardSpec
    rows, emits entity.shard_set.expanded, and returns a
    ShardSetView with the expected shard_count.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=ShardingEventTopics.EXPANDED,
        subscriber=lambda e: received.append(e),
    )

    spec = MatrixSpec(
        dimensions={"os": ["linux", "darwin"], "py": ["3.12"]},
    )
    view = expand_matrix(
        db_session=session,
        project_id=PROJECT_UUID,
        parent_kind="test_run",
        parent_id=PARENT_UUID,
        matrix_spec=spec,
        strategy_name="cartesian",
    )
    testbase.assert_equal(view.state, ShardSetState.IN_PROGRESS)
    testbase.assert_equal(view.shard_count, 2)
    testbase.assert_equal(len(view.shards), 2)
    testbase.assert_equal(view.fail_fast, False)
    testbase.assert_equal(view.strategy_name, "cartesian")
    testbase.assert_equal(len(view.matrix_spec_canonical_sha256), 64)
    testbase.assert_equal(len(received), 1)
    return


def test_expand_matrix_fail_fast_strategy_sets_fail_fast_true():
    """
    **Feature: 6-matrix-sharding (M1)**
    **Property: expand_matrix with strategy_name="cartesian-fail-fast"
    persists fail_fast=True on the ShardSet row by default.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    spec = MatrixSpec(dimensions={"os": ["linux"]})
    view = expand_matrix(
        db_session=session,
        project_id=PROJECT_UUID,
        parent_kind="test_run",
        parent_id=PARENT_UUID,
        matrix_spec=spec,
        strategy_name="cartesian-fail-fast",
    )
    testbase.assert_equal(view.fail_fast, True)
    return


def test_expand_matrix_unknown_strategy_raises():
    """
    **Feature: 6-matrix-sharding (M1)**
    **Property: an unregistered strategy_name raises
    ShardingStrategyNotFoundError listing the registered
    options.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    spec = MatrixSpec(dimensions={"os": ["linux"]})
    raised = False
    try:
        expand_matrix(
            db_session=session,
            project_id=PROJECT_UUID,
            parent_kind="test_run",
            parent_id=PARENT_UUID,
            matrix_spec=spec,
            strategy_name="nope",
        )
    except ShardingStrategyNotFoundError as xcpt:
        raised = True
        testbase.assert_equal("nope" in str(xcpt), True)
    testbase.assert_equal(raised, True)
    return


def test_expand_matrix_invalid_parent_kind_raises():
    """
    **Feature: 6-matrix-sharding (M1)**
    **Property: an unsupported parent_kind raises
    ShardingStrategyNotFoundError before any expansion runs.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    spec = MatrixSpec(dimensions={"os": ["linux"]})
    raised = False
    try:
        expand_matrix(
            db_session=session,
            project_id=PROJECT_UUID,
            parent_kind="not_a_real_kind",
            parent_id=PARENT_UUID,
            matrix_spec=spec,
            strategy_name="cartesian",
        )
    except ShardingStrategyNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_expand_matrix_aspects_override_fail_fast():
    """
    **Feature: 6-matrix-sharding (M1)**
    **Property: ExpandAspects.fail_fast=True overrides a
    strategy that defaults to fail_fast=False.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    spec = MatrixSpec(dimensions={"os": ["linux", "darwin"]})
    view = expand_matrix(
        db_session=session,
        project_id=PROJECT_UUID,
        parent_kind="test_run",
        parent_id=PARENT_UUID,
        matrix_spec=spec,
        strategy_name="cartesian",
        aspects=ExpandAspects(fail_fast=True),
    )
    testbase.assert_equal(view.fail_fast, True)
    return


# -------------------------------------
# bind_shard_to_run + read helpers
# -------------------------------------

def test_bind_shard_to_run_records_run_id_and_emits():
    """
    **Feature: 6-matrix-sharding (M1)**
    **Property: bind_shard_to_run flips the shard to DISPATCHED,
    persists run_id + dispatched_at, and emits
    entity.shard.bound.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=ShardingEventTopics.SHARD_BOUND,
        subscriber=lambda e: received.append(e),
    )

    spec = MatrixSpec(dimensions={"os": ["linux"]})
    view = expand_matrix(
        db_session=session,
        project_id=PROJECT_UUID,
        parent_kind="test_run",
        parent_id=PARENT_UUID,
        matrix_spec=spec,
        strategy_name="cartesian",
    )
    shard = view.shards[0]
    bound = bind_shard_to_run(
        db_session=session,
        shard_set_id=shard.shard_set_id,
        shard_id=shard.shard_id,
        run_id=RUN_UUID,
    )
    testbase.assert_equal(bound.run_id, RUN_UUID)
    testbase.assert_equal(bound.state, ShardState.DISPATCHED)
    testbase.assert_equal(bound.dispatched_at is not None, True)
    testbase.assert_equal(len(received), 1)

    # Idempotent on the same run_id.
    again = bind_shard_to_run(
        db_session=session,
        shard_set_id=shard.shard_set_id,
        shard_id=shard.shard_id,
        run_id=RUN_UUID,
    )
    testbase.assert_equal(again.run_id, RUN_UUID)
    testbase.assert_equal(len(received), 1)
    return


def test_get_shard_set_returns_shards_in_group_order():
    """
    **Feature: 6-matrix-sharding (M1)**
    **Property: get_shard_set returns the persisted
    ShardSetView with shards ordered by parallel_group then
    sequence_in_group ascending.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    spec = MatrixSpec(
        dimensions={"os": ["linux", "darwin"], "py": ["3.12"]},
    )
    view = expand_matrix(
        db_session=session,
        project_id=PROJECT_UUID,
        parent_kind="test_run",
        parent_id=PARENT_UUID,
        matrix_spec=spec,
        strategy_name="cartesian",
    )
    refreshed = get_shard_set(
        db_session=session, shard_set_id=view.shard_set_id,
    )
    testbase.assert_equal(refreshed.shard_count, 2)
    seqs = [s.sequence_in_group for s in refreshed.shards]
    testbase.assert_equal(seqs, sorted(seqs))
    return


def test_get_shard_set_unknown_raises():
    """
    **Feature: 6-matrix-sharding (M1)**
    **Property: get_shard_set on an unknown id raises
    ShardSetNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        get_shard_set(db_session=session, shard_set_id=new_uuid())
    except ShardSetNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_list_shards_for_set_returns_only_target_set():
    """
    **Feature: 6-matrix-sharding (M1)**
    **Property: list_shards_for_set returns shards only for the
    requested shard_set_id even when multiple sets exist.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    spec_a = MatrixSpec(dimensions={"os": ["linux", "darwin"]})
    spec_b = MatrixSpec(dimensions={"os": ["windows"]})
    view_a = expand_matrix(
        db_session=session,
        project_id=PROJECT_UUID,
        parent_kind="test_run",
        parent_id=PARENT_UUID,
        matrix_spec=spec_a,
        strategy_name="cartesian",
    )
    view_b = expand_matrix(
        db_session=session,
        project_id=PROJECT_UUID,
        parent_kind="test_run",
        parent_id=new_uuid(),
        matrix_spec=spec_b,
        strategy_name="cartesian",
    )
    shards_a = list_shards_for_set(
        db_session=session, shard_set_id=view_a.shard_set_id,
    )
    shards_b = list_shards_for_set(
        db_session=session, shard_set_id=view_b.shard_set_id,
    )
    testbase.assert_equal(len(shards_a), 2)
    testbase.assert_equal(len(shards_b), 1)
    return


def test_expand_matrix_is_deterministic_across_runs():
    """
    **Feature: 6-matrix-sharding (M1)**
    **Property: re-expanding the same MatrixSpec yields the same
    set of shard ids in the same order.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    spec = MatrixSpec(
        dimensions={"os": ["linux", "darwin"], "py": ["3.11", "3.12"]},
    )
    first = expand_matrix(
        db_session=session,
        project_id=PROJECT_UUID,
        parent_kind="test_run",
        parent_id=PARENT_UUID,
        matrix_spec=spec,
        strategy_name="cartesian",
    )
    second = expand_matrix(
        db_session=session,
        project_id=PROJECT_UUID,
        parent_kind="test_run",
        parent_id=new_uuid(),
        matrix_spec=spec,
        strategy_name="cartesian",
    )
    first_ids = [s.shard_id for s in first.shards]
    second_ids = [s.shard_id for s in second.shards]
    testbase.assert_equal(first_ids, second_ids)
    testbase.assert_equal(
        first.matrix_spec_canonical_sha256,
        second.matrix_spec_canonical_sha256,
    )
    return
