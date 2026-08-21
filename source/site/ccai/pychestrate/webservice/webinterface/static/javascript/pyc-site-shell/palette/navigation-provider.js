const NAVIGATION_PROVIDER_ID = "shell.navigation";
const NAVIGATION_PROVIDER_LABEL = "Navigation";
const NAVIGATION_RESULT_LIMIT = 12;
const SCORE_LABEL_PREFIX = 400;
const SCORE_LABEL_SUBSTRING = 300;
const SCORE_GROUP_SUBSTRING = 200;
const SCORE_ROUTE_SUBSTRING = 150;
const SCORE_LABEL_SUBSEQUENCE = 100;
/*
 * The shell's own palette provider. Registered at shell boot for
 * every user, so the palette always has at least one working
 * provider -- it fuzzy-matches the navigation entries the shell
 * loaded from the nav manifest (plus any feature-bundle
 * registrations) and navigates on select. The manifest is already
 * permission-filtered server-side and the provider re-filters
 * through the sidebar registry's client-side visibility rules,
 * so results always reflect what the caller may actually reach.
 */
function register_navigation_palette_provider(palette, options) {
  palette.registerProvider({
    providerId: NAVIGATION_PROVIDER_ID,
    label: NAVIGATION_PROVIDER_LABEL,
    requiredPermissions: [],
    query: async (query) => {
      const visible_sidebar = options.get_visible_sidebar();
      const candidates = _collect_candidates(visible_sidebar);
      const results = _match_candidates(candidates, query);
      return results;
    }
  });
  return;
}
/*
 * Flatten the visible sidebar structure into palette candidates.
 * A static "Home" candidate leads so the bare "/" landing view is
 * reachable from the palette too.
 */
function _collect_candidates(visible_sidebar) {
  const candidates = [];
  candidates.push({
    id: "shell.home",
    label: "Home",
    group_label: null,
    route: "/"
  });
  for (const entry of visible_sidebar.ungrouped) {
    candidates.push({
      id: entry.entryId,
      label: entry.label,
      group_label: null,
      route: entry.route
    });
  }
  for (const bucket of visible_sidebar.groups) {
    for (const entry of bucket.entries) {
      candidates.push({
        id: entry.entryId,
        label: entry.label,
        group_label: bucket.group.label,
        route: entry.route
      });
    }
  }
  return candidates;
}
function _match_candidates(candidates, query) {
  const normalized = typeof query === "string" ? query.trim().toLowerCase() : "";
  if (normalized.length === 0) {
    const rtnval = [];
    return rtnval;
  }
  const scored = [];
  for (const candidate of candidates) {
    const score = _score_candidate(candidate, normalized);
    if (score > 0) {
      scored.push({ candidate, score });
    }
  }
  scored.sort((left, right) => right.score - left.score);
  const results = [];
  for (const item of scored.slice(0, NAVIGATION_RESULT_LIMIT)) {
    const candidate = item.candidate;
    const description = candidate.group_label !== null ? candidate.group_label + " — " + candidate.route : candidate.route;
    results.push({
      id: candidate.id,
      label: candidate.label,
      description,
      route: candidate.route
    });
  }
  return results;
}
/*
 * Score one candidate against the normalized query. Substring
 * matches on the label rank above group and route matches; a
 * character-subsequence match on the label (the classic palette
 * "fzf" affordance) is the lowest-ranked hit. Ties break toward
 * shorter labels so the most specific destination floats up.
 */
function _score_candidate(candidate, normalized_query) {
  const label = candidate.label.toLowerCase();
  const group_label = candidate.group_label !== null ? candidate.group_label.toLowerCase() : "";
  const route = candidate.route.toLowerCase();
  const tiebreak = Math.max(0, 50 - candidate.label.length);
  if (label.startsWith(normalized_query) === true) {
    const rtnval = SCORE_LABEL_PREFIX + tiebreak;
    return rtnval;
  }
  if (label.includes(normalized_query) === true) {
    const rtnval = SCORE_LABEL_SUBSTRING + tiebreak;
    return rtnval;
  }
  if (group_label.length > 0 && group_label.includes(normalized_query) === true) {
    const rtnval = SCORE_GROUP_SUBSTRING + tiebreak;
    return rtnval;
  }
  if (route.includes(normalized_query) === true) {
    const rtnval = SCORE_ROUTE_SUBSTRING + tiebreak;
    return rtnval;
  }
  if (_is_subsequence(normalized_query, label) === true) {
    const rtnval = SCORE_LABEL_SUBSEQUENCE + tiebreak;
    return rtnval;
  }
  const rtnval = 0;
  return rtnval;
}
function _is_subsequence(needle, haystack) {
  let needle_index = 0;
  for (let haystack_index = 0; haystack_index < haystack.length; haystack_index = haystack_index + 1) {
    if (needle_index >= needle.length) {
      break;
    }
    if (haystack[haystack_index] === needle[needle_index]) {
      needle_index = needle_index + 1;
    }
  }
  const rtnval = needle_index >= needle.length;
  return rtnval;
}
export {
  NAVIGATION_PROVIDER_ID,
  register_navigation_palette_provider
};
