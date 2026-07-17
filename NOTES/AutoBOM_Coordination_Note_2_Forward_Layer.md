# AutoBOM — Coordination Note 2 (Forward-Looking Layer)

## Purpose

This note delivers the **next functional layer** of AutoBOM: the app-wide search bar rework (PartsBox-backed with storage locations and supplier overlay), the Push-Back-to-Designer resolution rework (unified characteristic search with Designer-proposes/Production-applies model), and the Production inline-edit characteristic-match check.

**Prerequisite:** Coordination Note 1 (Housekeeping) must be complete first. This note assumes:

- Purchasing role fully removed from role structures
- CPN format consolidated to sigil
- Designer / Production / Admin sidebars restructured per Chapter B
- `d.orders`, `screen_purchasing.jsx`, `screen_admin.jsx` splits, ORDERS/SHIPMENTS, and pre-v4 order lifecycle deleted
- Request state model uses `bucketState` only
- Project has `program_id` FK
- CLAUDE.md is the current v4 operating context

If Housekeeping is not complete, stop this note and return to Note 1.

**Scope:** Twenty actions across four functional groups plus coordination. Three new capabilities are introduced (storage location search + storage location detail; unified characteristic search + Push-Back inline resolution with Designer-proposes/Production-applies model; Production inline-edit with characteristic-match check). Everything else is UX plumbing to connect them into the existing v4 model.

## Elicitation pattern

Same as previous sessions. One question at a time. Wait for my answer. Then execute.

---

## Group 1 — App-wide search bar functional change

The existing app-wide search bar's visual and placement stay unchanged. Only the data source, results structure, and behavior change. This is `search_available_stock` mode.

**1. Switch data source to PartsBox.** Route the app-wide search bar's queries to PartsBox's search API endpoint. Live PartsBox data replaces the static `CATALOG` (currently in `search.jsx` line 46). Mocked PartsBox dataset (from `partsbox-parts.csv` and `partsbox-storage.csv`) is available as a stand-in for the API contract during prototype work.

Ranking (currently in `rankHit` at `search.jsx` line 27) still applies to whatever the PartsBox API returns — normalize the response shape into the existing rank/hit structure.

**2. Three-section results layout.** When a query returns results, present up to three sections in this order:

- **In inventory** — parts matching from PartsBox (always shown when populated)
- **Storage locations** — PartsBox storage locations matching the query by name, description, or contained parts (always shown when populated)
- **Available from suppliers** — Mouser + DigiKey via sourcing engine (shown only when "Include suppliers" toggle is on)

Each section has its own header, result cards, and action affordances. **Sections are never deduped.** A part existing in both PartsBox and supplier results appears in both sections with different action affordances.

**3. Add "Include suppliers" toggle.** Off by default. Toggle on to add the third section. Toggle state persists per session.

**4. Storage location result card design.** When a storage location appears in results, the card shows:

- **Location name** in monospace (e.g., `A-3-7`, `Cabinet Bin-#107 FANS`)
- Description (from PartsBox, if present)
- Distinct part count
- Tags (`development`, `production`, `autobom-managed`) — surfaces the storage kind
- Preview of contents — first 3–5 parts with "+ N more" if longer
- **Click opens location detail INSIDE AutoBOM** (Action 5) — no external trip to PartsBox

**5. Storage location detail surface (new build).** Clicking a storage location result opens a detail view inside AutoBOM as a drawer OR a full-page route.

**Elicit: drawer or route?**

My recommendation: **route**. Storage locations are real physical things; they deserve first-class URLs. Add `storageDetail` to ROUTE_TABLE, add a `StorageDetailScreen` component. Breadcrumbs: `Inventory · Storage locations · <name>`.

Content:
- Location metadata (name, description, tags, storage kind)
- Full parts list stored there, with per-part quantity and MPN
- Cross-links to each part's PartsBox record via ID Anything™ code
- "Move parts" / "Add stock" actions (universal read+write per Inventory Activation v3.1)

**6. Empty states.**

- No PartsBox matches with the supplier toggle off → prompt: "No matches on hand. Try including suppliers."
- All sections empty with the supplier toggle on → "no matches found" state with option to source manually.

---

## Group 2 — Push-Back-to-Designer resolution rework

The existing Push-Back arrival and dashboard-inline expansion patterns are correct in principle. What changes is significant:

