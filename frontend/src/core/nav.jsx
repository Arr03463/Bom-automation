/* global React, PROJECTS, ROLE_META */
/* AutoBOM — navigation: hash routing, breadcrumbs, and persistent list state.
   Internally a route is { screen, id?, tab? }. The URL is the source of truth so
   browser Back/Forward and deep links work everywhere. */
const { useState: useStateNav, useEffect: useEffNav, useRef: useRefNav } = React;

/* screen ↔ URL path. :id is the one path param; tab rides in ?tab=. */
const ROUTE_TABLE = [
  { screen: 'd.dashboard', path: 'designer' },
  { screen: 'd.collections', path: 'designer/collections' },
  { screen: 'd.collectionDetail', path: 'designer/collections/:id' },
  { screen: 'p.dashboard', path: 'production' },
  { screen: 'p.boms', path: 'production/boms' },
  { screen: 'p.upload', path: 'production/boms/upload' },
  { screen: 'p.validate', path: 'production/boms/:id/validate' },
  { screen: 'p.sourcing', path: 'production/boms/:id/sourcing' },
  { screen: 'p.results', path: 'production/boms/:id/results' },
  { screen: 'p.procurement', path: 'production/boms/:id/procurement' },
  { screen: 'p.bomOverview', path: 'production/boms/:id' },
  { screen: 'a.dashboard', path: 'admin' },
  { screen: 'a.users', path: 'admin/users' },
  { screen: 'a.configuration', path: 'admin/configuration' },
  { screen: 'a.forceWaivers', path: 'admin/force-waivers' },
  { screen: 'a.audit', path: 'admin/audit' },
  { screen: 'purchasingEmbed', path: 'purchasing-view' },
  { screen: 'inventoryEmbed', path: 'inventory' },
  { screen: 'receiving', path: 'inventory/receiving' },
  { screen: 'storageDetail', path: 'inventory/storage/:id' },
  { screen: 'programs', path: 'programs' },
  { screen: 'programDetail', path: 'programs/:id' },
  { screen: 'v.dashboard', path: 'development' },
  { screen: 'v.collections', path: 'development/collections' },
  { screen: 'v.collectionDetail', path: 'development/collections/:id' },
  { screen: 'v.investigations', path: 'development/investigations' },
  { screen: 'v.investigationDetail', path: 'development/investigations/:id' },
  { screen: 'v.recommendations', path: 'development/recommendations' },
  { screen: 'v.recommendationDetail', path: 'development/recommendations/:id' },
  { screen: 'v.rework', path: 'development/rework' },
  { screen: 'v.reworkDetail', path: 'development/rework/:id' },
  { screen: 'v.firmware', path: 'development/firmware' },
  { screen: 'v.firmwareDetail', path: 'development/firmware/:id' },
  { screen: 'projects', path: 'projects' },
  { screen: 'projectDetail', path: 'projects/:id' },
  { screen: 'notifications', path: 'notifications' },
  { screen: 'settings', path: 'settings' },
];
const BY_SCREEN = Object.fromEntries(ROUTE_TABLE.map(r => [r.screen, r]));

function encodeRoute(route) {
  const e = BY_SCREEN[route.screen] || BY_SCREEN['d.dashboard'];
  let path = e.path.replace(':id', route.id != null ? encodeURIComponent(route.id) : '');
  path = path.replace(/\/$/, '');
  // `tab` and `project` ride in the query string. `project` carries the
  // originating PCB Project into the shared Upload BOM screen (which has no
  // :id segment of its own) so the form can pre-select it.
  const qs = new URLSearchParams();
  if (route.tab) qs.set('tab', route.tab);
  if (route.project) qs.set('project', route.project);
  const q = qs.toString();
  return '#/' + path + (q ? '?' + q : '');
}

