# AutoBOM — Coordination Note 3 (Create Flows + Baseline Cleanup)

## Purpose

This note delivers the Create Program and Create Project flows, cleans up the reachable and latent dead controls surfaced by the post-Session-2 diagnostic sweep, deletes the Task Center residue (retired concept from v4 that never got fully removed), and applies a set of baseline spec changes locked during this coordination cycle — sigil removal across all identifiers, the continuous-identifier model (Program → Project → BOM line → CPN as one growing string), Class field retirement from Project, and Standalone Project concept retirement.

**Prerequisites:** Sessions 1 (Housekeeping) and 2 (Forward Layer) must be complete. This note assumes:

- Purchasing role removed everywhere; embedded Purchasing surface in place
- CPN in sigil format currently rendered — this note removes the sigils
- Sidebars restructured per Chapter B
- Push-Back structured with reason/urgency/flaggedLines/addedComponentRequest; Designer-proposes/Production-applies model wired
- App-wide search bar PartsBox-backed with storage-location detail
- Production BOM screen inline-edit with characteristic-match check working
- Program object exists with `notifyOnEquivalentSwap` toggle
- CLAUDE.md is the current v4 operating context

If any of Session 1 or 2's rejection criteria didn't close, stop this note and return to earlier work.

**Scope:** Twenty-two actions across five functional groups plus coordination. Two new capabilities (Create Program, Create Project). One retired-concept sweep (Task Center residue). One reachable-dead-control sweep. One baseline spec change ripple (sigil removal + Class retirement + Standalone retirement + continuous-identifier model).

## Elicitation pattern

Same as previous sessions. One question at a time. Wait for answer. Then execute.

All architectural elicitations for this note are pre-closed by Aaron and Claude Architect during the coordination cycle. The elicitation points below are UI decisions that surfaced during writeup — Claude Design and Aaron close these before executing the affected actions.

---

## Group 1 — Reachable dead-control cleanup

The post-Session-2 diagnostic sweep surfaced five reachable-now dead controls. Actions 1–4 land now; the New Project and New Program buttons get their real wiring via Groups 3 and 4.

**1. Delete both stale `d.search` route references on `screen_collections.jsx`.**

- `screen_collections.jsx:48` — `go({ screen: 'd.search' })` on the "Search a part" button in the header
- `screen_collections.jsx:78` — `go({ screen: 'd.search' })` on the empty-state "Search a part" button

`d.search` was retired in Session 1 (standalone search page → contextual overlay). Both buttons should route to the app-wide search overlay (⌘K / Ctrl+K palette pattern established in Master Design Contract Section 5). Simplest implementation: remove the `go(...)` handler and add a keyboard shortcut hint next to the button label (e.g., "Search a part ⌘K"), OR remove the buttons entirely if they're redundant given the top-rail search input.

**Elicit:** remove the buttons entirely, OR keep them as visual affordances that trigger the same overlay the top-rail bar triggers?

**Recommendation:** keep them as affordances that trigger the same overlay. The empty-state button in particular is a helpful CTA for new Designers unfamiliar with the keyboard shortcut.

**2. Hide the Add supplier button on `screen_admin.jsx:307`.**

Remove the button from render output entirely. Not disabled, not greyed out — gone. Create Supplier flow is deferred to a future coordination note. When it lands, the button comes back with a real handler and modal. In the meantime, Configuration → Suppliers tab shows the existing suppliers (Mouser, DigiKey) with their config (API keys, base URL, enabled toggle), read/edit only.

**3. Wire the New Project button on `screen_shared.jsx:15` to the Create Project modal.**

Full implementation of the Create Project flow lives in Group 4. This action just wires the existing button's `onClick` to open the modal that Group 4 builds.

**4. Add a New Program button to the ProgramsScreen and wire it to the Create Program modal.**

ProgramsScreen currently has no create affordance. This action adds the button (top-right of the Programs list, matching the New Project button placement pattern). Full implementation of the Create Program flow lives in Group 3. This action just adds the button + wires the `onClick`.

---

## Group 2 — Task Center residue deletion

Task Center is on the retired-concepts list in CLAUDE.md ("Task Center in any form"). Session 1 was supposed to catch this and missed it. The full subsystem exists in `tasks.jsx` as orphan code — no ROUTE_TABLE entry, no dispatch in `app.jsx`, and the only entry point is the dev-gated `v.tasks` sidebar item.

Delete the subsystem. Repoint the four dead notification-emitting actions to route to related-object routes instead of `*.taskDetail`.