1. The per-flagged-line resolution mechanism (currently `InlinePartVerify` — manual MPN entry) is replaced with a unified characteristic search interface.
2. **Designer's resolution is a *recommendation*, not a commit.** Production applies it from their own Dashboard. This is a fundamental workflow change.
3. Push-Back reason category enum expands to include `missing-component`.
4. Push-Back structure grows to carry the fields Chapter A locked (reason category, urgency, per-flagged-line detail with own comment sub-thread).
5. The primary-action button pattern gets unified across action-needing dashboard items.

This is `search_suppliers` mode.

**7. Preserve the existing Push-Back arrival pattern.** "Needs Attention" section on the Designer Dashboard, "BOM EXCEPTION" cards showing BOM name/version/ID, Program → Project breadcrumb, Production's message, reason/urgency badges, part count needing action. Preserve — don't rebuild.

**8. Preserve the dashboard-inline expansion pattern.** Clicking the primary action expands the card inline. Resolution surface appears in the dashboard flow — never leaves the dashboard. Preserve.

**9. Unify the primary-action button pattern across action-needing dashboard items.** Currently every card has its own action verb (`Respond`, `Re-check sourcing`, `Run sourcing`, `Re-source replaced lines`, `Review`, `Add tracking`, `Retry`, `Reassign`, `Refresh token`).

Converge on one conceptual pattern with a single label:

**Elicit: which label unifies best?**
- **`Resolve`** — my recommendation. Concise, works for every card type.
- **Keep varied verbs but standardize position + style.** More natural language, less consistent affordance.
- **Custom per-type verbs but same button shape/color/position.**

My recommendation is a single label (`Resolve`) with a small secondary tag showing the specific action (e.g., `Resolve · Respond to Production`). Trades verbosity for scannable consistency.

**10. Extend the Push-Back structure with Chapter A fields plus `missing-component`.**

- `data.jsx` BOMS seed line 133: currently `exception: { by, when, to, note, loop }`. Extend to `pushback: { by, when, to, reason, urgency, note, loop, flaggedLines: [...], addedComponentRequest: {...} }`:
  - `reason` — enum: `obsolete` / `eol` / `unsourceable` / `zero-stock` / **`missing-component`** / `other`
  - `urgency` — enum: `blocking` / `standard`
  - `flaggedLines` — array of `{ lineNo, exReason, comments: [] }`
  - `addedComponentRequest` — populated when reason = `missing-component`, otherwise null. Fields: `{ mpn? (optional), characteristics: { voltage?, capacitance?, package?, ... }, description, quantityPerBoard, designator (optional) }`
- Rename the field from `exception` to `pushback` to match the current architectural term. Migrate existing seed entries.
- Update `store.jsx` `sendException` (line 147-157): rename to `sendPushback`. Accept `reason`, `urgency`, `perLineComments`, `addedComponentRequest` params. Attach the structured payload to the BOM.
- Update `store.jsx` `respondException` (line 110-125): rename to `resolvePushback`. See Action 12 for the new semantics — this action produces a *recommendation*, not a commit.

**11. Rework the per-flagged-line resolution surface as a unified search interface.** Each flagged-line sub-card becomes a search widget with:

- **MPN input field** (free-text, smart-matching against sourcing engine)
- **Manufacturer field as bidirectional-constrained dropdown/typeahead** — typing an MPN filters the manufacturer dropdown; selecting a manufacturer filters MPN matches.
- **Characteristic filters** extracted from the flagged part's specs, pre-loaded as the starting query, refinable by Designer.
- **MPN input and characteristic filters combine AND-style** in the same query. **One unified surface, not two separate widgets.**

For `missing-component` Push-Backs, the surface renders differently:
- No source part to compare against
- Characteristic filters seeded from Production's `addedComponentRequest` description
- Designer picks a candidate → recommends it as a NEW line addition (not a replacement of an existing line)

Keep `<InlinePartVerify>` as a reusable component for OTHER contexts (Dev Collection candidate entry — deferred). Just don't use it in Push-Back resolution anymore.

Create a new component (suggested name: `<PushbackReplaceLine>`) that takes:
- `flaggedPart` (source MPN, source characteristics) — nullable for `missing-component` Push-Backs
- `addedComponentRequest` (nullable — populated for `missing-component`)
- `onSelectCandidate(candidate)` (called when Designer picks a recommendation)

Internally this new component runs `search_suppliers` mode.

**12. Change Designer's resolution to *recommendation* semantics.** This is the big workflow change.

- Currently: Designer resolves → BOM state moves to `normalised` → replacements land on BOM lines → Production notified.
- **New:** Designer resolves → creates a `pushback.recommendation` object attached to the Push-Back → BOM state stays in `exceptions` → Production notified with a "Replacements recommended" Needs Attention card → Production clicks Apply → THEN master BOM version increments with recommended replacements applied → BOM state transitions to `normalised`.

