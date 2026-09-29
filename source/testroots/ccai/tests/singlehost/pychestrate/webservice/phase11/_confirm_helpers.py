"""
.. module:: _confirm_helpers
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Accept a destructive action's confirmation in a live browser test.

.. moduleauthor:: Code Craft AI LLC

A ``data-confirm`` form used to ask through the browser's own confirm box,
which a test accepts with ``page.on("dialog", ...)``. The shell now asks in a
``<dialog class="pyc-confirm">`` of its own (XC-15), which a test accepts by
pressing its Confirm button. :func:`auto_confirm` handles both, so a live
test does not depend on which one the deployed server uses.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any


#: Presses the confirmation dialog's Confirm button whenever one opens; runs
#: on every page the test loads.
_ACCEPT_SCRIPT: str = """
(() => {
    const accept = () => {
        const button = document.querySelector('dialog.pyc-confirm[open] [data-role="confirm-accept"]');
        if (button) { button.click(); }
    };
    new MutationObserver(accept).observe(document, {childList: true, subtree: true, attributes: true});
})();
"""


def auto_confirm(page: Any) -> None:
    """
        Accept every confirmation the page asks for, whichever kind.

        :param page: Playwright ``Page``.
    """
    page.on("dialog", lambda dialog: dialog.accept())
    page.add_init_script(_ACCEPT_SCRIPT)
    try:
        page.evaluate(_ACCEPT_SCRIPT)
    except Exception:  # noqa: BLE001 -- a page that has not loaded yet gets the init script
        pass
    return
