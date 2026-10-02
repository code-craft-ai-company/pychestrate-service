/*
 * A visible caption above a filter control (ORC-42).
 *
 * ``<mj-select label="State">`` gives the control an accessible name but draws it visually hidden, so the filter bars
 * of Runs, Builds, Pipelines and the Test Catalog showed a row of unlabelled drop-downs while Environments,
 * Provisioning, Clients and Pods wrote the name above each one. ``show_caption`` writes it above the control in the
 * field's wrapper, in the wrapper's own small muted type. The control keeps its accessible name; the caption is hidden
 * from assistive technology so the name is not read twice.
 *
 * This file is bundled into each bundle by esbuild.
 */

export function show_caption(wrapper, text) {
  const caption = document.createElement("span");
  caption.classList.add("pyc-filter-caption");
  caption.setAttribute("aria-hidden", "true");
  caption.textContent = text;
  wrapper.insertBefore(caption, wrapper.firstChild);
  return wrapper;
}
