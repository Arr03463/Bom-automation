**AutoBOM Team Release**

Complete Implementation Specification & Architecture Guardrails

**Primary audience: Claude Code — implementation owner. This document is intentionally self-contained and overly explicit.**

| **Purpose: finish the existing AutoBOM as a cohesive, team-ready application. Preserve working functionality, extend shared capabilities, deploy safely, then freeze the team release.** |
|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

Prepared from the current uploaded AutoBOM repository and the locked requirements defined for the team release.

## REVISION 2 — CODEX-AUDITED IMPLEMENTATION SPECIFICATION

This revision incorporates the independent AutoBOM Technical Review Findings produced from direct code inspection and local test execution. Where the earlier specification contained assumptions, the audited repository facts below take priority. Product requirements remain authoritative; the audit is used to correct implementation sequencing, expose regression risks, and identify existing code that must be extended rather than recreated.

# 1. Read This First — Mission and Non-Negotiables

| **Your job is NOT to redesign AutoBOM into a new product. Your job is to finish the existing AutoBOM for team use, preserve working behavior, make the application cohesive, deploy it safely, and then stop feature expansion.** |
|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

Assume you have no access to the conversation that produced these requirements. This document is the source of truth for the team-release implementation unless the repository itself proves a factual implementation detail differs. When repository reality and this document conflict, preserve the intended behavior described here and report the conflict before making a destructive change.

- **Cohesive-system rule:** AutoBOM must behave as one continuous application, not as a set of unrelated mini-tools placed beside one another.

- **Reuse before creation:** If a new requirement overlaps an existing capability, extend the existing shared capability and reuse it. Do not create a parallel implementation just for one screen or workflow.

- **Preserve proven behavior:** Do not delete or replace working BOM cleaning, sourcing, PartsBox project creation, Mouser cart creation, DigiKey MyList creation, exports, or caching unless the replacement is necessary and demonstrably preserves behavior.

- **Data flows forward:** Information already known by the application must be carried forward automatically. Do not ask the operator to re-enter project, part, supplier, replacement, review, cart, list, or other state that AutoBOM already has.

- **Minimal necessary refactor:** Refactor to enable shared behavior and multi-user safety; do not perform an aesthetic architecture rewrite.

- **Team release boundary:** After the requirements in this specification are complete and tested, this version is frozen except for bug fixes. Future procurement-intelligence ideas belong elsewhere.

# 2. Product Objective

AutoBOM is an internal BOM automation application used to clean designer BOMs, calculate build quantities, create/reuse PartsBox project data, source parts through Mouser and DigiKey, create supplier purchasing artifacts, and produce handoff outputs. The current application works locally but needs a final team-readiness pass before it is hosted in Streamlit Cloud and handed to other team members.

The finished experience should feel continuous:

Upload BOM → Clean/normalize → Apply build quantity → Create/reuse PartsBox project/storage → Source → Results workspace → Needs Review (if needed) → Replacement lookup → Update the same BOM state → Purchasing handoff → Downloads / team use

The application does not need to be “AI smart.” It needs to be robust, connected, predictable, and easy for a teammate to use without the original developer standing beside them.

# 3. Current Repository Snapshot (Observed)

The uploaded repository is a Python/Streamlit application. The following files already exist and must be treated as working assets to extend, not as disposable prototypes.

| **File / module**                       | **Observed responsibility**                                                                                                         | **Implementation implication**                                                                                                                                                                        |
|-----------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| app.py                                  | Thin Streamlit upload/options/results/download UI; writes uploaded files into shared input/.                                        | UI can be expanded, but P0 multi-user file collisions must be fixed: current uploads use shared input/\<filename\> and downloads can point to overwritten shared outputs.                             |
| src/workflow_runner.py                  | Central reusable orchestration via run_bom_workflow(); supplier sourcing, cart/list actions, PartsBox flow, exports, summary.       | Keep this as the primary orchestration seam. Audit confirmed it currently drops processed/review rows and structured Mouser/DigiKey identifiers; extend its return contract rather than bypassing it. |
| src/bom_cleaner.py                      | Large existing BOM normalization/cleaning and quantity logic.                                                                       | Do not rewrite as part of this closeout unless a specific bug requires it.                                                                                                                            |
| src/sourcing_engine.py                  | SupplierResult model, sourcing decisions, run cache + persistent cache, Mouser-first/DigiKey fallback behavior.                     | Reuse/extend for shared sourcing/replacement-related logic; avoid separate supplier-decision engines.                                                                                                 |
| src/mouser_client.py                    | Mouser product lookup and matching.                                                                                                 | Reuse in global lookup and replacement search.                                                                                                                                                        |
| src/digikey_client.py                   | DigiKey product details/keyword search and matching.                                                                                | Reuse in global lookup and replacement search.                                                                                                                                                        |
| src/mouser_cart_client.py               | Builds Mouser cart items and POSTs them to Cart API; supports CartKey input.                                                        | Automatic cart creation is explicitly preserved.                                                                                                                                                      |
| src/digikey_mylists_client.py           | Creates DigiKey MyList and adds parts; returns list_id.                                                                             | Preserve and surface automated DigiKey purchasing/share identity.                                                                                                                                     |
| src/partsbox_client.py                  | PartsBox API wrapper; part/all, project/all, storage/all, project/create, storage/create, project/add-entries and matching helpers. | Extend this shared client for inventory/search/admin operations and project lifecycle needs.                                                                                                          |
| src/partsbox_project_builder.py         | Creates/reuses project + same-name storage and adds BOM entries.                                                                    | Extend the existing lifecycle. Audit confirmed repeated runs can append duplicate BOM entries; reuse PartsBoxClient.get_project_entries() and add only missing/changed entries as appropriate.        |
| src/supplier_lookup_cache.py            | Persistent successful supplier lookup cache.                                                                                        | Preserve only if made safe. Audit confirmed direct shared JSON writes are not concurrency-safe; use atomic/coordinated writes or disable/isolate persistent cache in hosted multi-user mode.          |
| tests/test_sourcing_accuracy.py         | Existing supplier/sourcing test coverage.                                                                                           | Expand rather than replace.                                                                                                                                                                           |
| src/digikey_client.py token persistence | Refresh-token rotation currently rewrites the repository .env.                                                                      | Cloud blocker: move token persistence behind deployment-appropriate secure storage/configuration; do not rely on rewriting .env in Streamlit Cloud.                                                   |

