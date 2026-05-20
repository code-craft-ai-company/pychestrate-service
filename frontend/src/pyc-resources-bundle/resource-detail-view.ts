/**
 * ``<pyc-resource-detail>`` -- the resource detail view Custom
 * Element.
 *
 * On mount (route ``/resource-pools/resources/{resource_id}``) the
 * element fetches, in order:
 *
 * * ``GET /api/v1/resources/{resource_id}`` -- the resource record.
 * * ``GET …/resources/{resource_id}/health`` -- the current health
 *   probe record. A 404 means the resource has never been
 *   health-seeded -- rendered as an empty state, not an error.
 * * ``GET …/resources/{resource_id}/usage-history`` -- the
 *   newest-first usage timeline (a ``UsageRecordPage`` envelope).
 *
 * The usage timeline is rendered with a simple token-styled bar /
 * row layout -- no charting library.
 *
 * The element is a native Custom Element -- no framework. It calls
 * the REST API directly via ``fetch`` with ``credentials:
 * "same-origin"``. It never writes to ``localStorage`` /
 * ``sessionStorage``; all state lives in instance fields.
 */

import {
    type PageMeta,
    format_timestamp,
    short_id,
} from "./resource-pools-view.js"
import { is_valid_uuid } from "./pool-detail-view.js"

/**
 * An authoritative resource record, mirroring the ``Resource``
 * OpenAPI schema.
 */
export interface Resource {
    resource_id: string
    project_id: string
    kind: string
    display_name?: string | null
    description?: string | null
    identity_hash?: string | null
    state: string
    tags?: string[] | null
    attributes?: Record<string, unknown> | null
    created_at?: string | null
    updated_at?: string | null
}

/**
 * The current health-probe record for a resource, mirroring the
 * ``ResourceHealth`` OpenAPI schema.
 */
export interface ResourceHealth {
    health_id: string
    resource_id: string
    project_id: string
    probe_name: string
    probe_period_seconds?: number | null
    last_outcome: string
    last_probe_at?: string | null
    last_pass_at?: string | null
    last_fail_at?: string | null
    next_probe_at?: string | null
    pass_count?: number | null
    fail_count?: number | null
    consecutive_failures?: number | null
    last_error?: string | null
    last_payload?: Record<string, unknown> | null
}

/**
 * One usage-timeline event, mirroring the ``UsageRecord`` OpenAPI
 * schema.
 */
export interface UsageRecord {
    event_id: string
    source_event_id: string
    resource_id: string
    project_id: string
    event_type: string
    actor_id?: string | null
    pod_event_group_id?: string | null
    at_ts: string
    payload?: Record<string, unknown> | null
    annotations?: Record<string, unknown> | null
}

/**
 * The ``UsageRecordPage`` response shape.
 */
export interface UsageRecordPage {
    items: UsageRecord[]
    meta: PageMeta
}

/**
 * Diagnostic snapshot of the resource detail view's runtime state.
 * Exposed via the ``detailState`` accessor for unit tests.
 */
export interface ResourceDetailState {
    resourceId: string
    loading: boolean
    errored: boolean
    hasHealth: boolean
}

/**
 * Extract a ``resource_id`` from a shell-served path of the form
 * ``/resource-pools/resources/{resource_id}``. The resource-detail
 * route nests under the ``/resource-pools`` prefix because the
 * top-level ``/resources`` prefix is claimed by the legacy
 * resources blueprint. Returns an empty string when the path does
 * not name a single resource.
 *
 * @param path A request path (typically ``window.location.pathname``).
 *
 * @returns The resource id segment, or ``""``.
 */
