"""
.. module:: test_p30t_chip_tone_browser_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Status chips keep their tone inside other components'
               shadow roots (ORC-09).

.. moduleauthor:: Code Craft AI LLC

Bundles colour status chips with page-level ``::part(chip)`` rules,
which cannot reach a chip rendered inside ``<mj-data-table>``'s shadow
root, so every state in every list was the same grey. The site shell
now sets each chip's inherited ``--mj-chip-*`` properties from its
``data-tone`` (chrome/chip-tone.js).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict

from playwright.sync_api import Browser

from ccai import testbase

from ccai.testshared.factories.browsers.playwright_browser import (
    create_playwright_browser,
)

from ccai.tests.singlehost.pychestrate.webservice.phase13._shell_browser_harness import (
    open_shell_page,
)


testbase.originate.parameter(
    create_playwright_browser,
    identifier="browser",
)


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}

#: JS: put one chip per tone inside a foreign shadow root (as a table
#: cell would), then report each chip's rendered background.
SHADOW_CHIPS_JS: str = r"""
async () => {
  await customElements.whenDefined('mj-chip');
  const host = document.createElement('div');
  document.body.appendChild(host);
  const root = host.attachShadow({mode: 'open'});
  const tones = ['ok', 'warn', 'error', 'neutral'];
  for (const tone of tones) {
    const chip = document.createElement('mj-chip');
    chip.setAttribute('data-tone', tone);
    chip.textContent = tone;
    root.appendChild(chip);
  }
  await new Promise((resolve) => requestAnimationFrame(() => resolve()));
  const out = {};
  root.querySelectorAll('mj-chip').forEach((chip) => {
    out[chip.getAttribute('data-tone')] = getComputedStyle(chip.shadowRoot.querySelector('.chip')).backgroundColor;
  });
  window.__pycShadowChipRoot = root;
  return out;
}
"""

RETONE_JS: str = r"""
async () => {
  const chip = window.__pycShadowChipRoot.querySelector('mj-chip[data-tone="neutral"]');
  chip.setAttribute('data-tone', 'error');
  // The chip animates background changes; read it once settled.
  const part = chip.shadowRoot.querySelector('.chip');
  let previous = '';
  for (let attempt = 0; attempt < 40; attempt++) {
    await new Promise((resolve) => setTimeout(resolve, 50));
    const current = getComputedStyle(part).backgroundColor;
    if (current === previous) {
      return current;
    }
    previous = current;
  }
  return previous;
}
"""


def test_chips_inside_a_shadow_root_keep_distinct_tones(browser: Browser):
    """
    **Feature: status chip tone (ORC-09)**
    **Property: ok / warn / error chips inside a foreign shadow root
    render three different backgrounds, none of them the neutral one,
    in light and dark mode.**
    """
    for scheme in ("light", "dark"):
        page = open_shell_page(browser, color_scheme=scheme, **DESKTOP)
        try:
            colours = page.evaluate(SHADOW_CHIPS_JS)
            toned = [colours["ok"], colours["warn"], colours["error"]]
            testbase.assert_equal(
                (len(set(toned)), colours["neutral"] in toned),
                (3, False),
                "{}: {}".format(scheme, colours),
            )
        finally:
            page.context.close()
    return


def test_changing_a_chips_tone_recolours_it(browser: Browser):
    """
    **Feature: status chip tone (ORC-09)**
    **Property: a chip whose data-tone changes after it rendered takes
    the new tone.**
    """
    page = open_shell_page(browser, **DESKTOP)
    try:
        colours = page.evaluate(SHADOW_CHIPS_JS)
        retoned = page.evaluate(RETONE_JS)
        testbase.assert_equal(retoned, colours["error"])
    finally:
        page.context.close()
    return