Current workflow_runner response is intentionally small (success/errors/warnings/summary/outputs/messages). It does not currently expose enough structured runtime data for a rich results workspace. Expanding this response/state contract is a foundational task.

## 3.1 Codex-Audited Baseline — Confirmed Release Blockers

- P0 — Shared-file collision risk.

app.py currently saves uploads to input/\<sanitized original filename\>, while workflow_runner/export paths use the shared output/ directory. Two users or two sessions using the same filename can overwrite one another. This is a confirmed blocker for multi-user/team release.

- P0 — Repeated PartsBox runs can duplicate BOM entries.

partsbox_project_builder.py reuses same-name projects/storage, but add_bom_entries_to_project() adds the full BOM without comparing existing project entries. PartsBoxClient.get_project_entries() already exists and should be reused to make the project BOM write idempotent.

- P1 — Purchasing identifiers are currently dropped by orchestration.

mouser_cart_client.py returns the cart API response inside result and digikey_mylists_client.py returns list_id/list metadata, but workflow_runner.py reduces these to counts/messages. The structured values must be retained and returned to Streamlit.

- P1 — Processed BOM and review rows are unavailable to the UI.

workflow_runner.py holds result.clean_bom and result.review_items during execution, but returns only counts/messages/paths. This must be corrected before the Results workspace and Needs Review flow are implemented.

- P1 — PartsBox production tagging/filter behavior is not implemented.

Same-name project/storage creation already exists, but the production tag is not ensured and no saved-filter operation exists in the current PartsBox client. Extend the existing lifecycle; do not create a parallel path.

- P1 — Persistent supplier cache is not concurrency-safe.

SupplierLookupCache.save() writes directly to one JSON file without atomic replacement or coordination. Hosted multi-user use must either make writes atomic/coordinated or disable/isolate persistent cache behavior.

- P1 — DigiKey token refresh persistence is cloud-unsafe.

DigiKeyClient currently rewrites the repository .env when refresh tokens rotate. That assumption must be removed or abstracted behind deployment-appropriate secure persistence before Streamlit Cloud/team deployment.

## 3.2 Confirmed Current Test Baseline

- python -m unittest discover -s tests -v: 9 tests passed in the audited workspace.

- python -m py_compile app.py plus the audited core modules: passed.

- No live PartsBox, Mouser, or DigiKey API calls were made during the audit; live response shapes and undocumented capabilities still require vendor/API verification.

- The audited workspace did not contain .git metadata, so commit history and historical secret exposure were not verified.

# 4. Application-Wide Architecture Rule — Cohesion Over Feature Islands

| **If a feature already exists in a closely related form, extend that feature and reuse it. Do not rebuild a second version just because the caller is a different page.** |
|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

Examples of the required behavior:

- General Component Search, Needs Review → Find Replacement, BOM-line alternative search, and supplier lookup must reuse the same lookup/search services and normalized result representation.

- PartsBox Inventory and PartsBox fallback lookup must reuse the same PartsBox client/service. They may present different UI views, but should not have duplicate request/parsing logic.

- A replacement selected during Needs Review must update the active BOM/run state and flow into the normal sourcing and purchasing logic. Do not create a side spreadsheet or detached “replacement result.”

- Purchasing handoff must consume the already-resolved BOM state. Do not recalculate supplier decisions in a separate purchasing subsystem.

- Project/storage setup used during BOM upload and project-management views must call the same shared lifecycle logic.

- UI components may be different views of shared behavior, but the business logic underneath should be single-source wherever practical.

## 4.1 Separation is allowed when it is real

Do not force reuse where it makes the system harder to reason about. A dedicated UI page or adapter is acceptable when responsibilities are genuinely different. The prohibition is against duplicated business logic, duplicated supplier/PartsBox parsing, duplicated part models, and disconnected state — not against having multiple screens.

# 5. Locked Scope — What Must Be Finished

**1.** Shared component search and robust filtering, with PartsBox enabled by default and opt-in Mouser/DigiKey sources.

**2.** Dedicated PartsBox Inventory page/view backed by PartsBox API functionality.

**3.** Correct PartsBox project + storage lifecycle: same name, production tag, deduplication, and same-name saved filter using the locked conditions.

**4.** Rich BOM Results workspace with search/filter, status/source, summary, and Needs Review.

