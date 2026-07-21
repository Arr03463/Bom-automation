/* global React, Icon, StatusBadge, RoleTag, RoleDot, SupplierTag, Banner, EmptyState, Avatar, NeedsAttention,
   useStore, PROJECTS, fmtUSD, fmtInt */
const { useState: useStateDash } = React;

function StatePeek({ value, onChange, options }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span className="caption" style={{ display: 'flex', alignItems: 'center', gap: 5 }}><Icon name="sparkle" size={13} /> Preview state</span>
      <div style={{ display: 'inline-flex', border: '1px solid var(--border)', borderRadius: 7, overflow: 'hidden' }}>
        {options.map(o => (
          <button key={o.v} onClick={() => onChange(o.v)} style={{ border: 0, padding: '6px 11px', fontSize: 12.5, fontWeight: 600, cursor: 'pointer',
            background: value === o.v ? 'var(--action-soft)' : 'var(--bg-surface)', color: value === o.v ? 'var(--action)' : 'var(--text-secondary)',
            borderRight: o.last ? 0 : '1px solid var(--border)' }}>{o.label}</button>
        ))}
      </div>
    </div>
  );
}

function DashboardScreen({ go, flashId }) {
  const [state, setState] = useStateDash('default');
  const collections = useStore(s => s.collections.filter(c => c.role === 'designer'));
  const programs = useStore(s => s.programs || []);
  const me = useStore(s => s.users.find(u => u.id === s.currentUserId));
  const isNew = state === 'new';

  const myCollections = isNew ? [] : collections;
  const myPrograms = programs.filter(p => !me || p.owner === me.name);
  const recentPrograms = isNew ? [] : (myPrograms.length ? myPrograms : programs);
  const activeCount = collections.filter(c => c.state === 'active').length;
  const openReq = collections.filter(c => ['order-requested', 'rejected'].includes(c.state)).length;
  const reviewItems = collections.reduce((a, c) => a + c.items.filter(i => i.status === 'needs-review' || i.stale).length, 0);

  return (
    <div className="page">
      <div className="page-head">
        <div className="ph-titles"><div className="display">Good afternoon, Aaron</div>
          <div className="ph-sub">Your dashboard is your inbox — act on what needs you, right here.</div></div>
        <div className="ph-actions">
          <StatePeek value={state} onChange={setState} options={[{ v: 'default', label: 'Default' }, { v: 'new', label: 'New user', last: true }]} />
        </div>
      </div>

      {/* v1.3-rev: Dashboard IS the operational inbox. Every card acts inline. */}
      <NeedsAttention role="designer" go={go} flashId={flashId} preview={state} />

      <div className="stat-row" style={{ marginBottom: 18 }}>
        <div className="stat"><div className="st-label"><Icon name="layers" size={13} /> Active collections</div><div className="st-num">{isNew ? 0 : activeCount}</div><div className="st-sub">in research</div></div>
        <div className="stat"><div className="st-label"><Icon name="arrow" size={13} /> Open requests</div><div className="st-num">{isNew ? 0 : openReq}</div><div className="st-sub">{isNew ? '—' : 'awaiting + rejected'}</div></div>
        <div className="stat"><div className="st-label"><Icon name="alert" size={13} style={{ color: 'var(--warning)' }} /> Items needing review</div><div className="st-num" style={{ color: isNew ? undefined : 'var(--warning)' }}>{isNew ? 0 : reviewItems}</div><div className="st-sub">across collections</div></div>
        <div className="stat"><div className="st-label"><Icon name="folder" size={13} /> Programs</div><div className="st-num">{isNew ? 0 : myPrograms.length}</div><div className="st-sub">{isNew ? '—' : 'you own'}</div></div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 18, alignItems: 'start' }}>
        <div className="panel">
          <div className="panel-head"><Icon name="layers" size={16} /><span className="ph-title">My Collections</span>
            <button className="btn-link" style={{ marginLeft: 'auto' }} onClick={() => go({ screen: 'd.collections' })}>View all</button></div>
          {myCollections.length === 0 ? (
            <EmptyState icon="layers" title="You don't have any collections yet." sub="Create a collection to gather candidate parts for a program."
              actions={<button className="btn primary sm" onClick={() => go({ screen: 'd.collections' })}><Icon name="layers" size={14} />Go to Collections</button>} />
          ) : myCollections.slice(0, 5).map(c => (
            <div key={c.id} className="attn-item" style={{ cursor: 'pointer' }} onClick={() => go({ screen: 'd.collectionDetail', id: c.id })}>
              <div className="attn-main"><div style={{ display: 'flex', alignItems: 'center', gap: 9 }}><span style={{ fontWeight: 600, fontSize: 14 }}>{c.name}</span><StatusBadge status={c.state} /></div>
                <div className="am-meta">{(c.project && PROJECTS[c.project]) ? PROJECTS[c.project].name : ((programs.find(p => p.id === (c.program || c.program_id)) || {}).name || '—')} · {c.items.length} part{c.items.length !== 1 ? 's' : ''} · updated {window.fmtWhen(c.updated)}</div></div>
              <Icon name="chevright" size={16} style={{ color: 'var(--text-muted)' }} />
            </div>
          ))}
        </div>
        <div className="panel">
          <div className="panel-head"><Icon name="folder" size={16} /><span className="ph-title">Recent Programs</span>
            <button className="btn-link" style={{ marginLeft: 'auto' }} onClick={() => go({ screen: 'programs' })}>View all</button></div>
          {recentPrograms.length === 0 ? (
            <EmptyState icon="folder" title="No programs yet." sub="Programs group your Projects and Collections under one contract or product line." />
          ) : recentPrograms.slice(0, 5).map(p => (
            <div key={p.id} className="attn-item" style={{ cursor: 'pointer' }} onClick={() => go({ screen: 'programDetail', id: p.id })}>
              <div className="attn-main"><div style={{ display: 'flex', alignItems: 'center', gap: 9 }}><span className="mono caption" style={{ fontWeight: 700 }}>{p.code}</span><span style={{ fontWeight: 600, fontSize: 14 }}>{p.name}</span></div>
                <div className="am-meta">{p.projects.length} project{p.projects.length !== 1 ? 's' : ''}{p.customer ? ` · ${p.customer}` : ''} · owner {p.owner}</div></div>
              <Icon name="chevright" size={16} style={{ color: 'var(--text-muted)' }} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { DashboardScreen, StatePeek });
