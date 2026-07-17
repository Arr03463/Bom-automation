# AutoBOM Data Flow and Sequencing (v1.5.1)

**Purpose:** How data moves through the AutoBOM platform for every major workflow. Sequence descriptions, state transitions, and the invariants that must hold at each boundary.

**Companion documents:**
- `AutoBOM_Platform_Architecture.md` — the services these flows travel through
- `AutoBOM_API_Responsibility_Map.md` — which external APIs each step calls
- `AutoBOM_Code_to_Service_Connections.md` — where each flow lives in code

**Audience:** Claude Code (implementation reference), Claude Architect (spec cross-check), Claude Design (understanding state transitions to visualize).

---

## 1. Object hierarchy at a glance

```
Program (Designer-owned)
  ├── Collection[]  (Designer-owned)
  └── Project[]  (Production-owned; via nullable program_id FK)
        └── master BOM  (versioned at Project level; exactly one; immutable structure after upload)
              ├── BOM line[]  (with two on-hand qtys: project box + wall)
              └── Push-Back (structured; present when in exceptions state)
                  └── Recommendation (Designer's proposed replacements; Production applies)
        └── Build[]  (multiple over Project's lifetime)
              └── per-line overlay: used | skipped | deferred | rework

Orthogonal objects:
  - Request (bucket entry — from Collection or from BOM)
  - CPN issuance record (per line, referenced from Request → cart line → receiving)
  - Batch (groups Requests by supplier at flush time — writes to Josh's sheet)
  - Storage location (PartsBox — project boxes and wall bins)
```

**Ownership invariants:**
- Programs are Designer-owned. Designer has full CRUD.
- Projects are Production-owned. Production has full CRUD.
- Designer sees Program-linked Projects as read-only reference cards.
- Program → Project is parent-child *structural*. Production has full *operational* control regardless of Program link.
- **Master BOM structure is only changed via three paths:** Production inline-edit with characteristic-match check, Production applies Designer's Push-Back recommendation, or Model B re-upload ceremony.
- **Designer NEVER mutates master BOM directly.** Designer produces recommendations Production applies.

---

## 2. Flow — BOM upload through fulfillment

The primary end-to-end flow. Every step listed with state transitions and boundary events.

```
Production uploads BOM (first time — no downstream state to worry about)
    ↓  BOM.state = draft
Production validates BOM
    ↓  BOM.state = validated
Production runs sourcing
    ↓  BOM.state = sourcing (sourcing engine invoked; async)
Sourcing engine returns per-line results
    ↓  BOM.state = results | exceptions
     ↓ (if exceptions)                    ↓ (if all lines sourceable)
     Production sends Push-Back            Production reviews results
     BOM.state = exceptions                Production submits BOM as Request
     Designer receives Needs Attention     Request created, bucketState = QUEUED_*
     Designer resolves with recommendation Bucket timer eventually fires
     Production receives "Replacements     Batch flush pipeline runs (Sec. 5)
       recommended" card                   Bucket entries transition to WRITTEN
     Production clicks Apply               Josh's sheet gets row(s)
     BOM.state = normalised                Josh clicks cart URL in supplier UI
     Production re-runs sourcing           Josh places order (external)
     Loop until BOM.state = results        Physical bag ships
     ↓                                     Bag arrives at receiving (Sec. 6)
     Merge continues below                 PartsBox stock/add executes
                                           Fulfillment pill updates on archive
```

**Invariants that MUST hold:**
- Sourcing results older than the Admin-configured freshness threshold trigger stale-data warnings before Request submission.
- BOM state must be `results` or `normalised` to submit as Request. `exceptions` state blocks submission until Push-Back resolves AND Production applies the recommendations.
- CPN is generated at Request creation, before the Request enters the bucket.
- Bucket state and BOM state are decoupled — a BOM can proceed to Build execution while its Request is in the bucket.

---

## 3. Flow — Push-Back submission, recommendation, application

Cross-boundary handshake orchestration. Full sequence with routing and state transitions. **Note the two-step commit:** Designer proposes; Production applies.

### 3.1 Submission (Production → decision engine)

Two triggers, both flow to the same submission handler:

