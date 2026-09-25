# AutoBOM Operator Guide

Audience: a teammate using AutoBOM day-to-day, not the developer.

## Run BOM

1. Upload your BOM as CSV or XLSX.
2. Enter a build quantity and a PartsBox project name (project/storage
   names are shared -- AutoBOM creates or reuses a same-name PartsBox
   project + storage location, tagged `production`).
3. Choose which suppliers to source against (Mouser/DigiKey) and whether
   to create a Mouser cart / DigiKey MyList automatically as part of this
   run, then click **Run BOM Automation**.
4. Review the messages/warnings, then scroll down to **Results**:
   - Summary metrics (Total Parts / PartsBox / Mouser / DigiKey / Needs
     Review).
   - **All Results**: search and filter the processed BOM.
   - **Needs Review**: parts that couldn't be automatically sourced.

## Needs Review

For each item needing review:

1. **Retry Exact Part** -- re-attempts the same MPN/manufacturer lookup.
   Use this first if you suspect a transient API issue.
2. **Find Replacement** -- opens the same search used by Component
   Search, prefilled with what AutoBOM already knows about the part.
   Search Mouser/DigiKey, review candidates, and select one. AutoBOM
   updates the BOM row and re-runs sourcing for it automatically.
3. **Check PartsBox** -- last-resort fallback lookup against PartsBox
   inventory, for when no purchasable replacement is available.

Approving a replacement is always your decision -- AutoBOM will not
silently substitute a part.

## Component Search

A general-purpose search independent of any specific BOM run. PartsBox is
searched by default; enable Mouser/DigiKey to include live supplier
results. Use the dynamic filters (only shown when the current results
actually have that data) to narrow by category, package, and parametric
ranges (voltage, tolerance, etc.).

## PartsBox Inventory

A read-only view over PartsBox itself (PartsBox remains the system of
record). Search or click **Browse All** with an empty query. Storage
Locations shows which storage locations carry the `production` tag.

## Purchasing

1. Purchasing status reflects the **current** BOM state, derived per
   supplier:
   - **Ready for Handoff**: every supplier that actually has items to buy
     has a current cart/MyList.
   - **Stale — BOM Changed**: a Needs Review action changed the BOM since
     purchasing artifacts were generated -- regenerate before handing off.
   - **Needs Review**: resolve remaining Needs Review items first.
   - **Partial — Generation Failed** / **Generation Failed**: one or both
     suppliers' cart/MyList creation failed -- see the error(s) shown, and
     retry. A supplier that already succeeded will NOT be recreated by a
     retry; only the failed one is retried.
   - **Not Required**: a supplier with zero sourced items for it never
     blocks readiness.
2. Click **Regenerate Purchasing** to (re)create what's needed from the
   current BOM. This is the ONLY action that can create a live Mouser
   cart or DigiKey MyList -- navigating, filtering, or just leaving the
   page open never does.
3. **Mouser**: cart creation is automatic; sharing with purchasing is a
   manual step for now -- open Mouser yourself, use its Share action, and
   hand the resulting Access ID directly to purchasing. Nothing needs to
   be pasted back into AutoBOM. Confirmed with Mouser: the Access ID is
   derived internally from the CartKey, but that derivation isn't
   currently exposed through any supported public/Automation Services
   API -- this is the current supported workflow, with a clean extension
   point for a future supported Mouser sharing API/integration.
   AutoBOM's role ends at handoff: checkout, payment, and order
   submission always happen manually, outside AutoBOM.
4. **DigiKey**: MyList creation is automatic; hand the List ID to
   purchasing so they can locate it in DigiKey. Confirmed (2026-09-25,
   live): the MyLists API does not provide a separate share
   identifier/link -- the List ID is the identifier there is.

## Downloads (Run BOM and Purchasing pages)

Each output file (cleaned CSV, cleaned workbook, sourcing report, DigiKey
list CSV, PartsBox import/unmatched CSVs, run summary) tracks its own
freshness. A file is disabled for download when it's stale (the BOM
changed since it was generated) or when its last generation attempt
failed -- **other files being current does not re-enable it**. Two files
(the multi-sheet cleaned workbook and the PartsBox unmatched CSV) are
never automatically regenerated after a BOM change; re-run BOM Automation
if you need a current copy of either.

## What NOT to do

- Don't click **Regenerate Purchasing** repeatedly "just in case" --
  it's a no-op for anything already current, but each attempt for a
  failed/stale supplier does make a live vendor call.
- Don't treat a disabled download as a bug -- it means that specific file
  doesn't match the current BOM; regenerate or re-run instead.
- Don't manually edit files under `runs/` -- they're per-run scratch
  space and may be cleaned up automatically (see the deployment guide's
  retention policy).
- Don't paste a Mouser or DigiKey secret/token into any AutoBOM field --
  none of AutoBOM's own UI ever asks for one.