export function resource_id_from_path(path: string): string {
    if (typeof path !== "string" || path.length === 0) {
        const rtnval = ""
        return rtnval
    }
    const prefix = "/resource-pools/resources/"
    if (path.startsWith(prefix) === false) {
        const rtnval = ""
        return rtnval
    }
    let tail = path.slice(prefix.length)
    const slash_index = tail.indexOf("/")
    if (slash_index >= 0) {
        tail = tail.slice(0, slash_index)
    }
    const query_index = tail.indexOf("?")
    if (query_index >= 0) {
        tail = tail.slice(0, query_index)
    }
    const rtnval = tail
    return rtnval
}

/**
 * Classify a health outcome into a coarse badge tone.
 *
 * @param outcome One of the ``ResourceHealth.last_outcome`` enum
 *                values.
 *
 * @returns ``"ok"`` | ``"error"`` | ``"neutral"``.
 */
export function health_tone(outcome: string): string {
    if (outcome === "pass") {
        const rtnval = "ok"
        return rtnval
    }
    if (outcome === "fail") {
        const rtnval = "error"
        return rtnval
    }
    const rtnval = "neutral"
    return rtnval
}

/**
 * Classify a resource state into a coarse badge tone.
 *
 * @param state One of the ``Resource.state`` enum values.
 *
 * @returns ``"ok"`` | ``"warn"`` | ``"error"`` | ``"neutral"``.
 */
export function resource_state_tone(state: string): string {
    if (state === "available") {
        const rtnval = "ok"
        return rtnval
    }
    if (state === "leased" || state === "maintenance") {
        const rtnval = "warn"
        return rtnval
    }
    if (state === "quarantined" || state === "retired") {
        const rtnval = "error"
        return rtnval
    }
    const rtnval = "neutral"
    return rtnval
}

/**
 * Classify a usage-event type into a coarse tone for the timeline
 * marker -- a ``*.failed`` / ``*.rejected`` event reads as error,
 * a ``*.granted`` / ``*.registered`` event as ok.
 *
 * @param event_type A timeline event type string.
 *
 * @returns ``"ok"`` | ``"error"`` | ``"neutral"``.
 */
export function usage_event_tone(event_type: string): string {
    if (typeof event_type !== "string") {
        const rtnval = "neutral"
        return rtnval
    }
    const lowered = event_type.toLowerCase()
    if (
        lowered.indexOf("fail") >= 0 ||
        lowered.indexOf("reject") >= 0 ||
        lowered.indexOf("quarantine") >= 0
    ) {
        const rtnval = "error"
        return rtnval
    }
    if (
        lowered.indexOf("grant") >= 0 ||
        lowered.indexOf("register") >= 0 ||
        lowered.indexOf("pass") >= 0
    ) {
        const rtnval = "ok"
        return rtnval
    }
    const rtnval = "neutral"
    return rtnval
}

/**
 * Build the ``GET /resources/{resource_id}`` detail URL.
 *
 * @param resource_id Resource identifier.
 *
 * @returns A relative URL string.
 */
export function build_resource_url(resource_id: string): string {
    const rtnval = "/api/v1/resources/" + encodeURIComponent(resource_id)
    return rtnval
}

/**
 * Build the ``GET …/resources/{resource_id}/health`` URL.
 *
 * @param resource_id Resource identifier.
 *
 * @returns A relative URL string.
 */
export function build_resource_health_url(resource_id: string): string {
    const rtnval = build_resource_url(resource_id) + "/health"
    return rtnval
}

/**
 * Build the ``GET …/resources/{resource_id}/usage-history`` URL.
 *
 * @param resource_id Resource identifier.
 *
 * @returns A relative URL string.
 */
export function build_resource_usage_url(resource_id: string): string {
    const rtnval = build_resource_url(resource_id) + "/usage-history"
    return rtnval
}

/**
 * The resource detail view Custom Element. Register it with
 * ``customElements.define("pyc-resource-detail", PycResourceDetail)``.
 */
export class PycResourceDetail extends HTMLElement {
    private _resource_id: string
    private _resource: Resource | null
    private _health: ResourceHealth | null
    private _usage: UsageRecord[]
    private _loading: boolean
    private _errored: boolean
    private _root: HTMLElement | null

