"""
.. module:: ccai.testshared.factories.webui
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Fixture builders for the consumer web UI templates.

.. moduleauthor:: Code Craft AI LLC

Two modules live here:

* :mod:`dataclass_fixtures` -- a generic populator that builds an
  instance of any ``@dataclass`` response type from its type
  hints, in a *populated* variant (every Optional set, every list
  holding one element) and a *sparse* variant (Optionals ``None``,
  lists empty).
* :mod:`template_contexts` -- the registry that maps the variable
  names the jinja templates read to fixture builders, so the
  render-smoke suite can render every template against objects
  shaped exactly like the manager response dataclasses the
  handlers pass.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"