**5.** Needs Review recovery workflow centered on finding a replacement using the shared lookup feature; PartsBox is a last-resort fallback in that recovery flow.

**6.** Preserve Mouser automatic Cart API creation and CartKey path. Use manual Model B only for Mouser sharing in the interim.

**7.** DigiKey purchasing handoff remains automated through MyList/share ID/key API workflow.

**8.** Quality-of-life/operator usability improvements.

**9.** Streamlit Cloud / multi-user-safe file, session, cache, and secret handling.

**10.** End-to-end team testing and release freeze.

# 6. Explicit Non-Goals

- Do not turn this closeout into the future procurement-intelligence platform.

- Do not add a full inventory-management replacement for PartsBox; PartsBox remains the inventory system of record.

- Do not redesign the app in a new web framework solely for aesthetics.

- Do not remove the automatic Mouser cart path because sharing is temporarily manual.

- Do not implement fragile browser automation for Mouser sharing unless explicitly directed later.

- Do not invent undocumented supplier/PartsBox API endpoints. If an API operation required by the workflow is unavailable, keep the architecture ready for it and implement the cleanest supported fallback.

- Do not expose secrets, .env values, tokens, or customer BOM data in logs or commits.

# 7. Shared Application State / Data Contract

The current runner returns only summaries and paths. The team UI needs structured data that persists through the active Streamlit session. Extend the existing workflow result instead of creating an unrelated global state store.

Audit-confirmed detail: workflow_runner.py currently has access to result.clean_bom and result.review_items during execution, and receives structured Mouser cart / DigiKey MyList results, but does not preserve them in the returned contract. Phase 2 should expose these existing values first; do not rebuild equivalent data by rereading exported files.

A recommended logical shape (exact names may differ if a cleaner fit exists):

result = {  
"success": bool,  
"errors": \[...\],  
"warnings": \[...\],  
"messages": \[...\],  
"summary": {...},  
"outputs": {...},  
"run": {  
"run_id": "...",  
"project_name": "...",  
"build_quantity": 10,  
"source_file_name": "..."  
},  
"bom_rows": \[ ...normalized/processed rows... \],  
"review_items": \[ ...references into the same BOM state... \],  
"partsbox": {  
"project": {...}, "storage": {...}, "filter": {...}  
},  
"purchasing": {  
"mouser": {"cart_created": True, "cart_key": "...", ...},  
"digikey": {"list_created": True, "list_id": "...", "share_key_or_id": "...", ...}  
}  
}

- Do not serialize pandas DataFrames directly into JSON summaries. Maintain a UI/session representation and only serialize safe primitive data where needed.

- Every BOM row should have a stable row/run identifier so Needs Review and replacement actions can update the correct row.

- Source and status must be distinct concepts. Example: Source = Mouser, Status = Ready. Do not use supplier names as status values.

- Review actions should modify the same canonical BOM row/state and then call shared sourcing/purchasing logic as needed.

- Persist only what is appropriate. Streamlit session state is acceptable for active-run UI state; exported artifacts remain files; PartsBox remains system of record for inventory.

# 8. BOM Results Workspace — Detailed Requirement

After a successful or partially successful run, the operator must see a real results workspace rather than only metric cards and download buttons. Existing downloads remain available, but they are no longer the only way to understand the run.

## 8.1 Required high-level layout

AutoBOM Results — \<Project Name\>  
  
Total Parts \| PartsBox \| Mouser \| DigiKey \| Needs Review  
  
\[ Search current BOM results... \]  
Source \[All\] Status \[All\] Manufacturer \[All\] Stock \[All\] More Filters  
  
\[ All Results \] \[ Needs Review (N) \]  
  
Interactive results table  
  
Purchasing / outputs / messages

## 8.2 Required result concepts

| **Concept**  | **Requirement**                                                                                                                                                        |
|--------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Source       | Separate field/view for PartsBox, Mouser, DigiKey, none/unknown where applicable.                                                                                      |
| Status       | Clear workflow status such as Ready, Needs Review, Not Found, Error, Pending, etc. Map from current sourcing_status values without losing underlying technical status. |
| Search       | Search within the processed BOM without rerunning the BOM.                                                                                                             |
| Filters      | At minimum source, status, manufacturer, stock/availability, and any useful BOM-level fields already present.                                                          |
| Sorting      | Allow practical sorting of visible result columns.                                                                                                                     |
| Review count | Needs Review count is derived from the same BOM state, not separately maintained.                                                                                      |
| Actions      | Per-row actions may include retry exact lookup, find replacement, or review details. These actions must reuse shared services.                                         |

## 8.3 Current statuses that must not be silently lost

The existing sourcing engine uses technical statuses such as sourced_mouser, sourced_digikey, check_wall_inventory, and manual_review. Preserve these for logic/debugging even if the UI maps them to friendlier labels.

# 9. Shared Component Search + Filtering Engine

| **Build ONE shared lookup/search capability. Different screens can invoke it with different defaults and prefilled criteria.** |
|--------------------------------------------------------------------------------------------------------------------------------|

## 9.1 General search behavior

- A global component search bar is required.

- PartsBox is enabled as a search source by default.

- Mouser and DigiKey are optional source toggles that the user can enable for the same search.

- The search should support MPN, manufacturer, description/keywords, supplier part number, and other fields available through normalized results.

