# AutoBOM — Post-Demo Hardening Backlog

**Status:** logged, not started. Nothing here is built.
**Created:** 2026-07-21 (night before the Wednesday demo)
**Working rule:** each item is its own branch, with tests. Deliberate, one at a
time — not a sweep. Nothing on this list is a demo blocker.

Source: the read-only pre-demo audit (findings A–E), plus two items Aaron
specified afterwards. Recorded here because the audit was delivered in
conversation and would otherwise be lost.

---

## Suggested order

`A-sweep → E1 → B → (1) → C1/C2 → D → (2)`

A/E first (credential + irreversible-stock safety), then B because item 1
depends on it, then the measurable performance wins, then cleanup. The launcher
(item 2) is independent and can be pulled forward whenever it's useful.

---

## ✅ Already closed (not backlog — recorded for context)

**A1 · A2 · A3 — supplier API key leaking through exception strings.**
Closed in `0fa200f`. Mouser passes its key in the query string, so a
network-level `requests` failure stringifies with the key embedded. Four sites
passed the raw exception through: `api/suppliers.py`, `api/sourcing.py` (SSE),
`services/bucket_flush.py`, and `supplier_base.py`'s own retry log.
`scrub_secrets()` now covers all four. Verified against a real network failure
on both the response body and the log file.

---

## New items (specified post-audit)

### 1. Live dry-run/live write-mode toggle — CLI control panel

Switch **write-mode** on the **running** stack, no restart.

- **Scope is write-mode only.** This has nothing to do with dev-vs-production
  environment mode. It governs one question: does the next write actually hit
  the supplier / PartsBox / Graph, or is it a preview?
- **Prereq: audit item B below.** The five gates must first route through
  `settings` and be **re-read at call time**. Today each client freezes its
  flag in `__init__`, so a running process cannot be re-gated at all — this was
  hit for real during the Phase 4 live-flush rehearsal, which needed a restart.
- **The panel must reflect ACTUAL runtime behavior.** Flip to live → the very
  next supplier/PartsBox call is genuinely live. A display that can disagree
  with what the code does is worse than no display.
- Switching **to live requires confirmation**. Startup always begins in
  dry-run. **Every flip is audit-logged** (actor, from→to, timestamp).
- One branch, tested. Tests must assert the toggle changes real call behavior,
  not just a displayed value.

### 2. One-command launcher — setup + run

PowerShell script at the repo root. On any machine: **clone → drop in `.env` →
one command → running.**

Must do, in order:
1. Preflight Python / Node / Postgres — **report clearly if missing**
2. Verify `.env` is present
3. Build venv + install backend deps
4. Install frontend deps
5. Migrate + seed
6. Free ports 8000 / 3000
7. Start both servers
8. Wait for health
9. Open the browser

**Explicitly cannot** create `.env` or install OS-level prerequisites — it
checks for those and reports. **Must not fail cryptically**; a missing
prerequisite should produce a plain sentence saying what to install.

*Real failure modes already hit this session, worth encoding:* npm 11 blocking
esbuild's postinstall (needs `node node_modules/esbuild/install.js`); orphaned
uvicorn `multiprocessing-fork` children holding port 8000 that survive killing
the parent; `uvicorn app.factory:app` being the ASGI path while `main.py` is
only a launcher.

---

## Audit items (from the pre-demo read-only review)

### A-sweep · Full leak-surface audit
A1/A2/A3 closed the four known instances of one bug. A deliberate sweep for a
**fifth** surface was explicitly deferred rather than done ad hoc. Check every
path where an exception, URL, or payload can reach a response body, a log, the
purchasing sheet, or the browser.

### B · Dry-run gating is five switches, not one
`FLUSH_MODE` was introduced as *the* switch but governs only the flush path.
Five gates are read independently via raw `os.getenv`, bypassing `settings`:

| Gate | Default | `.env` at time of audit |
|---|---|---|
| `SUPPLIER_DRY_RUN` | true | **false** |
| `MOUSER_CART_DRY_RUN` | true | **false** |
| `DIGIKEY_MYLISTS_ENABLED` | false | true |
| `PARTSBOX_DRY_RUN` | true | true |
| `FLUSH_MODE` | dry_run | *absent — implicit default* |