**Trigger A — Production's judgment (structured Push-Back from BOM screen):**

```
Production identifies problem lines (obsolete / EOL / unsourceable / missing-component)
    ↓
Production opens Send Push-Back modal
    ↓
Production fills structured fields:
    - reason: obsolete | eol | unsourceable | zero-stock | missing-component | other
    - urgency: blocking | standard
    - flaggedLines: [{ lineNo, exReason, comments }]   (empty for missing-component)
    - addedComponentRequest: { mpn?, characteristics, description, quantity }   (populated for missing-component)
    - note (overall)
    ↓
Production submits
    ↓
BOM.pushback = { by, when, reason, urgency, note, flaggedLines, addedComponentRequest, comments }
BOM.state = exceptions
```

**Trigger B — Characteristic-match failure on Production inline-edit:**

```
Production tries to inline-edit an MPN or manufacturer on the BOM screen
    ↓
Platform runs characteristic-match check via search_suppliers mode
    ↓
Match fails on at least one critical characteristic
    ↓
Soft flag appears: "This differs from the original in [X, Y]. Send to Designer, or continue as override?"
    ↓
Production picks "Send to Designer"
    ↓
Platform auto-generates Push-Back:
    - reason: 'other' (or 'unsourceable' if intent context suggests it)
    - urgency: standard
    - flaggedLines: [{ lineNo, exReason: 'Characteristic mismatch on attempted swap',
                       intendedReplacement: { mpn, manufacturer, characteristics } }]
    - note: 'Production tried to swap but characteristics differ.'
BOM.state = exceptions
Line stays as-is on master BOM (Production's inline edit is NOT committed)
```

### 3.2 Routing (decision engine)

```
Decision engine evaluates:
    IF BOM.project.program_id != null:
        route → Program owner Designer (from Program.owner)
        set responseDeadline = now + escalationWindow (Admin-configurable, default 24h)
    ELSE (standalone Project):
        route → unassigned pool
        no responseDeadline; any Designer can claim

Notification emitted:
    - kind: ACTION_REQUIRED
    - actionLabel: BOM EXCEPTION
    - sourceRole: production
    - targetRole: designer
    - verb: Resolve
    - route: d.dashboard (with card scroll-anchor)
```

### 3.3 Arrival (Designer side)

```
Designer opens Dashboard (their own, whether via notification click or direct nav)
    ↓
Needs Attention section renders BOM EXCEPTION card
    ↓ (or if Program-linked and escalated)
Card appears on ANY Designer's Dashboard in Unassigned Push-Backs section
    ↓ Designer clicks Take ownership OR the assigned Designer just clicks Resolve
    ↓
Card expands inline (no modal, no overlay, no navigation)
    ↓
Resolution surface renders:
    - Header (BOM, Program → Project, reason/urgency badges)
    - Overall comment thread (collapsible)
    - Per-flagged-line sub-cards  (for reason != missing-component)
      OR
      Missing-component request card (for reason == missing-component)
    - Batch primary action (initially disabled): "Send recommendations to Production"
```

### 3.4 Per-line resolution loop (for flagged-line Push-Backs)

```
For each flagged line:
    Designer sees unified characteristic search interface
    Query starts pre-loaded with flagged part's characteristics
    Designer refines: MPN input, manufacturer typeahead, characteristic filters
        Query runs in search_suppliers mode
        Results: Mouser + DigiKey (default section)
        Include wall toggle → adds PartsBox section
    Designer picks a candidate
    Designer clicks "Recommend this replacement"
        Flagged line marked with a *recommendation* (NOT a commit)
        Metadata attached to pushback.recommendation.perLine:
            { lineNo, recommendedMpn, recommendedMfr, source ("mouser"/"digikey"/"wall"), characteristics }
        IF datasheet URL returned AND PartsBox part has no attachment:
            AutoBOM downloads PDF (background)
            AutoBOM attaches to PartsBox via part/attachments
            attachment/type = "datasheet"
        Sub-card updates with recommendation stripe + Undo
    Designer can Undo, add comments, or move to next line
```

### 3.4a Missing-component resolution (for missing-component Push-Backs)