**5. Delete `tasks.jsx` entirely.**

Remove the file. Includes: `TaskCenter` component, `TaskDetail` component, `deriveTasks` helper, `unresolvedTaskCount` helper, `findTaskForNotif` helper, and everything else in the file.

**6. Delete the `<script>` reference to `tasks.jsx` in `AutoBOM Platform.html:49`.**

The file is loaded via `<script>` at that line. Once `tasks.jsx` is deleted, the script tag needs to go too. Otherwise you get a 404 on page load.

**7. Remove the `v.tasks` sidebar entry from `permissions.jsx:148`.**

Development-role sidebar has a `v.tasks` item pointing at the (now non-existent) Task Center route. Delete the entry from `NAV_BY_ROLE.development`. Development role stays dev-gated (`DEV_ROLE_ENABLED = false`); this is just cleanup of the dead nav item within it.

**8. Delete the orphaned `b.requestReview` crumb branch from `nav.jsx:114`.**

Session 1 neutered this to a no-op guard but didn't delete it. Delete the whole branch — no route in ROUTE_TABLE points at `b.requestReview` anymore, and the crumb structure doesn't need to defend against a route that doesn't exist.

**9. Delete the "New {kind}" dead button from `screen_development.jsx:193`.**

Latent, dev-gated, no handler. Remove the button from render output. When Development role reactivates in a future scope, its Create flows will be designed properly then.

**10. Repoint the four task-lifecycle notification routes in `store.jsx:593–655`.**

Actions affected: `resolveTask`, `acceptTask`, `reopenTask`, `blockTask`.

Currently each emits two notifications (keyed to `task.sourceRole` and `task.targetRole`) with `screen: '${ROLE_PREFIX[role]}.taskDetail'`. Those `*.taskDetail` routes don't exist in ROUTE_TABLE — dead links.

Repoint each notification's `screen` to the route for the related object, using `task.relatedKind` and `task.relatedId` that already exist on the task payload. Concretely:

