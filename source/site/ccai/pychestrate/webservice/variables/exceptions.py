"""
.. module:: variables.exceptions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Exceptions raised by 2-global-variables service APIs.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class VariableNotFoundError(Exception):
    """
        Raised when a requested variable binding does not exist.
    """


class InvalidVariableScopeError(Exception):
    """
        Raised when a caller supplies an unsupported scope or scope_id.
    """


class InvalidVariableValueError(Exception):
    """
        Raised when a value does not match the declared ``value_type``.
    """
