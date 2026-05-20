/**
 * ``<pyc-pipeline-detail>`` -- the pipeline-definition detail view
 * Custom Element.
 *
 * On mount (route ``/pipelines/{pipeline_id}``) the element fetches
 * ``GET /api/v1/projects/{project_id}/pipelines/{pipeline_id}`` for
 * the pipeline-definition snapshot and renders its identity plus a
 * visualization of the stage DAG.
 *
 * DAG visualization approach
 * --------------------------
 * The stage DAG is rendered as an inline-SVG node-and-edge layout.
 * Layout is deliberately lightweight -- no force-directed engine:
 *
 * 1. ``compute_dag_columns`` assigns each stage a *depth* equal to
 *    the longest dependency chain reaching it (a Kahn-style
 *    longest-path layering). Stages with no ``needs`` land in
 *    column 0; each dependent lands one column to the right of its
 *    deepest dependency.
 * 2. ``compute_dag_layout`` turns those columns into pixel
 *    positions -- columns map to x, row-within-column maps to y --
 *    yielding one box per stage plus one edge per ``needs`` entry.
 *
 * Both functions are pure (no DOM, no fetch) so they are
 * unit-testable in isolation.
 *
 * When the DAG cannot be laid out as a clean DAG -- a dependency
 * cycle leaves some stages unranked -- the view falls back to a
 * plain adjacency-list rendering ("Stage A → depends on: B, C").
 * The SVG layout is the primary rendering; the adjacency list is
 * the documented fallback for pathological inputs.
 *
 * Because the route carries only ``pipeline_id`` (no project id)
 * the first fetch addresses a project-agnostic resolver path,
 * ``/api/v1/pipelines/{pipeline_id}`` -- the server resolves the
 * owning project. The ``project_id`` is then read off the returned
 * ``PipelineDefinition``.
 *
 * The element is a native Custom Element -- no framework. It calls
 * the REST API directly via ``fetch`` with ``credentials:
 * "same-origin"``. It never writes to ``localStorage`` /
 * ``sessionStorage``; all state lives in instance fields.
 */

import {
    type PipelineDefinition,
    type PipelineStage,
    short_id,
    format_timestamp,
} from "./pipelines-list-view.js"

/**
 * One stage placed at a layout column with a row index.
 */
export interface DagColumnAssignment {
    stageId: string
    column: number
    row: number
}

/**
 * Outcome of the column-assignment pass.
 */
export interface DagColumns {
    /** Per-stage column + row, in stable stage order. */
    assignments: DagColumnAssignment[]
    /** True when every stage was rankable (the input is a DAG). */
    isDag: boolean
}

/**
 * A laid-out node box in the DAG SVG.
 */
export interface DagNode {
    stageId: string
    x: number
    y: number
    width: number
    height: number
}

/**
 * A laid-out edge between two node boxes -- ``from`` depends on
 * (``needs``) ``to``; the edge is drawn ``to`` → ``from``.
 */
export interface DagEdge {
    fromStageId: string
    toStageId: string
    x1: number
    y1: number
    x2: number
    y2: number
}

/**
 * The full laid-out DAG -- node boxes, edges, and the canvas size.
 */
export interface DagLayout {
    nodes: DagNode[]
    edges: DagEdge[]
    width: number
    height: number
    isDag: boolean
}

/**
 * Node box width, in SVG user units.
 */
const NODE_WIDTH: number = 140

/**
 * Node box height, in SVG user units.
 */
const NODE_HEIGHT: number = 44

/**
 * Horizontal gap between adjacent columns.
 */
const COLUMN_GAP: number = 80

/**
 * Vertical gap between stacked rows in a column.
 */
const ROW_GAP: number = 24

/**
 * Outer padding around the laid-out DAG.
 */
const CANVAS_PADDING: number = 20

/**
 * Diagnostic snapshot of the detail view's runtime state. Exposed
 * via the ``detailState`` accessor for unit tests.
 */
export interface PipelineDetailState {
    pipelineId: string
    projectId: string
    loading: boolean
    errored: boolean
    isDag: boolean
}

/**
 * Base path of the projects REST collection.
 */
const PROJECTS_API_PATH: string = "/api/v1/projects"

/**
 * Project-agnostic pipeline resolver path. The server resolves the
 * owning project from the pipeline id.
 */
const PIPELINES_RESOLVER_PATH: string = "/api/v1/pipelines"