function decodeRoute(hash) {
  let h = (hash || '').replace(/^#\/?/, '');
  const [path, query] = h.split('?');
  const params = query ? new URLSearchParams(query) : null;
  const tab = params ? params.get('tab') : null;
  const project = params ? params.get('project') : null;
  const segs = path.split('/').filter(Boolean);
  if (segs.length === 0) return { screen: 'd.dashboard' };
  // candidates with matching segment count
  const cands = ROUTE_TABLE.map(r => ({ r, parts: r.path.split('/') })).filter(x => x.parts.length === segs.length);
  // prefer fewer params (more static) — static literal routes win over :id routes
  cands.sort((a, b) => a.parts.filter(p => p[0] === ':').length - b.parts.filter(p => p[0] === ':').length);
  for (const { r, parts } of cands) {
    let id = null, ok = true;
    for (let i = 0; i < parts.length; i++) {
      if (parts[i][0] === ':') id = decodeURIComponent(segs[i]);
      else if (parts[i] !== segs[i]) { ok = false; break; }
    }
    if (ok) return { screen: r.screen, id, tab, project };
  }
  return { screen: 'd.dashboard' };
}

function routeKey(route) { return encodeRoute(route).split('?')[0]; }

/* screen → sidebar nav-item key (for active-item highlighting). Detail/step screens
   fold up to their list item; everything else highlights itself. Replaces the old
   static NAV_OF map in app.jsx (derived here so there is one source of truth). */
const NAV_KEY_OVERRIDES = {
  'd.collectionDetail': 'd.collections', 'd.exception': 'd.dashboard',
  'p.upload': 'projects', 'p.validate': 'projects', 'p.sourcing': 'projects', 'p.results': 'projects',
  'p.procurement': 'projects', 'p.bomOverview': 'projects', 'p.boms': 'projects',
  'programDetail': 'programs', 'projectDetail': 'projects', 'receiving': 'inventoryEmbed',
  'storageDetail': 'inventoryEmbed',
};
function navKeyForScreen(screen) { return NAV_KEY_OVERRIDES[screen] || screen; }

/* ---- Breadcrumbs: hierarchical, every crumb a link ---- */
function buildCrumbs(route, state) {
  const C = (label, screen, id, tab) => ({ label, route: screen ? { screen, id, tab } : null });
  const proj = (pid) => (state.projects[pid] || { name: pid });
  const s = route.screen;
  const find = (coll, id) => state[coll].find(x => x.id === id);

  // workspace roots
  if (s === 'd.dashboard') return [C('Designer', 'd.dashboard')];
  if (s === 'd.collections') return [C('Designer', 'd.dashboard'), C('Collections')];
  if (s === 'd.collectionDetail') { const c = find('collections', route.id); const p = proj(c ? c.project : ''); return [C('PCB Projects', 'projects'), C(p.name, 'projectDetail', c && c.project, 'collections'), C('Collections', 'd.collections'), C(c ? c.name : route.id)]; }

  if (s === 'p.dashboard') return [C('Production', 'p.dashboard')];
  if (s === 'p.boms') return [C('PCB Projects', 'projects'), C('BOMs')];
  if (s === 'p.upload') return [C('PCB Projects', 'projects'), C('Upload BOM')];
  if (['p.bomOverview', 'p.validate', 'p.sourcing', 'p.results', 'p.procurement'].includes(s)) {
    const b = find('boms', route.id); const p = proj(b ? b.project : '');
    const base = [C('PCB Projects', 'projects'), C(p.name, 'projectDetail', b && b.project, 'boms'), C(b ? b.name : route.id, s === 'p.bomOverview' ? null : 'p.bomOverview', route.id)];
    const step = { 'p.validate': 'Validation', 'p.sourcing': 'Sourcing', 'p.results': 'Sourcing Results', 'p.procurement': 'Procurement Package' }[s];
    return step ? [...base, C(step)] : base;
  }

  if (s === 'a.dashboard') return [C('Admin', 'a.dashboard')];
  if (s.startsWith('a.')) { const lbl = { 'a.users': 'Users', 'a.configuration': 'Configuration', 'a.forceWaivers': 'Force-Waivers Log', 'a.audit': 'Audit Log' }[s]; return [C('Admin', 'a.dashboard'), C(lbl)]; }

  if (s === 'v.dashboard') return [C('Development', 'v.dashboard')];
  if (s === 'v.collections') return [C('Development', 'v.dashboard'), C('Collections')];
  if (s === 'v.collectionDetail') { const x = find('collections', route.id); const p = proj(x ? x.project : ''); return [C('PCB Projects', 'projects'), C(p.name, 'projectDetail', x && x.project, 'collections'), C('Collections', 'v.collections'), C(x ? x.name : route.id)]; }
  if (s === 'v.investigations') return [C('Development', 'v.dashboard'), C('Investigations')];
  if (s === 'v.investigationDetail') { const x = find('investigations', route.id); const p = proj(x ? x.project : ''); return [C('PCB Projects', 'projects'), C(p.name, 'projectDetail', x && x.project), C('Investigations', 'v.investigations'), C(x ? x.title : route.id)]; }
  if (s === 'v.recommendations') return [C('Development', 'v.dashboard'), C('Improvements')];
  if (s === 'v.recommendationDetail') { const x = find('recommendations', route.id); const p = proj(x ? x.project : ''); return [C('PCB Projects', 'projects'), C(p.name, 'projectDetail', x && x.project), C('Improvements', 'v.recommendations'), C(x ? x.title : route.id)]; }
  if (s === 'v.rework') return [C('Development', 'v.dashboard'), C('Rework Packages')];
  if (s === 'v.reworkDetail') { const x = find('reworks', route.id); const p = proj(x ? x.project : ''); return [C('PCB Projects', 'projects'), C(p.name, 'projectDetail', x && x.project), C('Rework Packages', 'v.rework'), C(x ? x.title : route.id)]; }
  if (s === 'v.firmware') return [C('Development', 'v.dashboard'), C('Firmware Releases')];
  if (s === 'v.firmwareDetail') { const x = find('firmwares', route.id); const p = proj(x ? x.project : ''); return [C('PCB Projects', 'projects'), C(p.name, 'projectDetail', x && x.project), C('Firmware Releases', 'v.firmware'), C(x ? x.title : route.id)]; }

  if (s === 'storageDetail') return [C('Inventory', 'inventoryEmbed'), C('Storage locations', 'inventoryEmbed'), C(route.id || 'Location')];
  if (s === 'projects') return [C('PCB Projects')];
  if (s === 'projectDetail') { const p = proj(route.id); return [C('PCB Projects', 'projects'), C(p.name)]; }
  if (s === 'notifications') return [C('Notifications')];
  if (s === 'settings') return [C('Account Settings')];
  return [C('AutoBOM', 'd.dashboard')];
}

/* ---- useHashRoute: drive route from the URL hash (Back/Forward + deep links) ---- */
function useHashRoute(defaultScreen) {
  const [route, setRoute] = useStateNav(() => decodeRoute(location.hash));
  useEffNav(() => {
    const onHash = () => setRoute(decodeRoute(location.hash));
    window.addEventListener('hashchange', onHash);
    // Caller supplies the landing screen for the signed-in role; 'd.dashboard'
    // was hardcoded here, which sent every role to the Designer workspace.
    if (!location.hash) {
      const home = defaultScreen || 'd.dashboard';
      location.replace(encodeRoute({ screen: home }));
      setRoute(decodeRoute(encodeRoute({ screen: home })));
    }
    return () => window.removeEventListener('hashchange', onHash);
  }, [defaultScreen]);
  // navigate: push a new history entry (unless replacing)
  const navigate = (r, replace) => {
    if (typeof r === 'string') r = { screen: r };
    const h = encodeRoute(r);
    if (h === location.hash) { setRoute(decodeRoute(h)); return; }
    if (replace) location.replace(h); else location.hash = h;
  };
  return [route, navigate];
}

/* ---- Persistent list/queue UI state (filters, search, sort) ---- */
const LS_KEY = 'autobom.liststate.v1';
function loadLS() { try { return JSON.parse(sessionStorage.getItem(LS_KEY) || '{}'); } catch (e) { return {}; } }
function saveLS(all) { try { sessionStorage.setItem(LS_KEY, JSON.stringify(all)); } catch (e) {} }
function useListState(key, defaults) {
  const [val, setVal] = useStateNav(() => { const all = loadLS(); return { ...defaults, ...(all[key] || {}) }; });
  const set = (patch) => setVal(v => { const nv = { ...v, ...patch }; const all = loadLS(); all[key] = nv; saveLS(all); return nv; });
  return [val, set];
}

/* ---- Scroll position memory, keyed by route ---- */
const SCROLL = {};
function rememberScroll(route) { SCROLL[routeKey(route)] = window.scrollY; }
function restoreScroll(route) { const y = SCROLL[routeKey(route)] || 0; requestAnimationFrame(() => window.scrollTo(0, y)); }

Object.assign(window, { ROUTE_TABLE, encodeRoute, decodeRoute, routeKey, navKeyForScreen, buildCrumbs, useHashRoute, useListState, rememberScroll, restoreScroll });
