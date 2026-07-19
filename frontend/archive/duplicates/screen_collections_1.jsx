/* global React, Icon, StatusBadge, RoleDot, SupplierTag, EmptyState,
   useStore, PROJECTS, fmtUSD, fmtInt */
const { useState: useStateColl } = React;

const COLL_FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'active', label: 'Active' },
  { key: 'order-requested', label: 'Order requested' },
  { key: 'rejected', label: 'Rejected' },
  { key: 'ordered', label: 'Ordered' },
];

function collSummary(c) {
  const review = c.items.filter(i => i.status === 'needs-review' || i.stale).length;
  const mouser = c.items.filter(i => i.supplier === 'mouser').length;
  const digikey = c.items.filter(i => i.supplier === 'digikey').length;
  const est = c.items.reduce((a, i) => a + (i.ext || 0), 0);
  return { review, mouser, digikey, est };
}

function CollectionListScreen({ go, demoEmpty }) {
  const [ls, setLs] = window.useListState('d.collections', { filter: 'all', q: '' });
  const filter = ls.filter, q = ls.q;
  const [showNew, setShowNew] = React.useState(false);
  const setFilter = (v) => setLs({ filter: v });
  const setQ = (v) => setLs({ q: v });
  const all = useStore(s => s.collections.filter(c => c.role === 'designer'));
  const programs = useStore(s => s.programs || []);
  const scopeName = (c) => (c.project && PROJECTS[c.project]) ? PROJECTS[c.project].name : ((programs.find(p => p.id === c.program_id) || {}).name || '—');
  const source = demoEmpty ? [] : all;

  let rows = source.filter(c => filter === 'all' ? true : c.state === filter);
  if (q.trim()) {
    const s = q.toLowerCase();
    rows = rows.filter(c => c.name.toLowerCase().includes(s) || scopeName(c).toLowerCase().includes(s));
  }

  const counts = {};
  COLL_FILTERS.forEach(f => counts[f.key] = f.key === 'all' ? source.length : source.filter(c => c.state === f.key).length);
  const attentionCount = source.filter(c => c.items.some(i => i.status === 'needs-review')).length;

  return (
    <div className="page">
      <div className="page-head">
        <div className="ph-titles">
          <div className="display">Collections</div>
          <div className="ph-sub">Your engineering research workspaces. Save parts here while you investigate, then request an order.</div>
        </div>
        <div className="ph-actions">
          <button className="btn" onClick={() => window.__openSearch('palette')}><Icon name="search" size={15} />Search a part <span className="kbd" style={{ marginLeft: 6 }}>⌘K</span></button>
          <button className="btn primary" onClick={() => setShowNew(true)}><Icon name="plus" size={15} />New Collection</button>
        </div>
      </div>

      {attentionCount > 0 && !demoEmpty && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '9px 14px', background: 'var(--danger-soft)', border: '1px solid #f3c2c2', borderRadius: 8, color: '#9b2222', marginBottom: 16, fontSize: 13 }}>
          <Icon name="alert" size={16} />
          <span><strong>{attentionCount} collection{attentionCount > 1 ? 's' : ''}</strong> need your attention — exceptions flagged or a request was rejected.</span>
        </div>
      )}

      <div className="filterbar">
        {COLL_FILTERS.map(f => (
          <button key={f.key} className={`fchip${filter === f.key ? ' active' : ''}`} onClick={() => setFilter(f.key)}>
            {f.label}<span className="fc-n">{counts[f.key]}</span>
          </button>
        ))}
        <div className="searchfield" style={{ marginLeft: 'auto', minWidth: 240 }}>
          <Icon name="search" size={15} style={{ color: 'var(--text-muted)' }} />
          <input value={q} placeholder="Filter collections…" onChange={e => setQ(e.target.value)} />
        </div>
      </div>

      <div className="tbl-wrap" style={{ borderRadius: '0 0 10px 10px', borderTop: 0 }}>
        {rows.length === 0 ? (
          demoEmpty ? (
            <EmptyState icon="layers" title="You don't have any collections yet."
              sub="A collection is an open research space for parts you're investigating. Start by searching for a part."
              actions={<>
                <button className="btn primary" onClick={() => window.__openSearch('palette')}><Icon name="search" size={14} />Search a part</button>
                <button className="btn" onClick={() => setShowNew(true)}><Icon name="plus" size={14} />New Collection</button>
              </>} />
          ) : (
            <EmptyState icon="filter" title="No collections match this filter."
              sub="Try a different status filter or clear your search."
              actions={<button className="btn" onClick={() => { setFilter('all'); setQ(''); }}>Clear filters</button>} />
          )
        ) : rows.map(c => {
          const s = collSummary(c);
          const flagged = c.items.some(i => i.status === 'needs-review');
          return (
            <div key={c.id} className="lrow" onClick={() => go({ screen: 'd.collectionDetail', id: c.id })}
              style={{ boxShadow: `inset 3px 0 0 ${flagged ? 'var(--danger)' : 'var(--role-designer)'}` }}>
              <div style={{ minWidth: 0 }}>
                <div className="lr-title" style={{ display: 'flex', alignItems: 'center', gap: 9, flexWrap: 'wrap' }}>
                  {window.DevKindGlyph && <window.DevKindGlyph kind="designer" size={13} />}
                  <span>{c.name}</span>
                  <StatusBadge status={c.state} />
                </div>
                <div className="lr-meta">
                  <span className="mono">{c.id}</span>
                  <span className="tr-sep" />
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}><Icon name="folder" size={13} />{scopeName(c)}</span>
                  <span className="tr-sep" />
                  <span>{c.items.length} part{c.items.length !== 1 ? 's' : ''}</span>
                  <span className="tr-sep" />
                  <span>updated {c.updated}</span>
                  {s.review > 0 && <><span className="tr-sep" /><span style={{ color: 'var(--warning)', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: 4 }}><Icon name="alert" size={12} />{s.review} need review</span></>}
                </div>
              </div>
              <div className="lr-right">
                <div className="lr-stats">
                  {s.mouser > 0 && <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}><span className="dot" style={{ background: 'var(--supplier-mouser)' }} /><b>{s.mouser}</b> Mouser</span>}
                  {s.digikey > 0 && <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}><span className="dot" style={{ background: 'var(--supplier-digikey)' }} /><b>{s.digikey}</b> DigiKey</span>}
                  {s.est > 0 && <span>est. <b className="mono">{fmtUSD(s.est)}</b></span>}
                </div>
              </div>
            </div>
          );
        })}
      </div>
      {showNew && <NewCollectionModal kind="designer" onClose={() => setShowNew(false)} onCreated={(id) => { setShowNew(false); go({ screen: 'd.collectionDetail', id }); }} />}
    </div>
  );
}

Object.assign(window, { CollectionListScreen });