/**
 * Extract a ``pipeline_id`` from a shell-served path of the form
 * ``/pipelines/{pipeline_id}``. Returns an empty string when the
 * path does not name a single pipeline.
 *
 * @param path A request path (typically ``window.location.pathname``).
 *
 * @returns The pipeline id segment, or ``""`` when the path is not
 *          a pipeline-detail path.
 */
export function pipeline_id_from_path(path: string): string {
    if (typeof path !== "string" || path.length === 0) {
        const rtnval = ""
        return rtnval
    }
    const prefix = "/pipelines/"
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
 * Build the project-scoped ``GET …/pipelines/{pipeline_id}`` URL.
 *
 * @param project_id Owning project identifier.
 * @param pipeline_id Pipeline-definition identifier.
 *
 * @returns A relative URL string.
 */
export function pipeline_detail_url(
    project_id: string,
    pipeline_id: string,
): string {
    const rtnval = PROJECTS_API_PATH + "/" +
        encodeURIComponent(project_id) + "/pipelines/" +
        encodeURIComponent(pipeline_id)
    return rtnval
}

/**
 * Assign each stage a layout column via a longest-path layering.
 *
 * A stage with no ``needs`` lands in column 0. Every other stage
 * lands one column to the right of its deepest dependency. The
 * pass iterates until every stage is ranked or no further progress
 * is possible -- the latter signals an unresolved dependency cycle,
 * in which case ``isDag`` is false and the unranked stages are
 * omitted from ``assignments``.
 *
 * Pure -- no DOM, no fetch. Unit-tested directly.
 *
 * @param stages The pipeline's stages.
 *
 * @returns The per-stage column + row assignment.
 */
export function compute_dag_columns(stages: PipelineStage[]): DagColumns {
    const known_ids: Set<string> = new Set()
    for (const stage of stages) {
        known_ids.add(stage.stage_id)
    }

    const depth_by_id: Map<string, number> = new Map()
    let progressed = true
    while (progressed === true) {
        progressed = false
        for (const stage of stages) {
            if (depth_by_id.has(stage.stage_id) === true) {
                continue
            }
            const needs = stage.needs
            let deepest = -1
            let resolvable = true
            if (needs !== undefined && needs !== null) {
                for (const dep_id of needs) {
                    if (known_ids.has(dep_id) === false) {
                        // An unknown reference does not block layout --
                        // treat it as already satisfied at depth -1.
                        continue
                    }
                    const dep_depth = depth_by_id.get(dep_id)
                    if (dep_depth === undefined) {
                        resolvable = false
                        break
                    }
                    if (dep_depth > deepest) {
                        deepest = dep_depth
                    }
                }
            }
            if (resolvable === false) {
                continue
            }
            depth_by_id.set(stage.stage_id, deepest + 1)
            progressed = true
        }
    }

    const is_dag = depth_by_id.size === stages.length

    const row_cursor: Map<number, number> = new Map()
    const assignments: DagColumnAssignment[] = []
    for (const stage of stages) {
        const column = depth_by_id.get(stage.stage_id)
        if (column === undefined) {
            continue
        }
        const cursor = row_cursor.get(column)
        const row = cursor === undefined ? 0 : cursor
        row_cursor.set(column, row + 1)
        assignments.push({
            stageId: stage.stage_id,
            column: column,
            row: row,
        })
    }

    const rtnval: DagColumns = {
        assignments: assignments,
        isDag: is_dag,
    }
    return rtnval
}

/**
 * Turn a column assignment into a pixel layout -- one box per
 * stage, one edge per ``needs`` reference.
 *
 * Columns map to x (column index × (node width + column gap));
 * rows map to y (row index × (node height + row gap)). Each edge
 * runs from the right edge of the dependency box to the left edge
 * of the dependent box.
 *
 * Pure -- no DOM, no fetch. Unit-tested directly.
 *
 * @param stages The pipeline's stages.
 *
 * @returns The laid-out DAG -- nodes, edges, canvas size.
 */
export function compute_dag_layout(stages: PipelineStage[]): DagLayout {
    const columns = compute_dag_columns(stages)

    const node_by_id: Map<string, DagNode> = new Map()
    const nodes: DagNode[] = []
    let max_x = 0
    let max_y = 0
    for (const entry of columns.assignments) {
        const x = CANVAS_PADDING +
            entry.column * (NODE_WIDTH + COLUMN_GAP)
        const y = CANVAS_PADDING +
            entry.row * (NODE_HEIGHT + ROW_GAP)
        const node: DagNode = {
            stageId: entry.stageId,
            x: x,
            y: y,
            width: NODE_WIDTH,
            height: NODE_HEIGHT,
        }
        node_by_id.set(entry.stageId, node)
        nodes.push(node)
        if (x + NODE_WIDTH > max_x) {
            max_x = x + NODE_WIDTH
        }
        if (y + NODE_HEIGHT > max_y) {
            max_y = y + NODE_HEIGHT
        }
    }

    const edges: DagEdge[] = []
    for (const stage of stages) {
        const dependent = node_by_id.get(stage.stage_id)
        if (dependent === undefined) {
            continue
        }
        const needs = stage.needs
        if (needs === undefined || needs === null) {
            continue
        }
        for (const dep_id of needs) {
            const dependency_node = node_by_id.get(dep_id)
            if (dependency_node === undefined) {
                continue
            }
            const edge: DagEdge = {
                fromStageId: stage.stage_id,
                toStageId: dep_id,
                x1: dependency_node.x + dependency_node.width,
                y1: dependency_node.y + dependency_node.height / 2,
                x2: dependent.x,
                y2: dependent.y + dependent.height / 2,
            }
            edges.push(edge)
        }
    }

    const rtnval: DagLayout = {
        nodes: nodes,
        edges: edges,
        width: max_x + CANVAS_PADDING,
        height: max_y + CANVAS_PADDING,
        isDag: columns.isDag,
    }
    return rtnval
}

/**
 * SVG namespace URI -- required so ``createElementNS`` produces
 * real SVG elements.
 */
const SVG_NS: string = "http://www.w3.org/2000/svg"

/**
 * The pipeline detail view Custom Element. Register it with
 * ``customElements.define("pyc-pipeline-detail", PycPipelineDetail)``.
 */
export class PycPipelineDetail extends HTMLElement {
    private _pipeline_id: string
    private _project_id: string
    private _pipeline: PipelineDefinition | null
    private _loading: boolean
    private _errored: boolean
    private _is_dag: boolean
    private _root: HTMLElement | null

    public constructor() {
        super()
        this._pipeline_id = ""
        this._project_id = ""
        this._pipeline = null
        this._loading = false
        this._errored = false
        this._is_dag = true
        this._root = null
    }

    /**
     * Observed attributes -- ``pipeline-id`` may be supplied
     * explicitly by a host; otherwise it is read from the path on
     * mount.
     */
    public static get observedAttributes(): string[] {
        const rtnval = ["pipeline-id"]
        return rtnval
    }

    /**
     * Diagnostic accessor used by unit tests to inspect the view's
     * runtime state without scraping the DOM.
     */
    public get detailState(): PipelineDetailState {
        const rtnval = {
            pipelineId: this._pipeline_id,
            projectId: this._project_id,
            loading: this._loading,
            errored: this._errored,
            isDag: this._is_dag,
        }
        return rtnval
    }

    /**
     * Lifecycle hook -- resolve the pipeline id, render the chrome,
     * and fetch the snapshot.
     */
    public connectedCallback(): void {
        const attr_id = this.getAttribute("pipeline-id")
        if (attr_id !== null && attr_id.length > 0) {
            this._pipeline_id = attr_id
        } else {
            this._pipeline_id = pipeline_id_from_path(window.location.pathname)
        }
        this._render_chrome()
        void this._load()
        return
    }

    /**
     * Fetch the pipeline snapshot and render it. Exposed so unit
     * tests can await a load cycle.
     */
    public async load(): Promise<void> {
        await this._load()
        return
    }

    private async _load(): Promise<void> {
        if (this._pipeline_id.length === 0) {
            this._loading = false
            this._errored = true
            this._render_body()
            return
        }
        this._loading = true
        this._errored = false
        this._render_body()

        const pipeline = await this._fetch_pipeline()
        if (pipeline === null) {
            this._loading = false
            this._errored = true
            this._render_body()
            return
        }

        this._pipeline = pipeline
        this._project_id = pipeline.project_id
        this._loading = false
        this._errored = false
        this._render_body()
        return
    }

    /**
     * Fetch the pipeline-definition snapshot via the project-
     * agnostic resolver path.
     *
     * @returns The ``PipelineDefinition``, or ``null`` on failure.
     */
    private async _fetch_pipeline(): Promise<PipelineDefinition | null> {
        let url = PIPELINES_RESOLVER_PATH + "/" +
            encodeURIComponent(this._pipeline_id)
        if (this._project_id.length > 0) {
            url = pipeline_detail_url(this._project_id, this._pipeline_id)
        }
        try {
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            })
            if (response.ok === false) {
                throw new Error(
                    "pipeline fetch failed: HTTP " + String(response.status),
                )
            }
            const body = await response.json()
            const rtnval = body as PipelineDefinition
            return rtnval
        } catch (reason: unknown) {
            console.warn(
                "pychestrate.ui.pipelines.detail_fetch_failed",
                { reason: String(reason) },
            )
            const rtnval = null
            return rtnval
        }
    }

    /**
     * Build the persistent chrome -- heading, back link, and the
     * body region the data render replaces.
     */
    private _render_chrome(): void {
        const root = document.createElement("section")
        root.classList.add("pyc-pipeline-detail")
        root.setAttribute("role", "main")
        root.setAttribute("aria-label", "Pipeline detail")

        const heading = document.createElement("h1")
        heading.classList.add("pyc-pipeline-detail__heading")
        heading.textContent = "Pipeline detail"
        root.appendChild(heading)

        const back = document.createElement("a")
        back.classList.add("pyc-pipeline-detail__back-link")
        back.setAttribute("href", "/pipelines")
        back.setAttribute("data-role", "back-link")
        back.textContent = "Back to pipelines"
        root.appendChild(back)

        const body = document.createElement("div")
        body.classList.add("pyc-pipeline-detail__body")
        body.setAttribute("data-role", "body")
        root.appendChild(body)

        this._root = root
        this.replaceChildren(root)
        return
    }

    /**
     * Re-render the body region from the current pipeline
     * snapshot, driving the loading / error / loaded states.
     */
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
            loading.classList.add("pyc-pipeline-detail__status")
            loading.setAttribute("data-role", "loading-state")
            loading.textContent = "Loading pipeline…"
            body.replaceChildren(loading)
            return
        }

        if (this._errored === true || this._pipeline === null) {
            const error = document.createElement("p")
            error.classList.add(
                "pyc-pipeline-detail__status",
                "pyc-pipeline-detail__status--error",
            )
            error.setAttribute("data-role", "error-state")
            error.textContent = "Failed to load this pipeline. Try refreshing."
            body.replaceChildren(error)
            return
        }

        const fragment = document.createDocumentFragment()
        fragment.appendChild(this._build_summary(this._pipeline))
        fragment.appendChild(this._build_dag_section(this._pipeline.stages))
        fragment.appendChild(this._build_stage_list(this._pipeline.stages))
        body.replaceChildren(fragment)
        return
    }

    /**
     * Build the pipeline summary block -- identity, name, schema
     * version, commit, filename, cached timestamp.
     *
     * @param pipeline The current pipeline snapshot.
     *
     * @returns A populated summary section element.
     */
    private _build_summary(pipeline: PipelineDefinition): HTMLElement {
        const section = document.createElement("section")
        section.classList.add("pyc-pipeline-detail__summary")
        section.setAttribute("role", "region")
        section.setAttribute("aria-label", "Pipeline summary")

        const id_row = document.createElement("div")
        id_row.classList.add("pyc-pipeline-detail__id-row")

        const id_value = document.createElement("span")
        id_value.classList.add("pyc-pipeline-detail__pipeline-id")
        id_value.setAttribute("data-role", "pipeline-id")
        id_value.textContent = short_id(pipeline.pipeline_id)
        id_value.title = pipeline.pipeline_id
        id_row.appendChild(id_value)

        const name_value = document.createElement("span")
        name_value.classList.add("pyc-pipeline-detail__name")
        name_value.setAttribute("data-role", "pipeline-name")
        name_value.textContent = pipeline.name
        id_row.appendChild(name_value)
        section.appendChild(id_row)

        const grid = document.createElement("dl")
        grid.classList.add("pyc-pipeline-detail__grid")

        this._append_field(grid, "Project", pipeline.project_id)
        this._append_field(grid, "Schema version", String(pipeline.schema_version))
        const stage_count = Array.isArray(pipeline.stages)
            ? pipeline.stages.length
            : 0
        this._append_field(grid, "Stages", String(stage_count))
        const commit = pipeline.commit_sha
        if (commit !== undefined && commit !== null && commit.length > 0) {
            this._append_field(grid, "Commit SHA", commit)
        }
        const filename = pipeline.filename
        if (filename !== undefined && filename !== null && filename.length > 0) {
            this._append_field(grid, "Filename", filename)
        }
        this._append_field(grid, "Cached", format_timestamp(pipeline.cached_at))

        section.appendChild(grid)
        return section
    }

    /**
     * Append one labelled field to a definition-list grid.
     *
     * @param grid The ``<dl>`` to append into.
     * @param label The field's display label.
     * @param value The field's display value.
     */
    private _append_field(grid: HTMLElement, label: string, value: string): void {
        const field = document.createElement("div")
        field.classList.add("pyc-pipeline-detail__field")
        const term = document.createElement("dt")
        term.textContent = label
        const def = document.createElement("dd")
        def.textContent = value
        field.appendChild(term)
        field.appendChild(def)
        grid.appendChild(field)
        return
    }

    /**
     * Build the DAG-visualization section -- the inline-SVG node-
     * and-edge layout, or the adjacency-list fallback when the
     * stages do not form a clean DAG.
     *
     * @param stages The pipeline's stages.
     *
     * @returns A populated DAG section element.
     */
    private _build_dag_section(stages: PipelineStage[]): HTMLElement {
        const section = document.createElement("section")
        section.classList.add("pyc-pipeline-detail__dag")
        section.setAttribute("data-role", "dag-section")
        section.setAttribute("role", "region")
        section.setAttribute("aria-label", "Pipeline DAG")

        const heading = document.createElement("h2")
        heading.classList.add("pyc-pipeline-detail__section-heading")
        heading.textContent = "Stage DAG"
        section.appendChild(heading)

        if (stages.length === 0) {
            const empty = document.createElement("p")
            empty.classList.add("pyc-pipeline-detail__status")
            empty.setAttribute("data-role", "dag-empty")
            empty.textContent = "This pipeline has no stages."
            section.appendChild(empty)
            this._is_dag = true
            return section
        }

        const layout = compute_dag_layout(stages)
        this._is_dag = layout.isDag

        if (layout.isDag === false) {
            const notice = document.createElement("p")
            notice.classList.add(
                "pyc-pipeline-detail__status",
                "pyc-pipeline-detail__status--error",
            )
            notice.setAttribute("data-role", "dag-cycle-notice")
            notice.textContent =
                "Stages do not form a clean DAG — showing dependency list."
            section.appendChild(notice)
            section.appendChild(this._build_adjacency_list(stages))
            return section
        }

        section.appendChild(this._build_dag_svg(layout))
        return section
    }

    /**
     * Build the inline-SVG node-and-edge rendering of the DAG.
     *
     * @param layout The pre-computed pixel layout.
     *
     * @returns An ``<svg>`` element wrapped in a scroll container.
     */
    private _build_dag_svg(layout: DagLayout): HTMLElement {
        const wrapper = document.createElement("div")
        wrapper.classList.add("pyc-pipeline-detail__dag-canvas")
        wrapper.setAttribute("data-role", "dag-canvas")

        const svg = document.createElementNS(SVG_NS, "svg")
        svg.setAttribute(
            "viewBox",
            "0 0 " + String(layout.width) + " " + String(layout.height),
        )
        svg.setAttribute("width", String(layout.width))
        svg.setAttribute("height", String(layout.height))
        svg.classList.add("pyc-pipeline-detail__dag-svg")
        svg.setAttribute("role", "img")
        svg.setAttribute("aria-label", "Pipeline stage DAG")

        for (const edge of layout.edges) {
            const line = document.createElementNS(SVG_NS, "line")
            line.setAttribute("x1", String(edge.x1))
            line.setAttribute("y1", String(edge.y1))
            line.setAttribute("x2", String(edge.x2))
            line.setAttribute("y2", String(edge.y2))
            line.setAttribute("class", "pyc-pipeline-detail__dag-edge")
            line.setAttribute("data-role", "dag-edge")
            svg.appendChild(line)
        }

        for (const node of layout.nodes) {
            const group = document.createElementNS(SVG_NS, "g")
            group.setAttribute("data-role", "dag-node")
            group.setAttribute("data-stage-id", node.stageId)

            const rect = document.createElementNS(SVG_NS, "rect")
            rect.setAttribute("x", String(node.x))
            rect.setAttribute("y", String(node.y))
            rect.setAttribute("width", String(node.width))
            rect.setAttribute("height", String(node.height))
            rect.setAttribute("rx", "6")
            rect.setAttribute("class", "pyc-pipeline-detail__dag-box")
            group.appendChild(rect)

            const text = document.createElementNS(SVG_NS, "text")
            text.setAttribute("x", String(node.x + node.width / 2))
            text.setAttribute("y", String(node.y + node.height / 2))
            text.setAttribute("text-anchor", "middle")
            text.setAttribute("dominant-baseline", "middle")
            text.setAttribute("class", "pyc-pipeline-detail__dag-label")
            text.textContent = node.stageId
            group.appendChild(text)

            svg.appendChild(group)
        }

        wrapper.appendChild(svg)
        return wrapper
    }

    /**
     * Build the adjacency-list fallback rendering -- one row per
     * stage naming the stages it depends on.
     *
     * @param stages The pipeline's stages.
     *
     * @returns An adjacency-list ``<ul>`` element.
     */
    private _build_adjacency_list(stages: PipelineStage[]): HTMLElement {
        const list = document.createElement("ul")
        list.classList.add("pyc-pipeline-detail__adjacency")
        list.setAttribute("data-role", "dag-adjacency")
        for (const stage of stages) {
            const item = document.createElement("li")
            item.classList.add("pyc-pipeline-detail__adjacency-row")
            const name = document.createElement("strong")
            name.textContent = stage.stage_id
            item.appendChild(name)
            const needs = stage.needs
            const detail = document.createElement("span")
            if (needs !== undefined && needs !== null && needs.length > 0) {
                detail.textContent = " → depends on: " + needs.join(", ")
            } else {
                detail.textContent = " → no dependencies"
            }
            item.appendChild(detail)
            list.appendChild(item)
        }
        return list
    }

    /**
     * Build the stage-list section -- one card per stage naming
     * its when-clause, dependency list, and step ids.
     *
     * @param stages The pipeline's stages.
     *
     * @returns A populated stage-list section element.
     */
    private _build_stage_list(stages: PipelineStage[]): HTMLElement {
        const section = document.createElement("section")
        section.classList.add("pyc-pipeline-detail__stages")
        section.setAttribute("data-role", "stage-section")
        section.setAttribute("role", "region")
        section.setAttribute("aria-label", "Pipeline stages")

        const heading = document.createElement("h2")
        heading.classList.add("pyc-pipeline-detail__section-heading")
        heading.textContent = "Stages"
        section.appendChild(heading)

        if (stages.length === 0) {
            const empty = document.createElement("p")
            empty.classList.add("pyc-pipeline-detail__status")
            empty.setAttribute("data-role", "stages-empty")
            empty.textContent = "No stages defined."
            section.appendChild(empty)
            return section
        }

        const list = document.createElement("ul")
        list.classList.add("pyc-pipeline-detail__stage-list")
        for (const stage of stages) {
            const item = document.createElement("li")
            item.classList.add("pyc-pipeline-detail__stage")
            item.setAttribute("data-role", "stage-card")

            const stage_name = document.createElement("strong")
            stage_name.classList.add("pyc-pipeline-detail__stage-name")
            stage_name.textContent = stage.stage_id
            item.appendChild(stage_name)

            const when = stage.when_clause
            if (when !== undefined && when !== null && when.length > 0) {
                const chip = document.createElement("span")
                chip.classList.add("pyc-pipeline-detail__stage-when")
                chip.textContent = "when: " + when
                item.appendChild(chip)
            }

            const needs = stage.needs
            const needs_text = document.createElement("span")
            needs_text.classList.add("pyc-pipeline-detail__stage-needs")
            if (needs !== undefined && needs !== null && needs.length > 0) {
                needs_text.textContent = "needs: " + needs.join(", ")
            } else {
                needs_text.textContent = "needs: none"
            }
            item.appendChild(needs_text)

            const steps = stage.steps
            const steps_text = document.createElement("span")
            steps_text.classList.add("pyc-pipeline-detail__stage-steps")
            if (Array.isArray(steps) === true && steps.length > 0) {
                const step_ids: string[] = []
                for (const step of steps) {
                    step_ids.push(step.step_id)
                }
                steps_text.textContent = "steps: " + step_ids.join(", ")
            } else {
                steps_text.textContent = "steps: none"
            }
            item.appendChild(steps_text)

            list.appendChild(item)
        }
        section.appendChild(list)
        return section
    }
}
