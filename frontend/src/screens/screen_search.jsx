/* global React, Icon, StatusBadge, SupplierTag, Banner, EmptyState, Freshness, Popover,
   CATALOG, useStore, PROJECTS, RECENT_SEARCHES, fmtUSD, fmtInt */
const { useState: useStateSearch, useRef: useRefSearch, useEffect: useEffSearch } = React;

function findMatches(q) {
  const s = q.trim().toUpperCase();
  if (!s) return [];
  return Object.values(CATALOG).filter(c =>
    c.mpn.toUpperCase().includes(s) || c.mfr.toUpperCase().includes(s) || c.desc.toUpperCase().includes(s)
  );
}

function SupplierResultCard({ name, supplier, off, recommended }) {
  const zero = off.stock === 0;
  return (
    <div className={`supcard${recommended ? ' recommended' : ''}`}>
      <div className="supcard-head">
        <SupplierTag supplier={supplier} />
        {recommended && <span className="rec-flag">Recommended</span>}
        {zero && !recommended && <span className="rec-flag" style={{ color: 'var(--danger)', background: 'var(--danger-soft)' }}>Zero stock</span>}
      </div>
      <div className="supcard-body">
        <div className="sup-line"><span className="sl-k">Stock</span>
          <span style={{ fontWeight: 600, color: zero ? 'var(--danger)' : 'var(--success)' }}>{zero ? '0 — no stock' : fmtInt(off.stock)}</span></div>
        <div className="sup-line"><span className="sl-k">Unit price</span><span className="mono" style={{ fontWeight: 600 }}>{off.price ? fmtUSD(off.price) : '—'}</span></div>
        <div className="sup-line"><span className="sl-k">Supplier PN</span><span className="mono">{off.pn}</span></div>
        <a className="sup-line" href={off.url} style={{ marginTop: 2 }} onClick={e => e.preventDefault()}>
          <span style={{ color: 'var(--action)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 5 }}>
            View on {supplier === 'mouser' ? 'Mouser' : 'DigiKey'} <Icon name="external" size={13} /></span>
        </a>
      </div>
    </div>
  );
}

function ResultCard({ c, onAdd }) {
  const addRef = useRefSearch(null);
  const [menu, setMenu] = useStateSearch(false);
  const eol = c.lifecycle === 'obsolete';
  const addable = useStore(s => s.collections.filter(x => x.role === 'designer' && ['active', 'rejected'].includes(x.state)));

  return (
    <div className="card" style={{ overflow: 'visible' }}>
      <div style={{ padding: '15px 18px', borderBottom: '1px solid var(--border-soft)', display: 'flex', alignItems: 'flex-start', gap: 14 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <span className="mono" style={{ fontSize: 17, fontWeight: 600 }}>{c.mpn}</span>
            <StatusBadge status={eol ? 'obsolete' : 'active'} />
          </div>
          <div className="secondary" style={{ marginTop: 4 }}>{c.mfr} · {c.desc}</div>
        </div>
        <div style={{ position: 'relative', flex: 'none' }}>
          <button ref={addRef} className="btn primary" onClick={() => setMenu(m => !m)}>
            <Icon name="plus" size={15} />Add to Collection<Icon name="chevdown" size={14} />
          </button>
          <Popover anchorRef={addRef} open={menu} onClose={() => setMenu(false)} align="right" width={260}>
            <div className="menu-label">Add to collection</div>
            {addable.map(x => (
              <div key={x.id} className="mi" onClick={() => { setMenu(false); onAdd(c.mpn, { id: x.id, name: x.name }); }}>
                <Icon name="layers" size={15} style={{ color: 'var(--role-designer)' }} />
                <span>{x.name}</span><span className="mi-sub">{projectName(x.project)}</span>
              </div>
            ))}
            <div className="mi new" onClick={() => { setMenu(false); onAdd(c.mpn, { id: null, name: c.mpn + ' research' }); }}>
              <Icon name="plus" size={15} />Create new collection…
            </div>
          </Popover>
        </div>
      </div>

      {eol && (
        <div style={{ padding: '0 18px' }}>
          <Banner kind="danger" icon="ban" title="Obsolete / End-of-Life">
            {c.note || 'This part is not recommended for new designs.'} Consider a replacement before adding it to a production BOM.
          </Banner>
        </div>
      )}

      <div style={{ padding: '16px 18px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 11 }}>
          <span className="label" style={{ fontWeight: 700 }}>Supplier sourcing</span>
          <Freshness ts={c.fresh} stale={c.stale} />
          {c.recommend && <span style={{ marginLeft: 'auto', fontSize: 12.5, color: 'var(--text-secondary)' }}>
            Decision engine recommends <strong style={{ color: c.recommend === 'mouser' ? 'var(--supplier-mouser)' : 'var(--supplier-digikey)' }}>{c.recommend === 'mouser' ? 'Mouser' : 'DigiKey'}</strong></span>}
        </div>
        <div className="supplier-grid">
          <SupplierResultCard name={c.mpn} supplier="mouser" off={c.mouser} recommended={c.recommend === 'mouser'} />
          <SupplierResultCard name={c.mpn} supplier="digikey" off={c.digikey} recommended={c.recommend === 'digikey'} />
        </div>
        {c.stale && <div style={{ marginTop: 12 }}>
          <Banner kind="warn" title="Sourcing data is stale">Pricing and stock for this part are older than 24 hours. Re-check before requesting an order.</Banner>
        </div>}
      </div>
    </div>
  );
}

function SearchScreen({ onAdd }) {
  const [query, setQuery] = useStateSearch('');
  const [submitted, setSubmitted] = useStateSearch('');
  const [phase, setPhase] = useStateSearch('idle'); // idle | cache | live | done
  const inputRef = useRefSearch(null);
  const timers = useRefSearch([]);

  useEffSearch(() => () => timers.current.forEach(clearTimeout), []);

  const run = (q) => {
    timers.current.forEach(clearTimeout); timers.current = [];
    setQuery(q); setSubmitted(q); setPhase('cache');
    timers.current.push(setTimeout(() => setPhase('live'), 520));
    timers.current.push(setTimeout(() => setPhase('done'), 1180));
  };
  const results = phase === 'done' ? findMatches(submitted) : [];

  return (
    <div className="page">
      <div className="page-head">
        <div className="ph-titles">
          <div className="display">Part Search</div>
          <div className="ph-sub">Search Mouser and DigiKey by MPN, partial MPN, or manufacturer. Save parts into a collection.</div>
        </div>
      </div>

      <div className="searchfield" style={{ height: 46, fontSize: 15, marginBottom: 18 }}>
        <Icon name="search" size={18} style={{ color: 'var(--text-muted)' }} />
        <input ref={inputRef} value={query} placeholder="Search by MPN, partial MPN (4+ chars), or manufacturer + MPN…"
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && query.trim()) run(query); }} />
        {query && <button className="icon-btn" style={{ width: 30, height: 30 }} onClick={() => { setQuery(''); setPhase('idle'); inputRef.current.focus(); }}><Icon name="x" size={16} /></button>}
        <button className="btn primary" disabled={!query.trim()} onClick={() => run(query)}>Search</button>
      </div>

      {/* IDLE */}
      {phase === 'idle' && (
        <EmptyState icon="search" title="Search by MPN, partial MPN (4+ chars), or Manufacturer + MPN."
          sub="Results show live stock and pricing from Mouser and DigiKey, plus the recommended supplier."
          actions={
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'center' }}>
              {RECENT_SEARCHES.map(s => (
                <button key={s} className="fchip" onClick={() => run(s)}><Icon name="history" size={13} /><span className="mono">{s}</span></button>
              ))}
            </div>} />
      )}

      {/* SEARCHING */}
      {(phase === 'cache' || phase === 'live') && (
        <div className="card" style={{ padding: '34px 24px', textAlign: 'center' }}>
          <div className="spinner" style={{ margin: '0 auto 14px' }} />
          <div style={{ fontWeight: 600 }}>{phase === 'cache' ? 'Searching cached sourcing data…' : 'Checking live with Mouser + DigiKey…'}</div>
          <div className="caption" style={{ marginTop: 4 }}>Query: <span className="mono">{submitted}</span></div>
          <div style={{ display: 'flex', gap: 18, justifyContent: 'center', marginTop: 14 }}>
            <span className="caption" style={{ display: 'flex', alignItems: 'center', gap: 6 }}><Icon name="check" size={13} style={{ color: 'var(--success)' }} />Cache</span>
            <span className="caption" style={{ display: 'flex', alignItems: 'center', gap: 6, color: phase === 'live' ? 'var(--info)' : undefined }}>
              {phase === 'live' ? <span className="spinner" style={{ width: 13, height: 13 }} /> : <Icon name="clock" size={13} />}Live suppliers</span>
          </div>
        </div>
      )}

      {/* RESULTS */}
      {phase === 'done' && results.length > 0 && (
        <div style={{ display: 'grid', gap: 14 }}>
          <div className="caption">{results.length} result{results.length > 1 ? 's' : ''} for <span className="mono">{submitted}</span></div>
          {results.map(c => <ResultCard key={c.mpn} c={c} onAdd={onAdd} />)}
        </div>
      )}

      {/* NOT FOUND */}
      {phase === 'done' && results.length === 0 && (
        <EmptyState icon="search" title={`No results for "${submitted}".`}
          sub="Try a partial MPN (4+ characters) or include the manufacturer name. Check for typos in the part number."
          actions={<button className="btn" onClick={() => { setQuery(''); setPhase('idle'); }}>Clear search</button>} />
      )}
    </div>
  );
}

Object.assign(window, { SearchScreen });