Concretely:
- `store.jsx` `resolvePushback`: creates a `recommendation` object with the Designer's picks, does NOT mutate BOM lines yet. Fires `RECOMMENDATIONS_RECEIVED` notification to Production.
- New store action `applyPushbackRecommendation(pushbackId)` — Production-only. Commits recommendations to master BOM lines, increments BOM version, transitions BOM state to `normalised`, fires re-sourcing notification.

**13. Add "Replacements recommended" Needs Attention card on Production Dashboard.** Card shows:
- BOM identifier
- Number of recommended replacements
- Reason category from the original Push-Back
- Designer who resolved
- Primary action: **Apply** (which commits recommendations to master BOM)
- Secondary action: **Review** (opens Push-Back detail with recommendations visible before applying)

**14. Wire per-line search to `search_suppliers` mode.**

- Supplier-primary polarity. Default data: Mouser + DigiKey via sourcing engine.
- Both MPN input and characteristic filter queries route through this mode.
- DigiKey's Product Information V4 exposes ParametricFilters natively. Sourcing engine translates characteristic filters into DigiKey ParametricFilters parameters.
- Mouser parametric support is weaker. Fall back to keyword-with-spec-hints if needed.

**15. Add "Include wall" toggle to the per-line search.** Off by default. When on, adds a section with PartsBox matches to the result list. Both sections shown, never deduped.

**16. Design the per-line search result card.** Show:
- MPN, manufacturer, description
- **Characteristics comparison against the flagged part** (matches / differs / improves) when a source part exists. For `missing-component`, show against the requested characteristics.
- Stock level
- Price
- Action affordance differs by section:
  - Supplier section: `Recommend this replacement`
  - Wall section: `Recommend from wall · <location>`

**17. Datasheet URL as first-class capability with PartsBox persistence.**

- Result cards display datasheet link when Mouser or DigiKey APIs return one.
- **On user-action** (Designer attaches a candidate as recommendation OR Production applies a recommendation): AutoBOM downloads the datasheet PDF and attaches to PartsBox part record via `part/attachments` API with `attachment/type = "datasheet"`.
- If PartsBox part already has a datasheet attached, skip.
- If API returns null, omit the link.
- Attachment is a background operation. If it fails, log for Admin diagnostic. Don't block user's workflow.

**18. Preserve secondary paths** (comment, defer, reassign per Production Alignment v1.1.1). Ensure they still work after the surface rework.

---

## Group 3 — Production inline-edit characteristic-match check

**19. Design the Production BOM screen inline-edit affordance with characteristic-match check.**

Every line on the Production BOM screen becomes inline-editable. The edit affordance differs by field type:

**Non-structural fields** (line note, description text, designator text):
- Freely editable inline by Production
- No characteristic check
- Audit-logged with actor + timestamp; no user-provided reason required

**Structural fields** (MPN, manufacturer, quantity):
- Editable inline
- On save, platform runs characteristic-match check via `search_suppliers` mode:
  - Fetch new MPN's characteristics from suppliers
  - Compare against source line's characteristics
  - Match criteria (silent swap succeeds): package/footprint match, nominal value match, tolerance equal-or-tighter, voltage rating equal-or-higher, temperature range equal-or-wider
- **On match:** silent swap. Master BOM version increments. Auto-recorded audit entry: "characteristic-match equivalent swap: [old MPN] → [new MPN], delta: [details]". No manual reason required. Designer FYI notification fires on Program-linked Projects (Admin-configurable per Program — see Action 20).
- **On mismatch:** Production sees a soft flag: "This differs from the original in [X, Y]. Send to Designer, or continue as override?"
  - **Send to Designer** — auto-generates a Push-Back with the flagged line + Production's intended replacement pre-populated as context. Notification to Designer. Line stays as-is on master BOM (edit is not committed).
  - **Continue as override** — requires manual audit reason (≥10 chars). Master BOM version increments. Designer notified via FYI.

**Design considerations:**
- The characteristic-match check must feel instant to Production. Query the sourcing engine synchronously; if delayed, show a spinner but proceed.
- Soft flag rendering: appears inline near the edited row, doesn't block the rest of the BOM screen.
- Audit reason field appears only when "Continue as override" is picked.
- Never surprise Production with a hard block — the flag is a warning, not a wall.

**20. Add Admin per-Program FYI notification policy.**