    public constructor() {
        super()
        this._resource_id = ""
        this._resource = null
        this._health = null
        this._usage = []
        this._loading = false
        this._errored = false
        this._root = null
    }

    /**
     * Observed attributes -- ``resource-id`` may be supplied
     * explicitly by a host; otherwise it is read from the path on
     * mount.
     */
    public static get observedAttributes(): string[] {
        const rtnval = ["resource-id"]
        return rtnval
    }

    /**
     * Diagnostic accessor used by unit tests to inspect the view's
     * runtime state without scraping the DOM.
     */
    public get detailState(): ResourceDetailState {
        const rtnval: ResourceDetailState = {
            resourceId: this._resource_id,
            loading: this._loading,
            errored: this._errored,
            hasHealth: this._health !== null,
        }
        return rtnval
    }

    /**
     * Lifecycle hook -- resolve the resource id, render the chrome,
     * and fetch the initial snapshot.
     */
    public connectedCallback(): void {
        const attr_resource = this.getAttribute("resource-id")
        if (attr_resource !== null && attr_resource.length > 0) {
            this._resource_id = attr_resource
        } else {
            this._resource_id = resource_id_from_path(
                window.location.pathname,
            )
        }
        this._render_chrome()
        void this._load()
        return
    }

    /**
     * Fetch the resource snapshot. Exposed so unit tests can await a
     * load cycle.
     */
    public async load(): Promise<void> {
        await this._load()
        return
    }

    private async _load(): Promise<void> {
        if (is_valid_uuid(this._resource_id) === false) {
            this._loading = false
            this._errored = true
            this._render_body()
            return
        }
        this._loading = true
        this._errored = false
        this._render_body()

        const resource = await this._fetch_json<Resource>(
            build_resource_url(this._resource_id),
            "resource_fetch_failed",
        )
        if (resource === null) {
            this._loading = false
            this._errored = true
            this._render_body()
            return
        }
        this._resource = resource

        this._health = await this._fetch_json<ResourceHealth>(
            build_resource_health_url(this._resource_id),
            "health_fetch_failed",
        )

        const usage = await this._fetch_json<UsageRecordPage>(
            build_resource_usage_url(this._resource_id),
            "usage_fetch_failed",
        )
        if (usage !== null && Array.isArray(usage.items) === true) {
            this._usage = usage.items
        }

        this._loading = false
        this._errored = false
        this._render_body()
        return
    }

