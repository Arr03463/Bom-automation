# AutoBOM — Coordination Note 1 (Housekeeping / Drift Correction)

## Purpose

This is a **hygiene pass** that brings the codebase to a clean v4 baseline. No new capabilities are added in this pass — everything either aligns with the current v4 architecture, gets deleted as v1.3 residue, or gets restructured per Chapter B workspace decisions.

**Prerequisite:** Read the new `CLAUDE.md` in this same directory first. It supersedes the previous CLAUDE.md and reflects Chapter A + Chapter B decisions, tenets, and the retired v1.3 concepts. Do not proceed until CLAUDE.md is loaded and internalized.

**Why housekeeping first:** The next coordination note (Note 2 — Forward-Looking Layer) builds the app-wide search bar rework and the Push-Back resolution rework. Both changes lean on a codebase where Purchasing is not a role, where the CPN format is consistent, where the sidebars match Chapter B, and where the state model has one truth per Request. Building on top of drifted foundations creates layered problems that compound. This note removes the drift.

**Scope:** Twelve actions across three groups plus coordination. All actions are pure clean-up + restructure. No new UI patterns, no new data flows, no new APIs. If any action feels like it's growing beyond scope, elicit — this note is deliberately narrow.

## Elicitation pattern

Same as previous sessions. One question at a time. Wait for my answer. Then execute.

---

## Group 1 — Role and CPN cleanup

**1. Fully remove Purchasing as a role from the codebase.**

- `permissions.jsx`: remove `purchasing` from `ROLE_META`, remove `NAV_BY_ROLE.purchasing`, remove any `purchasing` from `CAP_CATALOG` capability groups.
- `app.jsx`: remove `purchasing` from `ROLE_PREFIX` and `PREFIX_ROLE`. Remove any `purchasing`-specific branches in notification routing.
- `screen_admin.jsx`: remove `'purchasing'` from `ALL_ROLES_FULL` (line 5). Similarly for any other role-list arrays used to render Admin UI.
- `data.jsx`: update user seed data. David Okafor currently has `roles: ['purchasing']` (line 44) — change to `roles: ['production']` (David becomes a Production user in the v4 model; he still operates the embedded Purchasing view like everyone else). If any other users have `'purchasing'` in their roles, change similarly.
- `shell.jsx`: the role switcher comment already reflects v4 (three login roles). Confirm code matches — should be no live changes needed here since the array was already filtered.
- `store.jsx`: notification templates that hard-code `'purchasing'` for `sourceRole` / `targetRole` / `forRoles` — change to whichever role actually receives them under v4 (usually Admin for batch failures, requester for FYI).

**Rejection criteria for this action:**
- Any string `'purchasing'` remaining in an active role-list array (`ALL_ROLES`, `ROLE_META` keys, `NAV_BY_ROLE` keys).
- Any user seed with `roles` including `'purchasing'`.
- Any notification with `forRoles: ['purchasing']` or `targetRole: 'purchasing'`.

The `purchasing` string may remain ONLY in historical audit entries and in retired-notification templates being deleted.

---

**2. Consolidate CPN generation to the sigil format.**

Currently two CPN generators exist: the sigil generator (`sigilCpn` in `screen_embedded.jsx` line 22-36 — correct) and the old initials-based generator (`cpnFor` in `data.jsx` line 484 — retired).

