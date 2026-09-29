/*
 * What the server said, when it refused a request (ORC-08).
 *
 * Every REST error is an RFC 7807 problem document whose `detail` says what
 * was wrong with this request ("No enrolled pod can take this run"). Bundle
 * views mapped the status to a fixed sentence and dropped the detail, so a
 * refused run said "The environment cannot accept this action" whatever the
 * reason. These two helpers let a view keep its sentence as the fallback and
 * show the server's own words when it has some.
 *
 * This file is bundled into each bundle by esbuild.
 */

// Details that only repeat the HTTP reason phrase say nothing a view's own
// sentence does not say better ("Unknown project." beats "Not Found").
const REASON_PHRASES = [
  "bad request",
  "unauthorized",
  "unauthenticated",
  "authentication required.",
  "forbidden",
  "not found",
  "method not allowed",
  "conflict",
  "unprocessable entity",
  "validation failed",
  "internal server error",
  "service unavailable",
  "error",
];

/*
 * The `detail` of an already-parsed problem document as one line, or "" when
 * there is none or it only repeats the reason phrase.
 */
export function problem_detail_of_body(body) {
  if (body !== null && typeof body === "object" && typeof body.detail === "string") {
    const line = body.detail.split(/\r?\n/).map((part) => part.trim()).filter((part) => part.length > 0).join(" ");
    if (line.length > 0 && REASON_PHRASES.indexOf(line.toLowerCase()) < 0) {
      return line;
    }
  }
  return "";
}

/*
 * The problem document's `detail` of a refused response as one line, or ""
 * when the response succeeded, has no readable body, or the detail only
 * repeats the reason phrase. The body is read for a refused response (a
 * successful one is left alone): call it in place of reading the body yourself.
 */
export async function read_problem_detail(response) {
  if (response.ok === true) {
    return "";
  }
  try {
    return problem_detail_of_body(await response.json());
  } catch (error) {
    // Not JSON (a proxy's page, an empty body): there is no detail.
    return "";
  }
}

/* "Provisioning run not started: <detail>", or the view's own sentence. */
export function message_with_detail(prefix, detail, generic) {
  if (typeof detail === "string" && detail.length > 0) {
    return prefix + ": " + detail;
  }
  return generic;
}
