# 6-environment-registry — Environments are compositions (proposal, awaiting approval)

Status: **proposed 2026-10-17, nothing built.** Written after the observation that an environment's `kind` offers
only `k8s-cluster`, while a real lab environment is a mixture: hardware, networks, dynamically created virtual
resources, virtualization servers, power controllers, serial port concentrators.

## 1. Problem

An `Environment` carries one `kind_name` (`k8s-cluster` is the only kind shipped) and one `attrs` object validated
by that kind. The original spec (`requirements.md`, Requirement 3) reads "an environment is a `dev`, `staging` or
`prod` of *one* kind, and more kinds arrive as extensions". That cannot describe a lab, where the thing you declare,
reserve, provision, freeze and guard is a **set of different things that depend on each other**: a board is powered by
outlet 3 of a PDU, its console is port 12 of a serial concentrator, it sits on a VLAN, and the virtual machines a run
creates are hosted on a hypervisor that is itself part of the environment. Adding more single kinds (a `vm-pool`, a
`lab-rack`) would only move the same limit around: every lab is a different mix.

The same single-kind shape exists in two neighbours: the registry resource plane has one resource kind (`device`),
the legacy resource pages have a five-value type enum. This proposal does not change either (section 7).

## 2. Assumptions to confirm (these shape everything below)

1. **An environment stays the unit you declare, freeze, provision, drift-check and guard.** It stays one row, with
   its state, freeze, history, last-applied pointer and guards. What changes is that it **has members**; it no longer
   *is* one kind.
2. **A member has a kind, a name (unique inside the environment) and its attributes.** Kinds are the existing
   `environment_kind` extension point (same protocol: `kind_name`, `attribute_fields`, `validate_attrs`), so a site can
   still add its own. `k8s-cluster` stays, as a member kind.
3. **Shipped member kinds**: `hardware`, `network`, `virtualization-server`, `virtual-resources` (dynamic),
   `power-controller`, `serial-concentrator`, `k8s-cluster`, and `generic` (a name, a note and free attributes, for
   what nobody has modelled yet).
4. **Members link to each other with a small set of typed links** (`power`, `console`, `host`, `network`), checked
   when saved: the target must exist in the same environment and be of the right kind.
5. **Hardware members point at a resource in the registry resource plane** (the model jobs use, per
   `model-convergence.md` section 3), so reservation, leases and health come from there and a member does not
   re-invent them. A form can register the resource for you when you add the member.
6. **Dynamic members describe what a run creates, and the instances a run created are recorded separately**, read
   from the run's outputs, never typed by hand.
7. **Credentials are vault references, never values** (the same `{"$secret": "<ref>"}` convention packets now use).
8. **Existing environments migrate by becoming an environment with one `k8s-cluster` member** carrying the old
   attributes. The old create call (`name`, `kind_name`, `attrs`) keeps working as shorthand for that.
9. **Modelling comes first; acting comes later.** Power-cycling a device or opening its console are *actions* that need
   their own design (permissions, audit, safety); this proposal records the relationships they will use.

## 3. Model

`Environment` keeps its columns. `kind_name` stays on the row as a derived summary (the distinct kinds of its members, sorted and joined
with `+`, cut to the column's 64 characters, empty when there are none) so the existing `kind` filter and list column keep working. The unique
constraint `(project_id, kind_name, name)` becomes `(project_id, name)`.

`EnvironmentMember` (new, `orch_environment_member`):

| column | meaning |
|---|---|
| `member_id` | UUID |
| `environment_id` | owner; the member goes with its environment |
| `kind_name` | the member kind |
| `name` | 1-128 chars, unique inside the environment |
| `description` | text |
| `resource_id` | optional UUID of a registry resource (`hardware`; allowed on other kinds that are also devices) |
| `attrs` | JSON, validated by the kind |
| `links` | JSON list of `{"type", "to", "port"?}`; `to` is another member's name |
| `created_at`, `updated_at` | |

`EnvironmentInstance` (new, section 5): what a dynamic member's runs actually created.

### Shipped kinds

| kind | what it is | main attributes | links |
|---|---|---|---|
| `hardware` | a physical device under test or in use | `model`, `serial_number`, `role` (free text), `location` (rack/slot), `management_address` | `power` -> power-controller, `console` -> serial-concentrator, `network` -> network (with `address`) |
| `network` | a network the members share | `cidr`, `vlan`, `gateway`, `dns` (list), `purpose` | (is a target) |
| `virtualization-server` | a hypervisor or cloud endpoint that hosts virtual resources | `platform` (`vmware`, `kvm`, `proxmox`, `other`), `endpoint` (URL), `credential` (vault reference), `capacity` hints | `network` |
| `virtual-resources` | virtual machines or containers a run creates | `template`/`image`, `count`, `cpu`, `memory_mb`, `disk_gb`, `name_pattern` | `host` -> virtualization-server, `network` |
| `power-controller` | a PDU or smart power switch | `model`, `endpoint`, `credential` (vault reference), `outlets` (count) | (is a target; the link carries the outlet) |
| `serial-concentrator` | a console server | `model`, `endpoint`, `credential`, `ports` (count) | (is a target; the link carries the port) |
| `k8s-cluster` | unchanged | unchanged | `network` |
| `generic` | anything else | free attributes | any |

### Links

A link is `{"type": "power", "to": "pdu-1", "port": "3"}` on the *dependent* member (the board names the outlet that
powers it), because that is how people describe a lab ("this board is on PDU 1, outlet 3"). Rules, enforced on save:
`to` names an existing member of the same environment; the target's kind is allowed for the type (`power` ->
`power-controller`, `console` -> `serial-concentrator`, `host` -> `virtualization-server`, `network` -> `network`);
`port` is required for `power` and `console` and must be within the target's `outlets` / `ports` when it gives a
count; two members may not claim the same `(target, port)`. Deleting a member that others link to is refused, naming
them (never a dangling link).