- Move `sigilCpn` from `screen_embedded.jsx` to `data.jsx` as the canonical CPN generator. Rename to `cpnFor` (so callers don't have to update).
- Delete the old `cpnFor` implementation and its comment (`data.jsx` line 478 and line 484).
- Update `screen_collection_detail.jsx` line 92 to use the new canonical `cpnFor` — no code change needed if we rename the sigil version to `cpnFor`.
- Update any other callers throughout the codebase that reference `cpnFor` — they should all just work with the canonical sigil version.
- Update seed data references (`customerRef: 'TVCA-RND-02'` etc.) to use the sigil format where they're intended to represent CPNs.

**Rejection criteria:**
- `ownerInitials(...)` still called anywhere.
- Two different CPN generators in the code.
- Old-format CPN strings in seed data referenced as CPNs.

Note: `customerRef` on ORDERS objects is being deleted in Action 8 anyway; don't spend cycles updating orders.

---

## Group 2 — Sidebar and route restructure

**3. Designer sidebar cleanup.**

- `permissions.jsx` `NAV_BY_ROLE.designer` (line 145-152): remove the `d.orders` entry entirely.
- `permissions.jsx` `NAV_SHARED` (line 187): remove the `projects` entry (Projects moves out of shared; see Action 4).
- `shell.jsx` line 91: remove the `.filter(n => !(n.key === 'projects' && activeRole === 'designer'))` workaround — no longer needed since Projects isn't in NAV_SHARED at all.

Final Designer sidebar: Dashboard, Programs, Collections, Purchasing (embedded), Inventory (embedded), Notifications.

**4. Production sidebar cleanup.**

- `permissions.jsx` `NAV_BY_ROLE.production` (line 153-159):
  - Remove `receiving` entry (Receiving is accessed via embedded Inventory's "Start receiving" action, not top-level).
  - Add `{ key: 'projects', label: 'Projects', icon: 'folder' }` right after `p.boms`.

Final Production sidebar: Dashboard, BOMs, Projects, Purchasing (embedded), Inventory (embedded), Notifications.

**5. Admin sidebar restructure.**

- `permissions.jsx` `NAV_BY_ROLE.admin` (line 176-184): replace with:
  - `a.dashboard` — Dashboard
  - `a.configuration` — Configuration (NEW: single tabbed screen absorbing workflow, suppliers, system settings)
  - `programs` — Programs
  - `a.users` — Users
  - `purchasingEmbed` — Purchasing (embedded, Full default)
  - `inventoryEmbed` — Inventory (embedded)
  - `a.forceWaivers` — Force-Waivers log (NEW)
  - `a.audit` — Audit Log

- Delete `a.roles`, `a.workflow`, `a.suppliers`, `a.settings` as separate sidebar entries. Their content merges into `a.configuration`.
- Create new screen `AdminConfiguration` that tabs among Roles & Permissions, Workflow, Suppliers, System Settings. Existing screens (`RolesPermissions`, `WorkflowConfig`, `SupplierConfig`, `SystemSettings`) become tab panels inside the new configuration screen.
- Create new screen `ForceWaiversLog` that shows audit entries filtered to force-waive actions. Include: entity, actor, reason, before/after state, timestamp.
- Ensure `purchasingEmbed` opened from Admin defaults to Full mode (query param, state, or Admin-specific default in the embedded screen).

Final Admin sidebar: Dashboard, Configuration, Programs, Users, Purchasing (embedded, Full default), Inventory (embedded), Force-Waivers log, Audit Log, Notifications.

**Elicit before building AdminConfiguration if unclear which tabs go inside.**

**6. Delete `d.orders` route + `MyOrdersScreen` component.**

- `nav.jsx` ROUTE_TABLE (line 13): remove the `d.orders` entry.
- `app.jsx` line 15-58: delete the `MyOrdersScreen` function entirely.
- `app.jsx` line 215: remove the `case 'd.orders'` dispatch branch.
- `app.jsx` CRUMBS map (line 104-116): remove `d.orders` key.
- `app.jsx` NAV_OF map (line 118-126): remove `d.orders` key.
- `screen_dashboard.jsx` line 68-79: delete the "My Orders" panel from the Designer Dashboard. The dashboard's stats row (line 46-51) has a "Orders in flight" stat that references `myOrders.length` — update or remove that stat too. Same for the collection-side layout — dashboard becomes a single-column layout (My Collections panel on its own) or gets a different second panel.

**Elicit if uncertain what to replace the second panel with** — options include: a "Recent Programs" panel, or dashboard becomes one-column, or "Recent activity across my Collections" panel. My recommendation: one-column Needs Attention + My Collections stacked, with the removed panel space folding into Programs Recently Viewed or similar low-stakes info.

---

## Group 3 — State model and dead code cleanup

**7. Add `program_id` FK to Projects.**

- `data.jsx` PROJECTS object (line 33-38): add `program_id` field to each Project.
  - `tvca-rev2`: `program_id: 'terra-voyager'` (linked)
  - `gate-eval`: `program_id: 'gatekeeper'` (linked)
  - `wall-q2`: `program_id: 'restock'` (linked)
  - `bldc`: `program_id: null` (standalone Project — no Program)
- Update `PROGRAMS` (line 435-449): the `projects: [...]` reverse array should reflect this. `bldc` should NOT appear in any Program's projects array (it's standalone).
- Update `ProgramDetailScreen` to render linked Projects as **read-only reference cards** (not editable — Production owns Projects, Designer just sees the link). Card links out to `projectDetail`.

**8. Delete pre-v4 order lifecycle.**

- `store.jsx`:
  - Delete `approveRequest` (line 176-182).
  - Delete `placeOrder` (line 187-201).
  - Delete `createShipment` (line 205-216).
  - Delete `setShipmentStatus` (line 217-231).
  - Delete `setOrderStep` (line 232-264).
  - Delete `_rollupRequest` (line 266-284).
- `data.jsx`:
  - Delete `ORDERS` seed array (line 168-173).
  - Delete `SHIPMENTS` seed array (line 470-475).
  - Remove `orders` and `shipments` from the `seedState` return object (line 512-513).
- Anywhere in code that references `orders` or `shipments` state slices → clean up. Callers should either be removed or refactored to use the archive view (batch-level, in embedded Purchasing) instead.
- Update Request seed data: remove `state: 'approved'`, `state: 'ordered'` and any pre-v4 request states. Use `bucketState` only. Also remove `approvedBy`, `approvedWhen`, `poId` fields from Request seed.

**9. Clean overlapping Request state fields.**

- After Action 8, Requests carry only `bucketState` for lifecycle. Delete the `state` field from Request seed and from any store action that writes to `.state` on a Request.
- Update `store.jsx` `requestToOrder` (line 98-109): writes only `bucketState`, not `state`.
- Update `submitBomToPurchasing` (line 164-173): same.
- Any UI that reads `req.state` → change to `req.bucketState`.

**10. Retire `screen_purchasing.jsx` entirely.**

- Delete `screen_purchasing.jsx` file.
- `app.jsx` imports (line 6): remove `PurchasingDashboard`, `RequestReviewScreen` from the destructured global imports.
- `app.jsx` line 228: remove the `case 'b.requestReview'` dispatch branch.
- `nav.jsx` ROUTE_TABLE line 23: remove the `b.requestReview` route entry.
- `nav.jsx` breadcrumb builder line 110: remove the `if (s === 'b.requestReview')` branch.
- `app.jsx` CRUMBS map: remove `b.requestReview`.
- `app.jsx` NAV_OF map: remove `b.requestReview`.
- `search.jsx` line 118: request result `case 'request'` currently routes to `b.requestReview` — reroute to `purchasingEmbed` with a query param that opens the specified request in a modal / drawer, OR to `projectDetail` with the Request tab. Design decision:

  **Elicit: how should a Request search result open in v4?**
  - Option A: Opens embedded Purchasing view with a query param that highlights / expands the request row into an inline detail
  - Option B: Opens the request's Project detail with the Requests tab active
  - Option C: Opens the source Collection or BOM (whichever generated the request)

  My recommendation: Option A — because Requests are Purchasing-workflow objects and the embedded view already displays them.

- `screen_bom_overview.jsx` line 45, 72: `b.requestReview` references — route to embedded Purchasing or Project detail per the elicitation answer above.
- `tasks.jsx` line 217: same treatment.
- Any other references to `b.requestReview` → reroute similarly.

**11. Delete `d.search` standalone screen residue.**

- `nav.jsx` ROUTE_TABLE line 10: remove the `d.search` entry.
- `app.jsx` line 212: remove `case 'd.search'` dispatch (currently identical to `d.dashboard`).
- `app.jsx` CRUMBS map (line 105): remove `d.search`.
- `app.jsx` NAV_OF map: remove `d.search`.
- `app.jsx` deep-link handler (line 162-168): keep the redirect logic that opens the command palette from a `d.search` hash, but move it to handle a hash that doesn't match any route (fallback) rather than a specific `d.search` case. OR simplify: remove the redirect, since after removing the route the hash would just fall through to `d.dashboard` naturally.
- `CLAUDE.md` (old version) references `/designer/search` — no longer applies; new CLAUDE.md doesn't reference it.

**12. Delete duplicate CRUMBS + NAV_OF static maps in `app.jsx`.**

- `app.jsx` line 104-126 declares `CRUMBS` and `NAV_OF` as static hardcoded maps.
- `buildCrumbs(route, state)` in `nav.jsx` is the dynamic canonical breadcrumb builder — used at `app.jsx` line 264.
- `NAV_OF` is used for sidebar active-item highlighting at `app.jsx` line 194.
- Consolidate: derive `NAV_OF` from `ROUTE_TABLE` in `nav.jsx` (map screen → nav item key). Delete both static maps from `app.jsx`.
- Confirm every screen still has its sidebar item highlighted correctly after the change.

---

## Group 4 — Coordination

**13. Elicit upfront if anything is ambiguous.**

Explicit elicitation points already flagged in the actions above:
- Action 5: what tabs go inside the new AdminConfiguration screen
- Action 6: what replaces the "My Orders" panel on the Designer Dashboard
- Action 10: how should a Request search result open in v4

Any other ambiguity — same pattern: one question at a time, wait for my answer, then execute.

---

## Rejection criteria for the whole session

If any of these are still true at the end of the session, the housekeeping did not close:

- Any string `'purchasing'` in an active role-list array.
- Any user with `roles: ['purchasing']` in seed.
- `NAV_BY_ROLE.purchasing` still defined.
- `ROLE_META.purchasing` still defined.
- `d.orders` route or screen or nav item present anywhere.
- `MyOrdersScreen` component still in the codebase.
- Old CPN generator (`ownerInitials`, `<bucket>-<sourceId>-<initials>-<line>` format) still active.
- ORDERS or SHIPMENTS seed arrays or state slices still present.
- `approveRequest`, `placeOrder`, `createShipment`, `setShipmentStatus`, `setOrderStep`, `_rollupRequest` still in store.
- Request `state` field with values from `approved` / `partially-ordered` / `ordered` / `shipped`.
- `screen_purchasing.jsx` file still exists.
- `b.requestReview`, `b.dashboard`, `b.purchasing`, `b.requests`, `b.orders`, `b.orderPlace`, `b.orderExec`, `b.shipments` referenced anywhere in active code.
- `receiving` as a top-level Production sidebar item.
- Static `CRUMBS` or `NAV_OF` map in `app.jsx`.
- Designer Dashboard "My Orders" panel present.
- Any Push-Back / exception routing to `d.exception` — Push-Back arrival is Needs Attention only (this was already correct in some places, but confirm no regression).

---

## What this note does NOT include

To keep the scope tight:

- **The app-wide search bar functional change** (PartsBox-backed default, "Include suppliers" toggle, three-section results, storage locations). That's Note 2, Group 2.
- **The Push-Back resolution rework** (unified search interface with characteristic filters + bidirectional manufacturer typeahead, `search_suppliers` mode wiring). That's Note 2, Group 3.
- **The datasheet lifecycle attachment flow.** That's Note 2 as well.
- **The Build object model** (Chapter B multi-Build-per-Project with per-line overlay). Deferred to a later layer (Production BOM screen rebuild). Do not attempt in this session.
- **The CPN issuance table.** Deferred to when the fulfillment-tracking feature is built out in embedded Purchasing archive (later layer).
- **Cart-building for batch flush.** Deferred to a later layer (Purchasing v4 pipeline integration).
- **Programs UI beyond what already exists.** Create Program flow is a future coordination note.

If a housekeeping action reveals that a related piece of Note 2 work would be trivially easy to fold in, **flag it and elicit**. Don't quietly expand scope.
