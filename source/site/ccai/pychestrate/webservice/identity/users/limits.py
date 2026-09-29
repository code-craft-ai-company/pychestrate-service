"""
.. module:: identity.users.limits
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Length limits for user fields (ADM-41).

.. moduleauthor:: Code Craft AI LLC

A 3,000-character display name broke the users table, because nothing bounded
it. The database column holds 256; a name a person would type is far shorter.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


#: The longest display name the forms and the REST API accept.
MAX_DISPLAY_NAME_LENGTH: int = 100


def display_name_too_long_message() -> str:
    """
        The message every entry point gives for a display name over the limit.

        :returns: Sentence for the person.
    """
    rtnval = "Display name must be at most {} characters".format(MAX_DISPLAY_NAME_LENGTH)
    return rtnval


__all__ = ["MAX_DISPLAY_NAME_LENGTH", "display_name_too_long_message"]