```
Designer sees unified characteristic search interface
Query starts with Production's addedComponentRequest characteristics
    (no flagged part to compare against)
Designer refines search
    Query runs in search_suppliers mode
    Results ranked by characteristics match against addedComponentRequest
Designer picks a candidate
Designer clicks "Recommend this addition"
    Recommendation attached to pushback.recommendation.addedLine:
        { mpn, mfr, source, characteristics, quantityPerBoard, suggestedDesignator }
    Datasheet auto-fetch on user-action (same as flagged-line flow)
Designer can Undo or add comments
```

### 3.5 Batch resubmission (Designer → Production) — RECOMMENDATION, not commit

```
All flagged lines have recommendations (and/or missing-component has a recommendation)
    ↓
Batch primary action "Send recommendations to Production" becomes enabled
    ↓
Designer clicks it
    ↓
Push-Back state transitions from 'open' to 'recommendations_sent'
BOM.state STAYS in 'exceptions' — master BOM is NOT mutated yet
BOM.pushback.recommendation is populated with:
    perLine: [{ lineNo, recommendedMpn, recommendedMfr, source, characteristics }]
    addedLine: { mpn, mfr, source, quantityPerBoard, suggestedDesignator }   (for missing-component)
    resolvedBy, resolvedWhen, resolutionSummary
    ↓
Notification emitted:
    - kind: ACTION_REQUIRED
    - actionLabel: REPLACEMENTS RECOMMENDED
    - sourceRole: designer
    - targetRole: production
    - verb: Apply
    - route: p.dashboard (with card scroll-anchor)
    ↓
Production dashboard shows "Replacements recommended" card
    Card details: BOM identifier, count of recommendations, reason, Designer who resolved
    Primary action: Apply
    Secondary action: Review (opens push-back detail with recommendations visible before applying)
```

### 3.6 Application (Production side — the actual commit)

```
Production reviews the recommendations (optional; can skip straight to Apply)
    ↓
Production clicks Apply
    ↓
For each recommendation in pushback.recommendation.perLine:
    Master BOM line[lineNo].mpn ← recommendedMpn
    Master BOM line[lineNo].manufacturer ← recommendedMfr
    Master BOM line[lineNo].characteristics ← from Designer's pick
    Master BOM line[lineNo].source = 'resolved-from-pushback'
    Master BOM line[lineNo].resolvedBy = Designer (from recommendation)
    Master BOM line[lineNo].appliedBy = current user (Production)

For addedLine (if present):
    New line appended to master BOM with:
        mpn, manufacturer, characteristics, quantityPerBoard, designator (suggested)
        source = 'added-via-pushback'
    PartsBox project BOM updated to include the new line
    ↓
Master BOM version increments (v_new = v_prev + 1)
BOM.state transitions from 'exceptions' to 'normalised'
Push-Back state transitions from 'recommendations_sent' to 'applied'
    ↓
Audit event written:
    action: 'push-back recommendations applied'
    actor: Production user
    before: master BOM v_prev
    after: master BOM v_new
    ↓
Notification emitted (FYI to Designer who resolved):
    - kind: FYI
    - actionLabel: RECOMMENDATIONS APPLIED
    - sourceRole: production
    - targetRole: designer (the resolver)
    - route: (link to BOM detail)
```

### 3.7 Secondary paths

**Designer side:**
- **Comment (Designer)** — write to Push-Back overall thread or per-line sub-thread. Optionally notifies Production. No state change.
- **Defer (Designer)** — mark Push-Back as deferred with reason. Persists in Needs Attention with visual defer state. Production is notified. Response deadline paused.
- **Reassign (Designer)** — hand to another Designer with a note.

**Production side (after recommendations sent):**
- **Review** — open Push-Back detail with recommendations visible before applying. Does NOT commit.
- **Reject specific recommendations** — Production can click Reject on individual per-line recommendations. Push-Back state moves back to 'open'; Designer notified with rejection reason. Designer re-resolves.
- **Cancel Push-Back** — Production withdraws entire Push-Back with reason. Master BOM stays unchanged. Push-Back state = 'withdrawn'. Designer's completed recommendations discarded.

### 3.8 Run Build gating