    private async _fetch_json<T>(
            url: string,
            failure_tag: string,
        ): Promise<T | null> {
        try {
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === false) {
                const rtnval = null
                return rtnval
            }
            const body = await response.json()
            const rtnval = body as T
            return rtnval
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.resources." + failure_tag,
                { reason: String(reason) },
            )
            const rtnval = null
            return rtnval
        }
    }

    private _render_chrome(): void {
        const root = document.createElement("section")
        root.classList.add("pyc-resources", "pyc-resource-detail")
        root.setAttribute("role", "main")
        root.setAttribute("aria-label", "Resource detail")

        const heading = document.createElement("h1")
        heading.classList.add("pyc-resources__heading")
        heading.textContent = "Resource detail"
        root.appendChild(heading)

        const back = document.createElement("a")
        back.classList.add("pyc-resources__back-link")
        back.setAttribute("href", "/resource-pools")
        back.setAttribute("data-role", "back-link")
        back.textContent = "Back to resource pools"
        root.appendChild(back)

        const body = document.createElement("div")
        body.classList.add("pyc-resources__body")
        body.setAttribute("data-role", "body")
        root.appendChild(body)

        this._root = root
        this.replaceChildren(root)
        return
    }

    private _render_body(): void {
        if (this._root === null) {
            return
        }
        const body = this._root.querySelector('[data-role="body"]')
        if (body === null) {
            return
        }

        if (this._loading === true) {
            const loading = document.createElement("p")
            loading.classList.add("pyc-resources__status")
            loading.setAttribute("data-role", "loading-state")
            loading.textContent = "Loading resource…"
            body.replaceChildren(loading)
            return
        }

        if (this._errored === true || this._resource === null) {
            const error = document.createElement("p")
            error.classList.add(
                "pyc-resources__status",
                "pyc-resources__status--error",
            )
            error.setAttribute("data-role", "error-state")
            error.textContent =
                "Failed to load this resource. Try refreshing."
            body.replaceChildren(error)
            return
        }

        const fragment = document.createDocumentFragment()
        fragment.appendChild(this._build_summary(this._resource))
        fragment.appendChild(this._build_health())
        fragment.appendChild(this._build_usage_timeline())
        body.replaceChildren(fragment)
        return
    }

    private _build_summary(resource: Resource): HTMLElement {
        const section = document.createElement("section")
        section.classList.add("pyc-resources__summary")
        section.setAttribute("role", "region")
        section.setAttribute("aria-label", "Resource summary")

        const id_row = document.createElement("div")
        id_row.classList.add("pyc-resources__id-row")
        const id_value = document.createElement("span")
        id_value.classList.add("pyc-resources__id")
        id_value.setAttribute("data-role", "resource-id")
        id_value.textContent = short_id(resource.resource_id)
        id_value.title = resource.resource_id
        id_row.appendChild(id_value)

        const badge = document.createElement("span")
        badge.classList.add("pyc-badge")
        badge.setAttribute("data-role", "state-badge")
        badge.setAttribute(
            "data-tone",
            resource_state_tone(resource.state),
        )
        badge.textContent = resource.state
        id_row.appendChild(badge)
        section.appendChild(id_row)

        const grid = document.createElement("dl")
        grid.classList.add("pyc-resources__grid")
        this._append_field(grid, "Resource id", resource.resource_id)
        this._append_field(grid, "Kind", resource.kind)
        this._append_field(grid, "Project", resource.project_id)
        const display_name =
            resource.display_name !== null &&
                resource.display_name !== undefined
                ? resource.display_name
                : ""
        if (display_name.length > 0) {
            this._append_field(grid, "Display name", display_name)
        }
        this._append_field(grid, "State", resource.state)
        this._append_field(
            grid,
            "Created",
            format_timestamp(resource.created_at),
        )
        section.appendChild(grid)

        const tags = Array.isArray(resource.tags) === true
            ? (resource.tags as string[])
            : []
        if (tags.length > 0) {
            const tag_list = document.createElement("div")
            tag_list.classList.add("pyc-resources__tag-list")
            for (const tag of tags) {
                const chip = document.createElement("span")
                chip.classList.add("pyc-resources__tag")
                chip.textContent = tag
                tag_list.appendChild(chip)
            }
            section.appendChild(tag_list)
        }
        return section
    }

    private _build_health(): HTMLElement {
        const section = document.createElement("section")
        section.classList.add("pyc-resources__health")
        section.setAttribute("data-role", "health-section")
        section.setAttribute("role", "region")
        section.setAttribute("aria-label", "Resource health")

        const heading = document.createElement("h2")
        heading.classList.add("pyc-resources__section-heading")
        heading.textContent = "Health"
        section.appendChild(heading)

        if (this._health === null) {
            const empty = document.createElement("p")
            empty.classList.add("pyc-resources__status")
            empty.setAttribute("data-role", "health-empty")
            empty.textContent =
                "No health record has been seeded for this resource."
            section.appendChild(empty)
            return section
        }

        const health = this._health

        const outcome_row = document.createElement("div")
        outcome_row.classList.add("pyc-resources__id-row")
        const badge = document.createElement("span")
        badge.classList.add("pyc-badge")
        badge.setAttribute("data-role", "health-badge")
        badge.setAttribute("data-tone", health_tone(health.last_outcome))
        badge.textContent = health.last_outcome
        outcome_row.appendChild(badge)
        const probe = document.createElement("span")
        probe.classList.add("pyc-resources__reservation-label")
        probe.textContent = " " + health.probe_name
        outcome_row.appendChild(probe)
        section.appendChild(outcome_row)

        const grid = document.createElement("dl")
        grid.classList.add("pyc-resources__grid")
        this._append_field(
            grid,
            "Last probe",
            format_timestamp(health.last_probe_at),
        )
        this._append_field(
            grid,
            "Last pass",
            format_timestamp(health.last_pass_at),
        )
        this._append_field(
            grid,
            "Last fail",
            format_timestamp(health.last_fail_at),
        )
        this._append_field(
            grid,
            "Pass count",
            String(health.pass_count !== null &&
                health.pass_count !== undefined
                ? health.pass_count
                : 0),
        )
        this._append_field(
            grid,
            "Fail count",
            String(health.fail_count !== null &&
                health.fail_count !== undefined
                ? health.fail_count
                : 0),
        )
        this._append_field(
            grid,
            "Consecutive failures",
            String(health.consecutive_failures !== null &&
                health.consecutive_failures !== undefined
                ? health.consecutive_failures
                : 0),
        )
        section.appendChild(grid)

        if (
            health.last_error !== null &&
            health.last_error !== undefined &&
            health.last_error.length > 0
        ) {
            const error = document.createElement("p")
            error.classList.add("pyc-resources__health-error")
            error.setAttribute("data-role", "health-error")
            error.textContent = "Last error: " + health.last_error
            section.appendChild(error)
        }
        return section
    }

    private _build_usage_timeline(): HTMLElement {
        const section = document.createElement("section")
        section.classList.add("pyc-resources__usage")
        section.setAttribute("data-role", "usage-section")
        section.setAttribute("role", "region")
        section.setAttribute("aria-label", "Usage history")

        const heading = document.createElement("h2")
        heading.classList.add("pyc-resources__section-heading")
        heading.textContent = "Usage history"
        section.appendChild(heading)

        if (this._usage.length === 0) {
            const empty = document.createElement("p")
            empty.classList.add("pyc-resources__status")
            empty.setAttribute("data-role", "usage-empty")
            empty.textContent =
                "No usage-history events for this resource."
            section.appendChild(empty)
            return section
        }

        const timeline = document.createElement("ol")
        timeline.classList.add("pyc-resources__timeline")
        timeline.setAttribute("data-role", "usage-timeline")
        for (const record of this._usage) {
            const item = document.createElement("li")
            item.classList.add("pyc-resources__timeline-entry")

            const marker = document.createElement("span")
            marker.classList.add("pyc-resources__timeline-marker")
            marker.setAttribute(
                "data-tone",
                usage_event_tone(record.event_type),
            )
            item.appendChild(marker)

            const detail = document.createElement("div")
            detail.classList.add("pyc-resources__timeline-detail")

            const type_line = document.createElement("span")
            type_line.classList.add("pyc-resources__timeline-type")
            type_line.textContent = record.event_type
            detail.appendChild(type_line)

            const ts_line = document.createElement("span")
            ts_line.classList.add("pyc-resources__timeline-ts")
            ts_line.textContent = format_timestamp(record.at_ts)
            detail.appendChild(ts_line)

            item.appendChild(detail)
            timeline.appendChild(item)
        }
        section.appendChild(timeline)
        return section
    }

    private _append_field(
            grid: HTMLElement,
            label: string,
            value: string,
        ): void {
        const field = document.createElement("div")
        field.classList.add("pyc-resources__field")
        const term = document.createElement("dt")
        term.textContent = label
        const def = document.createElement("dd")
        def.textContent = value
        field.appendChild(term)
        field.appendChild(def)
        grid.appendChild(field)
        return
    }
}