- The user must be able to refine results with robust filtering similar in spirit to distributor parametric search. Exact filter availability depends on fields returned by the connected sources; do not fabricate parameters.

- Search/filtering must be responsive and should not rerun the whole BOM workflow.

## 9.2 Filter categories to support where data exists

- Manufacturer

- Category / part type

- Package / case / footprint

- Mounting type

- Value/specification fields relevant to the component category

- Voltage/current/power/tolerance or analogous parametric constraints where available

- Stock availability

- Lifecycle/status where available

- Source (PartsBox/Mouser/DigiKey)

- Price / quantity-break information where returned

- Review/status context when searching inside a BOM run

## 9.3 Normalization requirement

Supplier and PartsBox responses do not have identical schemas. Normalize results into a common representation for display/filtering while preserving raw source payload or source-specific metadata when useful. Do not force every source field into a lowest-common-denominator model if it would throw away valuable details.

## 9.4 Reuse requirement

- General Component Search invokes the shared search service with PartsBox on by default and Mouser/DigiKey toggles.

- Needs Review → Find Replacement invokes the same service with Mouser/DigiKey prioritized and the failed part characteristics pre-populated.

- PartsBox Inventory may reuse PartsBox-side filtering/search primitives but presents inventory-specific details/actions.

- BOM Results search is primarily a filter over the already-processed run data; where it offers “search alternatives,” it should call the same shared component lookup service.

# 10. Needs Review — Recovery Workflow

Needs Review must be an action-oriented recovery queue, not merely a list of errors. The default recovery strategy is to help the user find a valid replacement. In this specific workflow, checking PartsBox is a last-resort fallback, even though PartsBox is the default source in the general Component Search feature.

## 10.1 Required order of operations

**1.** Show the reason the row needs review (no stock, obsolete/unavailable, missing/ambiguous match, API error, missing MPN, etc.).

**2.** Offer Retry / Verify Exact Part where that could resolve a transient or matching issue.

**3.** Primary action: Find Replacement.

**4.** Open the shared lookup engine with characteristics already known from the original BOM row / supplier data. Do not make the user re-enter data the app already knows.

**5.** Prioritize Mouser and DigiKey for purchasable replacement candidates.

**6.** Allow the operator to tighten/loosen relevant characteristics and compare candidates.

**7.** The operator selects/approves a replacement; AutoBOM updates the same BOM/run state, records the decision, and reruns the relevant sourcing/purchasing preparation for that row.

**8.** If no acceptable replacement is found, offer Check PartsBox as the last-resort inventory lookup.

**9.** If still unresolved, mark for manual/engineering review with a clear reason.

## 10.2 Replacement safety / agency

AutoBOM may rank/filter candidates based on explicit technical constraints, but the operator must remain responsible for approving a substitute. Do not silently replace a component solely because a search result appears similar.

## 10.3 Example flow

Needs Review: 10 µF / 25 V / X7R / 0805 / ±10%  
Reason: selected supplier cannot cover required quantity  
  
\[ Retry Exact Part \]  
\[ Find Replacement \] ← primary  
Search starts with known constraints prefilled  
Sources: Mouser + DigiKey  
User reviews candidates and selects one  
→ active BOM row updates  
→ sourcing status updates  
→ purchasing state updates  
  
Last resort: \[ Check PartsBox Inventory \]  
Then: \[ Mark for Engineering Review \]

# 11. PartsBox Inventory View

Add a clear PartsBox Inventory entry point/page. This is not a separate inventory system; it is an AutoBOM interface over PartsBox API capabilities. PartsBox remains the source of truth.

- Search and filter inventory using shared PartsBox service methods.

- Display useful part identity, quantity/stock, storage location, tags, description/manufacturer/MPN, and other fields actually returned by the API.

- Support useful manipulations through the PartsBox API when supported and appropriate (for example stock/location-related operations), but do not invent unsupported endpoints.

- Use clear confirmation/error handling for write operations.

- Do not duplicate PartsBox request/parsing code in the UI. Extend PartsBoxClient or an adjacent shared PartsBox service.

- Keep inventory functionality consistent with cloud/team authentication and write-safety requirements.

# 12. PartsBox Project / Storage / Filter Lifecycle

| **Locked soft-link design: project name, storage location name, and saved filter name are the SAME name. The storage location must have the production tag.** |
|---------------------------------------------------------------------------------------------------------------------------------------------------------------|

## 12.1 Required lifecycle

**1.** Sanitize/resolve the project name using the existing naming logic.

**2.** Find or create the PartsBox project with that name.

**3.** Find or create a PartsBox storage location with the exact same name.

**4.** Ensure that storage location contains the tag production. This requirement applies to newly created storage and to an existing same-name storage that lacks the tag, if the PartsBox API supports updating it.

**5.** Create/find the PartsBox saved filter with the exact same name.

**6.** The saved filter conditions are exactly: Storage Location Name equals \<project/storage name\> AND Storage Location Tags contains production.

**7.** Do not add an extra project-name tag as a second association mechanism. The shared name is the soft association; production is the qualifying storage tag.

**8.** Do not create duplicate projects, storage locations, or filters when they already exist.

9\. Make PartsBox BOM-entry writes idempotent. Before adding entries to a reused project, call the existing PartsBoxClient.get_project_entries() path and compare against the intended BOM. Do not blindly append the full BOM on every run.