While `BOM.state == exceptions` OR any Push-Back is unresolved on the Project's master BOM (regardless of recommendation state), that Project's **Run Build** action is blocked. Only after Production applies (or cancels) the Push-Back does `BOM.state` transition to `normalised` and Run Build become available.

Admin `force-waive` can override with reason logged to Force-Waivers log.

---

## 4. Flow — Production inline-edit with characteristic-match check

The everyday-edit path. Production makes small corrections directly on the master BOM. Platform gates structural changes with silent characteristic-match check.

### 4.1 Non-structural field edits (freely editable)

```
Production clicks line note / description / designator text on BOM screen
    ↓
Inline edit affordance appears
    ↓
Production types new value
    ↓
Production saves (blur or click-away)
    ↓
Master BOM line[lineNo].{field} updated
Master BOM version increments (minor version bump — v_prev.1, v_prev.2, ...)
    ↓
Audit event written:
    action: 'inline metadata edit'
    actor: Production
    before/after: field value
    ↓
No notifications fire (metadata-only)
```

### 4.2 Structural field edits (MPN or manufacturer)

```
Production clicks MPN or Manufacturer on BOM screen
    ↓
Inline edit affordance appears with typeahead
Typeahead runs in search_suppliers mode:
    - Type in field → sourcing engine queries Mouser + DigiKey
    - Show candidate results ranked by characteristic-match against source line
    ↓
Production picks a candidate (or types a specific MPN)
    ↓
Production saves
    ↓
Platform runs characteristic-match check:
    Fetch new MPN's characteristics
    Compare against source line's characteristics
    Match criteria:
        - package/footprint match
        - nominal value match (capacitance, resistance, voltage rating)
        - tolerance equal-or-tighter
        - voltage rating equal-or-higher
        - temperature range equal-or-wider

    ↓
IF match on all criteria:
    Silent swap:
        Master BOM line[lineNo].mpn ← new MPN
        Master BOM line[lineNo].manufacturer ← new manufacturer
        Master BOM line[lineNo].characteristics ← from typeahead
        Master BOM version increments (major bump — v_prev + 1)
    ↓
    Auto-recorded audit entry:
        action: 'characteristic-match equivalent swap'
        actor: Production
        before: { mpn, mfr, characteristics }
        after: { mpn, mfr, characteristics }
        delta: computed diff on non-critical characteristics (tighter tolerance, higher voltage, etc.)
        reason: null (auto-recorded, no manual reason needed)
    ↓
    IF Program-linked Project AND Program.notifyOnEquivalentSwap == true:
        FYI notification to Program owner Designer:
            "Production swapped [old MPN] → [new MPN] on [Project.master BOM], both spec-matched."
    ↓
    Datasheet lifecycle: if new MPN's datasheet URL returned and PartsBox part has no attachment,
    background attach.

IF mismatch on at least one critical characteristic:
    Soft flag appears inline near the edited row:
        "This differs from the original in [X, Y]. Send to Designer, or continue as override?"
        Options: [Send to Designer] [Continue as override] [Cancel edit]
    ↓
    IF Production picks "Send to Designer":
        Auto-generate Push-Back (see Section 3.1 Trigger B)
        Master BOM line stays as-is (edit NOT committed)
    ↓
    IF Production picks "Continue as override":
        Prompt for audit reason (≥10 chars, required)
        Production types reason
        Production confirms
        ↓
        Master BOM line[lineNo] updated with new MPN/mfr/characteristics
        Master BOM version increments (major bump)
        Audit entry: 'characteristic-match override' with actor, before, after, reason
        FYI notification to Program owner Designer (ALWAYS, regardless of notifyOnEquivalentSwap):
            "Production overrode characteristic-match on [old MPN] → [new MPN], reason: [X]."
    ↓
    IF Production picks "Cancel edit":
        No state change, no audit event
```

### 4.3 Rejection criteria for characteristic-match check

- Match check must feel instant to Production (typeahead latency < 500ms perceived; background full check < 2s).
- Never hard-block Production. Soft flag only.
- Never silently override without match — the whole point is that mismatches surface a UI prompt.
- Silent match swaps must always audit-log the delta, even on silent commit.

---

## 5. Flow — Model B re-upload ceremony

