/* global React, Icon, StatusBadge, SupplierTag, RoleTag, CATALOG, getState, useStore,
   storeActions, encodeRoute, PROJECTS */
/* AutoBOM — global search overlay.
   One component, two presentation modes:
     - 'dropdown'  : anchored under the top rail search bar
     - 'palette'   : centred command palette (⌘K / Ctrl+K)
   In both modes: live results on every keystroke, categorised, ranked.
   The page underneath stays visible and interactive. Escape closes and restores
   focus to where the user was — scroll/filters/panels are never touched. */
const { useState: useStateS, useRef: useRefS, useEffect: useEffS, useMemo: useMemoS } = React;

/* ---- recents (sessionStorage) ---- */
const RECENTS_KEY = 'autobom.recents.v1';
function loadRecents() { try { return JSON.parse(sessionStorage.getItem(RECENTS_KEY) || '[]'); } catch (e) { return []; } }
function pushRecent(item) {
  const list = loadRecents().filter(x => !(x.kind === item.kind && x.id === item.id));
  list.unshift({ ...item, ts: Date.now() });
  sessionStorage.setItem(RECENTS_KEY, JSON.stringify(list.slice(0, 12)));
}

/* ---- helpers ---- */
const norm = (s) => String(s || '').toLowerCase();
const eq = (a, b) => norm(a) === norm(b);
const has = (s, q) => norm(s).includes(norm(q));

/* Rank a single hit (lower is better). Mirrors the spec. */
function rankHit({ kind, mpn, mfr, mfrMpn, supplierPns, name }, q) {
  const Q = norm(q);
  if (kind === 'component') {
    if (eq(mpn, q)) return 1;
    if (mfrMpn && Q === norm(mfrMpn)) return 2;
    if (supplierPns && supplierPns.some(p => eq(p, q))) return 3;
    if (has(mpn, q)) return 4;
  }
  if (['collection', 'bom', 'project', 'request'].includes(kind) && has(name, q)) return 5;
  return 99;
}

/* ---- storage-location index: aggregate PartsBox parts by their storage bins ---- */
function storageIndex(inventory) {
  const map = new Map();
  for (const p of (inventory || [])) {
    for (const l of (p.locations || [])) {
      let e = map.get(l.name);
      if (!e) { e = { name: l.name, kind: l.kind, parts: [], units: 0 }; map.set(l.name, e); }
      e.parts.push({ mpn: p.mpn, qty: l.qty, desc: p.desc });
      e.units += (l.qty || 0);
      if (l.kind === 'project') e.kind = 'project'; // project-box label wins when a bin is mixed
    }
  }
  return map;
}

/* App-wide search runs in `search_available_stock` mode: PartsBox inventory is the primary
   source, storage locations are first-class results, and Mouser/DigiKey are an overlay behind
   the "Include suppliers" toggle. Workflow objects (Collections, BOMs, Projects, Requests) stay
   searchable as their own sections. Sections are never deduped. */
