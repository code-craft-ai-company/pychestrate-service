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

/*
 * A state or status as it reads on a chip: the stored spelling with its underscores and dashes
 * read as spaces ("dispatch_unconfirmed" -> "dispatch unconfirmed", "needs_investigation" ->
 * "needs investigation"), and a state stored in capitals in lowercase ("IN_USE" -> "in use").
 * The stored value is still what the colour and the logic go by.
 */
export function state_label(state) {
  if (typeof state !== "string" || state.length === 0) {
    return "\u2014";
  }
  const words = state.replace(/[_-]+/g, " ");
  // A state stored in capitals (a pod's IN_USE, a client's REVOKED) reads in the glossary's lowercase vocabulary.
  return /^[A-Z0-9 ]+$/.test(words) ? words.toLowerCase() : words;
}

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

// A job name that is only an identifier says nothing a person can read (test
// runs are named by their catalog entry's id), so it is treated as no name.
const IDENTIFIER_PATTERN = /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$|^[0-9a-f]{16,}$/i;

// What an unnamed run is called, by its kind.
const KIND_TITLES = [
  ["rpa-", "RPA run"],
  ["build-", "Build run"],
  ["provision-", "Provisioning run"],
];

/* What to call a run in a list: its job name when it is readable, else its kind ("Test run"). */
export function run_title(run) {
  const name = typeof run.job_name === "string" ? run.job_name.trim() : "";
  if (name.length > 0 && IDENTIFIER_PATTERN.test(name) === false) {
    return name;
  }
  const job_type = typeof run.job_type === "string" ? run.job_type.trim() : "";
  for (const [prefix, title] of KIND_TITLES) {
    if (job_type.startsWith(prefix) === true) {
      return title;
    }
  }
  return "Test run";
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
