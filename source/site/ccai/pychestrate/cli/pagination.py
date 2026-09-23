"""
.. module:: cli.pagination
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Follow the pages of a list command (``--all``,
               ``--limit``).

.. moduleauthor:: Code Craft AI LLC

A list operation pages one of two ways:

* **page** -- ``page`` / ``per_page`` query parameters; the answer is
  ``{"items": [...], "meta": {"page", "per_page", "total"}}``;
* **offset** -- ``offset`` / ``limit`` query parameters; the answer is
  ``{"<things>": [...], "total", "offset", "limit"}``.

``--all`` requests page after page until the last one and prints the
items as one list; ``--limit N`` (page lists; on offset lists
``--limit`` is the server's own page size) stops after ``N`` items.
Without either, pyc prints the one page it asked for and notes on
stderr how many items the server has in all.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Callable, Dict, List, Optional

from ccai.pychestrate.cli import renderer
from ccai.pychestrate.cli.models import RestOperation, RestResponse


PAGE_MODE: str = "page"
OFFSET_MODE: str = "offset"

#: Most pages ``--all`` requests before stopping (with a note).
MAX_PAGES: int = 1000


def pagination_mode(*, operation: RestOperation) -> Optional[str]:
    """
        How ``operation`` pages, from its query parameters.

        :param operation: Operation.

        :returns: :data:`PAGE_MODE`, :data:`OFFSET_MODE` or ``None``.
    """
    names = set(operation.query_param_names)
    if "page" in names and "per_page" in names:
        rtnval: Optional[str] = PAGE_MODE
        return rtnval
    if "offset" in names and "limit" in names:
        rtnval = OFFSET_MODE
        return rtnval
    return None


def _as_int(value: Any) -> Optional[int]:
    """
        ``value`` as an int, or ``None``.

        :param value: Value.

        :returns: Int or ``None``.
    """
    try:
        rtnval: Optional[int] = int(value)
    except (TypeError, ValueError):
        rtnval = None
    return rtnval


def more_items_note(*, mode: str, body: Any) -> Optional[str]:
    """
        The stderr note for a single page that is not the whole list.

        :param mode: Pagination mode.
        :param body: The page's answer.

        :returns: Note, or ``None`` when the page is the whole list.
    """
    items = renderer.items_of(body)
    if items is None or not isinstance(body, dict):
        return None
    if mode == PAGE_MODE:
        meta = body.get("meta", None)
        if not isinstance(meta, dict):
            return None
        page = _as_int(meta.get("page", None)) or 1
        per_page = _as_int(meta.get("per_page", None)) or len(items)
        total = _as_int(meta.get("total", None))
        first = (page - 1) * per_page
        paging_hint = "--page N"
    else:
        total = _as_int(body.get("total", None))
        first = _as_int(body.get("offset", None)) or 0
        paging_hint = "--offset N"
    if total is None or first + len(items) >= total:
        return None
    if len(items) == 0:
        shown = "no items"
    else:
        shown = "items {}-{}".format(first + 1, first + len(items))
    rtnval = "note: showing {} of {}; add --all for every page (or {}).".format(shown, total, paging_hint)
    return rtnval


def fetch_pages(
        *,
        mode: str,
        query_params: Dict[str, str],
        send: Callable[[Dict[str, str]], RestResponse],
        item_limit: Optional[int],
        note: Callable[[str], None]
    ) -> Any:
    """
        Request page after page and return every item as one list.

        :param mode: :data:`PAGE_MODE` or :data:`OFFSET_MODE`.
        :param query_params: The command's query parameters (the first
                             page's ``page`` / ``offset`` start there).
        :param send: Sends one request with the given query parameters.
        :param item_limit: Stop after this many items (``None``: all).
        :param note: Writes a note to stderr.

        :returns: The collected items, or the first answer unchanged
                  when it is not a list.
    """
    collected: List[Any] = []
    params = dict(query_params)
    page = _as_int(params.get("page", None)) or 1
    offset = _as_int(params.get("offset", None)) or 0
    first_page_length: Optional[int] = None
    pages = 0

    while True:
        if mode == PAGE_MODE:
            params["page"] = str(page)
        else:
            params["offset"] = str(offset)
        response = send(params)
        body = response.body
        items = renderer.items_of(body)
        if items is None:
            if pages == 0:
                return body
            break
        collected.extend(items)
        pages = pages + 1
        if first_page_length is None:
            first_page_length = len(items)

        if item_limit is not None and len(collected) >= item_limit:
            collected = collected[:item_limit]
            break
        if len(items) == 0:
            break
        if mode == PAGE_MODE:
            meta = body.get("meta", None) if isinstance(body, dict) else None
            meta = meta if isinstance(meta, dict) else {}
            per_page = _as_int(meta.get("per_page", None)) or _as_int(params.get("per_page", None))
            total = _as_int(meta.get("total", None))
            if per_page is not None and len(items) < per_page:
                break
            if total is not None and per_page is not None and page * per_page >= total:
                break
            page = page + 1
        else:
            page_size = _as_int(params.get("limit", None)) or first_page_length
            total = _as_int(body.get("total", None)) if isinstance(body, dict) else None
            offset = offset + len(items)
            if page_size is not None and len(items) < page_size:
                break
            if total is not None and offset >= total:
                break
        if pages >= MAX_PAGES:
            note("note: stopped after {} pages ({} items); narrow the query or use --limit.".format(
                pages, len(collected)
            ))
            break

    rtnval = collected
    return rtnval


__all__ = [
    "MAX_PAGES",
    "OFFSET_MODE",
    "PAGE_MODE",
    "fetch_pages",
    "more_items_note",
    "pagination_mode",
]