- Any path constructing a client directly, without the orchestrator overriding
  `client.dry_run`, is **live regardless of `FLUSH_MODE`**. `bucket_flush` does
  override correctly; nothing forces others to.
- Flags freeze in `__init__` → no runtime re-gating (blocks item 1).
- `FLUSH_MODE` isn't in `.env`; posture rests on a code default.

*Verified safe:* `/api/purchasing/cart/preview` uses pure builder functions —
no client, no HTTP.

### C · Performance & caching (measured)

- **C1 — `/api/inventory` = 7.08s cold, 5.52s repeat.** Every call refetches all
  3121 PartsBox parts. `_load_cache()` is a failure-fallback only and has **no
  TTL check**. CLAUDE.md specifies *"Cache-with-TTL: 60s default,
  Admin-configurable, refresh-on-write."* Biggest latency in the app.
- **C2 — app-wide search bypasses `SupplierLookupCache` entirely.** It is wired
  into `sourcing_engine`/`sourcing_runner` but **not** `/api/suppliers/search`.
  With live-on-keystroke search against a ~1000/day cap, biggest quota risk.
- **C3 —** cache TTLs are env-only, not in the `configuration` table, despite
  Bounded Admin calling for Admin-tunable TTL.
- **C4 —** `_num_id` / `_next_batch_id` / `_next_build_id` load **every id in
  the table** and regex them per insert. O(n) per write, and racy: two
  concurrent inserts can compute the same id.

*Measured fine:* bootstrap at 0.06s — no N+1 problem in practice.

### D · Dead / redundant pathways

- **D1 —** `create_project_partsbox` returns a synthetic `PB-<ID>` ref and
  **never persists it**. Looks like it establishes PartsBox linkage; doesn't.
  This is the gap that forced the Build endpoint to refuse to guess a box.
- **D2 —** four near-identical project-name helpers (`projName` ×2,
  `projNameProd`, canonical `projectName`). Consolidate on the canonical one.
- **D3 —** `screen_embedded.jsx` comment claims "sigil format"; `cpnFor`
  actually emits the correct continuous-identifier chain. Comment only.
- **D4 —** CPN is still generated **client-side** in `data.jsx`, against the
  locked *"ONE service, in ONE place"* rule (expected — the CPN service is
  deferred). Its wall branch emits a location-based `A-3-7-001`, which is not
  the Program→Project chain.
- **D5 —** CLAUDE.md's tree lists `docs/README.md` as the documentation index;
  the file does not exist.

### E · Hardening

- **E1 — Builds have no idempotency key.** A double-click or client retry could
  **double-consume real stock**. Highest-value item now that a stock-consuming
  endpoint exists.
- **E2 —** `_resolve_partsbox_project` falls back to matching by **project
  name**. Guarded and fails closed, but name-matching to decide which box to
  drain is fuzzy for an irreversible action.
- **E3 —** DigiKey refresh-token rotation writes to `.env`; a lock and a
  fingerprinted cross-process cache exist, but two processes writing `.env` is
  still last-writer-wins.

> **E1 + E2 + D1 are really one work item:** real, persisted project↔PartsBox-box
> linkage. There is no `Project.partsbox_ref` column today.

---

## Receiving — its own spec pass, not an extension of `stock/add`

Logged, deliberately **not** designed yet. The prototype's Receiving screen is a
labelled shell (*"Full receiving flow … arrives in the Inventory Activation
build"*), and `stock/add` alone is not the feature.

What it needs to be — a **reconciliation engine** that:
- tracks what was sent out,
- knows what is expected in,
- knows the destination project box **and storage location per part**,
- matches a scan against expected incoming and checks it off,
- maintains **cross-project state**, so another project using the same part
  doesn't re-add what was already received here.

That is a designed engine on top of `stock/add`, and it gets specced properly
post-demo. Existing constraints still bind: PartsBox owns scanning; distributor
barcode APIs are never called during receiving.
