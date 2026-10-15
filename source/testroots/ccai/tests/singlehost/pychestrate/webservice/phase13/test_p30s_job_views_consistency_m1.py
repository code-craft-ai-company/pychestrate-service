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
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.webservice.runs.restapi.v1 import runs_routes
from ccai.pychestrate.webservice.webinterface.blueprints.projects import routes_rpa

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


def _render_progress(progress: object) -> str:
    template = strict_environment().from_string('{% import "site_shell/_macros.html" as ui %}{{ ui.job_progress(progress) }}')
    return template.render(progress=progress)


def test_a_running_jobs_page_shows_its_progress_bar_and_the_pods_message():
    """
    **Feature: RPA job page (E2E-23)**
    **Property: when the pod has reported progress the job's status card shows a bar with the percent and the pod's last message ("tick 16"); with only a message it shows the
    message; with nothing reported (or an unknown percent and no message) it shows nothing, as before.**
    """
    both = _render_progress({"percent": 26.67, "message": "tick 16"})
    message_only = _render_progress({"percent": None, "message": "starting up"})
    nothing = _render_progress(None)
    empty = _render_progress({"percent": None, "message": ""})

    testbase.assert_equal(
        (
            '<progress max="100" value="27"' in both, "27%" in both, "tick 16" in both,
            "<progress" in message_only, "starting up" in message_only,
            nothing.strip(), "<progress" in empty, "tick" in empty,
        ),
        (True, True, True, False, True, "", False, False),
    )
    return


def test_describe_progress_reads_the_percent_and_the_message_and_a_failed_read_leaves_no_bar():
    """
    **Feature: RPA job page (E2E-23)**
    **Property: ``describe_progress`` turns a run's progress block into ``{percent, message}`` (a number as a float, a missing or non-numeric percent as None, the notes as the message) and
    nothing when none was reported; the job page's helper returns None rather than failing the page when reading the progress raises.**
    """
    def _described(block: object) -> object:
        patch = create_module_patch(runs_routes, "_progress_summary_block")
        mock = patch.activate()
        mock.configure(side_effect=lambda **kwargs: block)
        try:
            return runs_routes.describe_progress(db_session=None, run_id="r")
        finally:
            patch.deactivate()

    class _Job:
        job_id = "11111111-1111-4111-8111-111111111111"

    patch = create_module_patch(runs_routes, "describe_progress")
    mock = patch.activate()

    def _boom(**kwargs: object) -> object:
        raise RuntimeError("progress tables unavailable")

    mock.configure(side_effect=_boom)
    try:
        survived = routes_rpa._job_progress(db_session=None, job=_Job())
    finally:
        patch.deactivate()

    testbase.assert_equal(
        (_described({"percent_complete": 40, "notes": "tick 24"}), _described({"percent_complete": None, "notes": None}), _described({"percent_complete": True, "notes": "x"}), _described(None), survived),
        ({"percent": 40.0, "message": "tick 24"}, {"percent": None, "message": ""}, {"percent": None, "message": "x"}, None, None),
    )
    return