10\. Add targeted tests for first-run creation and repeated-run reuse to prove the second execution does not duplicate existing BOM entries.

## 12.2 Saved filter API uncertainty

The current repository does not implement saved filter-preset creation. The Codex audit confirmed no saved-filter operation exists in src/partsbox_client.py. Do not invent a PartsBox endpoint. Verify current official API support before implementation. If no supported API exists, preserve the same-name project/storage + production-tag convention and document the exact manual filter creation procedure as the team-release fallback.

## 12.3 Build/inventory intent

The purpose of this naming/tag/filter convention is to make project-specific production inventory easy to select and to support future/PartsBox build behavior that draws from the intended same-name production storage. Do not broaden consumption to unrelated dev/prototype stock unless explicitly requested.

# 13. Supplier and Purchasing Handoff

Mouser and DigiKey have intentionally different interim sharing behavior. Do not force them into identical implementation details. They should feed one cohesive purchasing area/state while preserving each supplier’s actual capabilities.

## 13.1 Mouser — preserve automatic Cart API creation

- Existing automatic Mouser cart creation MUST remain.

- Keep the path that builds Mouser cart items from rows with selected_supplier=mouser and sourcing_status=sourced_mouser.

- Keep Cart API submission and capture/retain the returned CartKey when available.

- The audit confirmed mouser_cart_client.py returns the cart API response inside its result object, but workflow_runner.py currently discards that structure. Preserve and promote the existing response rather than issuing a second cart query solely to recover CartKey.

- Do not replace automatic cart creation with a manual CSV-only process.

- Expose enough structured result data from create_mouser_cart_from_bom()/workflow_runner for the UI/state to know whether creation succeeded, item count, CartKey, and errors.

## 13.2 Mouser Model B — TEMPORARY sharing only

Mouser’s sharing step is manual for the team release because the desired CartKey→Share Access ID API capability is not yet confirmed. Model B applies ONLY to Mouser sharing, not to DigiKey.

- AutoBOM may prepare the normal Mouser purchasing/cart data and keep automatic cart creation.

- For the actual share handoff, the operator completes Mouser’s share action manually and obtains the Mouser Access ID/share key.

- The operator gives that Access ID/share key directly to purchasing.

- Do NOT require the operator to return to AutoBOM and paste the share key merely to complete Model B. That would add friction and create throwaway UI.

- Do not remove CartKey handling. Desired future Model A is automatic: AutoBOM creates cart → receives CartKey → invokes supported/private Mouser share API → obtains Access ID/share key → gives it to purchasing.

## 13.3 DigiKey — automated MyList/share workflow

- Preserve existing DigiKey MyLists creation and returned list_id.

- The audit confirmed digikey_mylists_client.py already returns list_id/list metadata, while workflow_runner.py flattens it into messages. Preserve this returned object through orchestration; verify the exact share-key/share-ID field against the current live API before relying on a field beyond list_id.

- Implement/surface the automated DigiKey share ID/key workflow available through its API/integration path. Model B manual sharing is NOT the DigiKey plan.

- Purchasing handoff should clearly expose the DigiKey list identity/share value and list name/status without requiring a manual reconstruction of the list.

- If the exact share field differs from list_id, keep both distinct in structured state.

## 13.4 Shared purchasing layer

The purchasing UI/state should consume the resolved BOM and the supplier action results. It should not re-source components. It can present supplier-specific cards/sections, but they come from one purchasing handoff state.

# 14. Quality-of-Life / Operator Experience

- Simplify the default operator path. Advanced implementation toggles should not dominate the main screen.

- Use sensible defaults for the normal team workflow.

- Show progress/status clearly during long API operations.

- Errors should explain what failed and what the operator can do next.

- Keep technical details available for debugging but do not make normal operators interpret raw exceptions.

- Use consistent labels for project, source, status, review, and purchasing.

- Add concise operator instructions inside the deployed app.

- Do not remove export/download functionality; integrate it into the results/purchasing experience.

# 15. Streamlit Cloud and Multi-User Safety

P0 RELEASE BLOCKER: The current app writes uploaded files into a shared input/ directory and workflow_runner/exporters write into shared output/. The Codex audit confirmed that same-name uploads and generated files can collide across sessions. This must be corrected before any team/cloud release, even if the UI feature work is otherwise complete.

- Generate a unique run/session identifier.

- Use a per-run temporary working directory for uploaded source files and generated active-run artifacts.

- Do not allow two users uploading the same filename to overwrite one another.

- Downloads must refer to the current session/run only.

- Treat local cloud filesystem as ephemeral. Do not use it as the authoritative inventory/project database.

- Move runtime secrets from local .env deployment dependence to Streamlit/cloud secrets/environment configuration. Never commit secret values.

- Audit supplier lookup cache behavior: SupplierLookupCache currently writes one JSON file directly with no locking/atomic replacement. For hosted multi-user use, implement atomic/coordinated writes or disable/isolate persistent cache behavior. Add a concurrency-focused test.

- Do not leak one user’s BOM/result paths or data into another user’s session.

- DigiKey OAuth/token refresh writeback currently rewrites the repository .env. Replace this deployment assumption with a secure, writable, deployment-appropriate token persistence/configuration strategy before cloud release; add a mocked token-rotation test.

# 16. File-Level Implementation Guidance