function search(query, includeSuppliers) {
  if (!query.trim()) return null;
  const q = query.trim();
  const s = getState();

  // 1 — In inventory (PartsBox, primary source)
  const inv = s.inventory || [];
  const invHits = [];
  for (const p of inv) {
    const exact = eq(p.mpn, q);
    if (exact || has(`${p.mpn} ${p.mfr || ''} ${p.desc || ''} ${p.cat || ''}`, q))
      // id feeds the React key (`invpart:<id>`). PartsBox legitimately holds
      // several part records per MPN, so keying on mpn produced duplicate keys
      // and risked rows being dropped or reused. p.id is unique per record.
      invHits.push({ kind: 'invpart', id: p.id || p.mpn, mpn: p.mpn, mfr: p.mfr, desc: p.desc, onHand: p.onHand, low: p.low, locations: p.locations || [], tags: p.tags || [], rank: exact ? 1 : has(p.mpn, q) ? 4 : 5 });
  }
  invHits.sort((a, b) => a.rank - b.rank);

  // 2 — Storage locations (matched by name, or by a contained part)
  const stHits = [];
  for (const e of storageIndex(inv).values()) {
    const nameMatch = has(e.name, q);
    if (nameMatch || e.parts.some(pt => has(pt.mpn, q) || has(pt.desc, q)))
      stHits.push({ kind: 'storage', id: e.name, name: e.name, storageKind: e.kind, parts: e.parts, units: e.units, rank: nameMatch ? 2 : 6 });
  }
  stHits.sort((a, b) => a.rank - b.rank);

  // 3 — Available from suppliers: fetched LIVE (Mouser + DigiKey) in the overlay
  //     component and merged in; no static catalog here.
  const supHits = [];

  // Workflow objects (AutoBOM's own DB)
  const colHits = [], devHits = [], bomHits = [], projHits = [], reqHits = [];
  for (const x of s.collections) {
    const isDev = x.role === 'development';
    if (isDev && !window.DEV_ROLE_ENABLED) continue;
    const r = rankHit({ kind: 'collection', name: x.name }, q);
    const catMatch = isDev && x.category && has(x.category, q);
    if (r < 99 || has(x.id, q) || catMatch) {
      const scopeName = (isDev && !x.project) || !PROJECTS[x.project] ? ((s.programs || []).find(pp => pp.id === (x.program || x.program_id)) || {}).name || '—' : projectName(x.project);
      const hit = { kind: isDev ? 'devcollection' : 'collection', id: x.id, name: x.name,
        sub: `${scopeName} · ${isDev ? (x.category + ' · ') : ''}${x.items.length} parts`,
        state: isDev ? window.DC_BADGE[x.state] : x.state, rank: r < 99 ? r : 5 };
      (isDev ? devHits : colHits).push(hit);
    }
  }
  for (const x of s.boms) {
    if (x.state === 'draft') continue;
    const r = rankHit({ kind: 'bom', name: x.name }, q);
    if (r < 99 || has(x.id, q)) bomHits.push({ kind: 'bom', id: x.id, name: x.name, sub: `${projectName(x.project)} · ${x.items.length} lines`, state: window.BOM_BADGE[x.state], rank: r < 99 ? r : 5 });
  }
  for (const x of Object.values(s.projects)) {
    const r = rankHit({ kind: 'project', name: x.name }, q);
    if (r < 99) projHits.push({ kind: 'project', id: x.id, name: x.name, sub: `Lead: ${x.lead}`, rank: r });
  }
  for (const x of s.requests) {
    const r = rankHit({ kind: 'request', name: x.title }, q);
    if (r < 99 || has(x.id, q)) reqHits.push({ kind: 'request', id: x.id, name: x.title, sub: `${x.id} · from ${x.from}`, state: x.bucketState, rank: r < 99 ? r : 5 });
  }

  const byKind = { invpart: invHits, storage: stHits, supplier: supHits, collection: colHits, devcollection: devHits, bom: bomHits, project: projHits, request: reqHits };
  const ORDER = ['invpart', 'storage', 'supplier', 'collection', 'devcollection', 'bom', 'project', 'request'];
  return ORDER.map(k => ({ kind: k, items: byKind[k] })).filter(g => g.items.length);
}

const KIND_META = {
  invpart: { label: 'In inventory', icon: 'box' },
  storage: { label: 'Storage locations', icon: 'folder' },
  supplier: { label: 'Available from suppliers', icon: 'truck' },
  collection: { label: 'Designer Collections', icon: 'layers' },
  devcollection: { label: 'Development Collections', icon: 'sparkle' },
  bom: { label: 'BOMs', icon: 'boms' },
  project: { label: 'PCB Projects', icon: 'folder' },
  request: { label: 'Requests', icon: 'inbox' },
};

function routeForHit(h) {
  switch (h.kind) {
    case 'invpart': return null;
    case 'supplier': return null;
    case 'storage': return { screen: 'storageDetail', id: h.id };
    case 'collection': return { screen: 'd.collectionDetail', id: h.id };
    case 'devcollection': return { screen: 'v.collectionDetail', id: h.id };
    case 'bom': return { screen: 'p.bomOverview', id: h.id };
    case 'project': return { screen: 'projectDetail', id: h.id };
    case 'request': return { screen: 'purchasingEmbed', tab: h.id };
    default: return null;
  }
}

