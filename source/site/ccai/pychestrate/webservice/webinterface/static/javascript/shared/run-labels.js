/*
 * What a run, build or provisioning row says it is (ORC-11).
 *
 * Rows used to lead with an 8-character hash. A row now leads with what ran,
 * and the id follows, smaller, for the person who needs to quote it.
 *
 * This file is bundled into each bundle by esbuild.
 */

// Build, provision and RPA runs carry "<kind>-<detail>" job types; anything
// else is a test run.
const JOB_TYPE_KINDS = [
  ["rpa-", "RPA"],
  ["build-", "Build"],
  ["provision-", "Provisioning"],
];

/* "build-makefile" -> "Build · makefile", "testbase" -> "Test · testbase". */
export function job_type_label(job_type) {
  const text = typeof job_type === "string" ? job_type.trim() : "";
  if (text.length === 0) {
    return "—";
  }
  for (const [prefix, label] of JOB_TYPE_KINDS) {
    if (text.startsWith(prefix) === true) {
      const detail = text.slice(prefix.length);
      return detail.length > 0 ? label + " · " + detail : label;
    }
  }
  return "Test · " + text;
}

/* What to call a run in a list: its job name, else its kind. */
export function run_title(run) {
  const name = typeof run.job_name === "string" ? run.job_name.trim() : "";
  if (name.length > 0) {
    return name;
  }
  const label = job_type_label(run.job_type);
  return label === "—" ? "Run" : label;
}

/*
 * What a build ran: its runner kind and target ("makefile · build-docs"),
 * or just the runner kind when it names no target.
 */
export function build_title(build) {
  const kind = typeof build.runner_kind === "string" && build.runner_kind.length > 0 ? build.runner_kind : "build";
  const inputs = build.inputs !== null && typeof build.inputs === "object" ? build.inputs : {};
  const target = typeof inputs.target === "string" ? inputs.target.trim() : "";
  return target.length > 0 ? kind + " · " + target : kind;
}

/* Where a build's source came from: "main @ github.com/acme/repo", or "" without one. */
export function build_source_label(build) {
  const source = build.source;
  if (source === null || source === void 0 || typeof source !== "object") {
    return "";
  }
  const ref = typeof source.ref === "string" ? source.ref : "";
  let repository = typeof source.url === "string" ? source.url : "";
  repository = repository.replace(/^[a-z+]+:\/\//i, "").replace(/\.git$/i, "").replace(/^[^@/]*@/, "");
  if (ref.length > 0 && repository.length > 0) {
    return ref + " @ " + repository;
  }
  return ref.length > 0 ? ref : repository;
}

/* "Provisioning a run": what a provisioning run did, e.g. "apply · terraform". */
export function provisioning_title(run) {
  const action = typeof run.action === "string" && run.action.length > 0 ? run.action : "run";
  const driver = typeof run.driver_name === "string" ? run.driver_name : "";
  return driver.length > 0 ? action + " · " + driver : action;
}