| **Area**                             | **Preferred direction**                                                                                                                                                                                                                                    |
|--------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| app.py                               | Keep UI orchestration thin. Use st.session_state for active run state and per-run/session working directories. Never save active uploads to a shared filename-derived path.                                                                                |
| workflow_runner.py                   | Expand return contract to expose existing clean_bom/review rows, PartsBox lifecycle result, raw/normalized Mouser cart result including CartKey, DigiKey MyList/list/share result, and output paths. Preserve current summary/output keys where practical. |
| partsbox_client.py                   | Add supported API operations/search/stock/storage/tag methods here or in a thin shared PartsBox service. Extend dry-run write operation coverage for every new write endpoint.                                                                             |
| partsbox_project_builder.py          | Extend same-name project/storage lifecycle; production tagging; saved-filter abstraction/fallback; and idempotent BOM-entry synchronization using existing project-entry reads. Do not add the full BOM blindly on reused projects.                        |
| sourcing_engine.py                   | Preserve current supplier-decision semantics. Reuse SupplierResult/normalization ideas for shared lookup. Do not make a second sourcing engine.                                                                                                            |
| mouser_client.py / digikey_client.py | Reuse as supplier adapters. Add search/normalization capability here or behind a shared search service rather than duplicating API calls in UI.                                                                                                            |
| mouser_cart_client.py                | Preserve automatic cart creation. Normalize/extract CartKey from the existing returned API response and propagate it upward; do not replace with CSV-only flow.                                                                                            |
| digikey_mylists_client.py            | Preserve list creation/add-parts and propagate returned list_id/list metadata upward. Verify and expose share identifiers supported by the current API.                                                                                                    |
| New shared module(s), if needed      | A small part_lookup/search service and/or normalized part result model is acceptable when it centralizes behavior used by multiple screens. Avoid unnecessary framework layers.                                                                            |
| tests/                               | Add targeted tests for each shared service and workflow; use fakes/mocks for network APIs.                                                                                                                                                                 |
| supplier_lookup_cache.py             | Make shared cache writes atomic/coordinated or disable/isolate persistent cache in hosted mode. Preserve lookup-cache semantics without risking corruption/lost updates.                                                                                   |
| digikey_client.py token persistence  | Abstract refresh-token persistence away from direct .env rewriting for cloud use; preserve the existing authentication flow while making storage deployable and testable.                                                                                  |

# 17. Recommended Implementation Phases and Gates

## 17.0 Audit-Driven Priority Override

The independent audit changes implementation priority. Correct the confirmed release blockers before spending significant time on visual polish. The product feature order below still applies, but these audited defects are mandatory gates:

- P0: isolate every active run/session file path so same-name uploads/exports cannot collide.

- P0: make repeated PartsBox project BOM writes idempotent so rerunning the same project does not append duplicate entries.

- P1: preserve structured processed/review rows and supplier purchasing identifiers through workflow_runner.

- P1: ensure production storage tagging and handle saved-filter API uncertainty explicitly.

- P1: make supplier cache behavior safe for multi-user hosting.

- P1: remove the cloud assumption that DigiKey token rotation can rewrite a shared repository .env.

## Phase 0 — Baseline and safety

- Run current tests and record baseline.

- Compile-check core modules.

- Create a feature branch/worktree.

- Do not commit .env or generated customer files.

- Document current behavior that must remain green.

- Add a regression test proving two same-name uploads/runs resolve to distinct working paths and independent contents.

- Decide and implement the per-run working-directory seam now, before later UI pages depend on shared input/output paths.

## Phase 1 — PartsBox lifecycle correctness

- Same-name project/storage reuse.

- Production tag on new storage.

- Ensure production tag on existing storage if supported.

- Saved-filter lifecycle using locked conditions or clean documented fallback if API does not support creation.

- Unit tests for duplicate/reuse/tagging behavior.

- Use PartsBoxClient.get_project_entries() before project/add-entries and add/synchronize only what is required. Repeated identical runs must not append duplicate BOM entries.

- Add mocked first-run and repeated-run tests for PartsBox BOM entry idempotency.

| **Gate: no search/UI expansion until PartsBox lifecycle tests pass and current project/BOM-entry behavior remains intact.** |
|-----------------------------------------------------------------------------------------------------------------------------|

## Phase 2 — Rich workflow return + session state

- Return processed BOM rows and stable row IDs.

- Return structured PartsBox and purchasing results.

- Promote the existing Mouser cart API response/CartKey and DigiKey MyList result/list_id instead of reconstructing them from messages or exports.

- Expose clean_bom and review_items as stable UI/session data with row identifiers.

- Preserve existing summary/output keys for backward compatibility where practical.

- Store active run state in Streamlit session.

## Phase 3 — Results workspace

- Summary metrics.

- All Results table.

- Search/filter/sort current run.

- Needs Review tab derived from same data.

- Preserve download outputs.

## Phase 4 — Shared component lookup/search

- Common normalized search results.

- PartsBox default source.

- Mouser/DigiKey toggles.

- Robust filters using available data.

- No duplicate supplier search logic.

## Phase 5 — Needs Review replacement flow

- Prefilled criteria.

- Mouser/DigiKey replacement search.

- User-approved replacement.

- Update same BOM row/state.

- Rerun relevant sourcing.

- PartsBox fallback last.

- Engineering review final.

