"""
.. module:: test_p16c_messaging_request_context_m2
    :synopsis: Tests for P16c — 0-message-bus M2 request_id
               ContextVar propagation.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import asyncio
import threading

from automojo import testbase

from automojo.pychestrate.webservice.messaging import request_context


def _prepare_runtime() -> None:
    request_context.reset_for_testing()
    return


# -------------------------------------
# Default + imperative setter
# -------------------------------------

def test_default_request_id_is_none():
    """
    **Feature: 0-message-bus (M2)**
    **Property: a fresh process has no request_id bound.**
    """
    _prepare_runtime()
    testbase.assert_equal(request_context.current_request_id(), None)
    return


def test_set_then_current_returns_value():
    """
    **Feature: 0-message-bus (M2)**
    **Property: set_request_id stamps the current context;
    current_request_id returns the bound value.**
    """
    _prepare_runtime()
    request_context.set_request_id(request_id="req-alpha")
    testbase.assert_equal(
        request_context.current_request_id(), "req-alpha",
    )
    return


def test_reset_request_id_restores_prior_value():
    """
    **Feature: 0-message-bus (M2)**
    **Property: reset_request_id with the token returned by
    set_request_id restores the prior binding.**
    """
    _prepare_runtime()
    request_context.set_request_id(request_id="req-outer")
    inner_token = request_context.set_request_id(
        request_id="req-inner",
    )
    request_context.reset_request_id(token=inner_token)
    testbase.assert_equal(
        request_context.current_request_id(), "req-outer",
    )
    return


def test_reset_with_none_token_is_no_op():
    """
    **Feature: 0-message-bus (M2)**
    **Property: reset_request_id tolerates a None token so
    callers can roll back without bookkeeping.**
    """
    _prepare_runtime()
    request_context.set_request_id(request_id="req-alpha")
    request_context.reset_request_id(token=None)
    testbase.assert_equal(
        request_context.current_request_id(), "req-alpha",
    )
    return


# -------------------------------------
# bound_request_id context manager
# -------------------------------------

def test_bound_request_id_stamps_and_restores():
    """
    **Feature: 0-message-bus (M2)**
    **Property: bound_request_id stamps the ContextVar for
    the duration of the with block and restores the prior
    value on exit.**
    """
    _prepare_runtime()
    request_context.set_request_id(request_id="req-outer")
    with request_context.bound_request_id(request_id="req-inner"):
        testbase.assert_equal(
            request_context.current_request_id(), "req-inner",
        )
    testbase.assert_equal(
        request_context.current_request_id(), "req-outer",
    )
    return


def test_bound_request_id_restores_on_exception():
    """
    **Feature: 0-message-bus (M2)**
    **Property: bound_request_id restores the prior value
    even when the with body raises.**
    """
    _prepare_runtime()
    request_context.set_request_id(request_id="req-outer")
    raised = False
    try:
        with request_context.bound_request_id(request_id="req-inner"):
            raise RuntimeError("simulated_failure")
    except RuntimeError:
        raised = True
    testbase.assert_equal(raised, True)
    testbase.assert_equal(
        request_context.current_request_id(), "req-outer",
    )
    return


def test_bound_request_id_yields_value():
    """
    **Feature: 0-message-bus (M2)**
    **Property: bound_request_id yields the supplied value
    so callers can use it directly in the with binding.**
    """
    _prepare_runtime()
    seen = None
    with request_context.bound_request_id(
        request_id="req-yielded",
    ) as value:
        seen = value
    testbase.assert_equal(seen, "req-yielded")
    return


def test_bound_request_id_handles_none_value():
    """
    **Feature: 0-message-bus (M2)**
    **Property: bound_request_id with request_id=None clears
    the binding within the block and restores on exit.**
    """
    _prepare_runtime()
    request_context.set_request_id(request_id="req-outer")
    with request_context.bound_request_id(request_id=None):
        testbase.assert_equal(
            request_context.current_request_id(), None,
        )
    testbase.assert_equal(
        request_context.current_request_id(), "req-outer",
    )
    return


# -------------------------------------
# Thread isolation
# -------------------------------------

def test_thread_does_not_inherit_request_id():
    """
    **Feature: 0-message-bus (M2)**
    **Property: a synchronous worker thread does NOT
    inherit the parent's request_id — Python's ContextVar
    isolates per-thread.**
    """
    _prepare_runtime()
    request_context.set_request_id(request_id="parent-req")
    seen = []

    def _worker():
        seen.append(request_context.current_request_id())
        return

    thread = threading.Thread(target=_worker)
    thread.start()
    thread.join()
    testbase.assert_equal(seen, [None])
    return


def test_worker_can_install_captured_request_id():
    """
    **Feature: 0-message-bus (M2)**
    **Property: a worker thread that captures the parent's
    request_id at publish time can re-install it through
    bound_request_id for the duration of a subscriber
    callback.**
    """
    _prepare_runtime()
    captured = "captured-req-id"
    seen = []

    def _worker():
        with request_context.bound_request_id(request_id=captured):
            seen.append(request_context.current_request_id())
        # Confirm the worker's binding cleared on exit.
        seen.append(request_context.current_request_id())
        return

    thread = threading.Thread(target=_worker)
    thread.start()
    thread.join()
    testbase.assert_equal(seen, [captured, None])
    return


# -------------------------------------
# Asyncio task inheritance
# -------------------------------------

def test_asyncio_task_inherits_parent_context():
    """
    **Feature: 0-message-bus (M2)**
    **Property: an asyncio.create_task call captures the
    spawning task's context — the child task observes the
    parent's request_id.**
    """
    _prepare_runtime()
    request_context.set_request_id(request_id="parent-req")
    captured = []

    async def _child():
        captured.append(request_context.current_request_id())
        return

    async def _parent():
        await asyncio.create_task(_child())
        return

    asyncio.run(_parent())
    testbase.assert_equal(captured, ["parent-req"])
    return


# -------------------------------------
# reset_for_testing
# -------------------------------------

def test_reset_for_testing_clears_binding():
    """
    **Feature: 0-message-bus (M2)**
    **Property: reset_for_testing drops the binding back to
    None so the next test starts clean.**
    """
    request_context.set_request_id(request_id="leaked-from-prior")
    request_context.reset_for_testing()
    testbase.assert_equal(request_context.current_request_id(), None)
    return
