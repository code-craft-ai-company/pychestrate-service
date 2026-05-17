"""
.. module:: automojo.testshared.skip_helper
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tiny helper for raising :class:`SkipError` with
               the ``reason`` + ``bug`` attributes testbase's
               result recorder reads.

.. moduleauthor:: Automation Mojo LLC

testbase's per-scope ``__exit__`` consumers call
``ex_inst.reason`` and ``ex_inst.bug`` when a
:class:`automojo.errors.exceptions.SkipError` bubbles out of a
test (see
``automojo.testbase.sequencing.sequencertestscope.__exit__``
around line 180). The base ``SkipError`` class itself does not
define these attributes -- callers must set them on the
instance before raising. This helper does that in one call so
test bodies stay readable.

Usage::

    from automojo.testshared.skip_helper import skip_test

    if some_precondition_not_met:
        skip_test(reason="needs PYCHESTRATE_TEST_ADMIN_LOGIN")
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import NoReturn

from automojo.errors.exceptions import SkipError


def skip_test(*, reason: str, bug: str = "") -> NoReturn:
    """
        Raise a :class:`SkipError` instance whose ``reason`` and
        ``bug`` attributes are populated so testbase's per-scope
        ``__exit__`` consumer can read them without an
        :class:`AttributeError`.

        :param reason: Human-readable reason the test is being
                       skipped. Surfaced in the test result.
        :param bug: Optional bug/issue reference (e.g. JIRA key)
                    associated with the skip. Empty when no
                    tracker entry is relevant.

        :raises: :class:`SkipError` (always).
    """
    err = SkipError(reason)
    err.reason = reason
    err.bug = bug
    raise err


__all__ = [
    "skip_test",
]
