"""
.. module:: test_p30s_job_views_consistency_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Job pages agree with themselves (E2E-23): the log viewer
               never says "log is complete" over an empty log, and the
               RPA job page refreshes itself while the job is active.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai import testbase

from ccai.tests.singlehost.pychestrate.webservice.phase13._template_harness import (
    strict_environment,
)


def _render_log_viewer(*, text: str, running: bool) -> str:
    template = strict_environment().from_string(
        '{% import "site_shell/_macros.html" as ui %}{{ ui.log_viewer(text, running=running) }}'
    )
    rtnval = template.render(text=text, running=running)
    return rtnval


def test_log_viewer_messages_agree_with_the_log():
    """
    **Feature: shared log viewer (E2E-23)**
    **Property: a finished job with no output says so once; "log is
    complete" only appears over actual log text; a running job with no
    output yet says it is waiting.**
    """
    finished_empty = _render_log_viewer(text="", running=False)
    finished_full = _render_log_viewer(text="step 1 ok", running=False)
    running_empty = _render_log_viewer(text="", running=True)
    testbase.assert_equal(
        ("log is complete" in finished_empty, "No log output yet" in finished_empty,
         "no log output was recorded" in finished_empty,
         "log is complete" in finished_full,
         "No log output yet" in running_empty),
        (False, False, True, True, True),
    )
    return


def test_rpa_job_page_declares_a_live_region_while_active():
    """
    **Feature: RPA job page (E2E-23)**
    **Property: the page's status / details region is marked for live
    refresh exactly while the job is active.**
    """
    source = strict_environment().loader.get_source(
        strict_environment(), "projects/rpa/detail.html",
    )[0]
    testbase.assert_equal(
        ('data-live-region="rpa-job"' in source,
         "data-live-region-active=\"{{ 'true' if is_active else 'false' }}\"" in source),
        (True, True),
    )
    return
