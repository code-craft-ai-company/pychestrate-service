"""
.. module:: test_p31zt_embed_error_page_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A rejected embed shows a styled page that says what happened (ORC-46).

.. moduleauthor:: Code Craft AI LLC

The page shown in place of an embed whose signed URL was rejected was a bare
paragraph in the browser's default style, "This embed could not be displayed
(403)", with nothing about why or who could fix it. It now follows the design
tokens (light and dark), has a heading, says in plain words what was wrong with
the link, and points the viewer to whoever shared it. The reason stays on the
page for tooling, and the statuses are unchanged.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai import testbase

from ccai.pychestrate.webservice.embed.restapi.v1 import embed_routes
from ccai.pychestrate.webservice.embed.signing import VerificationOutcome


class _Request:
    def __init__(self, *, view_key: str, query: dict) -> None:
        self.path_params = {"view_key": view_key}
        self.query_params = query
        return


def test_every_reason_a_link_can_be_rejected_has_words_for_a_person():
    """
    **Feature: embed error page (ORC-46)**
    **Property: each rejection reason (every non-verified signing outcome
    and an unknown view kind) has its own plain-language message, and none
    shows the generic fallback.**
    """
    reasons = [outcome.value for outcome in VerificationOutcome if outcome != VerificationOutcome.VERIFIED] + ["unknown_view_kind"]
    missing = [reason for reason in reasons if reason not in embed_routes.EMBED_ERROR_MESSAGES]

    testbase.assert_equal(missing, [])
    return


def test_the_error_page_is_styled_explained_and_keeps_the_reason_for_tooling():
    """
    **Feature: embed error page (ORC-46)**
    **Property: the page links the design tokens, sets the viewport, has one
    h1, says the link expired (for ``expired``), tells the viewer to ask
    whoever shared it, shows the status, and keeps ``data-embed-error``.**
    """
    page = embed_routes._embed_error_html(status=403, reason="expired")

    testbase.assert_equal(
        ("/static/styles/pyc-tokens.css" in page, 'name="viewport"' in page, page.count("<h1>"),
         "The link has expired." in page, "Ask whoever shared it for a new link" in page,
         "Error 403" in page, 'data-embed-error="expired"' in page, "<style>" in page),
        (True, True, 1, True, True, True, True, True),
    )
    return


def test_a_reason_from_the_request_cannot_inject_markup_into_the_page():
    """
    **Feature: embed error page (ORC-46)**
    **Property: a reason string containing markup is escaped in both the
    attribute and the message, and an unknown reason gets the generic
    sentence.**
    """
    page = embed_routes._embed_error_html(status=403, reason='"><script>alert(1)</script>')

    testbase.assert_equal(
        ("<script>" in page, "&lt;script&gt;" in page, "The link could not be accepted." in page),
        (False, True, True),
    )
    return


def test_the_statuses_of_the_serving_route_are_unchanged():
    """
    **Feature: embed error page (ORC-46)**
    **Property: an unknown view kind answers 404, a link with no expiry
    401, and a link with a bad signature 403, each with the styled page.**
    """
    unknown = embed_routes.handle_serve_embed(_Request(view_key="no-such-view", query={}))
    incomplete = embed_routes.handle_serve_embed(_Request(view_key=_a_view_kind(), query={"e": "not-a-number"}))
    forged = embed_routes.handle_serve_embed(
        _Request(view_key=_a_view_kind(), query={"e": "4102444800", "s": "00", "k": "no-such-key", "a": "x"})
    )

    testbase.assert_equal(
        (unknown.status_code, incomplete.status_code, forged.status_code,
         all(b"pyc-tokens.css" in response.body for response in (unknown, incomplete, forged))),
        (404, 401, 403, True),
    )
    return


def _a_view_kind() -> str:
    from ccai.pychestrate.webservice.embed.view_catalog import list_view_kinds

    return list_view_kinds()[0].view_kind_name
