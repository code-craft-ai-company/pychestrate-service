"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz_stored_values_read_as_words_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A stored state or kind reads as words on server-rendered pages (ADM-27).

.. moduleauthor:: Code Craft AI LLC

The UI glossary says a stored value is not a label: underscores read as spaces and a state stored in capitals reads in lowercase. The
bundle pages did this; the server-rendered pages printed what was stored, so the API Tokens page showed a service account as ``ACTIVE`` and a
variable's type would read ``SECRET_REF``. The ``state_words`` filter now does it, the ``status_badge`` macro uses it, and the badges that
printed an enum's ``.value`` use it too. An infrastructure job's state also goes through ``status_badge``, so it has the tone every
other state has. This test covers the filter, the macro, and a lint that fails when a template prints an enum's ``.value`` unfiltered.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import enum
import os
import re

from typing import Dict, List

from ccai import testbase

from ccai.pychestrate.webservice.webinterface.foundation import templating


class _Stored(enum.Enum):
    ACTIVE = "ACTIVE"
    IN_USE = "IN_USE"
    SUCCEEDED = "succeeded"


#: ``{{ thing.value }}``: an enum's stored value printed as it is. (An ``<option value="...">`` must keep the stored value: it is what the form sends.)
RAW_VALUE = re.compile(r"(?<!<option value=\")\{\{\s*[A-Za-z_][\w.]*\.value\s*\}\}")


def _webinterface() -> str:
    current = os.path.dirname(os.path.abspath(__file__))
    while not os.path.isdir(os.path.join(current, "source", "site")) and current != os.path.dirname(current):
        current = os.path.dirname(current)
    return os.path.join(current, "source", "site", "ccai", "pychestrate", "webservice", "webinterface")


def test_the_filter_says_stored_values_the_way_a_person_would():
    """
    **Feature: states in words (ADM-27)**
    **Property: ``state_words`` turns underscores into spaces, lowercases a value stored in capitals, reads an enum member as its value and
    leaves text that already reads well, an absent value and a number alone.**
    """
    cases = [
        templating.state_words_filter("IN_USE"),
        templating.state_words_filter("ACTIVE"),
        templating.state_words_filter("dispatch_unconfirmed"),
        templating.state_words_filter("Needs attention"),
        templating.state_words_filter(_Stored.IN_USE),
        templating.state_words_filter(_Stored.SUCCEEDED),
        templating.state_words_filter(None),
        templating.state_words_filter(7),
        templating.state_words_filter(""),
    ]

    testbase.assert_equal(cases, ["in use", "active", "dispatch unconfirmed", "Needs attention", "in use", "succeeded", None, 7, ""])
    return


def test_the_status_badge_macro_uses_it_and_keeps_the_tone():
    """
    **Feature: states in words (ADM-27)**
    **Property: ``status_badge`` shows ``ACTIVE`` as "active" in the success tone, ``IN_USE`` as "in use", and an absent value as a dash;
    the tone is still chosen from the stored value.**
    """
    environment = templating.build_jinja_environment(
        template_search_paths=[os.path.join(_webinterface(), "site_shell", "templates")], strict_undefined=True,
    )
    templating.install_template_globals(environment=environment)
    template = environment.from_string(
        '{% import "site_shell/_macros.html" as ui %}{{ ui.status_badge(first) }}|{{ ui.status_badge(second) }}|{{ ui.status_badge(third) }}'
    )

    rendered = template.render(first=_Stored.ACTIVE, second="IN_USE", third=None)

    testbase.assert_equal(
        rendered,
        '<span class="badge badge-success">active</span>|<span class="badge badge-secondary">in use</span>|<span class="badge badge-secondary">—</span>',
    )
    return


def test_no_template_prints_an_enum_value_as_stored():
    """
    **Feature: states in words (ADM-27)**
    **Property: no server-rendered template prints ``{{ something.value }}`` unfiltered (use ``state_words`` or ``status_badge``).**
    """
    found: Dict[str, List[int]] = {}
    for base, _dirs, files in os.walk(_webinterface()):
        for name in files:
            if name.endswith(".html"):
                path = os.path.join(base, name)
                with open(path, encoding="utf-8") as handle:
                    text = handle.read()
                for match in RAW_VALUE.finditer(text):
                    found.setdefault(os.path.relpath(path, _webinterface()), []).append(text.count("\n", 0, match.start()) + 1)

    testbase.assert_equal(found, {})
    return
