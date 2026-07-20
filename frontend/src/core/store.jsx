/* global React, seedState, uid, line, CATALOG */
/* AutoBOM — shared workflow store. A single connected state with actions that
   mutate global state and propagate notifications + audit across every role. */
const { useSyncExternalStore } = React;

/* Phase 3: the store is now a client cache over the real backend. STATE starts
   empty and is hydrated from GET /api/bootstrap after login. Auth goes through
   the real /api/auth/* endpoints (session cookie); the client-side seed login is
   gone. In dev mode the backend login is the seed-email path (3 role users). */
function emptyState() {
  return {
    authed: false, currentUserId: null, activeRole: 'designer', booting: true,
    users: [], projects: {}, collections: [], boms: [], requests: [], programs: [],
    inventory: [], notifications: [], audit: [], suppliers: [],
    system: { status: [], workflow: {}, settings: {}, batch: { main: {}, critical: {} }, jobs: [], stuck: [] },
    investigations: [], recommendations: [], reworks: [], firmwares: [],
    comments: {}, datasheets: {}, seq: { req: 100, po: 3000, bom: 100, col: 100, inv: 100, rec: 100 },
  };
}

let STATE = emptyState();

const listeners = new Set();
function emit() { STATE = { ...STATE }; listeners.forEach(l => l()); }
function subscribe(l) { listeners.add(l); return () => listeners.delete(l); }
function getState() { return STATE; }

const actorName = () => (STATE.users.find(u => u.id === STATE.currentUserId) || {}).name || 'You';

function landingRoleFor(user) {
  const roles = (user && user.roles) || [];
  if (user && user.primaryRole && roles.includes(user.primaryRole)) return user.primaryRole;
  return roles[0] || 'designer';
}

/* Merge the backend bootstrap slices into STATE (single source of truth). */
function applyBootstrap(data) {
  Object.assign(STATE, data);
}

/* Load the session user's authorized slice and mark authed. */
async function hydrateSession(user) {
  const data = await window.api.get('/bootstrap');
  applyBootstrap(data);
  STATE.authed = true;
  STATE.booting = false;
  STATE.currentUserId = user.id;
  STATE.activeRole = user.activeRole || landingRoleFor(user);
  emit();
}

/* On load, restore an existing session (valid cookie) if any. */
async function boot() {
  try {
    const me = await window.api.get('/auth/me');   // { user, auth_mode }
    if (me && me.user) { await hydrateSession(me.user); return; }
  } catch (e) { /* backend unreachable -> show login */ }
  STATE.booting = false; emit();
}

function pushNotif(n) {
  // Derive the new-shape fields when callers haven't set them yet.
  // This keeps existing call sites working while new ones can pass routes{} + actionLabel + verb directly.
  const v = (n.verb || 'View').trim();
  const isFyi = n.kind === 'fyi' || /^(view|track|open)/i.test(v);
  const forRoles = n.forRoles || (n.routes ? Object.keys(n.routes) : []);
  const sourceRole = n.sourceRole || n.actorRole || null;
  // Resolver-ready destination per role. If caller gave routes{}, trust it;
  // otherwise fall back to the legacy single `go` for every forRoles member.
  const routes = n.routes || (n.go ? Object.fromEntries(forRoles.map(r => [r, n.go])) : {});
  const targetRole = n.targetRole || forRoles[0] || null;
  STATE.notifications = [{
    id: uid('n'), group: 'Today', unread: true, when: 'just now',
    kind: isFyi ? 'fyi' : 'action', actionLabel: n.actionLabel || null,
    sourceRole, targetRole, routes, ...n,
  }, ...STATE.notifications];
}

/* Resolve where a clicked notification should take the viewer.
   Spec: route to where THE USER can act, in THEIR workspace — never the originator.
   - Prefer the route keyed by the user's currently-active role.
   - Else, if the user holds the targetRole, return that route + switchTo so the
     app can switch context with a sticky "Switched to X" banner (Option A).
   - Else, return any route the user can reach (any role they hold), no switch.
   - Else (no role match — happens for FYI notifs the user shouldn't see), pick
     the first route as a last resort and don't switch.

   Returns { route, switchTo } where switchTo is the role to switch TO (or null). */
function resolveNotificationRoute(notif, user, activeRole) {
  const routes = (notif && notif.routes) || {};
  const userRoles = (user && user.roles) || [];
  // 1. Currently-active role wins outright.
  if (routes[activeRole]) return { route: routes[activeRole], switchTo: null };
  // 2. Target role the user actually holds → auto-switch.
  if (notif.targetRole && userRoles.includes(notif.targetRole) && routes[notif.targetRole])
    return { route: routes[notif.targetRole], switchTo: notif.targetRole };
  // 3. Any other role the user holds.
  for (const r of userRoles) if (routes[r]) return { route: routes[r], switchTo: r };
  // 4. Last resort.
  const k = Object.keys(routes)[0];
  return k ? { route: routes[k], switchTo: null } : { route: { screen: 'notifications' }, switchTo: null };
}
function pushAudit(a) {
  const ts = 'Today ' + new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
  STATE.audit = [{ id: uid('au'), ts, user: actorName(), role: STATE.activeRole, ...a }, ...STATE.audit];
}

const sum = (items, sup) => items.filter(i => i.supplier === sup).reduce((a, i) => a + (i.ext || 0), 0);
const grand = (items) => items.reduce((a, i) => a + (i.ext || 0), 0);

