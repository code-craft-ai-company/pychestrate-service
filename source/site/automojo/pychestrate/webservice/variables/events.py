"""
.. module:: variables.events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Event topic names published by 2-global-variables.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class VariableEventTopics:
    """
        String constants for every entity topic owned by 2-global-variables.
    """

    VARIABLE_SET: str = "entity.variable.set"
    VARIABLE_UNSET: str = "entity.variable.unset"