- In Program detail, add an Admin-only toggle: "Notify Program owner Designer of equivalent-part swaps on this Program's linked Projects" (default on).
- When off, silent characteristic-match swaps on this Program's linked Projects do NOT fire FYI notifications to the Program owner Designer.
- Override notifications (mismatch + Continue as override) always fire regardless of this toggle.
- Store on Program object as `notifyOnEquivalentSwap` boolean.

---

## Group 4 — Coordination

**21. Elicit upfront if anything is ambiguous.**

Explicit elicitation points already flagged:
- Action 5: storage location detail as drawer or route
- Action 9: primary-action button unification approach

Any other ambiguity — same pattern.

---

## Rejection criteria for the whole session

If any of these are true at the end of the session, the layer did not close:

- App-wide search bar still uses static `CATALOG` for its data source.
- App-wide search bar has no "Include suppliers" toggle.
- Storage locations do not appear as their own section in app-wide search results.
- Storage location result cards link out to PartsBox instead of opening in-app detail.
- Push-Back resolution still uses `<InlinePartVerify>` (manual MPN + Manufacturer + Verify Part).
- Push-Back per-line resolution surface does not offer characteristic filters.
- Manufacturer field on Push-Back per-line resolution is a free-text input rather than a bidirectional-constrained typeahead.
- **Push-Back structure does not carry `reason` and `urgency` fields.**
- **Push-Back reason category enum does not include `missing-component`.**
- **Push-Back missing-component branch is not supported** (no `addedComponentRequest` object; no way to add a component that wasn't on master).
- **Designer's Push-Back resolution silently mutates the master BOM** — must produce a *recommendation* Production applies.
- **Production has no "Replacements recommended" Needs Attention card** — must exist with Apply as primary action.
- **`applyPushbackRecommendation` store action does not exist.**
- Push-Back arrival navigates away from the dashboard (should be dashboard-inline expansion only).
- Datasheet URL is displayed but never attached to PartsBox on user-action.
- App-wide search results and Push-Back resolution results dedupe across sections.
- Different primary-action verbs across action-needing dashboard items (goal: unified pattern).
- **Production BOM screen has no inline-edit affordance on non-structural fields** (line note, description, designator text should be freely editable).
- **Production BOM screen has no characteristic-match check on MPN/manufacturer inline edits.**
- **Characteristic-match failures do NOT surface soft flag with Send to Designer / Continue as override options.**
- **Silent characteristic-match equivalent swaps do NOT fire Designer FYI notification** on Program-linked Projects (subject to Admin per-Program toggle).
- **Program object has no `notifyOnEquivalentSwap` toggle for Admin.**

---

## What this note does NOT include

To keep the scope tight:

- **Inventory Activation v3.1 receiving flow rebuild.** Planned as the next layer.
- **Production BOM screen rebuild for Builds + overlay + variant declaration.** Chapter B's Build overlay model lives in that later layer. This note only touches the master BOM edit affordances, not the Build creation flow.
- **The Sourcing + Decision Backbone spec.** Architect's work, separate deliverable. This note assumes the sourcing engine is a black box that exposes `search_available_stock()` and `search_suppliers()` plus characteristic-match check.
- **CPN issuance table + fulfillment pill rendering.** Deferred to when embedded Purchasing archive gets its fulfillment tracking.
- **Cart-building for batch flush.** Deferred to Purchasing v4 pipeline integration layer.
- **Create Program flow beyond adding the notifyOnEquivalentSwap toggle.** Full Create Program flow is a future coordination note.
- **Model B re-upload ceremony UI.** Deferred to Production BOM screen rebuild layer (the re-upload affordance itself lives on the BOM screen).
- **v1.5.1 doc refresh across the module packages.** Architect's work; happens after this layer lands.

---

## After this note lands

The prototype will visibly demonstrate:

1. **App-wide search** as a real PartsBox-backed interface with storage locations as first-class results and supplier overlay toggle.
2. **Push-Back resolution** as a characteristic-search-driven flow where Designer picks recommendations based on part specs, and Production applies them on their own Dashboard. The role separation (Designer proposes, Production applies) is visible in every step.
3. **Production inline-edit** with a characteristic-match check that stays out of the way for equivalent swaps and gently surfaces mismatches without blocking work.
4. **Datasheet coverage** growing over time as parts get used.
5. **`missing-component` Push-Backs** work end-to-end — Production requests, Designer recommends, Production applies.

At that point, the two most-user-facing improvements from Chapter A land visibly, and the workflow separation Aaron described ("Production edits when they can, Push-Back to Designer when they can't") is embodied in the UI. Remaining Chapter B work (Build overlay, master BOM Model B re-upload UI, receiving rebuild) becomes the natural next-layer conversation.