- `task.relatedKind === 'bom'` → route to `p.bomDetail` (or wherever BOM detail lives — Production BOM screen)
- `task.relatedKind === 'collection'` → route to `d.collectionDetail`
- `task.relatedKind === 'request'` → route to `purchasingEmbed` with `?req=<id>` (matches Session 1's Request search routing pattern)
- `task.relatedKind === 'pushback'` → route to the parent BOM's screen with `?pushback=<id>` (dashboard-inline expansion happens on the Designer/Production dashboard, not a detail route)

**Elicit:** for the `pushback` case, is dashboard-inline the right target? Or route to BOM detail?

**Recommendation:** dashboard-inline. Push-Back resolution surface is the Dashboard Needs Attention card, per Master Design Contract Section 6. Route to `d.dashboard` or `p.dashboard` (depending on target role) with `?pushback=<id>` and let the dashboard scroll to the matching card.

Note: with tasks.jsx deleted, these four actions might themselves have no callers left — the sweep noted `resolveTask/acceptTask/reopenTask/blockTask` were only invoked from `TaskDetail`. If that's true, the actions themselves can also be deleted after the repoint. Verify caller-count before deleting the actions themselves; keep the actions and repointed routes if they emit meaningful notifications elsewhere.

---

## Group 3 — Create Program flow

**Elicitation locks recap:**

- 5-field modal: identifier (user-provided short code) · name · owner · customer · description · tags
- Identifier validation: trim whitespace + reject empty + no duplicates on Program name (Rule 1)
- Save behavior: audit event + navigate to Program detail. No PartsBox side effect. No notifications.

**11. Build the Create Program modal component.**

Modal opens from the New Program button (Action 4).

Fields:

- **Identifier** (required) — free-form text input. Live-validated: trim whitespace, reject empty, reject if any existing Program has the same name (uniqueness check). Short display hint: "e.g., TVCA, GDR, MC" — encourages short values for the continuous-identifier chain.
- **Name** (required, no duplicates) — longer descriptive name. Same trim + reject-empty + uniqueness rules.
- **Owner** (defaults to current Designer, dropdown of Designers to reassign)
- **Customer** (optional, free-text — external customer name or blank for internal R&D)
- **Description** (optional, free-text)
- **Tags** (optional, chip input)

Buttons:
- **Cancel** — dismiss modal without state change
- **Create** — validate all fields → run backend save (Action 12) → close modal → navigate to new Program's detail

Live validation surfaces inline error text under any invalid field. Create button disabled until all validation passes.

**12. Add the `createProgram` store action.**

Action signature: `createProgram({ identifier, name, owner, customer, description, tags })`

Behavior:
- Generate a new Program record with the provided fields plus:
  - `id` (auto-generated, backend concern — Claude Code figures out format)
  - `status: 'Active'` (default)
  - `startedDate: today` (auto-set)
  - `targetDate: null` (deferred to Edit Program)
  - `notifyOnEquivalentSwap: true` (default; matches Session 2 Action 20's default state)
- Persist the Program (in prototype: append to `state.programs` seed array; in backend future: POST to `/api/programs`)
- Write audit event: `Program created` with actor + timestamp + before/after snapshot
- No PartsBox side effect (Programs are pure AutoBOM concept — nothing external needs to know)
- No notifications fire (Program creation is quiet)
- Return the new Program's `id`

**13. Wire the modal's Create button to `createProgram`, then navigate to Program detail.**

Modal state persists error surface if the backend rejects (e.g., name collision race). On success, modal dismisses and app routes to the new Program's detail page.

---

## Group 4 — Create Project flow

**Elicitation locks recap:**

- 4-field modal: identifier · name · lead · program (required dropdown) · description (5 visible fields total, no Class field)
- Identifier validation: trim whitespace + reject empty
- Name: required, no duplicates on Project name (Rule 2)
- program_id required (no Standalone option in the dropdown; Standalone concept retired entirely)
- Empty Program list state: modal blocks with "Create a Program first" prompt + link to Create Program modal
- PartsBox timing: opt-in checkbox at Project save, default checked (immediate PartsBox create)
- Save behavior: audit event + create PartsBox project + storage location (if checkbox checked) + navigate to Project detail

**14. Build the Create Project modal component.**

Modal opens from the New Project button (Action 3).

Empty-programs-list guard: if no Programs exist in `state.programs`, the modal renders a full-height blocker state — a message ("You need to create a Program before creating a Project.") and a single button "Create Program" that opens the Create Program modal (Group 3). No other fields visible.

Fields (when at least one Program exists):

- **Identifier** (required) — free-form text input. Live-validated: trim whitespace, reject empty. Note: uniqueness scope is within-Program (a Project identifier like "REV2" is fine if it's unique among that Program's Projects — different Programs can have Projects with the same identifier because the continuous-identifier chain includes the parent Program).
- **Name** (required, no duplicates on Project name globally) — descriptive Project name. Trim + reject-empty + global uniqueness.
- **Lead** (defaults to current Production user, dropdown of Production users to reassign)
- **Program** (required dropdown, one option per existing Program — no Standalone option, no null option)
- **Description** (optional, free-text)

At the bottom, before Cancel/Create:

- ☐ **Create PartsBox project + storage location now** — checkbox, default checked. User can uncheck for placeholder Projects that shouldn't have a PartsBox side effect at creation time.

Buttons:
- **Cancel** — dismiss modal without state change
- **Create** — validate all fields → run backend save (Action 15) → close modal → navigate to new Project's detail

**15. Add the `createProject` store action.**

Action signature: `createProject({ identifier, name, lead, program_id, description, createPartsBoxNow })`

Behavior:
- Generate a new Project record with the provided fields plus:
  - `id` (auto-generated, backend concern)
  - `program_id` (required — the FK to the selected Program)
  - `status: 'Active'` (default)
- Persist the Project
- **If `createPartsBoxNow === true`:**
  - Call PartsBox `project/create` idempotently (matches POC `find_project_by_name` before create pattern)
  - Call PartsBox `storage/create` idempotently (same pattern)
  - Store both PartsBox IDs on the Project record for future reference
  - **If either fails:** log error for Admin, still create the Project record internally (don't block user), but flag the Project as having a "PartsBox creation pending" state that surfaces on the Project detail page with a retry action
- **If `createPartsBoxNow === false`:**
  - Project record exists in AutoBOM only
  - Project detail page shows a "Create PartsBox project" affordance the user can trigger later
- Write audit event: `Project created` with actor + timestamp + before/after + `createPartsBoxNow` flag
- No notifications fire (Project creation is quiet)
- Return the new Project's `id`

**16. Wire the modal's Create button to `createProject`, then navigate to Project detail.**

Same pattern as Action 13.

**17. Add the "Create PartsBox project" affordance to Project detail.**

Visible on the Project detail page only when `createPartsBoxNow` was false at creation time AND the PartsBox project + storage location don't yet exist. Hides itself once they do exist. Behavior on click: idempotent PartsBox `project/create` + `storage/create`, matching Action 15's PartsBox path.

Location on the Project detail page: near the header, as a callout row or button. Visual emphasis: a subtle callout ("This Project isn't tracked in PartsBox yet. [Create PartsBox project]") — not a modal, not intrusive, but visible.

---

## Group 5 — Baseline spec changes (sigil removal + Class retirement + Standalone retirement + continuous-identifier model)

These are UI ripples of decisions locked during the coordination cycle. They're structural changes to how identifiers and objects render across the platform, not new capabilities.

**18. Remove all CPN sigil prefixes from displays.**

Currently CPN renders with a leading `#` (project-bound) or `~` (wall-bound). Remove the sigil character across every display surface:

- Bucket entry rows (embedded Purchasing view)
- Archive rows
- Receiving scan confirmation screen
- BOM line displays showing generated CPN
- Any notification body text that includes CPN
- Search result cards showing CPN

The sigil character is NOT stored in the CPN string itself under this change — it's removed at the data level too, not just at display. Any existing CPN in seed data currently rendered with a sigil needs to have the sigil stripped from the stored string. Verify with a grep for `# +${cpn}` or `~ +${cpn}` patterns and replace.

**19. Add a scope pill next to every CPN display.**

Since the visual sigil distinction is gone, render a compact chip next to each CPN indicating scope:

- **Project** chip (violet or neutral) — for project-bound CPNs
- **Wall** chip (amber or contrasting) — for wall-bound CPNs

Chip appears immediately adjacent to the CPN string. Size: small, single-line, low visual weight but readable at a glance. Design consistent with existing chip patterns in the prototype (see the existing category chips on Collection cards, Program tags, etc.).

Scope data source: the CPN issuance record's `scope` field (`'project'` or `'wall'`). Field already exists in the data model — this is just adding the rendering.

**20. Retire the Class field from the Project object entirely.**

Class was a Production/R&D radio on the Project schema. Under the coordination cycle lock, Program context provides that distinction — a Project's parent Program tells you whether it's a Production initiative or an R&D one. Class field is redundant.

Delete:
- Class radio from any Create/Edit Project modal
- Class chip from Project detail header
- Class filter from Projects list
- `class` field from `state.projects` seed entries in `data.jsx`
- Any component code reading `project.class`

**21. Retire the Standalone Project concept entirely from the codebase.**

Under the coordination cycle lock, every Project must belong to a Program (`program_id` non-nullable). Delete any code path that handles the standalone case:

- Push-Back routing decision engine: the "IF standalone → unassigned pool direct" branch simplifies — every Push-Back routes to Program owner Designer first, escalates to unassigned pool after the configurable window
- Programs listing: no "Standalone Projects" section anywhere
- Project detail: no "Standalone" badge or state
- Any seed data with `program_id: null` needs a Program parent assigned before this note lands (BLDC Motor Controller and Wall Replenishment in current seed data are candidates — assign them to appropriate Programs, either existing or new)

If seed data needs new parent Programs to house currently-standalone Projects, create those Programs as part of this action (e.g., an "R&D" Program housing BLDC Motor Controller and a "Wall Restock" Program housing Wall Replenishment). Two new Programs plus the reassignment.

**22. Apply the continuous-identifier model across the platform.**

The continuous-identifier model: Program's `identifier` → Project's `identifier` extends the parent Program's identifier → BOM line identifier extends the parent Project's identifier → CPN IS the BOM line identifier.

Concretely:

- Program has `identifier` field (user-provided at Create Program, e.g., "TVCA")
- Project has `identifier` field (user-provided at Create Project, e.g., "R2"). Full Project reference is derived: `${program.identifier}-${project.identifier}` = "TVCA-R2"
- BOM lines have their own line-level identifier (line number or zero-padded index). Full BOM line reference derived: `${project.identifier chain}-${line.identifier}` = "TVCA-R2-042"
- CPN generation: when a Request line is created, the CPN string IS the full derived chain. No separate CPN generation logic — the identifier already exists. CPN string: "TVCA-R2-042"

Display convention:
- Program list rows show the identifier prominently (in monospace) with the name secondary
- Project list rows show the derived `${program.identifier}-${project.identifier}` string with name secondary
- BOM lines show the derived chain
- CPNs render the full chain in monospace with the scope pill next to it

The chain's max length constraint is 20 chars (CPN 20-char cap for supplier customer reference fields). This is a coding concern Claude Code enforces at CPN generation time. UI doesn't need to enforce this — user could theoretically create identifiers that push past 20 chars, but the platform then flags at CPN generation, not at Program/Project creation. That's a future backend enforcement, not a Group 5 action.

---

## Group Zero — Coordination

**Elicit upfront if anything is ambiguous.**

Explicit elicitation points already flagged:

- Action 1: buttons remove-entirely vs affordance-to-overlay
- Action 10 pushback case: dashboard-inline vs BOM detail routing

Any other ambiguity — same one-question-at-a-time pattern.

---

## Rejection criteria for the whole session

If any of these are true at the end of the session, the note did not close:

- `tasks.jsx` still exists
- `<script>` reference to `tasks.jsx` still in `AutoBOM Platform.html`
- `v.tasks` sidebar item still in `permissions.jsx:148`
- `b.requestReview` orphan crumb still in `nav.jsx:114`
- "New {kind}" dead button still in `screen_development.jsx:193`
- `*.taskDetail` route strings still emitted anywhere in `store.jsx`
- `resolveTask` / `acceptTask` / `reopenTask` / `blockTask` still emit dead routes (must repoint using `task.relatedKind` + `task.relatedId`)
- Both `d.search` refs on `screen_collections.jsx:48` and `:78` still present
- Add supplier button on `screen_admin.jsx:307` still rendered
- New Project button on `screen_shared.jsx:15` still lacks an `onClick`
- New Program button doesn't exist on ProgramsScreen
- No `createProgram` action in `store.jsx`
- No `createProject` action in `store.jsx`
- Create Program modal missing any of: identifier, name, owner, customer, description, tags fields
- Create Program modal identifier or name field lacks live uniqueness validation
- Create Project modal missing any of: identifier, name, lead, program (required), description fields
- Create Project modal shows "Standalone" as a Program dropdown option
- Create Project modal missing the "Create PartsBox project + storage location now" checkbox (default checked)
- Create Project modal doesn't block on empty Program list with "Create a Program first" prompt
- Create Project doesn't call PartsBox `project/create` + `storage/create` when checkbox is checked
- Project detail lacks a "Create PartsBox project" affordance when PartsBox wasn't created at Project creation
- CPN sigil (`#` or `~`) still visible in any CPN display
- CPN scope pill ("Project" / "Wall") missing from any CPN display surface
- Class field still exists on Project schema, Create/Edit modals, detail header, or Projects list filter
- Standalone Project code paths still exist (routing branches, badges, `program_id: null` seed entries)
- Programs/Projects don't have `identifier` field on their schemas
- BLDC Motor Controller and Wall Replenishment (previously Standalone in seed data) don't have parent Programs assigned

---

## What this note does NOT include

To keep the scope tight:

- **Create Supplier flow.** Deferred to a future coordination note. Add supplier button is hidden until then.
- **Edit Program flow, Edit Project flow.** Existing edit affordances stay as they are; this note doesn't touch them beyond removing the Class field from Edit Project.
- **CPN generation logic backend.** The 20-char enforcement, format string configuration, exact separator conventions — all backend implementation details. Claude Code handles these when backend integration lands. This note just makes sure the UI renders whatever CPN string the platform provides, without sigils.
- **Development role reactivation.** DEV_ROLE_ENABLED stays false. Group 2 cleans up Development-role residue but doesn't reactivate anything.
- **Model B re-upload ceremony UI.** Still deferred to Production BOM screen rebuild layer.
- **Doc updates for v1.5.1 → v1.5.2.** Architect's work; happens after this layer lands. This note references the v1.5.2-level changes implicitly (sigil removal, Class retirement, Standalone retirement, continuous-identifier model) but the .docx/.md doc revisions come after.

---

## After this note lands

The prototype will visibly demonstrate:

1. **Create Program and Create Project as functional flows** — users can create Programs and Projects from the UI, with proper validation and Program-parent enforcement.
2. **Optional PartsBox creation** on Project save, matching real-world usage patterns (some Projects are placeholders; most are real).
3. **The continuous-identifier chain** rendering across the platform — Program TVCA → Project TVCA-R2 → BOM line TVCA-R2-042 → CPN TVCA-R2-042. Visible traceability from any level.
4. **No dead controls** — every button reachable in the UI does something or isn't there.
5. **Task Center residue gone** — no more retired-concept code lurking behind dev flags.
6. **Scope pill** distinguishing project-bound and wall-bound CPNs visually, without relying on sigil characters.

At that point, the prototype has closed the elicited scope of Sessions 1, 2, and 3. Remaining scope from earlier notes (Model B re-upload UI, Build overlay refinements, Create Supplier, Development role reactivation, backend integration) becomes the next layer of coordination conversations.