## Phase 6 — PartsBox Inventory

- Dedicated page using shared PartsBox service.

- Search/filter/display.

- Supported manipulation operations with confirmation.

- No duplicate project/storage logic.

## Phase 7 — Purchasing handoff

- Mouser cart creation remains automated; CartKey captured.

- Mouser sharing remains manual Model B only.

- DigiKey automated MyList/share key/id surfaced.

- Purchasing state consumes resolved BOM.

## Phase 8 — Cloud/team hardening

- Per-run temp files.

- Session isolation.

- Secret handling.

- Cache concurrency.

- DigiKey refresh-token persistence must no longer depend on rewriting repository .env in hosted deployment.

- Add concurrent cache-write coverage or explicitly disable/isolate persistent cache in cloud mode.

- OAuth/cloud considerations.

- Deployment smoke test.

## Phase 9 — Team validation and freeze

- Run a real BOM end to end.

- Have another employee complete normal workflow without developer assistance.

- Fix defects.

- Tag stable Team Release.

- After release: bug fixes only unless scope is reopened.

# 18. Acceptance Criteria — Feature by Feature

| **Area**                 | **Pass condition**                                                                                                                                                                                                              |
|--------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Cohesion                 | No duplicate part-search/supplier/PartsBox business logic is introduced for individual pages; shared services are reused.                                                                                                       |
| Results                  | Processed BOM is visible in-app with summary, source/status, search, filters, and Needs Review.                                                                                                                                 |
| Search                   | PartsBox is default; Mouser/DigiKey can be toggled on; results support meaningful parametric filtering from available fields.                                                                                                   |
| Review                   | Find Replacement is primary recovery action; uses same lookup engine; selected replacement updates active BOM state; PartsBox is last-resort fallback.                                                                          |
| PartsBox project         | Project and storage have same name; no duplicates; storage has production tag.                                                                                                                                                  |
| PartsBox filter          | Same-name filter uses Storage Location Name = name AND Storage Location Tags contains production, or limitation/fallback is explicitly handled if API cannot create it.                                                         |
| PartsBox inventory       | Dedicated inventory view uses shared PartsBox client/service and actual API data.                                                                                                                                               |
| Mouser                   | Automatic cart creation remains working; CartKey is retained; sharing is manual only as temporary Model B.                                                                                                                      |
| DigiKey                  | MyList creation remains working; automated share/list ID/key is surfaced for purchasing.                                                                                                                                        |
| Cloud                    | Two users/runs cannot overwrite or see each other’s temporary files/state; secrets are not stored in committed files.                                                                                                           |
| Regression               | Current BOM cleaning, quantity math, sourcing fallback, exports, PartsBox project/storage reuse, idempotent PartsBox BOM entries, Mouser cart creation, DigiKey MyList creation, and existing sourcing tests remain functional. |
| Run isolation            | Two users/sessions can upload the same filename and run concurrently without overwriting or reading one another’s input/output artifacts.                                                                                       |
| PartsBox idempotency     | Rerunning an existing project does not append duplicate BOM entries; existing project-entry reads are reused to determine required writes.                                                                                      |
| Structured handoff       | workflow_runner returns processed/review rows plus structured Mouser and DigiKey purchasing results; UI does not recover these values by parsing messages or exported files.                                                    |
| Cloud token/cache safety | Hosted deployment does not rely on shared .env mutation; supplier cache cannot corrupt or silently lose data through concurrent writes.                                                                                         |

# 19. Testing Requirements

## 19.1 Unit tests

- PartsBox project/storage deduplication.

- PartsBox repeated-run BOM-entry idempotency using mocked get_project_entries() and add-entries responses.

- Production tag creation/update behavior.

- Saved-filter request construction/fallback behavior.

- Normalized search-result mapping for each source.

- Search/filter predicates and parametric constraints.

- Needs Review routing and replacement state update.

- Mouser CartKey extraction and cart result retention.

- DigiKey list/share identifier retention.

- Workflow runner structured response and backward-compatible summary keys.

- Per-run path generation / filename isolation.

- Two concurrent/simulated same-name uploads produce distinct paths and independent downloadable artifacts.

- SupplierLookupCache concurrent update behavior (or explicit hosted-mode disable/isolation behavior).

- DigiKey refresh-token rotation does not require direct repository .env rewrite in hosted configuration.

## 19.2 Integration tests with mocked APIs

- BOM → sourcing → results state.

- Review item → replacement → updated sourcing state.

- PartsBox project/storage lifecycle.

- Mouser cart creation path.

- DigiKey MyList/share path.

- API failures produce recoverable UI state instead of crashing the app.

## 19.3 Manual end-to-end checklist

**1.** Upload CSV BOM and XLSX BOM.

**2.** Use a real project name; confirm same-name PartsBox project/storage behavior.

2a. Run the same project a second time and verify the PartsBox BOM does not gain duplicate entries.

**3.** Confirm production tag.

**4.** Confirm filter behavior/fallback.

**5.** Run supplier sourcing.

**6.** Verify Results table.

**7.** Filter to Mouser/DigiKey/Review.

**8.** Open a review item and use Find Replacement.

**9.** Approve a replacement and confirm the same BOM row updates.

**10.** Confirm PartsBox fallback appears only after replacement path in review.

**11.** Create Mouser cart and retain CartKey.

