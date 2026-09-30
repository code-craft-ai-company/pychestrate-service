/*
 * One empty state for the bundle lists (ORC-34).
 *
 * A list with nothing in it said "No pods defined" and stopped. It should say
 * what is missing, what to do first, and where: this builds that paragraph, so
 * every view words and marks it the same way. It keeps each view's own class
 * (its stylesheet decides the look) and always carries ``data-role="empty-state"``
 * so a test or a script can find it; the link, when there is one, carries
 * ``data-role="empty-state-link"``.
 *
 * This file is bundled into each bundle by esbuild.
 */

/*
 * The paragraph for an empty list.
 *
 *   class_name  the view's own class for a status line
 *   inline      true for a <span> (inside a notice box) instead of a <p>
 *   role        an ARIA role to set ("status" for a live region)
 *   message     what is missing, as a sentence ("No SLOs in this project yet.")
 *   next_step   what to do about it, as a sentence (optional)
 *   link        { href, label, class_name } for the page where the first step is
 *               done (optional; class_name is the view's own link class)
 */
export function build_empty_state({ class_name, message, next_step, link, inline, role }) {
  const paragraph = document.createElement(inline === true ? "span" : "p");
  if (typeof class_name === "string" && class_name.length > 0) {
    paragraph.classList.add(class_name);
  }
  paragraph.setAttribute("data-role", "empty-state");
  if (typeof role === "string" && role.length > 0) {
    paragraph.setAttribute("role", role);
  }
  const words = [message];
  if (typeof next_step === "string" && next_step.length > 0) {
    words.push(next_step);
  }
  paragraph.appendChild(document.createTextNode(words.join(" ")));
  if (link !== undefined && link !== null) {
    paragraph.appendChild(document.createTextNode(" "));
    const anchor = document.createElement("a");
    if (typeof link.class_name === "string" && link.class_name.length > 0) {
      anchor.classList.add(link.class_name);
    }
    anchor.setAttribute("href", link.href);
    anchor.setAttribute("data-role", "empty-state-link");
    anchor.textContent = link.label;
    paragraph.appendChild(anchor);
  }
  return paragraph;
}

/*
 * Replace ``region``'s content with the empty state for a page that works inside
 * a project when there is none: creating one is the first step.
 */
export function show_no_projects(region, { link_class_name }) {
  region.replaceChildren(
    build_empty_state({
      inline: true,
      message: "No projects exist yet.",
      next_step: "This page works inside a project, so create one first.",
      link: { href: "/projects/create", label: "Create a project", class_name: link_class_name },
    })
  );
}