Full-file re-upload of the master BOM. Always allowed at any BOM state. Ceremony scales with downstream impact.

### 5.1 Trigger

```
Production clicks "Re-upload master BOM" button on Project detail (visible always)
    ↓
File picker opens
    ↓
Production selects new BOM file (CSV or XLSX)
    ↓
Platform runs BOM cleaning pipeline on new file (same as initial upload)
```

### 5.2 Impact analysis

```
Platform analyzes what will be invalidated by the replace:
    - Any open Push-Backs on current master BOM?
    - Any in-flight sourcing runs?
    - Any Requests in the bucket referencing this BOM?
    - Any Builds in draft state against this BOM?
    - Any completed Builds (informational, not invalidated)
    ↓
Confirmation modal renders with itemized list:
    "Re-uploading will:
     - Cancel 2 open Push-Backs (Designer will be notified)
     - Cancel 1 in-flight sourcing run
     - Flag 3 Requests currently in the Purchasing bucket (they'll go into review state)
     - Recompute coverage for 1 draft Build
     - Increment master BOM version from v3 to v4

     Reason for re-upload (required, ≥10 chars):"
    ↓
Production types reason
    ↓
Production clicks Confirm (or Cancel — no change)
```

### 5.3 Execution

```
Platform commits the replace atomically:
    Master BOM structure replaced with cleaned new upload
    Master BOM version increments (v_prev + 1)
    BOM state → 'draft' (must be re-validated + re-sourced before any downstream action)
    ↓
Downstream effects:
    - Open Push-Backs → transition to 'cancelled_by_reupload' state with reason
    - In-flight sourcing runs → cancelled
    - Bucket entries → bucketState transitions to 'flagged_for_review' (Admin/Purchasing can act)
    - Draft Builds → coverage recomputed against new master; if red, Build flagged with warning
    ↓
Audit entry written:
    action: 'master BOM re-upload (Model B ceremony)'
    actor: Production
    before: BOM v_prev structure summary
    after: BOM v_new structure summary
    reason: (Production's provided reason)
    ↓
Notifications fire:
    - Designer (per cancelled Push-Back) with reason
    - Admin (batch summary) if bucket entries were flagged
    - Production (self, FYI) confirming the re-upload succeeded
    ↓
PartsBox project BOM synced to match new master:
    Old entries removed
    New entries added
    (Designers not doing this — automatic AutoBOM ↔ PartsBox sync)
```

### 5.4 State transitions

