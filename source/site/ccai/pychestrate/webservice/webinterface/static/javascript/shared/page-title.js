/*
 * The tab title of a bundle detail page names the thing being looked at
 * (ORC-35). The shell titles every bundle route from its navigation entry
 * ("Runs · Pychestrate"); once a detail view has loaded its entity it puts
 * the entity in front: "Run 3f2a1b7c · Runs · Pychestrate".
 *
 * The title the page had is remembered on the root element, so a view that
 * renders again (a refresh, a poll) replaces the entity instead of stacking
 * a second one in front of the first.
 *
 * This file is bundled into each bundle by esbuild.
 */

const SECTION_TITLE_KEY = "pycSectionTitle";
const ENTITY_TITLE_KEY = "pycEntityTitle";

export function set_entity_title(entity_label) {
  if (typeof entity_label !== "string" || entity_label.trim().length === 0) {
    return;
  }
  const root = document.documentElement;
  if (root.dataset[ENTITY_TITLE_KEY] === void 0 || document.title !== root.dataset[ENTITY_TITLE_KEY]) {
    // The title is the section's (or a server page's): remember it.
    root.dataset[SECTION_TITLE_KEY] = document.title;
  }
  const title = entity_label.trim() + " · " + root.dataset[SECTION_TITLE_KEY];
  root.dataset[ENTITY_TITLE_KEY] = title;
  document.title = title;
  return;
}
