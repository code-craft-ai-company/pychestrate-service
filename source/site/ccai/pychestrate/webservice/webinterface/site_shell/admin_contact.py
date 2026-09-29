"""
.. module:: webinterface.site_shell.admin_contact
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Whom to ask for access (XC-21).

.. moduleauthor:: Code Craft AI LLC

A person who reaches a page they may not use, or who has no role at all, was
told to "ask an administrator" without being told who that is. The installation
names a contact in ``PYCHESTRATE_ADMIN_CONTACT`` (an email address, a chat
handle, a team name: whatever a person can act on); the shell shows it on the
no-access screen (as a mail link when it is an address) and the server adds it
to the 403 page. Without one nothing is added, so no page names a person the
installation did not name.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os


#: The environment variable that names the person or team to ask for access.
ENV_ADMIN_CONTACT: str = "PYCHESTRATE_ADMIN_CONTACT"

#: The longest contact shown; anything longer is cut.
MAX_CONTACT_LENGTH: int = 200


def admin_contact() -> str:
    """
        The configured access contact.

        Whitespace runs (including line breaks) collapse to one space and the
        text is cut at :data:`MAX_CONTACT_LENGTH`, so a stray newline in a unit
        file cannot break a page or an attribute.

        :returns: The contact, or an empty string when none is configured.
    """
    raw = os.environ.get(ENV_ADMIN_CONTACT, "")
    rtnval = " ".join(str(raw).split())[:MAX_CONTACT_LENGTH]
    return rtnval


def access_request_sentence() -> str:
    """
        The sentence that tells a person whom to ask.

        :returns: ``To ask for access, contact <contact>.``, or an empty
                  string when no contact is configured.
    """
    contact = admin_contact()
    if len(contact) == 0:
        return ""
    rtnval = "To ask for access, contact {}.".format(contact)
    return rtnval


__all__ = [
    "ENV_ADMIN_CONTACT",
    "MAX_CONTACT_LENGTH",
    "access_request_sentence",
    "admin_contact",
]
