/* global React, seedState, uid, line, CATALOG */
/* AutoBOM — shared workflow store. A single connected state with actions that
   mutate global state and propagate notifications + audit across every role. */
const { useSyncExternalStore } = React;

let STATE = seedState();

const listeners = new Set();
function emit() { STATE = { ...STATE }; listeners.forEach(l => l()); }
function subscribe(l) { listeners.add(l); return () => listeners.delete(l); }
function getState() { return STATE; }

const actorName = () => (STATE.users.find(u => u.id === STATE.currentUserId) || {}).name || 'You';

/* ---- Prototype auth (Note 4). Email-only; sessionStorage persistence; Model D landing.
   No backend — real Microsoft SSO replaces logIn/logOut in Phase 2, UX contract unchanged. ---- */
const AUTH_KEY = 'autobom.auth.v1';
function lastRoleKey(uid) { return 'autobom.lastRole.' + uid; }
function persistAuth() {
  try {
    if (STATE.authed && STATE.currentUserId) {
      sessionStorage.setItem(AUTH_KEY, JSON.stringify({ userId: STATE.currentUserId, activeRole: STATE.activeRole }));
      sessionStorage.setItem(lastRoleKey(STATE.currentUserId), STATE.activeRole);
    } else { sessionStorage.removeItem(AUTH_KEY); }
  } catch (e) {}
}
function landingRoleFor(user) {
  const roles = (user && user.roles) || [];
  let last = null; try { last = sessionStorage.getItem(lastRoleKey(user.id)); } catch (e) {}
  if (last && roles.includes(last)) return last;                 // return session → last-active role
  if (user.primaryRole && roles.includes(user.primaryRole)) return user.primaryRole; // first login → primary
  return roles[0] || 'designer';
}
(function hydrateAuth() {
  try {
    const raw = sessionStorage.getItem(AUTH_KEY);
    if (!raw) return;
    const { userId, activeRole } = JSON.parse(raw);
    const u = STATE.users.find(x => x.id === userId && x.active);
    if (u) { STATE.authed = true; STATE.currentUserId = userId; STATE.activeRole = u.roles.includes(activeRole) ? activeRole : landingRoleFor(u); }
  } catch (e) {}
})();

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
  /* Prototype auth — email-only login against seed users (Note 4). */
  logIn(email) {
    const e = (email || '').trim().toLowerCase();
    if (!e) return { ok: false, error: 'Enter your work email.' };
    const u = STATE.users.find(x => x.email.toLowerCase() === e);
    if (!u) return { ok: false, error: "We don't recognize that email. Try a seed user." };
    if (!u.active) return { ok: false, error: 'This account is deactivated. Contact an administrator.' };
    STATE.currentUserId = u.id; STATE.authed = true; STATE.activeRole = landingRoleFor(u);
    persistAuth();
    pushAudit({ action: 'Logged in (prototype)', entity: u.id, before: '—', after: u.email });
    emit(); return { ok: true };
  },
  logOut() {
    const u = STATE.users.find(x => x.id === STATE.currentUserId);
    if (u) pushAudit({ action: 'Logged out (prototype)', entity: u.id, before: u.email, after: '—' });
    STATE.authed = false;
    try { sessionStorage.removeItem(AUTH_KEY); } catch (err) {}
    emit();
  },
  /* Role switcher — scoped to roles the logged-in user actually holds. */
  setRole(role) {
    const u = STATE.users.find(x => x.id === STATE.currentUserId);
    if (u && u.roles && !u.roles.includes(role)) return;
    STATE.activeRole = role;
    persistAuth();
    emit();
  },

  /* DESIGNER */
  addToCollection(mpn, collectionId, newName) {
    let col = STATE.collections.find(c => c.id === collectionId);
    if (!col && newName) {
      col = { id: 'COL-0' + (STATE.seq.col++), name: newName, project: 'tvca-rev2', state: 'active',
        creator: actorName(), ownerId: STATE.currentUserId, role: 'designer', updated: 'just now', updatedBy: actorName(), created: 'Today', desc: '', items: [] };
      STATE.collections = [col, ...STATE.collections];
    }
    if (!col) return;
    const c = CATALOG[mpn];
    const no = col.items.length + 1;
    const rec = c && c.recommend;
    col.items = [...col.items, line(no, mpn, 1, rec ? 'sourced-' + rec : 'needs-review')];
    col.updated = 'just now'; col.updatedBy = actorName();
    pushAudit({ action: 'Part added to collection', entity: col.id, before: `${no - 1} parts`, after: `${no} parts` });
    emit();
    return col;
  },
  updateQty(collectionId, no, qty) {
    const col = STATE.collections.find(c => c.id === collectionId); if (!col) return;
    col.items = col.items.map(i => i.no === no ? { ...i, qty, ext: i.unit != null ? +(i.unit * qty).toFixed(2) : null } : i);
    col.updated = 'just now'; emit();
  },
  requestToOrder(collectionId, note, critical) {
    const col = STATE.collections.find(c => c.id === collectionId); if (!col) return;
    const reqId = 'REQ-0' + (STATE.seq.req++);
    col.state = 'order-requested'; col.reqId = reqId; col.updated = 'just now'; col.updatedBy = actorName();
    STATE.requests = [{ id: reqId, title: col.name, kind: 'collection', sourceId: col.id, project: col.project,
      from: actorName(), fromRole: 'designer', submitted: 'just now', age: 0, critical: !!critical, bucketState: critical ? 'QUEUED_CRITICAL' : 'QUEUED_MAIN', note: note || '', resubmit: !!col.rejection, items: col.items }, ...STATE.requests];
    // Dropping a request into the bucket is NOT a request for Purchasing's permission —
    // Purchasing doesn't approve/reject/review. No action notification is sent to Purchasing.
    // (The bucket view is the surface; an item simply appears there.)
    pushAudit({ action: 'Collection submitted to Purchasing', entity: col.id, before: 'ACTIVE', after: 'ORDER REQUESTED' });
    emit(); return reqId;
  },
  /* Designer resolves a Push-Back — produces a RECOMMENDATION, never mutates the master BOM.
     Production applies it from their Dashboard (applyPushbackRecommendation). */
  resolvePushback(bomId, { recommendations, note }) {
    const bom = STATE.boms.find(b => b.id === bomId); if (!bom || !bom.pushback) return;
    bom.pushback.recommendation = {
      by: actorName(), when: 'just now', note: note || '',
      picks: (recommendations || []).map(r => ({ lineNo: r.lineNo != null ? r.lineNo : null, added: !!r.added,
        mpn: r.candidate.mpn, mfr: r.candidate.mfr || '', desc: r.candidate.desc || '', section: r.candidate.section || 'supplier',
        location: r.candidate.location || null, datasheet: r.candidate.datasheet || null, request: r.request || null })),
    };
    bom.pushback.recommendation.picks.forEach(p => actions.attachDatasheet(p.mpn, p.datasheet)); // datasheet on user-action
    bom.updated = 'just now'; bom.updatedBy = actorName();
    const n = bom.pushback.recommendation.picks.length;
    pushNotif({ forRoles: ['production'], targetRole: 'production', sourceRole: 'designer', kind: 'action',
      type: 'REPLACEMENTS RECOMMENDED', actorRole: 'designer',
      actionLabel: 'Apply replacements', verb: 'Resolve',
      body: `${bom.name} · ${n} replacement${n > 1 ? 's' : ''} recommended by ${actorName()} — review and Apply to the master BOM.`,
      who: actorName(), entity: bom.id,
      routes: { production: { screen: 'p.dashboard' }, designer: { screen: 'p.bomOverview', id: bom.id } } });
    pushAudit({ action: 'Push-Back resolved — recommendations sent', entity: bom.id, before: 'EXCEPTIONS', after: 'EXCEPTIONS (recommended)' });
    emit();
  },
  /* Production commits Designer's recommendation to the master BOM (version increments). */
  applyPushbackRecommendation(bomId) {
    const bom = STATE.boms.find(b => b.id === bomId); if (!bom || !bom.pushback || !bom.pushback.recommendation) return;
    const rec = bom.pushback.recommendation;
    rec.picks.forEach(p => {
      if (p.added) {
        const no = bom.items.length + 1; const c = CATALOG[p.mpn] || {};
        bom.items = [...bom.items, line(no, p.mpn, (p.request && p.request.quantityPerBoard) || 1, c.recommend ? 'sourced-' + c.recommend : 'needs-review')];
      } else {
        bom.items = bom.items.map(i => {
          if (i.no !== p.lineNo) return i; const c = CATALOG[p.mpn] || {};
          return { ...i, mpn: p.mpn, mfr: p.mfr || c.mfr || i.mfr, desc: c.desc || p.desc || i.desc, status: 'validated', exReason: null, replacement: { from: i.mpn, by: rec.by } };
        });
      }
      actions.attachDatasheet(p.mpn, p.datasheet);
    });
    bom.version = (bom.version || 1) + 1;
    bom.state = 'normalised'; bom.updated = 'just now'; bom.updatedBy = actorName();
    bom.pushback.appliedBy = actorName(); bom.pushback.appliedWhen = 'just now';
    pushNotif({ forRoles: ['production'], targetRole: 'production', sourceRole: 'production', kind: 'action',
      type: 'REPLACEMENTS APPLIED', actorRole: 'production', actionLabel: 'Re-run sourcing', verb: 'Resolve',
      body: `${bom.name} · recommendations applied to master BOM v${bom.version} — ready for re-sourcing.`, who: actorName(), entity: bom.id,
      routes: { production: { screen: 'p.sourcing', id: bom.id }, designer: { screen: 'p.bomOverview', id: bom.id } } });
    pushAudit({ action: `Recommendations applied to master BOM (v${bom.version})`, entity: bom.id, before: 'EXCEPTIONS', after: 'NORMALISED' });
    emit();
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
  createBom({ name, project, buildQty, overage }) {
    // One BOM per PCB Project (1:1). Refuse if this project already has a non-draft BOM.
    if (STATE.boms.some(b => b.project === project && b.state !== 'draft')) return null;
    const id = 'BOM-0' + (STATE.seq.bom++);
    const bom = { id, name, project, state: 'validated', creator: actorName(), ownerId: STATE.currentUserId, role: 'production',
      updated: 'just now', updatedBy: actorName(), created: 'Today', buildQty, overage,
      validation: { errors: 0, warnings: 2, notes: ['Line 4: quantity inferred from reference designators.', 'Lines 6–7: duplicate MPN consolidated.'] },
      items: [ line(1, 'STM32G431CBT6', buildQty, 'validated'), line(2, 'GRM188R71H104KA93D', buildQty * 20, 'validated'),
        line(3, 'ERJ-3EKF1002V', buildQty * 32, 'validated'), line(4, 'TPS54560DDAR', buildQty, 'validated') ] };
    STATE.boms = [bom, ...STATE.boms];
    pushAudit({ action: 'BOM uploaded & validated', entity: id, before: '—', after: 'VALIDATED' });
    emit(); return id;
  },
  completeSourcing(bomId) {
    const bom = STATE.boms.find(b => b.id === bomId); if (!bom) return;
    bom.items = bom.items.map((i, k) => i.status === 'needs-review' ? i : { ...i, status: k % 2 ? 'sourced-digikey' : 'sourced-mouser', supplier: k % 2 ? 'digikey' : 'mouser' });
    const hasEx = bom.items.some(i => i.status === 'needs-review');
    bom.state = 'results'; bom.updated = 'just now';
    pushAudit({ action: 'Sourcing run complete', entity: bom.id, before: 'SOURCING', after: hasEx ? 'RESULTS (exceptions)' : 'RESULTS' });
    emit();
  },
  sendPushback(bomId, opts) {
    const { lineNos = [], reason = 'other', urgency = 'standard', note = '', perLineComments = {}, addedComponentRequest = null } = opts || {};
    const bom = STATE.boms.find(b => b.id === bomId); if (!bom) return;
    bom.state = 'exceptions';
    const flaggedLines = lineNos.map(no => ({ lineNo: no, exReason: (bom.items.find(i => i.no === no) || {}).exReason || 'Needs engineering review', comments: perLineComments[no] ? [{ by: actorName(), when: 'just now', body: perLineComments[no] }] : [] }));
    bom.pushback = { by: actorName(), when: 'just now', to: bom.creator, reason, urgency, note, loop: (bom.pushback?.loop || 0) + 1, flaggedLines, addedComponentRequest, recommendation: null, comments: [] };
    if (flaggedLines.length) bom.items = bom.items.map(i => flaggedLines.find(f => f.lineNo === i.no) ? { ...i, status: 'needs-review' } : i);
    const count = flaggedLines.length + (addedComponentRequest ? 1 : 0);
    pushNotif({ forRoles: ['designer'], targetRole: 'designer', sourceRole: 'production', kind: 'action',
      type: 'BOM EXCEPTION', actorRole: 'production',
      actionLabel: `Resolve ${count} item${count > 1 ? 's' : ''}`, verb: 'Resolve',
      body: `${bom.name} · ${reason === 'missing-component' ? 'missing component requested' : count + ' line' + (count > 1 ? 's' : '') + ' flagged'} for engineering review.`, who: actorName(), entity: bom.id,
      routes: { designer: { screen: 'd.dashboard' }, production: { screen: 'p.bomOverview', id: bom.id } } });
    pushAudit({ action: 'Push-Back sent to Designer', entity: bom.id, before: 'RESULTS', after: 'EXCEPTIONS' });
    emit();
  },
  createPackage(bomId) {
    const bom = STATE.boms.find(b => b.id === bomId); if (!bom) return;
    bom.partsbox = 'PB-' + bom.id.replace('BOM-', ''); bom.updated = 'just now';
    pushAudit({ action: 'PartsBox project created', entity: bom.id, before: 'RESULTS', after: 'PACKAGED' });
    emit();
  },
  submitBomToPurchasing(bomId, note) {
    const bom = STATE.boms.find(b => b.id === bomId); if (!bom) return;
    const reqId = 'REQ-0' + (STATE.seq.req++);
    bom.state = 'submitted'; bom.reqId = reqId; bom.updated = 'just now'; bom.updatedBy = actorName();
    STATE.requests = [{ id: reqId, title: bom.name, kind: 'bom', sourceId: bom.id, project: bom.project,
      from: actorName(), fromRole: 'production', submitted: 'just now', age: 0, critical: false, bucketState: 'QUEUED_MAIN', note: note || '', resubmit: false, items: bom.items }, ...STATE.requests];
    // No approval notification to Purchasing — the request simply enters the Main bucket.
    pushAudit({ action: 'BOM submitted to Purchasing', entity: bom.id, before: 'PACKAGED', after: 'SUBMITTED' });
    emit(); return reqId;
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
  setUserRoles(userId, roles) {
    const u = STATE.users.find(x => x.id === userId); if (!u) return;
    const before = '[' + u.roles.join(', ') + ']'; u.roles = roles;
    pushAudit({ action: 'Roles updated', entity: userId, before, after: '[' + roles.join(', ') + ']' });
    emit();
  },
  setUserOverrides(userId, overrides) {
    const u = STATE.users.find(x => x.id === userId); if (!u) return;
    const before = '[' + (u.overrides || []).join(', ') + ']';
    u.overrides = overrides;
    pushAudit({ action: 'User permission overrides updated', entity: userId, before, after: '[' + overrides.join(', ') + ']' });
    emit();
  },
  toggleUserActive(userId) {
    const u = STATE.users.find(x => x.id === userId); if (!u) return;
    u.active = !u.active;
    pushAudit({ action: u.active ? 'User activated' : 'User deactivated', entity: userId, before: u.active ? 'INACTIVE' : 'ACTIVE', after: u.active ? 'ACTIVE' : 'INACTIVE' });
    emit();
  },
  inviteUser({ name, email, roles }) {
    const id = 'u-' + name.toLowerCase().split(' ')[0];
    STATE.users = [...STATE.users, { id, name, email, roles: roles && roles.length ? roles : ['readonly'], active: true, intern: false, lastActive: 'Never', created: 'Today', title: '—' }];
    pushAudit({ action: 'User invited', entity: id, before: '—', after: 'ACTIVE (' + (roles?.join(', ') || 'readonly') + ')' });
    emit();
  },
  toggleSupplier(id) {
    const s = STATE.suppliers.find(x => x.id === id); if (!s) return;
    s.enabled = !s.enabled; pushAudit({ action: s.enabled ? 'Supplier enabled' : 'Supplier disabled', entity: id, before: s.enabled ? 'OFF' : 'ON', after: s.enabled ? 'ON' : 'OFF' }); emit();
  },
  setConfig(path, value) {
    const [grp, key] = path.split('.');
    if (STATE.system[grp]) { STATE.system[grp][key] = value; pushAudit({ action: 'Config changed: ' + path, entity: 'system', before: '—', after: String(value) }); emit(); }
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

  markAllRead() { STATE.notifications = STATE.notifications.map(n => ({ ...n, unread: false })); emit(); },
  markRead(id) { const n = STATE.notifications.find(x => x.id === id); if (n) { n.unread = false; emit(); } },

  /* COMMENTS — every commentable object */
  addComment(entityId, body) {
    const text = (body || '').trim(); if (!text || !entityId) return null;
    const u = STATE.users.find(x => x.id === STATE.currentUserId);
    const c = { id: uid('cmt'), userId: STATE.currentUserId, name: u?.name || actorName(), role: STATE.activeRole, when: 'just now', body: text };
    STATE.comments = { ...STATE.comments, [entityId]: [...(STATE.comments[entityId] || []), c] };
    pushAudit({ action: 'Comment posted', entity: entityId, before: '—', after: text.length > 60 ? text.slice(0, 60) + '…' : text });
    emit(); return c.id;
  },

  /* PROGRAMS — Create (v4). Pure AutoBOM concept: no PartsBox side effect, no notifications. */
  createProgram({ identifier, name, owner, customer, description, tags }) {
    const id = 'prog-' + Math.random().toString(36).slice(2, 8);
    const idf = (identifier || '').trim();
    const prog = { id, identifier: idf, code: idf, name: (name || '').trim(), owner: owner || actorName(),
      customer: (customer || '').trim() || null, desc: (description || '').trim(), status: 'Active',
      started: 'Jul 2026', target: null, tags: tags || [], notifyOnEquivalentSwap: true, projects: [] };
    STATE.programs = [...(STATE.programs || []), prog];
    pushAudit({ action: 'Program created', entity: id, before: '—', after: `${idf} · ${prog.name}` });
    emit(); return id;
  },
  /* PROJECTS — Create (v4). program_id required (Standalone retired). Optional PartsBox create at save. */
  createProject({ identifier, name, lead, program_id, description, createPartsBoxNow }) {
    const id = 'proj-' + Math.random().toString(36).slice(2, 8);
    const proj = { id, identifier: (identifier || '').trim(), name: (name || '').trim(),
      lead: lead || actorName(), program_id, desc: (description || '').trim(), status: 'active', created: 'Today',
      partsbox: { created: false, pending: false, projectId: null, storageId: null } };
    if (createPartsBoxNow) actions._doPartsBoxSetup(proj);
    STATE.projects = { ...STATE.projects, [id]: proj };
    const prog = (STATE.programs || []).find(p => p.id === program_id);
    if (prog) prog.projects = [...(prog.projects || []), id];
    pushAudit({ action: 'Project created', entity: id, before: '—', after: `${proj.name} · PartsBox ${createPartsBoxNow ? 'requested' : 'deferred'}` });
    emit(); return id;
  },
  /* Idempotent PartsBox project + storage create (mirrors POC find-or-create). Used at save and via the detail affordance. */
  _doPartsBoxSetup(proj) {
    try {
      proj.partsbox = { created: true, pending: false, projectId: 'PB-' + proj.name.replace(/[^A-Za-z0-9]/g, '').slice(0, 8).toUpperCase(), storageId: 'PBS-' + proj.name.replace(/[^A-Za-z0-9]/g, '').slice(0, 8).toUpperCase() };
      pushAudit({ action: 'PartsBox project + storage location created', entity: proj.id, before: '—', after: proj.partsbox.projectId });
    } catch (e) {
      proj.partsbox = { created: false, pending: true, projectId: null, storageId: null };
      pushAudit({ action: 'PartsBox creation failed — pending retry', entity: proj.id, before: '—', after: 'PENDING' });
    }
  },
  createProjectPartsBox(projectId) {
    const proj = STATE.projects[projectId]; if (!proj || proj.partsbox?.created) return;
    actions._doPartsBoxSetup(proj); proj.updated = 'just now'; emit();
  },

  /* COLLECTIONS — live editing + creation (designer + development share the same shape) */
  createCollection({ kind, name, program_id, project, category, desc, notes, tags, priority, relatedBom, relatedDevTask }) {
    const isDev = kind === 'development';
    const id = (isDev ? 'DCOL-0' : 'COL-0') + String(STATE.seq.col++).padStart(2, '0');
    const c = { id, name: name.trim(), program_id: program_id || null, project: project || null, state: isDev ? 'draft' : 'active',
      role: isDev ? 'development' : 'designer', kind: isDev ? 'development' : 'designer',
      creator: actorName(), ownerId: STATE.currentUserId,
      category: category || (isDev ? 'Investigation' : null),
      updated: 'just now', updatedBy: actorName(), created: 'Today',
      desc: desc || '', notes: notes || '',
      tags: tags || [], priority: priority || null, relatedBom: relatedBom || null, relatedDevTask: relatedDevTask || null,
      items: [], outcomes: isDev ? [] : undefined };
    STATE.collections = [c, ...STATE.collections];
    pushAudit({ action: `${isDev ? 'Development' : 'Designer'} Collection created`, entity: id, before: '—', after: 'DRAFT' });
    emit(); return id;
  },
  renameCollection(cid, name) {
    const c = STATE.collections.find(x => x.id === cid); if (!c) return;
    const before = c.name; const after = name.trim(); if (!after || after === before) return;
    c.name = after; c.updated = 'just now'; c.updatedBy = actorName();
    pushAudit({ action: 'Collection renamed', entity: cid, before, after });
    emit();
  },
  setCollectionDescription(cid, desc) {
    const c = STATE.collections.find(x => x.id === cid); if (!c) return;
    c.desc = desc; c.updated = 'just now'; c.updatedBy = actorName();
    pushAudit({ action: 'Collection description updated', entity: cid, before: '—', after: '—' });
    emit();
  },
  setCollectionProject(cid, project) {
    const c = STATE.collections.find(x => x.id === cid); if (!c) return;
    const before = c.project; c.project = project; c.updated = 'just now'; c.updatedBy = actorName();
    pushAudit({ action: 'Collection project changed', entity: cid, before, after: project });
    emit();
  },
  setCollectionProgram(cid, programId) {
    const c = STATE.collections.find(x => x.id === cid); if (!c) return;
    const before = c.program_id; c.program_id = programId; c.project = null; c.updated = 'just now'; c.updatedBy = actorName();
    pushAudit({ action: 'Collection program changed', entity: cid, before, after: programId });
    emit();
  },
  removeFromCollection(cid, no) {
    const c = STATE.collections.find(x => x.id === cid); if (!c) return;
    const gone = c.items.find(i => i.no === no);
    c.items = c.items.filter(i => i.no !== no).map((i, k) => ({ ...i, no: k + 1 }));
    c.updated = 'just now'; c.updatedBy = actorName();
    if (gone) pushAudit({ action: 'Part removed from collection', entity: cid, before: gone.mpn, after: '—' });
    emit();
  },
  setItemNote(cid, no, note) {
    const c = STATE.collections.find(x => x.id === cid); if (!c) return;
    c.items = c.items.map(i => i.no === no ? { ...i, note } : i);
    c.updated = 'just now'; c.updatedBy = actorName(); emit();
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
