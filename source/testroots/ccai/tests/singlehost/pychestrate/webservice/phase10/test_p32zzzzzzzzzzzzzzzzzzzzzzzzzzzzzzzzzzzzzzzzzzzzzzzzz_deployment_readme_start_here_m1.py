"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz_deployment_readme_start_here_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The deployment README tells a reader where to start and every signpost points somewhere real (DOC-12).

.. moduleauthor:: Code Craft AI LLC

``deployment/README.md`` is a reference for the scripts, about 700 lines on six jobs (deploy, certificates, pod enrolment, monitoring, backup and restore, the CI
workflow), and the step-by-step "Deploy on a Linux host" guide the audit asked for already exists as chapter 13 of the published guide. A reader had no
signpost. The README now opens with a "Start here" table that points at the runbook and at each job's section. This test keeps the signposts honest: every
link in the table resolves to a heading of the README (by GitHub's rule for anchors) or to a file that exists.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re

from typing import List

from ccai import testbase

from ccai.testshared.factories.pyc.pyc_harness import find_repository_root


def _readme() -> str:
    return (find_repository_root() / "deployment" / "README.md").read_text(encoding="utf-8")


def _slug(heading: str) -> str:
    """GitHub's anchor for a heading: lower case, punctuation dropped (hyphens kept), spaces to hyphens."""
    text = heading.strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def _start_here() -> str:
    text = _readme()
    start = text.index("## Start here")
    return text[start:text.index("\n## ", start + 5)]


def test_start_here_comes_first_names_the_runbook_and_offers_each_job():
    """
    **Feature: deployment README navigation (DOC-12)**
    **Property: the README's first section after its introduction is "Start here"; it names the operator runbook (chapter 13), and its table has a row for
    deploying, renewing the certificate, pod mTLS, monitoring, backup and restore and the CI workflow.**
    """
    text = _readme()
    section = _start_here()
    headings = re.findall(r"^## (.+)$", text, re.M)

    testbase.assert_equal(
        (
            headings[0], "13-00-alpha-deployment" in section,
            [job in section for job in ("deploy-alpha-to-host.sh", "renew-cert.sh", "mTLS", "Monitoring", "Backup and restore", "CI deploy workflow")],
        ),
        ("Start here", True, [True] * 6),
    )
    return


def test_every_signpost_in_the_table_points_at_a_real_heading_or_file():
    """
    **Feature: deployment README navigation (DOC-12)**
    **Property: each ``(#anchor)`` link in "Start here" matches a heading of the README by GitHub's anchor rule, and each relative file link names a file
    that exists; the table links at least six places.**
    """
    text = _readme()
    section = _start_here()
    anchors = {_slug(heading) for heading in re.findall(r"^#{2,3} (.+)$", text, re.M)}
    links = re.findall(r"\]\(([^)\s]+)\)", section)
    broken: List[str] = []
    for link in links:
        if link.startswith("#"):
            if link[1:] not in anchors:
                broken.append(link)
        elif not link.startswith("http"):
            if not (find_repository_root() / "deployment" / link).resolve().exists():
                broken.append(link)

    testbase.assert_equal((broken, len(links) >= 7), ([], True))
    return
