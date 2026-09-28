"""
.. module:: webinterface.foundation.form_errors
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Turn validation errors into the per-field messages the
               server-rendered forms show next to their inputs.

.. moduleauthor:: Code Craft AI LLC

A form that fails validation re-renders with ``errors``, a
``{field name: message}`` dict. The templates show each message next
to its input through ``ui.field_error`` / ``ui.invalid_attrs`` and list
them all at the top through ``ui.error_summary`` (audit ADM-11). An
error that names no field keeps the flash banner above the form, so no
message is lost.

Managers name the field on the exception they raise
(``exc.field``); a route that knows which input it was parsing when a
plain ``ValueError`` escaped names it with ``field=``.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Dict, Optional


def error_message(exc: BaseException) -> str:
    """
        The sentence to show for ``exc``: its ``message`` attribute when
        it has one, else ``str(exc)``.

        :param exc: The raised error.

        :returns: The message text.
    """
    message = getattr(exc, "message", None)
    if isinstance(message, str) is True and len(message) > 0:
        rtnval = message
    else:
        rtnval = str(exc)
    return rtnval


def field_errors_from(exc: BaseException, *, field: Optional[str] = None) -> Dict[str, str]:
    """
        The ``{field: message}`` dict for one validation error.

        :param exc: The raised error.
        :param field: The form field to blame when the error does not
                      name one itself (for example the input a route was
                      parsing when a ``ValueError`` escaped). The error's
                      own ``field`` attribute wins.

        :returns: One entry when a field is known, else an empty dict
                  (the caller then flashes the message instead).
    """
    named = getattr(exc, "field", None)
    if isinstance(named, str) is True and len(named) > 0:
        chosen: Optional[str] = named
    else:
        chosen = field
    if chosen is None:
        rtnval: Dict[str, str] = {}
    else:
        rtnval = {chosen: error_message(exc)}
    return rtnval
