const DEFAULT_NAVIGATION_ENDPOINT = "/api/v1/me/navigation";
async function fetch_nav_manifest(endpoint = DEFAULT_NAVIGATION_ENDPOINT) {
  try {
    const response = await fetch(endpoint, {
      method: "GET",
      credentials: "same-origin",
      headers: { Accept: "application/json" }
    });
    if (response.ok === false) {
      const rtnval2 = {
        ok: false,
        manifest: null
      };
      return rtnval2;
    }
    const payload = await response.json();
    const manifest = _coerce_manifest(payload);
    if (manifest === null) {
      const rtnval2 = {
        ok: false,
        manifest: null
      };
      return rtnval2;
    }
    const rtnval = {
      ok: true,
      manifest
    };
    return rtnval;
  } catch (reason) {
    console.warn(
      "pychestrate.ui.shell.nav_manifest_fetch_failed",
      { endpoint, reason: String(reason) }
    );
    const rtnval = {
      ok: false,
      manifest: null
    };
    return rtnval;
  }
}
function apply_nav_manifest(registry, manifest) {
  if (manifest === null || Array.isArray(manifest.groups) === false) {
    return;
  }
  for (const group of manifest.groups) {
    if (group === null || typeof group.group_id !== "string" || group.group_id.length === 0) {
      continue;
    }
    registry.registerGroup({
      groupId: group.group_id,
      label: typeof group.label === "string" ? group.label : group.group_id,
      icon: group.icon !== void 0 ? group.icon : null,
      requiredPermissions: []
    });
    if (Array.isArray(group.entries) === false) {
      continue;
    }
    for (const entry of group.entries) {
      if (entry === null || typeof entry.route !== "string" || entry.route.length === 0) {
        continue;
      }
      registry.registerEntry({
        entryId: typeof entry.entry_id === "string" ? entry.entry_id : entry.route,
        label: typeof entry.label === "string" ? entry.label : entry.route,
        route: entry.route,
        icon: entry.icon !== void 0 ? entry.icon : null,
        requiredPermissions: [],
        group: group.group_id,
        section: typeof entry.section === "string" ? entry.section : ""
      });
    }
  }
  return;
}
function _coerce_manifest(payload) {
  if (payload === null || typeof payload !== "object") {
    return null;
  }
  const candidate = payload;
  if (Array.isArray(candidate.groups) === false) {
    return null;
  }
  const rtnval = {
    groups: candidate.groups,
    ui_profile: candidate.ui_profile !== null && typeof candidate.ui_profile === "object" ? candidate.ui_profile : null
  };
  return rtnval;
}
export {
  DEFAULT_NAVIGATION_ENDPOINT,
  apply_nav_manifest,
  fetch_nav_manifest
};