**12.** Complete manual Mouser share outside AutoBOM and hand Access ID directly to purchasing.

**13.** Create DigiKey MyList and confirm automated list/share identity.

**14.** Download expected artifacts.

**15.** Run two browser sessions/users concurrently and verify isolation.

15a. In both sessions, upload files with the same original filename and verify each session downloads only its own artifacts.

# 20. Error Handling and Observability

- Network failures must be source-specific; one supplier failure should not necessarily destroy the whole run.

- Preserve raw exception/context in logs where safe, but show actionable friendly messages in UI.

- Never print API keys, OAuth tokens, full secret headers, or .env contents.

- Record enough run context to diagnose which source/action failed without exposing customer-sensitive data.

- Dry-run modes must remain meaningful and cover new write operations.

# 21. Security / Data Handling

- Do not commit .env. The uploaded repo contains a local .env file; treat it as sensitive and do not reproduce its values.

- Use Streamlit/cloud secret management for deployed credentials.

- Customer/internal BOM files are transient working data unless an explicit persistence requirement is added.

- Avoid logging complete BOMs to shared logs by default.

- Be cautious with supplier OAuth refresh tokens in cloud deployment; current local file update behavior may not be suitable.

# 22. Definition of Done

| **The release is done when a teammate can open the hosted app, upload a BOM, understand the results, resolve exceptions through the integrated replacement workflow, use PartsBox inventory/project behavior, obtain supplier purchasing handoffs, and complete the normal workflow without the original developer explaining which separate tool to open next.** |
|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

- All acceptance criteria pass.

- Regression tests pass.

- Cloud multi-user isolation is verified.

- Repeated PartsBox runs are verified idempotent for project BOM entries.

- Structured Mouser CartKey/MyList identifiers and processed/review rows reach the UI/session state without message parsing.

- Hosted DigiKey token persistence and supplier-cache behavior are safe for multi-user deployment.

- Operator instructions exist in-app.

- Another team member successfully completes the workflow.

- Release is tagged/versioned.

- Further feature expansion is stopped unless explicitly reopened.

# 23. Required Claude Code Handoff Report

At the end of each implementation phase, report in a compact engineering format:

- Files changed.

- What existing shared capabilities were extended/reused.

- Any new shared abstraction and why it was necessary.

- Tests added/changed and results.

- Known limitations / API uncertainties.

- Regression risks.

- Exact next recommended phase.

- Any requirement you could not implement without external API confirmation.

| **Do not quietly work around a missing API by creating a disconnected manual subsystem. Preserve the cohesive architecture and explicitly surface the limitation.** |
|---------------------------------------------------------------------------------------------------------------------------------------------------------------------|

# Appendix A — Core Workflow in One View

RUN BOM  
│  
├─ Clean/normalize + quantities  
├─ PartsBox project/storage lifecycle  
│ └─ same name + production tag + same-name filter  
├─ Supplier sourcing (existing shared engine)  
└─ Results state  
│  
├─ All Results (search/filter/sort)  
├─ Needs Review  
│ ├─ retry exact  
│ ├─ Find Replacement → SHARED lookup engine → approve → same BOM state  
│ ├─ PartsBox fallback (last resort in review)  
│ └─ engineering review  
│  
└─ Purchasing handoff  
├─ Mouser: auto cart + CartKey; share manually for now  
└─ DigiKey: auto MyList + automated share/list ID/key  
  
GLOBAL ENTRY POINTS  
Component Search → SAME lookup engine (PartsBox default; Mouser/DigiKey toggles)  
PartsBox Inventory → SAME PartsBox client/service

# Appendix B — Do Not Recreate the Wheel Checklist

- Before adding a module, search the repo for related logic.

- Before adding an API call, check the existing source client.

- Before adding a search form, check the shared lookup service.

- Before adding a part schema, check the normalized/shared result model.

- Before adding project/storage creation, call the shared PartsBox lifecycle.

- Before recalculating purchasing, use the resolved BOM state.

- Before asking the operator for data, check whether the active run already knows it.

- If only 70% of an existing feature is sufficient, extend it to 100% and reuse the subset needed by each caller instead of making a second 30% implementation.

# Appendix C — Codex Audit Findings Incorporated Into This Revision

The following repository facts were independently confirmed and are now mandatory implementation constraints:

- app.py uses shared input/\<filename\> paths; output artifacts are also shared. Treat run isolation as P0.

- partsbox_project_builder.py reuses projects/storage but can append duplicate BOM entries on repeated runs. Reuse PartsBoxClient.get_project_entries() to make writes idempotent.

- mouser_cart_client.py and digikey_mylists_client.py already return structured purchasing data; workflow_runner.py currently drops it.

- workflow_runner.py has processed clean_bom/review_items during execution but does not return them to Streamlit.

- partsbox_client.py currently has no saved-filter operation and no confirmed stock/build API implementation in this repo; extend only after verifying supported endpoints.

- supplier_lookup_cache.py direct shared JSON writes are not concurrency-safe.

- digikey_client.py refresh-token rotation currently rewrites .env and must be adapted for cloud deployment.

- Baseline audit tests: 9 unit tests passed and core modules compiled; no live vendor API calls were executed.

If repository code and this revision conflict, first determine whether the conflict is an implementation bug, an outdated assumption, or an externally unverified API behavior. Preserve locked product requirements while avoiding invented API capabilities.