## 4. How it fits the rest

- **Runs.** A provisioning run still targets an environment. Its `driver_inputs` may name a member so one environment
  can have several apply targets (for example the virtual resources, not the hardware); a run with no member
  applies to the environment as a whole, as today.
- **Drift.** Drift detection keeps working per environment. It supports a *member kind* (today: whatever the drift
  driver declares for `k8s-cluster`): an environment is checked for each supported member, and members of kinds with
  no drift driver are reported as "not checked", never as clean.
- **Guards.** A rule receives `environment_kind` (the derived summary, as today), `environment_attrs` (for an
  environment with exactly one member, that member's attributes, so every existing rule behaves as before; otherwise
  empty) and a new `environment_members` list (`kind`, `name`, `attrs`), so a rule can say "no apply while a
  `power-controller` member is unreachable".
- **Resource plane.** A `hardware` member with a `resource_id` shows that resource's state and health on the
  environment page. A job that needs the environment's hardware reserves it through the pool/reservation logic of
  `model-convergence.md` step 4, not through anything new here.
- **Secrets.** `credential` attributes hold a vault reference. Saving checks it as the signed-in user, like a packet
  reference; the value is never stored or returned.
- **Events and audit.** Member changes write the environment's history ledger (`member_added`, `member_changed`,
  `member_removed`) and publish the existing environment events.

## 5. Dynamic members and their instances

A `virtual-resources` member is a *recipe*. A run that creates the machines reports them in its outputs (a list of
`{name, state, address, host}`); the service records each as an `EnvironmentInstance` (`member_id`, `name`, `state`,
`address`, `host_member` (name), `run_id`, `observed_at`) and replaces the member's set on every apply and on destroy.
The environment page lists them under the member ("3 of 4 running, last observed by run 1f3a…"). Instances are read
only: they are facts a run observed, not configuration.

## 6. REST and UI

REST (all under `/api/v1/projects/{project_id}/environments/{environment_id}`):

- `GET /members`, `POST /members`, `GET|PATCH|DELETE /members/{member_id}`; `GET /instances`.
- `POST /environments` takes `{name, description?, members?: [...]}`; `{name, kind_name, attrs}` still works and
  creates the one-member environment of assumption 8.
- `GET /api/v1/environment-kinds` lists kinds with their attribute fields and the link types each accepts (the form
  is built from this).

UI (Orchestration -> Environments):

- **Create**: a name and a description; no kind. The page then offers **Add member** (choose the kind first, then
  the form for that kind), so a new environment is built up rather than declared in one go.
- **Detail**: members grouped by kind with their links as readable lines ("powered by pdu-1, outlet 3; console:
  concentrator-a, port 12"), the registry resource's state for hardware, the instances of virtual members, and a
  one-line summary at the top ("2 boards, 1 network, 1 PDU, 1 console server, 1 hypervisor, 4 virtual machines").
- **List**: the Kind column shows the summary; the kind filter matches any member.

## 7. Not part of this proposal

- **Actions** on members (power cycle, open a console, reboot): they need their own design for permissions, audit and
  safety. This proposal stores the links they will follow.
- **Changing the resource kinds** of the registry plane or the legacy resource types. A `hardware` member refers to a
  registry resource; adding richer resource kinds (`power-controller`, `serial-concentrator` as reservable resources)
  is `model-convergence.md` step 5, and can follow without changing this model.
- **A topology diagram.** The links make one possible; the lists come first.
- **Cross-environment sharing** (one PDU serving two environments). Members belong to one environment for now.

## 8. Migration

An alembic migration adds the two tables, then for each existing `orch_environment` row inserts one `k8s-cluster`
member (name = the environment's name, attributes = the old `attrs`) and leaves `kind_name` as the summary, then
replaces the unique constraint. It is idempotent (an environment that already has members is skipped) and the
downgrade restores the constraint and deletes the member rows. Staging holds no environments (checked 2026-10-17:
`orch_environment` 0 rows), so the migration is exercised there on an empty table; the migration test builds
environments by hand.

## 9. Milestones (each shippable by itself)

1. **Model and API.** Tables, migration, member kinds (`hardware`, `network`, `virtualization-server`,
   `power-controller`, `serial-concentrator`, `virtual-resources`, `generic`, `k8s-cluster`), links and their rules,
   REST, the compatibility shorthand, history events. Tests: validation of every kind and link rule, the migration,
   REST.
2. **UI.** Create without a kind, Add member, the detail page, the list summary.
3. **Hardware and the resource plane.** `resource_id` on hardware members, the register-it-for-me shortcut, state
   and health on the page.
4. **Dynamic instances.** Run outputs recorded as instances, shown on the page.
5. **Guards and drift.** `environment_members` in the guard input; per-member-kind drift with "not checked".

## 10. Questions

- Is the shipped kind list right? In particular: should `hardware` split into more specific kinds (a `board`, a
  `server`, a `switch`), or is `role` plus attributes enough?
- Hardware members point at a registry resource (assumption 5). Should a hardware member be *allowed* to exist with no
  resource (described, not yet registered), or must it always have one?
- Should a member be able to belong to **more than one** environment (a shared PDU or hypervisor), or is one
  environment per member right for now?