/* ---------------- ACTIONS ---------------- */
const ROLE_PREFIX = { designer: 'd', production: 'p', purchasing: 'b', development: 'v', admin: 'a' };
const actions = {
  /* Real backend auth (dev mode = seed-email login for the 3 role users). */
  async logIn(email) {
    const e = (email || '').trim();
    if (!e) return { ok: false, error: 'Enter your work email.' };
    try {
      const user = await window.api.post('/auth/login', { email: e });
      await hydrateSession(user);
      return { ok: true };
    } catch (err) {
      return { ok: false, error: (err && err.message) || 'Login failed.' };
    }
  },
  async logOut() {
    try { await window.api.post('/auth/logout', {}); } catch (err) {}
    STATE = emptyState();
    STATE.booting = false;
    emit();
  },
  /* Role switcher — scoped to roles the logged-in user actually holds. */
  async setRole(role) {
    const u = STATE.users.find(x => x.id === STATE.currentUserId);
    if (u && u.roles && !u.roles.includes(role)) return;
    try {
      const user = await window.api.post('/auth/role', { role });
      STATE.activeRole = (user && user.activeRole) || role;
    } catch (err) {
      STATE.activeRole = role;
    }
    emit();
  },

  /* Apply the authoritative sourced BOM returned by the live sourcing stream. */
  applySourcingResult(bom) {
    if (!bom || !bom.id) return;
    STATE.boms = STATE.boms.map(b => (b.id === bom.id ? bom : b));
    emit();
  },
  /* Re-read a single BOM from the backend (used after apply/version bumps so the
     UI shows the new version, not stale state). */
  async refetchBom(bomId) {
    try {
      const bom = await window.api.get('/boms/' + bomId);
      if (bom && bom.id) { STATE.boms = STATE.boms.map(b => (b.id === bom.id ? bom : b)); emit(); }
    } catch (e) {}
  },
  /* Real BOM upload — the user's file bytes go to the server, bom_cleaner parses
     them, and a real BOM comes back. Throws on error (screen surfaces it). */
  async uploadBom(file, meta) {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('project_id', meta.project);
    fd.append('name', meta.name);
    fd.append('build_qty', String(meta.buildQty));
    fd.append('overage', String(meta.overage != null ? meta.overage : 10));
    const bom = await window.api.upload('/boms/upload', fd);
    STATE.boms = [bom, ...STATE.boms.filter(b => b.id !== bom.id)];
    emit();
    return bom;
  },

  /* DESIGNER */
  async addToCollection(mpn, collectionId) {
    if (!collectionId) return null;
    try {
      const c = CATALOG[mpn] || {};
      const col = await window.api.post('/collections/' + collectionId + '/items', { mpn, mfr: c.mfr, desc: c.desc, qty: 1 });
      STATE.collections = STATE.collections.map(x => x.id === col.id ? col : x); emit();
      return col;
    } catch (e) { return null; }
  },
  async updateQty(collectionId, no, qty) {
    try {
      const col = await window.api.patch('/collections/' + collectionId + '/items/' + no, { qty });
      STATE.collections = STATE.collections.map(x => x.id === col.id ? col : x); emit();
    } catch (e) {}
  },
  async requestToOrder(collectionId, note, critical) {
    try {
      const res = await window.api.post('/collections/' + collectionId + '/request-order', { note, critical: !!critical });
      STATE.collections = STATE.collections.map(x => x.id === res.collection.id ? res.collection : x);
      STATE.requests = [res.request, ...STATE.requests.filter(r => r.id !== res.request.id)];
      emit(); return res.request.id;
    } catch (e) { return null; }
  },
  /* Designer resolves a Push-Back — produces a RECOMMENDATION, never mutates the master BOM.
     Production applies it from their Dashboard (applyPushbackRecommendation). */
  async resolvePushback(bomId, { recommendations, note }) {
    const picks = (recommendations || []).map(r => ({ lineNo: r.lineNo != null ? r.lineNo : null, added: !!r.added,
      mpn: r.candidate.mpn, mfr: r.candidate.mfr || '', desc: r.candidate.desc || '' }));
    try {
      const bom = await window.api.post('/boms/' + bomId + '/resolve-pushback', { recommendations: picks, note });
      STATE.boms = STATE.boms.map(b => b.id === bom.id ? bom : b); emit();
    } catch (e) {}
  },
  /* Production commits Designer's recommendation to the master BOM. The returned
     BOM is the NEW version (re-read from the authoritative server return, per the
     guardrail — Production sees the post-apply state, not stale). */
  async applyPushbackRecommendation(bomId) {
    try {
      const bom = await window.api.post('/boms/' + bomId + '/apply-recommendation', {});
      STATE.boms = STATE.boms.map(b => b.id === bom.id ? bom : b); emit();
    } catch (e) {}
  },
  /* Datasheet lifecycle — attach to PartsBox on user-action; skip if already attached.
     Background op; a real failure would surface to Admin diagnostics (not modelled here). */
  attachDatasheet(mpn, url) {
    if (!mpn || !url) return;
    STATE.datasheets = STATE.datasheets || {};
    if (STATE.datasheets[mpn]) return; // already attached
    STATE.datasheets[mpn] = url;
    pushAudit({ action: 'Datasheet attached to PartsBox', entity: mpn, before: '—', after: 'attachment/type=datasheet' });
  },
  /* Push-Back secondary paths (Production Alignment v1.1.1). */
  commentPushback(bomId, text) {
    const bom = STATE.boms.find(b => b.id === bomId); if (!bom || !bom.pushback) return;
    bom.pushback.comments = [...(bom.pushback.comments || []), { by: actorName(), when: 'just now', body: text }];
    pushAudit({ action: 'Push-Back comment', entity: bom.id, before: '—', after: text.slice(0, 60) });
    emit();
  },
  deferPushback(bomId, reason) {
    const bom = STATE.boms.find(b => b.id === bomId); if (!bom || !bom.pushback) return;
    bom.pushback.deferred = { by: actorName(), when: 'just now', reason };
    pushAudit({ action: 'Push-Back deferred', entity: bom.id, before: '—', after: reason.slice(0, 60) });
    emit();
  },
  reassignPushback(bomId, note) {
    const bom = STATE.boms.find(b => b.id === bomId); if (!bom || !bom.pushback) return;
    bom.pushback.reassignedNote = note;
    pushAudit({ action: 'Push-Back reassigned', entity: bom.id, before: '—', after: note.slice(0, 60) });
    emit();
  },
  /* PRODUCTION inline-edit (v4). Non-structural fields free-edit; structural MPN/mfr go
     through the characteristic-match check (commitEquivalentSwap on match, commitOverride
     after a mismatch the user chooses to override). */
  editBomLineField(bomId, no, field, value) {
    const bom = STATE.boms.find(b => b.id === bomId); if (!bom) return;
    bom.items = bom.items.map(i => i.no === no ? { ...i, [field]: value } : i);
    bom.updated = 'just now'; bom.updatedBy = actorName();
    pushAudit({ action: `BOM line ${no} ${field} edited`, entity: bom.id, before: '—', after: String(value).slice(0, 40) });
    emit();
  },
  commitEquivalentSwap(bomId, no, newMpn, newMfr, delta) {
    const bom = STATE.boms.find(b => b.id === bomId); if (!bom) return;
    let oldMpn = '';
    bom.items = bom.items.map(i => { if (i.no !== no) return i; oldMpn = i.mpn; const c = CATALOG[newMpn] || {}; return { ...i, mpn: newMpn, mfr: newMfr || c.mfr || i.mfr, desc: c.desc || i.desc, replacement: { from: i.mpn, by: actorName() } }; });
    bom.version = (bom.version || 1) + 1; bom.updated = 'just now'; bom.updatedBy = actorName();
    pushAudit({ action: `Characteristic-match equivalent swap: ${oldMpn} → ${newMpn}${delta ? ' · ' + delta : ''}`, entity: bom.id, before: oldMpn, after: newMpn });
    actions._fyiEquivalentSwap(bom, oldMpn, newMpn, false);
    emit();
  },
  commitOverride(bomId, no, newMpn, newMfr, reason) {
    const bom = STATE.boms.find(b => b.id === bomId); if (!bom) return;
    let oldMpn = '';
    bom.items = bom.items.map(i => { if (i.no !== no) return i; oldMpn = i.mpn; const c = CATALOG[newMpn] || {}; return { ...i, mpn: newMpn, mfr: newMfr || c.mfr || i.mfr, desc: c.desc || i.desc, replacement: { from: i.mpn, by: actorName() } }; });
    bom.version = (bom.version || 1) + 1; bom.updated = 'just now'; bom.updatedBy = actorName();
    pushAudit({ action: `Characteristic-match OVERRIDE: ${oldMpn} → ${newMpn} — ${reason}`, entity: bom.id, before: oldMpn, after: newMpn });
    actions._fyiEquivalentSwap(bom, oldMpn, newMpn, true, reason);
    emit();
  },
  /* Send a mismatch to Designer as a structured Push-Back with the intended replacement as context. */
  pushbackFromEdit(bomId, no, newMpn, diffs) {
    const bom = STATE.boms.find(b => b.id === bomId); if (!bom) return;
    const item = bom.items.find(i => i.no === no) || {};
    actions.sendPushback(bomId, { lineNos: [no], reason: 'other', urgency: 'standard',
      note: `Production attempted an inline swap ${item.mpn} → ${newMpn}; characteristic-match failed on ${(diffs || []).join(', ')}. Please advise or recommend a replacement.`,
      perLineComments: { [no]: `Intended replacement: ${newMpn}` } });
  },
  _fyiEquivalentSwap(bom, oldMpn, newMpn, isOverride, reason) {
    const proj = STATE.projects[bom.project];
    const prog = proj && proj.program_id ? (STATE.programs || []).find(p => p.id === proj.program_id) : null;
    if (!prog) return;                                   // standalone Project → no Program owner Designer
    if (!isOverride && !prog.notifyOnEquivalentSwap) return; // Admin per-Program opt-out (equivalent swaps only)
    pushNotif({ forRoles: ['designer'], targetRole: 'designer', sourceRole: 'production', kind: 'fyi',
      type: isOverride ? 'CHARACTERISTIC OVERRIDE' : 'EQUIVALENT SWAP', actorRole: 'production',
      actionLabel: isOverride ? 'Override applied' : 'Equivalent swap', verb: 'View',
      body: isOverride
        ? `Production overrode characteristic-match on ${oldMpn} → ${newMpn} (${bom.name}), reason: ${reason}.`
        : `Production swapped ${oldMpn} → ${newMpn} on ${bom.name} — both spec-matched.`,
      who: actorName(), entity: bom.id,
      routes: { designer: { screen: 'p.bomOverview', id: bom.id }, production: { screen: 'p.bomOverview', id: bom.id } } });
  },
  setProgramNotify(programId, val) {
    const p = (STATE.programs || []).find(x => x.id === programId); if (!p) return;
    const before = !!p.notifyOnEquivalentSwap; p.notifyOnEquivalentSwap = !!val;
    pushAudit({ action: `Program FYI-on-equivalent-swap ${val ? 'enabled' : 'disabled'}`, entity: programId, before: String(before), after: String(!!val) });
    emit();
  },

  /* PRODUCTION */
  /* BOM creation is real file upload -> bom_cleaner (see uploadBom above). The
     simulated CATALOG-seeded createBom was removed in Phase 3. */
  completeSourcing(bomId) {
    const bom = STATE.boms.find(b => b.id === bomId); if (!bom) return;
    bom.items = bom.items.map((i, k) => i.status === 'needs-review' ? i : { ...i, status: k % 2 ? 'sourced-digikey' : 'sourced-mouser', supplier: k % 2 ? 'digikey' : 'mouser' });
    const hasEx = bom.items.some(i => i.status === 'needs-review');
    bom.state = 'results'; bom.updated = 'just now';
    pushAudit({ action: 'Sourcing run complete', entity: bom.id, before: 'SOURCING', after: hasEx ? 'RESULTS (exceptions)' : 'RESULTS' });
    emit();
  },
  async sendPushback(bomId, opts) {
    const { lineNos = [], reason = 'other', urgency = 'standard', note = '', addedComponentRequest = null } = opts || {};
    const bom = STATE.boms.find(b => b.id === bomId);
    const flaggedLines = lineNos.map(no => ({ lineNo: no, exReason: ((bom && bom.items.find(i => i.no === no)) || {}).exReason || 'Needs engineering review', comments: [] }));
    try {
      const updated = await window.api.post('/boms/' + bomId + '/pushback', { reason, urgency, note, flaggedLines, addedComponentRequest });
      STATE.boms = STATE.boms.map(b => b.id === updated.id ? updated : b); emit();
    } catch (e) {}
  },
  async createPackage(bomId) {
    // PartsBox project box is created with inventory wiring; record the ref for now.
    const bom = STATE.boms.find(b => b.id === bomId); if (bom) { bom.partsbox = 'PB-' + bom.id.replace('BOM-', ''); emit(); }
  },
  async submitBomToPurchasing(bomId, note, critical) {
    try {
      const res = await window.api.post('/boms/' + bomId + '/submit', { note, critical: !!critical });
      STATE.boms = STATE.boms.map(b => b.id === res.bom.id ? res.bom : b);
      STATE.requests = [res.request, ...STATE.requests.filter(r => r.id !== res.request.id)];
      emit(); return res.request.id;
    } catch (e) { return null; }
  },

  /* PURCHASING — order execution retired (v4). AutoBOM never places orders, approves
     requests, or tracks shipments. Requests flow straight into the shared purchasing
     bucket and batch to the Daily Purchasing List; a human places the order in the
     supplier's own UI. approveRequest / placeOrder / createShipment / setShipmentStatus /
     setOrderStep / _rollupRequest all removed. */

  /* DASHBOARD inline actions (v1.3-rev) — run from Needs Attention cards.
     Each mutates global state + writes audit/notifs exactly like the full-screen flow. */
  runBomSourcing(bomId) {
    // Inline 'Run sourcing' — mark sourced lines, leave needs-review flagged.
    const bom = STATE.boms.find(b => b.id === bomId); if (!bom) return;
    bom.items = bom.items.map((i, k) => (i.status === 'needs-review' || i.status === 'exception') ? i
      : { ...i, status: k % 2 ? 'sourced-digikey' : 'sourced-mouser', supplier: k % 2 ? 'digikey' : 'mouser', sourcedAt: Date.now() });
    const hasExc = bom.items.some(i => i.status === 'needs-review' || i.status === 'exception');
    bom.state = hasExc ? 'normalised' : 'results';
    bom.updated = 'just now'; bom.updatedBy = actorName();
    pushAudit({ action: 'Sourcing run (from dashboard)', entity: bom.id, before: 'VALIDATED', after: bom.state.toUpperCase() });
    emit();
  },
  resourceReplacedLines(bomId) {
    // Inline 'Re-source replaced lines' — clear needs-review on previously-flagged lines.
    const bom = STATE.boms.find(b => b.id === bomId); if (!bom) return;
    let n = 0;
    bom.items = bom.items.map((i, k) => {
      if (i.status === 'needs-review' || i.status === 'exception') { n++; return { ...i, status: k % 2 ? 'sourced-digikey' : 'sourced-mouser', supplier: k % 2 ? 'digikey' : 'mouser', sourcedAt: Date.now() }; }
      return i;
    });
    bom.state = 'results'; bom.updated = 'just now'; bom.updatedBy = actorName();
    pushAudit({ action: `Re-sourced ${n} replaced line${n === 1 ? '' : 's'} (from dashboard)`, entity: bom.id, before: 'NORMALISED', after: 'RESULTS' });
    emit();
  },
  recheckCollectionSourcing(cid) {
    // Inline 'Re-check sourcing' — refresh every stale item's timestamp.
    const c = STATE.collections.find(x => x.id === cid); if (!c) return;
    c.items = c.items.map(i => ({ ...i, stale: false, sourcedAt: Date.now() }));
    c.updated = 'just now'; c.updatedBy = actorName();
    pushAudit({ action: 'Sourcing re-checked (from dashboard)', entity: c.id, before: 'STALE', after: 'FRESH' });
    emit();
  },
  retryJob(jobId) {
    pushAudit({ action: 'Background job retried (from dashboard)', entity: jobId, before: 'FAILED', after: 'QUEUED' });
    if (STATE.system && STATE.system.jobs) STATE.system.jobs = STATE.system.jobs.filter(j => j.id !== jobId);
    emit();
  },
  reassignWorkflow(entityId, toName) {
    pushAudit({ action: `Workflow reassigned to ${toName} (from dashboard)`, entity: entityId, before: '—', after: toName });
    if (STATE.system && STATE.system.stuck) STATE.system.stuck = STATE.system.stuck.filter(s => s.id !== entityId);
    emit();
  },
  refreshDigiKeyToken() {
    const row = STATE.system?.status?.find(s => s.id === 'digikey');
    if (row) { row.state = 'green'; row.detail = 'Token refreshed · valid 24h'; row.tokenExpiry = null; }
    pushAudit({ action: 'DigiKey token refreshed (from dashboard)', entity: 'digikey-api', before: 'EXPIRING', after: 'VALID' });
    emit();
  },

  /* ADMIN */
  async setUserRoles(userId, roles) {
    try {
      const u = await window.api.patch('/users/' + userId, { roles });
      STATE.users = STATE.users.map(x => x.id === u.id ? u : x); emit();
    } catch (e) {}
  },
  async setUserOverrides(userId, overrides) {
    try {
      const u = await window.api.patch('/users/' + userId, { overrides });
      STATE.users = STATE.users.map(x => x.id === u.id ? u : x); emit();
    } catch (e) {}
  },
  async toggleUserActive(userId) {
    const cur = STATE.users.find(x => x.id === userId);
    try {
      const u = await window.api.patch('/users/' + userId, { active: !(cur && cur.active) });
      STATE.users = STATE.users.map(x => x.id === u.id ? u : x); emit();
    } catch (e) {}
  },
  inviteUser({ name, email, roles }) {
    // User invite (create) lands with the Admin write surface; no-op fallback avoided.
    console.warn('inviteUser: create-user endpoint not wired in this build');
  },
  async toggleSupplier(id) {
    const cur = STATE.suppliers.find(x => x.id === id);
    try {
      const s = await window.api.patch('/suppliers/' + id, { enabled: !(cur && cur.enabled) });
      STATE.suppliers = STATE.suppliers.map(x => x.id === s.id ? s : x); emit();
    } catch (e) {}
  },
  async setConfig(path, value) {
    const [grp, key] = path.split('.');
    if (STATE.system[grp]) { STATE.system[grp][key] = value; emit(); }   // optimistic UI mirror
    try { await window.api.patch('/config', { section: grp, key: grp, value: { [key]: value } }); } catch (e) {}
  },
  /* v2 bucket batching — Admin sets each stream's cadence; both are configurable, never hard-coded. */
  setBatchInterval(stream, min) {
    const b = STATE.system.batch[stream]; if (!b) return;
    const before = b.intervalMin;
    b.intervalMin = Math.max(5, min | 0);
    b.nextRunMin = Math.min(b.nextRunMin, b.intervalMin);
    pushAudit({ action: `${stream === 'critical' ? 'Critical' : 'Main'} batch interval changed`, entity: 'system-batch', before: `${before}m`, after: `${b.intervalMin}m` });
    emit();
  },
  flushBucket(stream) {
    const b = STATE.system.batch[stream]; if (!b) return;
    b.nextRunMin = 0; b.lastRun = 'just now';
    pushAudit({ action: `${stream === 'critical' ? 'Critical' : 'Main'} bucket flushed manually`, entity: 'system-batch', before: '—', after: 'FLUSHED' });
    emit();
    setTimeout(() => { b.nextRunMin = b.intervalMin; emit(); }, 50);
  },
  adminOverride(entity, after, reason) {
    pushAudit({ action: 'ADMIN OVERRIDE — ' + reason, entity, before: 'LOCKED', after });
    emit();
  },

  /* DEVELOPMENT */
  pushRecommendation(recId) {
    const r = STATE.recommendations.find(x => x.id === recId); if (!r) return;
    r.state = 'pushed'; r.pushedTo = { role: 'designer', toUserId: 'u-aaron', when: 'just now' }; r.updated = 'just now';
    pushNotif({ forRoles: ['designer'], type: 'IMPROVEMENT RECOMMENDATION', actorRole: 'development', body: `${actorName()} proposes “${r.title}”.`, who: actorName(), entity: r.id, verb: 'Review', go: { screen: 'v.recommendationDetail', id: r.id } });
    pushAudit({ action: 'Improvement Recommendation pushed to Designer', entity: r.id, before: 'DRAFT', after: 'AWAITING DESIGNER' });
    emit();
  },
  respondRecommendation(recId, decision, note) {
    const r = STATE.recommendations.find(x => x.id === recId); if (!r) return;
    r.state = decision === 'accepted' ? 'accepted' : decision === 'rejected' ? 'rejected' : 'investigating';
    r.response = { decision, by: actorName(), when: 'just now', note: note || '' };
    r.updated = 'just now';
    const TYPE = { accepted: 'RECOMMENDATION ACCEPTED', rejected: 'RECOMMENDATION REJECTED', investigating: 'RECOMMENDATION UNDER INVESTIGATION' }[decision];
    pushNotif({ forRoles: ['development'], type: TYPE, actorRole: STATE.activeRole, body: `${actorName()} ${decision} “${r.title}”.`, who: actorName(), entity: r.id, verb: 'View', reject: decision === 'rejected' ? (note || null) : null, go: { screen: 'v.recommendationDetail', id: r.id } });
    pushAudit({ action: `Recommendation ${decision}`, entity: r.id, before: 'AWAITING DESIGNER', after: decision.toUpperCase() });
    emit();
  },
  pushRework(rwkId) {
    const r = STATE.reworks.find(x => x.id === rwkId); if (!r) return;
    r.state = 'pushed'; r.pushedTo = { role: 'production', toUserId: 'u-maria', when: 'just now' }; r.updated = 'just now';
    pushNotif({ forRoles: ['production'], type: 'REWORK PACKAGE', actorRole: 'development', body: `${r.title} — ${r.boards || ''} units.`, who: actorName(), entity: r.id, verb: 'Open', go: { screen: 'v.reworkDetail', id: r.id } });
    pushAudit({ action: 'Rework Package pushed to Production', entity: r.id, before: 'DRAFT', after: 'AWAITING PRODUCTION' });
    emit();
  },
  returnRework(rwkId, note) {
    const r = STATE.reworks.find(x => x.id === rwkId); if (!r) return;
    r.state = 'returned'; r.results = { ...(r.results || {}), returnedBy: actorName(), returnedWhen: 'just now', note: note || '' };
    pushNotif({ forRoles: ['development'], type: 'REWORK RETURNED', actorRole: 'production', body: `${actorName()} returned ${r.title} with results.`, who: actorName(), entity: r.id, verb: 'View', go: { screen: 'v.reworkDetail', id: r.id } });
    pushAudit({ action: 'Rework returned to Development', entity: r.id, before: 'IN PROGRESS', after: 'RETURNED' });
    emit();
  },
  pushFirmware(fwId) {
    const f = STATE.firmwares.find(x => x.id === fwId); if (!f) return;
    f.state = 'validating'; f.pushedTo = { role: 'production', toUserId: 'u-maria', when: 'just now' }; f.updated = 'just now';
    pushNotif({ forRoles: ['production'], type: 'FIRMWARE FOR VALIDATION', actorRole: 'development', body: `${f.title} awaiting your validation.`, who: actorName(), entity: f.id, verb: 'Validate', go: { screen: 'v.firmwareDetail', id: f.id } });
    pushAudit({ action: 'Firmware Release pushed to Production', entity: f.id, before: 'RELEASED', after: 'VALIDATING' });
    emit();
  },
  validateFirmware(fwId, note) {
    const f = STATE.firmwares.find(x => x.id === fwId); if (!f) return;
    f.state = 'validated'; f.results = { by: actorName(), when: 'just now', note: note || '' };
    pushNotif({ forRoles: ['development'], type: 'FIRMWARE VALIDATED', actorRole: 'production', body: `${actorName()} validated ${f.title}.`, who: actorName(), entity: f.id, verb: 'View', go: { screen: 'v.firmwareDetail', id: f.id } });
    pushAudit({ action: 'Firmware validated', entity: f.id, before: 'VALIDATING', after: 'VALIDATED' });
    emit();
  },
  requestInvestigation(title, note) {
    // Production → Development
    const id = 'INV-0' + (STATE.seq.inv++);
    STATE.investigations = [{ id, title, kind: 'investigation', project: 'bldc', owner: 'Noah Park', ownerId: 'u-noah', role: 'development', assignee: 'Noah Park', state: 'open', updated: 'just now', created: 'Today', priority: 'medium', desc: note || '', relatedBom: null, relatedCollection: null, findings: [], pushedFrom: { role: STATE.activeRole, by: actorName(), when: 'just now', note: note || '' } }, ...STATE.investigations];
    pushNotif({ forRoles: ['development'], type: 'INVESTIGATION REQUESTED', actorRole: STATE.activeRole, body: `${actorName()} requested investigation: ${title}.`, who: actorName(), entity: id, verb: 'Open', go: { screen: 'v.investigationDetail', id } });
    pushAudit({ action: 'Investigation requested', entity: id, before: '—', after: 'OPEN' });
    emit(); return id;
  },
  closeInvestigation(invId, findings) {
    const i = STATE.investigations.find(x => x.id === invId); if (!i) return;
    i.state = 'findings'; i.findings = findings; i.updated = 'just now';
    if (i.pushedFrom) pushNotif({ forRoles: [i.pushedFrom.role], type: 'INVESTIGATION FINDINGS', actorRole: 'development', body: `Findings posted on ${i.id} — ${i.title}.`, who: actorName(), entity: i.id, verb: 'View', go: { screen: 'v.investigationDetail', id: i.id } });
    pushAudit({ action: 'Investigation findings posted', entity: i.id, before: 'ANALYSIS', after: 'FINDINGS' });
    emit();
  },

  /* DEVELOPMENT COLLECTIONS */
  createDevCollection({ name, project, category, desc }) {
    const id = 'DCOL-0' + String(STATE.seq.col++).padStart(2, '0');
    const c = { id, name, project, state: 'draft', role: 'development', creator: actorName(), ownerId: STATE.currentUserId,
      category: category || 'Investigation', updated: 'just now', updatedBy: actorName(), created: 'Today',
      desc: desc || '', outcomes: [], notes: '', items: [] };
    STATE.collections = [c, ...STATE.collections];
    pushAudit({ action: 'Development Collection created', entity: id, before: '—', after: 'DRAFT' });
    emit(); return id;
  },
  setDevCollectionState(cid, newState) {
    const c = STATE.collections.find(x => x.id === cid); if (!c) return;
    const before = (c.state || '').toUpperCase();
    c.state = newState; c.updated = 'just now'; c.updatedBy = actorName();
    pushAudit({ action: 'Development Collection state changed', entity: cid, before, after: newState.toUpperCase() });
    emit();
  },
  setDevItemNote(cid, no, note) {
    const c = STATE.collections.find(x => x.id === cid); if (!c) return;
    c.items = c.items.map(i => i.no === no ? { ...i, note } : i);
    c.updated = 'just now'; emit();
  },
  setDevCollectionNotes(cid, notes) {
    const c = STATE.collections.find(x => x.id === cid); if (!c) return;
    c.notes = notes; c.updated = 'just now'; emit();
  },
  /* generateOutcome — pick an outcome type, create the linked Dev object, push handshake, record outcome on collection. */
  generateOutcome(cid, { kind, title, desc, note, proposedMpn, currentMpn, boards, procedure, version, changelog }) {
    const c = STATE.collections.find(x => x.id === cid); if (!c) return null;
    let linkedId = null, targetRole = null, label = '';
    if (kind === 'recommendation') {
      linkedId = 'REC-0' + (STATE.seq.rec++);
      targetRole = 'designer'; label = 'Improvement Recommendation';
      STATE.recommendations = [{ id: linkedId, title: title || c.name, kind: 'recommendation', project: c.project,
        owner: actorName(), ownerId: STATE.currentUserId, role: 'development', assignee: actorName(),
        state: 'pushed', updated: 'just now', created: 'Today', desc: desc || c.desc,
        relatedBom: null, relatedDevCollection: c.id, proposedMpn, currentMpn,
        pushedTo: { role: 'designer', toUserId: 'u-aaron', when: 'just now' }, response: null }, ...STATE.recommendations];
      pushNotif({ forRoles: ['designer'], type: 'IMPROVEMENT RECOMMENDATION', actorRole: 'development', body: `${actorName()} proposes "${title || c.name}".`, who: actorName(), entity: linkedId, verb: 'Review', go: { screen: 'v.recommendationDetail', id: linkedId } });
    } else if (kind === 'rework') {
      linkedId = 'RWK-00' + (STATE.seq.rwk++);
      targetRole = 'production'; label = 'Rework Package';
      STATE.reworks = [{ id: linkedId, title: title || c.name, kind: 'rework', project: c.project,
        owner: actorName(), ownerId: STATE.currentUserId, role: 'development', assignee: 'Maria Chen',
        state: 'pushed', updated: 'just now', created: 'Today', boards: boards || 0,
        desc: desc || c.desc, relatedBom: null, relatedDevCollection: c.id,
        procedure: procedure || ['Per investigation findings'],
        pushedTo: { role: 'production', toUserId: 'u-maria', when: 'just now' }, results: null }, ...STATE.reworks];
      pushNotif({ forRoles: ['production'], type: 'REWORK PACKAGE', actorRole: 'development', body: `${title || c.name} — ${boards || ''} units.`, who: actorName(), entity: linkedId, verb: 'Open', go: { screen: 'v.reworkDetail', id: linkedId } });
    } else if (kind === 'firmware') {
      linkedId = 'FW-' + (version || '1.x');
      targetRole = 'production'; label = 'Firmware Release';
      STATE.firmwares = [{ id: linkedId, title: title || c.name, kind: 'firmware', project: c.project,
        owner: actorName(), ownerId: STATE.currentUserId, role: 'development', assignee: actorName(),
        state: 'validating', updated: 'just now', created: 'Today', version: version || '1.x', relatedBom: null, relatedDevCollection: c.id,
        desc: desc || c.desc, changelog: changelog || ['(see collection)'],
        pushedTo: { role: 'production', toUserId: 'u-maria', when: 'just now' }, results: null }, ...STATE.firmwares];
      pushNotif({ forRoles: ['production'], type: 'FIRMWARE FOR VALIDATION', actorRole: 'development', body: `${title || c.name} awaiting validation.`, who: actorName(), entity: linkedId, verb: 'Validate', go: { screen: 'v.firmwareDetail', id: linkedId } });
    } else if (kind === 'investigation-report') {
      linkedId = 'INV-0' + (STATE.seq.inv++);
      targetRole = 'designer'; label = 'Investigation Report';
      STATE.investigations = [{ id: linkedId, title: title || c.name, kind: 'investigation', project: c.project,
        owner: actorName(), ownerId: STATE.currentUserId, role: 'development', assignee: actorName(),
        state: 'findings', updated: 'just now', created: 'Today', priority: 'medium',
        desc: desc || c.desc, relatedBom: null, relatedDevCollection: c.id,
        findings: (note || c.notes || '').split('\n').filter(Boolean), pushedFrom: null }, ...STATE.investigations];
      pushNotif({ forRoles: ['designer'], type: 'INVESTIGATION REPORT', actorRole: 'development', body: `${actorName()} posted findings: ${title || c.name}.`, who: actorName(), entity: linkedId, verb: 'View', go: { screen: 'v.investigationDetail', id: linkedId } });
    } else if (kind === 'eng-change') {
      // Engineering Change Recommendation — simplified as a recommendation flavor
      linkedId = 'REC-0' + (STATE.seq.rec++);
      targetRole = 'designer'; label = 'Engineering Change Recommendation';
      STATE.recommendations = [{ id: linkedId, title: title || c.name, kind: 'recommendation', project: c.project,
        owner: actorName(), ownerId: STATE.currentUserId, role: 'development', assignee: actorName(),
        state: 'pushed', updated: 'just now', created: 'Today', desc: desc || c.desc,
        engineeringChange: true, relatedDevCollection: c.id,
        pushedTo: { role: 'designer', toUserId: 'u-aaron', when: 'just now' }, response: null }, ...STATE.recommendations];
      pushNotif({ forRoles: ['designer'], type: 'ENGINEERING CHANGE', actorRole: 'development', body: `${actorName()} requested engineering change: ${title || c.name}.`, who: actorName(), entity: linkedId, verb: 'Review', go: { screen: 'v.recommendationDetail', id: linkedId } });
    } else return null;

    c.outcomes = [{ id: 'OUT-0' + (Math.floor(Math.random() * 1000)), kind, label, targetRole, linkedId, when: 'just now', state: 'pushed' }, ...(c.outcomes || [])];
    c.state = 'recommendation-sent'; c.updated = 'just now'; c.updatedBy = actorName();
    pushAudit({ action: `Outcome generated: ${label} → ${targetRole}`, entity: c.id, before: 'READY', after: 'RECOMMENDATION SENT' });
    emit(); return linkedId;
  },

  async markAllRead() { STATE.notifications = STATE.notifications.map(n => ({ ...n, unread: false })); emit(); try { await window.api.post('/notifications/read-all', {}); } catch (e) {} },
  async markRead(id) { const n = STATE.notifications.find(x => x.id === id); if (n) { n.unread = false; emit(); } try { await window.api.post('/notifications/' + id + '/read', {}); } catch (e) {} },

  /* COMMENTS — every commentable object */
  async addComment(entityId, body) {
    const text = (body || '').trim(); if (!text || !entityId) return null;
    try {
      const res = await window.api.post('/comments', { entityId, body: text });
      STATE.comments = { ...STATE.comments, [entityId]: [...(STATE.comments[entityId] || []), res.comment] };
      emit(); return res.id;
    } catch (e) { return null; }
  },

  /* PROGRAMS — Create (v4). Pure AutoBOM concept: no PartsBox side effect, no notifications. */
  async createProgram({ identifier, name, owner, customer, description, tags }) {
    try {
      const prog = await window.api.post('/programs', { name: (name || '').trim(), code: (identifier || '').trim(),
        customer: (customer || '').trim() || null, desc: (description || '').trim(), tags: tags || [] });
      STATE.programs = [...(STATE.programs || []), prog]; emit(); return prog.id;
    } catch (e) { return null; }
  },
  /* PROJECTS — Create (v4). program_id required. Optional PartsBox create at save. */
  async createProject({ identifier, name, lead, program_id, description, createPartsBoxNow }) {
    try {
      let proj = await window.api.post('/projects', { name: (name || '').trim(), identifier: (identifier || '').trim(),
        program_id, desc: (description || '').trim() });
      if (createPartsBoxNow) { try { proj = await window.api.post('/projects/' + proj.id + '/partsbox', {}); } catch (e) {} }
      STATE.projects = { ...STATE.projects, [proj.id]: proj };
      const prog = (STATE.programs || []).find(p => p.id === program_id);
      if (prog) prog.projects = [...(prog.projects || []), proj.id];
      emit(); return proj.id;
    } catch (e) { return null; }
  },
  async createProjectPartsBox(projectId) {
    try {
      const proj = await window.api.post('/projects/' + projectId + '/partsbox', {});
      STATE.projects = { ...STATE.projects, [proj.id]: proj }; emit();
    } catch (e) {}
  },

  /* COLLECTIONS — real create + edit (Designer; Development deferred). */
  async createCollection({ name, program_id, project, category, desc }) {
    try {
      const c = await window.api.post('/collections', { name: (name || '').trim(), program: program_id, project: project || null, category, desc: desc || '' });
      STATE.collections = [c, ...STATE.collections]; emit(); return c.id;
    } catch (e) { return null; }
  },
  async renameCollection(cid, name) {
    const after = (name || '').trim(); if (!after) return;
    try { const c = await window.api.patch('/collections/' + cid, { name: after }); STATE.collections = STATE.collections.map(x => x.id === c.id ? c : x); emit(); } catch (e) {}
  },
  async setCollectionDescription(cid, desc) {
    try { const c = await window.api.patch('/collections/' + cid, { desc }); STATE.collections = STATE.collections.map(x => x.id === c.id ? c : x); emit(); } catch (e) {}
  },
  async setCollectionProject(cid, project) {
    try { const c = await window.api.patch('/collections/' + cid, { project }); STATE.collections = STATE.collections.map(x => x.id === c.id ? c : x); emit(); } catch (e) {}
  },
  async setCollectionProgram(cid, programId) {
    try { const c = await window.api.patch('/collections/' + cid, { program: programId }); STATE.collections = STATE.collections.map(x => x.id === c.id ? c : x); emit(); } catch (e) {}
  },
  async removeFromCollection(cid, no) {
    try { const c = await window.api.del('/collections/' + cid + '/items/' + no); STATE.collections = STATE.collections.map(x => x.id === c.id ? c : x); emit(); } catch (e) {}
  },
  async setItemNote(cid, no, note) {
    try { const c = await window.api.patch('/collections/' + cid + '/items/' + no, { note }); STATE.collections = STATE.collections.map(x => x.id === c.id ? c : x); emit(); } catch (e) {}
  },
  refreshSourcing(cid, no) {
    const c = STATE.collections.find(x => x.id === cid); if (!c) return;
    c.items = c.items.map(i => {
      if (no != null && i.no !== no) return i;
      const cat = CATALOG[i.mpn] || {};
      const sup = cat.recommend || (cat.mouser ? 'mouser' : 'digikey');
      const off = sup && cat[sup];
      const unit = off ? off.price : i.unit;
      return { ...i, status: sup ? 'sourced-' + sup : i.status, supplier: sup || i.supplier,
        supplierPn: off?.pn || i.supplierPn, unit, ext: unit != null ? +(unit * i.qty).toFixed(2) : null, stale: false, fresh: 'just now' };
    });
    c.updated = 'just now'; c.updatedBy = actorName();
    pushAudit({ action: no != null ? `Sourcing refreshed for line ${no}` : 'Sourcing refreshed for collection', entity: cid, before: '—', after: '—' });
    emit();
  },
};

function useStore(selector) {
  const state = useSyncExternalStore(subscribe, getState, getState);
  return selector ? selector(state) : state;
}

Object.assign(window, { useStore, storeActions: actions, getState, resolveNotificationRoute });

/* Restore an existing backend session (valid cookie) on load. Runs after
   window.api is installed by main.jsx. Safe if the backend is unreachable. */
boot();