/* ---- The overlay component ---- */
function SearchOverlay({ open, mode, anchorRect, initialQuery, onClose, go }) {
  const [q, setQ] = useStateS('');
  const [loading, setLoading] = useStateS(false);
  const [cursor, setCursor] = useStateS(0);
  const [addFor, setAddFor] = useStateS(null); // component MPN being added
  const inputRef = useRefS(null);
  const restore = useRefS({ active: null, scrollY: 0 });
  const loadTimer = useRefS(null);
  const recents = useMemoS(() => loadRecents(), [open]);
  const [includeSuppliers, setIncludeSuppliers] = useStateS(() => sessionStorage.getItem('autobom.search.includeSuppliers') === '1');
  const toggleSuppliers = () => setIncludeSuppliers(v => { const nv = !v; sessionStorage.setItem('autobom.search.includeSuppliers', nv ? '1' : '0'); return nv; });

  // Live supplier overlay (Mouser + DigiKey) — real backend call, debounced.
  const [supLive, setSupLive] = useStateS([]);
  const [supLoading, setSupLoading] = useStateS(false);
  const supTimer = useRefS(null);
  useEffS(() => {
    clearTimeout(supTimer.current);
    if (!open || !includeSuppliers || !q.trim()) { setSupLive([]); setSupLoading(false); return; }
    setSupLoading(true);
    supTimer.current = setTimeout(async () => {
      try {
        const res = await window.api.post('/suppliers/search', { query: q.trim() });
        const m = res.mouser, d = res.digikey, hits = [];
        if (m || d) hits.push({
          kind: 'supplier', id: (m && m.mpn) || (d && d.mpn) || q, mpn: (m && m.mpn) || (d && d.mpn) || q,
          mfr: (m && m.manufacturer) || (d && d.manufacturer) || '', desc: (m && m.description) || (d && d.description) || '',
          lifecycle: (m && m.lifecycle_status) || (d && d.lifecycle_status) || '',
          mouser: m ? { pn: m.supplier_part_number, stock: m.stock, price: m.unit_price } : null,
          digikey: d ? { pn: d.supplier_part_number, stock: d.stock, price: d.unit_price } : null,
          recommend: (m && m.stock > 0) ? 'mouser' : (d && d.stock > 0) ? 'digikey' : null, rank: 1,
        });
        setSupLive(hits);
      } catch (e) { setSupLive([]); }
      finally { setSupLoading(false); }
    }, 450);
    return () => clearTimeout(supTimer.current);
  }, [q, includeSuppliers, open]);

  // capture focus + scroll on open; restore on close
  useEffS(() => {
    if (open) {
      restore.current = { active: document.activeElement, scrollY: window.scrollY };
      setQ(initialQuery || ''); setCursor(0); setAddFor(null);
      requestAnimationFrame(() => inputRef.current?.focus());
    } else if (restore.current.active && restore.current.active.focus) {
      try { restore.current.active.focus(); } catch (e) {}
    }
  }, [open]);

  useEffS(() => {
    if (!open) return;
    clearTimeout(loadTimer.current);
    if (!q.trim()) { setLoading(false); return; }
    setLoading(true);
    loadTimer.current = setTimeout(() => setLoading(false), 220);
    return () => clearTimeout(loadTimer.current);
  }, [q, open]);

  const groups = useMemoS(() => search(q, includeSuppliers), [q, includeSuppliers]);
  // Merge the live supplier group into the sync results (in ORDER position).
  const displayGroups = useMemoS(() => {
    if (!q.trim()) return groups;
    const base = groups || [];
    if (!includeSuppliers || !supLive.length) return base;
    const supGroup = { kind: 'supplier', items: supLive };
    const out = []; let inserted = false;
    for (const g of base) { out.push(g); if (g.kind === 'storage') { out.push(supGroup); inserted = true; } }
    if (!inserted) { const idx = out.findIndex(g => g.kind === 'invpart'); if (idx >= 0) out.splice(idx + 1, 0, supGroup); else out.unshift(supGroup); }
    return out;
  }, [groups, supLive, includeSuppliers, q]);
  const flat = useMemoS(() => displayGroups ? displayGroups.flatMap(g => g.items) : [], [displayGroups]);
  // clamp cursor
  useEffS(() => { if (cursor >= flat.length) setCursor(Math.max(0, flat.length - 1)); }, [flat.length]);

  const activate = (h) => {
    pushRecent({ kind: h.kind, id: h.id, label: h.name || h.mpn });
    const r = routeForHit(h);
    if (r) { onClose(); go(r); }
  };
  const copy = async (mpn) => { try { await navigator.clipboard.writeText(mpn); } catch (e) {} };

  const onKey = (e) => {
    if (e.key === 'Escape') { e.preventDefault(); onClose(); return; }
    if (e.key === 'ArrowDown') { e.preventDefault(); setCursor(c => Math.min(flat.length - 1, c + 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setCursor(c => Math.max(0, c - 1)); }
    else if (e.key === 'Enter') { const h = flat[cursor]; if (h) activate(h); }
  };

  if (!open) return null;

  // positioning
  const wrapStyle = mode === 'dropdown' && anchorRect
    ? { position: 'fixed', top: anchorRect.bottom + 6, left: anchorRect.left, width: anchorRect.width, maxWidth: 'calc(100vw - 32px)' }
    : { position: 'fixed', top: '12vh', left: '50%', transform: 'translateX(-50%)', width: 'min(640px, 92vw)' };

  return (
    <>
      {/* Transparent scrim — clicks close but the page underneath remains visible. No backdrop blur. */}
      <div className="search-scrim" onMouseDown={onClose} />
      <div className={`search-overlay ${mode}`} style={wrapStyle} onMouseDown={(e) => e.stopPropagation()}>
        <div className="search-input-wrap">
          <Icon name="search" size={17} style={{ color: 'var(--text-muted)' }} />
          <input ref={inputRef} value={q} onChange={e => { setQ(e.target.value); setCursor(0); }} onKeyDown={onKey}
            placeholder={mode === 'palette' ? 'Search anything — MPN, BOM, project, PO… (esc to close)' : 'Search parts, BOMs, projects…'}
            spellCheck={false} autoComplete="off" />
          {(loading || supLoading) ? <span className="spinner" style={{ width: 14, height: 14 }} /> : (q && <button className="icon-btn" style={{ width: 28, height: 28 }} onClick={() => { setQ(''); inputRef.current.focus(); }}><Icon name="x" size={15} /></button>)}
          <span className="kbd kbd-esc">ESC</span>
        </div>

        <div className="search-suptoggle" style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 14px', borderBottom: '1px solid var(--border-soft)' }}>
          <Icon name="truck" size={13} style={{ color: 'var(--text-muted)' }} />
          <span className="caption">Include suppliers <span style={{ color: 'var(--text-muted)' }}>(Mouser · DigiKey)</span></span>
          <button type="button" role="switch" aria-checked={includeSuppliers} className={`switch${includeSuppliers ? ' on' : ''}`} onClick={toggleSuppliers} style={{ marginLeft: 'auto' }}><span className="knob" /></button>
          <span className="caption" style={{ minWidth: 22, textAlign: 'right' }}>{includeSuppliers ? 'On' : 'Off'}</span>
        </div>

        <div className="search-body">
          {!q.trim() ? (
            <IdleView recents={recents} go={(r) => { onClose(); go(r); }} onActivate={activate} />
          ) : (!displayGroups || displayGroups.length === 0) && !supLoading ? (
            <div className="search-empty">
              <div style={{ fontWeight: 600 }}>{includeSuppliers ? `No matches found for "${q}"` : 'No matches on hand'}</div>
              <div className="caption" style={{ marginTop: 4 }}>{includeSuppliers
                ? 'Nothing in inventory, storage, or at suppliers. Try a partial MPN, or source it manually from a collection.'
                : 'Nothing matches in inventory or storage.'}</div>
              {!includeSuppliers && <button className="btn primary sm" style={{ marginTop: 12 }} onClick={toggleSuppliers}><Icon name="truck" size={13} />Include suppliers</button>}
            </div>
          ) : (
            <>
              {(displayGroups || []).map(g => (
                <div key={g.kind} className="search-group">
                  <div className="search-group-head"><Icon name={KIND_META[g.kind].icon} size={12} /><span>{KIND_META[g.kind].label}</span><span className="caption">{g.items.length}</span></div>
                  {g.items.map(h => {
                    const i = flat.indexOf(h);
                    return <ResultRow key={`${h.kind}:${h.id}`} h={h} active={i === cursor} onHover={() => setCursor(i)} onActivate={() => activate(h)}
                      onCopy={() => copy(h.mpn)} onAdd={() => setAddFor(h.mpn)} />;
                  })}
                </div>
              ))}
            </>
          )}
        </div>

        <div className="search-footer">
          <span><kbd>↑</kbd><kbd>↓</kbd> Navigate</span>
          <span><kbd>↵</kbd> Open</span>
          <span><kbd>⌘</kbd><kbd>C</kbd> Copy MPN</span>
          <span><kbd>esc</kbd> Close</span>
        </div>

        {addFor && <AddToCollectionInline mpn={addFor} onClose={() => setAddFor(null)} onDone={(name) => { setAddFor(null); window.__toast?.(`Added ${addFor} to ${name}`, 'plus'); }} />}
      </div>
    </>
  );
}

function IdleView({ recents, go, onActivate }) {
  const allCollections = useStore(s => s.collections.filter(c => c.role === 'designer'));
  return (
    <>
      {recents.length > 0 && (
        <div className="search-group">
          <div className="search-group-head"><Icon name="clock" size={12} /><span>Recent</span></div>
          {recents.slice(0, 6).map((r, i) => (
            <div key={i} className="search-row" onClick={() => {
              if (r.kind === 'invpart' || r.kind === 'supplier' || r.kind === 'component') return; // parts surface in live results, not as nav
              const route = routeForHit({ kind: r.kind, id: r.id });
              if (route) go(route);
            }}>
              <Icon name={KIND_META[r.kind]?.icon || 'history'} size={15} />
              <span className={r.kind === 'component' ? 'mono' : ''} style={{ fontWeight: 600 }}>{r.label}</span>
              <span className="caption" style={{ marginLeft: 'auto', textTransform: 'uppercase', fontSize: 10.5, letterSpacing: '.04em' }}>{KIND_META[r.kind]?.label || r.kind}</span>
            </div>
          ))}
        </div>
      )}
      <div className="search-group">
        <div className="search-group-head"><Icon name="sparkle" size={12} /><span>Jump to</span></div>
        {[
          { label: 'Designer Dashboard', icon: 'dashboard', r: { screen: 'd.dashboard' } },
          { label: 'My Collections', icon: 'layers', r: { screen: 'd.collections' } },
          { label: 'PCB Projects', icon: 'folder', r: { screen: 'projects' } },
          { label: 'Purchasing', icon: 'inbox', r: { screen: 'purchasingEmbed' } },
        ].map((it, i) => (
          <div key={i} className="search-row" onClick={() => go(it.r)}>
            <Icon name={it.icon} size={15} />
            <span style={{ fontWeight: 600 }}>{it.label}</span>
          </div>
        ))}
      </div>
    </>
  );
}

function ResultRow({ h, active, onHover, onActivate, onCopy, onAdd }) {
  const ref = useRefS(null);
  useEffS(() => { if (active) ref.current?.scrollIntoView({ block: 'nearest' }); }, [active]);

  // Part rows (PartsBox inventory + supplier overlay) — mono MPN + Copy / Add affordances.
  if (h.kind === 'invpart' || h.kind === 'supplier') {
    const eol = h.lifecycle === 'obsolete';
    const sub = h.kind === 'invpart'
      ? [h.onHand != null ? `${h.onHand} on hand` : null, h.desc].filter(Boolean).join(' · ')
      : [h.mfr, h.desc].filter(Boolean).join(' · ');
    return (
      <div ref={ref} className={`search-row${active ? ' active' : ''}`} onMouseEnter={onHover} onClick={onActivate}>
        <Icon name={h.kind === 'invpart' ? 'box' : 'truck'} size={15} style={{ color: h.kind === 'invpart' ? 'var(--success)' : 'var(--action)' }} />
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="mono" style={{ fontWeight: 600 }}>{h.mpn}
            {eol && <span className="badge filled" style={{ background: 'var(--darkred)', marginLeft: 8 }}><Icon name="ban" size={11} />EOL</span>}
            {h.kind === 'invpart' && h.low && <span className="badge filled" style={{ background: 'var(--danger)', marginLeft: 8 }}><Icon name="alert" size={10} />LOW</span>}
          </div>
          <div className="caption" style={{ marginTop: 1 }}>{sub}</div>
        </div>
        <div className="search-actions">
          <button className="btn sm ghost" onClick={(e) => { e.stopPropagation(); onCopy(); }} title="Copy MPN"><Icon name="clipboard" size={13} />Copy</button>
          <button className="btn sm primary" onClick={(e) => { e.stopPropagation(); onAdd(); }} title="Add to collection"><Icon name="plus" size={13} />Add</button>
        </div>
      </div>
    );
  }

  // Storage location rows — first-class result; click opens the in-app detail route.
  if (h.kind === 'storage') {
    const tag = h.storageKind === 'project' ? 'production' : 'development';
    const preview = h.parts.slice(0, 4);
    return (
      <div ref={ref} className={`search-row${active ? ' active' : ''}`} onMouseEnter={onHover} onClick={onActivate} style={{ alignItems: 'flex-start' }}>
        <Icon name="folder" size={15} style={{ color: 'var(--text-secondary)', marginTop: 2 }} />
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span className="mono" style={{ fontWeight: 600 }}>{h.name}</span>
            <span className={`loc-chip ${h.storageKind}`}>{tag}</span>
            <span className="caption">{h.parts.length} part{h.parts.length === 1 ? '' : 's'} · {h.units} units</span>
          </div>
          <div className="caption" style={{ marginTop: 2 }}>{preview.map(p => p.mpn).join(', ')}{h.parts.length > preview.length ? ` + ${h.parts.length - preview.length} more` : ''}</div>
        </div>
        <Icon name="chevright" size={15} style={{ color: 'var(--text-muted)' }} />
      </div>
    );
  }

  return (
    <div ref={ref} className={`search-row${active ? ' active' : ''}`} onMouseEnter={onHover} onClick={onActivate}>
      <Icon name={KIND_META[h.kind].icon} size={15} />
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ fontWeight: 600 }}>{h.name}{h.kind !== 'project' && h.id && <span className="mono caption" style={{ marginLeft: 8 }}>{h.id}</span>}</div>
        {h.sub && <div className="caption" style={{ marginTop: 1 }}>{h.sub}</div>}
      </div>
      {h.state && <StatusBadge status={h.state} />}
    </div>
  );
}

function AddToCollectionInline({ mpn, onClose, onDone }) {
  const collections = useStore(s => s.collections.filter(c => c.role === 'designer' && ['active', 'rejected'].includes(c.state)));
  return (
    <div className="add-popover">
      <div className="menu-label">Add {mpn} to…</div>
      {collections.map(x => (
        <div key={x.id} className="mi" onClick={() => { storeActions.addToCollection(mpn, x.id, x.name); onDone(x.name); }}>
          <Icon name="layers" size={15} style={{ color: 'var(--role-designer)' }} /><span>{x.name}</span><span className="mi-sub">{projectName(x.project)}</span>
        </div>
      ))}
      <div className="mi new" onClick={() => { const name = mpn + ' research'; storeActions.addToCollection(mpn, null, name); onDone(name); }}>
        <Icon name="plus" size={15} />Create new collection…
      </div>
      <div className="mi" style={{ color: 'var(--text-muted)', borderTop: '1px solid var(--border-soft)', marginTop: 4 }} onClick={onClose}><Icon name="x" size={14} />Cancel</div>
    </div>
  );
}

Object.assign(window, { SearchOverlay, pushRecent });