- BOM state: any state → `draft` on re-upload (must re-validate → re-source → normalise → submit again)
- Push-Back state: any open → `cancelled_by_reupload` (terminal for that Push-Back)
- Build state: draft with old coverage → draft with new coverage (Build itself doesn't change, but readiness indicators re-render)
- Bucket entry state: QUEUED_* → `flagged_for_review` (needs Admin/Production review before proceeding)

### 5.5 Draft state re-upload (no ceremony)

If the master BOM is currently in `draft` state (never been validated, no downstream effects), re-upload skips the confirmation modal. Simple replace with minor audit entry. No reason required (nothing to invalidate).

---

## 6. Flow — Bucket flush pipeline (Purchasing v4.1)

Unchanged from v1.5. The atomic pipeline from bucket-timer-fire to sheet-row-written. Any step failure → whole batch stays Pending.

### 6.1 Trigger

- **Timer expiration** — Critical or Main stream's Admin-configured interval elapses.
- **Admin manual flush** — `flushBucket(stream)` action with audit reason.

### 6.2 Pipeline (atomic — all-or-nothing)

```
Step 1: SELECT bucket entries where bucketState IN (QUEUED_MAIN, QUEUED_CRITICAL)
        WHERE stream matches
        GROUP BY supplier target (Mouser vs DigiKey)
        ↓
Step 2: FOR EACH supplier group:
            IF Mouser group:
                Build cart via Mouser Cart API:
                    add_items_to_cart with each line carrying:
                        - MPN, quantity, supplier SKU
                        - customer reference field = CPN (issuance table)
                Retrieve cart URL
            IF DigiKey group:
                Create list via DigiKey MyLists API:
                    create_list, then add_parts_to_list with each line carrying:
                        - MPN, quantity, supplier SKU
                        - reference field = CPN
                Retrieve list URL
        ↓
Step 3: FOR EACH supplier group:
            Write row to Josh's Daily Purchasing List via Microsoft Graph OneDrive API:
                (12 columns per Purchasing v4.1 Section 4.2)
        ↓
Step 4: Update state:
            batch.state = WRITTEN
            batch.cartUrls = { mouser?, digikey? }
            batch.writtenAt = now
            FOR EACH bucket entry in batch:
                bucketState = WRITTEN
                writtenTo = batch.id
```

### 6.3 Failure modes and recovery

Unchanged from v1.5.

### 6.4 CPN traceability chain

Unchanged from v1.5.

---

## 7. Flow — Receiving (Inventory v3.1 Cases A-E)

Unchanged from v1.5. Physical bag arrives → AutoBOM decides routing → PartsBox executes stock write.

### 7.1 Scan and parse

```
User scans distributor QR/barcode on the receiving screen
    ↓
PartsBox native scanning parses the barcode
    ↓
Parse returns: { mpn, manufacturer, quantity, distributorSku, cpn }
```

**PartsBox owns scanning. Distributor barcode APIs are NOT called during receiving.**

### 7.2 CPN cross-reference and case selection

Unchanged from v1.5.

### 7.3 Case matrix

Unchanged from v1.5.

### 7.4 B2-Guarded creation sub-flow

Unchanged from v1.5.

### 7.5 Post-scan state update

Unchanged from v1.5.

---

## 8. Flow — Build execution (Chapter B locked model)

**Retired from v1.5:** Variant declaration diff-and-propagate. Different-new propagation. Variant CSV upload as separate flow.

**Locked in v1.5.1:** Build creation is master BOM + per-line overlay only. No file uploads at Build time. No diff operations. Different-in-variant scenarios flow through Push-Back with `missing-component` reason.

### 8.1 Build creation

```
Production opens Create Build on Project detail
    ↓
Production enters: build name, build quantity, notes
    ↓
Production clicks through master BOM setting per-line overlay:
    - used   (default — this Build consumes this line from project box)
    - skipped   (this Build omits this line)
    - deferred   (this Build defers this line — will be added later via rework)
    - rework   (this Build uses a different component realtime)
        Substitute component: MPN + mfr + qty entered here
        rework_type: realtime | post_hoc
        optional Development wall ticket ID
    ↓
Production submits Build creation
    ↓
Platform runs coverage check:
    - "used" lines: check qty available in project box
    - "skipped" lines: skip coverage check
    - "deferred" lines: skip coverage check
    - "rework" lines: check qty available at substitute component's source (project box or wall)
    ↓
Build enters draft state
Coverage indicators render per line (green / amber / red)
```

### 8.2 Missing-component during Build (flows through Push-Back)

```
Production realizes during Build creation that they need a component the master BOM doesn't have
(e.g., "we need a decoupling cap that wasn't on the BOM")
    ↓
Production cancels Build creation, returns to master BOM screen
    ↓
Production sends structured Push-Back with reason = 'missing-component'
    ↓
Push-Back flow (Section 3) runs to completion:
    Designer picks component → recommends → Production applies → master BOM version increments
    ↓
Production returns to Build creation on the new master BOM version
    ↓
The added component appears as a new line with default 'used' overlay
```

**Rationale:** Silent auto-propagation is retired. Every new-to-the-master component goes through Push-Back so Designer sees the addition. Preserves role separation and traceability.

### 8.3 Run Build

```
Production clicks Run Build on Build detail
    ↓
Gating checks:
    - Any unresolved Push-Back on master BOM? → BLOCKED unless Admin force-waive
    - Any "used" line with red coverage? → BLOCKED unless per-line waiver with reason
    - Any "used" line with amber coverage? → prompt for waiver (Continue with reason | Cancel)
    ↓
If all gates pass:
    ↓
PartsBox build/create called with consumption plan:
    - For each "used" line: consume from project box (qty * buildQty)
    - For each "skipped" line: no consumption
    - For each "deferred" line: no consumption
    - For each "rework" line: consume the substitute component from its source
    ↓
PartsBox executes stock deductions across locations
    ↓
On success: Build result screen renders
```

### 8.4 QR delivery on Build result

```
build/create succeeded
    ↓
AutoBOM calls PartsBox ID Anything™ QR image endpoint
    with Build's PartsBox reference
    ↓
Response: image (Content-Type: image/*)
    ↓
Build result screen renders QR inline
    ↓
Actions available: Print, Download, Copy Build ID
    ↓
Fallback if endpoint unreachable:
    "Open Build in PartsBox" link
```

**Do NOT build a QR generator in AutoBOM. Leverage PartsBox ID Anything.**

---

## 9. Flow — Datasheet lifecycle

Unchanged from v1.5, with expanded trigger list:

### 9.1 Display (no persistence)

Supplier result cards display datasheet link inline when Mouser or DigiKey API returns a non-null URL.

### 9.2 Persistence triggers (on user-action only)

The following user actions trigger the download-and-attach sub-flow:

- **Push-Back resolution** — Designer clicks Recommend this replacement on a supplier result card
- **Push-Back application** — Production clicks Apply on a Push-Back with recommendations
- **Collection add** — Designer clicks Add for a candidate in the Add Part drawer
- **Request submission** — At submit time, any Collection items lacking a PartsBox-attached datasheet trigger fetch
- **B2-Guarded auto-creation** — sourcing engine validates MPN and auto-creates the PartsBox part
- **Production inline-edit silent swap** — new MPN's datasheet attached if not present
- **Production override commit** — same

### 9.3 Download-and-attach sub-flow

Unchanged.

### 9.4 Self-healing coverage

Unchanged.

### 9.5 Display preference

Unchanged.

---

## 10. Flow — Notification routing

Notification record shape updated with new types.

### 10.1 Notification record shape

```
notification: {
    id, when, kind: ACTION_REQUIRED | FYI,
    actionLabel: string,
    verb: Resolve | Apply | Respond | Review | Validate | Investigate | Track | Retry | Reassign | Refresh | View,
    sourceRole, sourceObject: { type, id, name },
    targetRole,
    routes: {
        designer?: route,
        production?: route,
        admin?: route
    }
}
```

### 10.2 Resolve route on click

Unchanged.

### 10.3 Multi-role auto-switch

Unchanged.

### 10.4 Notification consumers by role — updated for v1.5.1

| Notification kind | Designer receives | Production receives | Admin receives |
|---|---|---|---|
| BOM EXCEPTION (Push-Back submitted) | ✓ (target) | — | — |
| REPLACEMENTS RECOMMENDED (Designer resolved Push-Back) | — | ✓ (target) | — |
| RECOMMENDATIONS APPLIED (Production applied recommendations, FYI to Designer) | ✓ (resolver, FYI) | — | — |
| EQUIVALENT SWAP FYI (Production silent characteristic-match swap on Program-linked Project) | ✓ (Program owner, FYI, per Program config) | — | — |
| OVERRIDE COMMIT (Production characteristic-match override with reason) | ✓ (Program owner, always) | — | — |
| RE-UPLOAD CANCELLATION (Model B re-upload cancelled Push-Back) | ✓ (resolver, if applicable) | — | — |
| BATCH FLUSH FAILURE | — | — | ✓ |
| STUCK WORKFLOW >48H | — | — | ✓ |
| FAILED JOB | — | — | ✓ |
| DIGIKEY TOKEN EXPIRING | — | — | ✓ |
| UNRECOGNIZED CPN AT RECEIVING | — | — | ✓ |
| LOW STOCK CROSSING | — | ✓ (project owner) | — |
| RECEIVING SUCCESS INTO PROJECT BOX | — | ✓ (project owner, FYI) | — |
| BUILD EXECUTION RESULT | — | ✓ (initiator) | — |
| BATCH WRITTEN (FYI to requester) | ✓ or — | ✓ or — | — |

**Purchasing role receives no notifications** — Purchasing is not a role.

---

## 11. State transition summary

Every stateful object with its allowed transitions.

### 11.1 BOM

```
draft → validated → sourcing → results → normalised → submitted
                                 ↓            ↑
                              exceptions   (via Push-Back recommendation applied)

Model B re-upload from any state → draft
Production inline-edit (metadata) → minor version bump, state stays
Production inline-edit (silent match) → major version bump, state stays
Production inline-edit (override commit) → major version bump, state stays
```

### 11.2 Request (bucket entry)

Unchanged from v1.5:

```
(created) → QUEUED_MAIN or QUEUED_CRITICAL → WRITTEN → PURCHASED or PROCESSED
```

Plus new state from Model B re-upload:
- `flagged_for_review` — Model B re-upload while this Request was in-flight; Admin/Production needs to review.

### 11.3 Batch (flush unit)

Unchanged from v1.5.

### 11.4 Build

Unchanged from v1.5:

```
draft → ready → running → complete or failed
```

### 11.5 Push-Back

```
(created) → open → recommendations_sent → applied
              ↓            ↓
            deferred    rejected (goes back to open)
              ↓
            withdrawn (by Production before Designer resolves)
            cancelled_by_reupload (via Model B ceremony)
```

`recommendations_sent` is a NEW state (v1.5.1) — Designer has produced recommendations but Production hasn't applied yet.
`applied` is the terminal success state — Production has committed the recommendations to the master BOM.

### 11.6 CPN issuance record

Unchanged from v1.5.

---

## 12. Cross-flow invariants

Constraints that MUST hold across all flows. Enforced by decision engine or validation layer.

### 12.1 Sourcing engine gates

Unchanged from v1.5.

### 12.2 Purchasing gates

Unchanged from v1.5.

### 12.3 Inventory gates

Unchanged from v1.5.

### 12.4 Push-Back gates — updated for v1.5.1

- Push-Back submission requires reason + urgency + (at least one flagged line OR an addedComponentRequest).
- Push-Back resolution requires Designer to attach a recommendation on each flagged line (or the addedComponentRequest for missing-component).
- **Push-Back application requires Production explicit click Apply.** No auto-apply, no silent commit.
- Master BOM version does NOT increment on Designer resolution — only on Production application.
- Master BOM state stays in `exceptions` until application.
- Run Build blocked while any Push-Back is unresolved OR in `recommendations_sent` state (until Production applies).
- Program-linked Push-Back respects escalation window before entering unassigned pool.

### 12.5 Build gates — updated for v1.5.1

- Build cannot be created without a master BOM in `results` or `normalised` state.
- Build execution requires all coverage-check gates to pass OR waivers with reasons.
- **Variant declaration diff-and-propagate is retired.** Build creation directly sets per-line overlay; no separate variant file.
- **"Different-new" scenarios go through Push-Back with `missing-component` reason** before Build creation resumes.
- QR delivery is best-effort; missing QR does not fail the build.

### 12.6 Master BOM immutability gates (NEW in v1.5.1)

- Master BOM structural changes (MPN, manufacturer, add/remove line) come from three paths ONLY: Production inline-edit with characteristic-match, Production applies Push-Back recommendation, Model B re-upload.
- Non-structural fields (line note, description, designator text) are freely editable inline by Production.
- Designer NEVER writes directly to master BOM. Designer writes to pushback.recommendation objects; Production applies.
- Characteristic-match check gate:
  - Match on all critical characteristics (package, nominal, tolerance ≥, voltage ≥, temp ≥) → silent swap allowed
  - Mismatch on any → soft flag with Send to Designer / Continue as override / Cancel
- Override commit requires manual audit reason (≥10 chars).
- Silent swaps always audit-log the delta.

### 12.7 Admin authority gates

Unchanged from v1.5.

---

## 13. What this document doesn't cover

- **Detailed API request/response schemas** — see `AutoBOM_API_Responsibility_Map.md`.
- **Service topology and decision engine internals** — see `AutoBOM_Platform_Architecture.md`.
- **Code file responsibilities and integration surface** — see `AutoBOM_Code_to_Service_Connections.md`.
- **UI patterns and design conventions** — see Master Design Contract v1.5.1.
- **Per-role capability grid** — see Permissions Matrix v1.5.
- **Rejection criteria enforcement details** — see each module package (Purchasing v4.1, Inventory v3.1, Designer Alignment v1.1.1, Production Alignment v1.1.1).
