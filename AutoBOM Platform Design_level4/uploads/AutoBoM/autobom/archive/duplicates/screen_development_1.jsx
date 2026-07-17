/* global React, Icon, StatusBadge, RoleTag, RoleDot, Avatar, Banner, EmptyState, TraceabilityStrip,
   RelatedLinks, useStore, storeActions, PROJECTS, fmtUSD, fmtInt */
const { useState: useStateV, useRef: useRefV } = React;

/* Map a dev-object state → badge key for the unified StatusBadge */
const DEV_BADGE = {
  investigation: { open: 'inv-open', analysis: 'inv-analysis', findings: 'inv-findings', closed: 'inv-closed' },
  recommendation: { draft: 'rec-draft', pushed: 'rec-pushed', accepted: 'rec-accepted', rejected: 'rec-rejected', investigating: 'rec-investigating' },
  rework: { draft: 'rw-draft', pushed: 'rw-pushed', inprogress: 'rw-inprogress', validated: 'rw-validated', returned: 'rw-returned' },
  firmware: { draft: 'fw-draft', released: 'fw-released', validating: 'fw-validating', validated: 'fw-validated' },
};
const DEV_KIND_META = {
  investigation: { label: 'Investigation', icon: 'search', listScreen: 'v.investigations', detailScreen: 'v.investigationDetail' },
  recommendation: { label: 'Improvement Recommendation', icon: 'sparkle', listScreen: 'v.recommendations', detailScreen: 'v.recommendationDetail' },
  rework: { label: 'Rework Package', icon: 'refresh', listScreen: 'v.rework', detailScreen: 'v.reworkDetail' },
  firmware: { label: 'Firmware Release', icon: 'upload', listScreen: 'v.firmware', detailScreen: 'v.firmwareDetail' },
};

function findObj(state, kind, id) {
  const map = { investigation: 'investigations', recommendation: 'recommendations', rework: 'reworks', firmware: 'firmwares' };
  return state[map[kind]].find(x => x.id === id);
}

/* ---------- Development Dashboard ---------- */
function DevelopmentDashboard({ go }) {
  const investigations = useStore(s => s.investigations);
  const recommendations = useStore(s => s.recommendations);
  const reworks = useStore(s => s.reworks);
  const firmwares = useStore(s => s.firmwares);
  const devCols = useStore(s => s.collections.filter(c => c.role === 'development'));

  const colsActive = devCols.filter(c => c.state === 'active');
  const colsAwaiting = devCols.filter(c => c.state === 'recommendation-sent');
  const colsRecent = [...devCols].sort((a, b) => (a.updated > b.updated ? -1 : 1)).slice(0, 4);

  // Handshakes awaiting action by another team
  const handshakes = [
    ...recommendations.filter(r => r.state === 'pushed').map(r => ({ kind: 'recommendation', obj: r, dir: 'out', team: 'Designer', actor: 'Designer' })),
    ...recommendations.filter(r => r.state === 'investigating').map(r => ({ kind: 'recommendation', obj: r, dir: 'in', team: 'Designer', actor: r.response?.by || 'Designer' })),
    ...reworks.filter(r => r.state === 'pushed' || r.state === 'inprogress').map(r => ({ kind: 'rework', obj: r, dir: 'out', team: 'Production', actor: 'Production' })),
    ...reworks.filter(r => r.state === 'returned').map(r => ({ kind: 'rework', obj: r, dir: 'in', team: 'Production', actor: r.results?.returnedBy })),
    ...firmwares.filter(f => f.state === 'validating').map(f => ({ kind: 'firmware', obj: f, dir: 'out', team: 'Production', actor: 'Production' })),
    ...investigations.filter(i => i.pushedFrom && i.state !== 'closed').map(i => ({ kind: 'investigation', obj: i, dir: 'in', team: i.pushedFrom.role, actor: i.pushedFrom.by })),
  ];

  const stats = [
    { label: 'Active Collections', n: colsActive.length, icon: 'layers' },
    { label: 'Awaiting Review', n: colsAwaiting.length, icon: 'send' },
    { label: 'Investigations in progress', n: investigations.filter(i => i.state !== 'closed').length, icon: 'search' },
    { label: 'Recs / Rework / FW open', n: recommendations.filter(r => r.state === 'pushed' || r.state === 'investigating').length + reworks.filter(r => r.state === 'pushed' || r.state === 'inprogress').length + firmwares.filter(f => f.state === 'validating').length, icon: 'refresh' },
  ];

  return (
    <div className="page">
      <div className="page-head">
        <div className="ph-titles"><div className="display">Development workspace</div>
          <div className="ph-sub">Investigate, improve, rework, release. You close the loop on every product.</div></div>
        <div className="ph-actions">
          <button className="btn" onClick={() => go({ screen: 'v.collections' })}><Icon name="layers" size={15} />New Development Collection</button>
          <button className="btn primary" style={{ background: 'var(--role-development)', borderColor: 'var(--role-development)' }} onClick={() => go({ screen: 'v.collections' })}><Icon name="plus" size={15} />Start Investigation</button>
        </div>
      </div>

      <div className="stat-row" style={{ marginBottom: 18 }}>
        {stats.map((s, i) => (
          <div key={i} className="stat"><div className="st-label"><Icon name={s.icon} size={13} style={{ color: 'var(--role-development)' }} /> {s.label}</div><div className="st-num" style={{ color: 'var(--role-development)' }}>{s.n}</div></div>
        ))}
      </div>

      {/* My Development Collections — card strip, most recently modified */}
      <div className="panel" style={{ marginBottom: 18 }}>
        <div className="panel-head"><Icon name="layers" size={16} style={{ color: 'var(--role-development)' }} /><span className="ph-title">My Development Collections</span>
          <button className="btn-link" style={{ marginLeft: 'auto' }} onClick={() => go({ screen: 'v.collections' })}>View all →</button></div>
        {colsRecent.length === 0 ? <EmptyState icon="layers" title="No development collections yet." sub="Start by creating a collection to investigate a question."
          actions={<button className="btn primary sm" onClick={() => go({ screen: 'v.collections' })}><Icon name="plus" size={14} />New collection</button>} />
        : <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 12, padding: 14 }}>
          {colsRecent.map(c => (
            <div key={c.id} className="card" style={{ padding: 14, cursor: 'pointer', borderLeft: '3px solid var(--role-development)' }} onClick={() => go({ screen: 'v.collectionDetail', id: c.id })}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 7 }}>
                {window.DevKindGlyph && <window.DevKindGlyph kind="development" size={13} />}
                <span style={{ fontWeight: 600, fontSize: 14, flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.name}</span>
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
                <StatusBadge status={window.DC_BADGE[c.state]} />
                {window.CategoryChip && <window.CategoryChip category={c.category} />}
              </div>
              <div className="caption">{PROJECTS[c.project].name} · {c.items.length} candidate{c.items.length !== 1 ? 's' : ''} · {c.updated}</div>
            </div>
          ))}
        </div>}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 18, alignItems: 'start', marginBottom: 18 }}>
        {/* Active investigations (collections) */}
        <div className="panel">
          <div className="panel-head"><Icon name="search" size={16} style={{ color: 'var(--role-development)' }} /><span className="ph-title">Active Investigations</span></div>
          {colsActive.length === 0 ? <EmptyState icon="search" title="No active investigations." />
          : colsActive.map(c => (
            <div key={c.id} className="attn-item" style={{ cursor: 'pointer' }} onClick={() => go({ screen: 'v.collectionDetail', id: c.id })}>
              <div className="attn-main">
                <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}><span style={{ fontWeight: 600, fontSize: 14 }}>{c.name}</span>{window.CategoryChip && <window.CategoryChip category={c.category} />}</div>
                <div className="am-meta">{PROJECTS[c.project].name} · {c.items.length} candidate{c.items.length !== 1 ? 's' : ''} · updated {c.updated}</div>
              </div>
              <Icon name="chevright" size={16} style={{ color: 'var(--text-muted)' }} />
            </div>
          ))}
        </div>

        {/* Recommendations awaiting review (collections that generated an outcome and are pending response) */}
        <div className="panel">
          <div className="panel-head"><Icon name="send" size={16} style={{ color: 'var(--role-development)' }} /><span className="ph-title">Recommendations Awaiting Review</span></div>
          {colsAwaiting.length === 0 ? <EmptyState icon="check" title="No outcomes awaiting response." />
          : colsAwaiting.map(c => {
            const o = c.outcomes && c.outcomes[0];
            return (
              <div key={c.id} className="attn-item" style={{ cursor: 'pointer' }} onClick={() => go({ screen: 'v.collectionDetail', id: c.id })}>
                <div className="attn-main">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 9, flexWrap: 'wrap' }}>
                    <span style={{ fontWeight: 600, fontSize: 14 }}>{c.name}</span>
                    {o && <span className="mono caption">{o.linkedId}</span>}
                  </div>
                  <div className="am-meta">{o ? <>{o.label} → <RoleTag role={o.targetRole} /> · {o.when}</> : 'Awaiting'}</div>
                </div>
                <Icon name="chevright" size={16} style={{ color: 'var(--text-muted)' }} />
              </div>
            );
          })}
        </div>
      </div>

      {/* Cross-team handshakes (unchanged behaviour) */}
      <div className="panel">
        <div className="panel-head"><Icon name="link" size={16} style={{ color: 'var(--role-development)' }} /><span className="ph-title">Cross-team Handshakes</span><span className="ph-meta">{handshakes.length} active</span></div>
        {handshakes.length === 0 ? <EmptyState icon="check" title="No active handshakes." />
        : handshakes.map(({ kind, obj, dir, team }) => (
          <div key={kind + obj.id} className="attn-item" style={{ cursor: 'pointer' }} onClick={() => go({ screen: DEV_KIND_META[kind].detailScreen, id: obj.id })}>
            <div className="attn-icon" style={{ background: dir === 'out' ? 'var(--success-soft)' : 'var(--info-soft)', color: dir === 'out' ? 'var(--role-development)' : 'var(--info)' }}><Icon name={dir === 'out' ? 'send' : 'inbox'} size={18} /></div>
            <div className="attn-main">
              <div style={{ display: 'flex', alignItems: 'center', gap: 9, flexWrap: 'wrap' }}>
                <span className="caption" style={{ fontWeight: 700, color: 'var(--role-development)', textTransform: 'uppercase', fontSize: 10.5, letterSpacing: '.04em' }}>{dir === 'out' ? `Awaiting ${team}` : `From ${team}`}</span>
                <span className="mono caption">{obj.id}</span>
              </div>
              <div className="am-title">{obj.title}</div>
              <div className="am-meta">{DEV_KIND_META[kind].label} · {PROJECTS[obj.project].name} · updated {obj.updated}</div>
            </div>
            <div className="am-action"><StatusBadge status={DEV_BADGE[kind][obj.state]} /></div>
          </div>
        ))}
      </div>
    </div>
  );
}

function DevList({ title, icon, items, kind, go }) {
  return (
    <div className="panel">
      <div className="panel-head"><Icon name={icon} size={16} /><span className="ph-title">{title}</span></div>
      {items.length === 0 ? <EmptyState icon={icon} title={`No ${DEV_KIND_META[kind].label.toLowerCase()}s active.`} />
      : items.slice(0, 5).map(it => (
        <div key={it.id} className="attn-item" style={{ cursor: 'pointer' }} onClick={() => go({ screen: DEV_KIND_META[kind].detailScreen, id: it.id })}>
          <div className="attn-main">
            <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}><span style={{ fontWeight: 600, fontSize: 14 }}>{it.title}</span><StatusBadge status={DEV_BADGE[kind][it.state]} /></div>
            <div className="am-meta">{PROJECTS[it.project].name} · {it.assignee} · updated {it.updated}</div>
          </div>
          <Icon name="chevright" size={16} style={{ color: 'var(--text-muted)' }} />
        </div>
      ))}
    </div>
  );
}

/* ---------- Generic list (used by all four dev object types) ---------- */
const FILTERS_BY_KIND = {
  investigation: [['all', 'All'], ['open', 'Open'], ['analysis', 'Analysis'], ['findings', 'Findings'], ['closed', 'Closed']],
  recommendation: [['all', 'All'], ['draft', 'Draft'], ['pushed', 'Awaiting designer'], ['investigating', 'Investigating'], ['accepted', 'Accepted'], ['rejected', 'Rejected']],
  rework: [['all', 'All'], ['draft', 'Draft'], ['pushed', 'Awaiting prod'], ['inprogress', 'In progress'], ['returned', 'Returned'], ['validated', 'Validated']],
  firmware: [['all', 'All'], ['draft', 'Draft'], ['released', 'Released'], ['validating', 'Validating'], ['validated', 'Validated']],
};
function DevListScreen({ kind, go }) {
  const map = { investigation: 'investigations', recommendation: 'recommendations', rework: 'reworks', firmware: 'firmwares' };
  const items = useStore(s => s[map[kind]]);
  const [ls, setLs] = window.useListState(`v.${kind}.list`, { filter: 'all' });
  const filter = ls.filter; const setFilter = (v) => setLs({ filter: v });
  const rows = filter === 'all' ? items : items.filter(x => x.state === filter);
  const counts = {}; FILTERS_BY_KIND[kind].forEach(([k]) => counts[k] = k === 'all' ? items.length : items.filter(x => x.state === k).length);
  const heading = { investigation: 'Investigations', recommendation: 'Improvement Recommendations', rework: 'Rework Packages', firmware: 'Firmware Releases' }[kind];
  const subhead = { investigation: 'Technical analysis you own — your discoveries, your root causes.', recommendation: 'Improvements pushed to Designer. Each one awaits an Accept / Reject / Investigate response.', rework: 'Rework procedures pushed to Production. Track progress and receive validated results.', firmware: 'Firmware releases pushed to Production for validation.' }[kind];

  return (
    <div className="page">
      <div className="page-head">
        <div className="ph-titles"><div className="display">{heading}</div><div className="ph-sub">{subhead}</div></div>
      </div>
      <div className="filterbar">
        {FILTERS_BY_KIND[kind].map(([k, l]) => <button key={k} className={`fchip${filter === k ? ' active' : ''}`} onClick={() => setFilter(k)}>{l}<span className="fc-n">{counts[k]}</span></button>)}
      </div>
      <div className="tbl-wrap flow" style={{ borderRadius: '0 0 10px 10px', borderTop: 0 }}>
        {rows.length === 0 ? <EmptyState icon={DEV_KIND_META[kind].icon} title={`No ${heading.toLowerCase()} in this filter.`} />
        : rows.map(it => (
          <div key={it.id} className="lrow" onClick={() => go({ screen: DEV_KIND_META[kind].detailScreen, id: it.id })}>
            <div style={{ minWidth: 0 }}>
              <div className="lr-title">{it.title}<StatusBadge status={DEV_BADGE[kind][it.state]} />{it.priority === 'high' && <span className="badge filled" style={{ background: 'var(--danger)' }}>HIGH</span>}</div>
              <div className="lr-meta">
                <span className="mono">{it.id}</span><span className="tr-sep" />
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}><Icon name="folder" size={13} />{PROJECTS[it.project].name}</span>
                <span className="tr-sep" /><span>{it.assignee}</span><span className="tr-sep" /><span>updated {it.updated}</span>
                {kind === 'rework' && it.boards && <><span className="tr-sep" /><span>{it.boards} units</span></>}
                {kind === 'firmware' && it.version && <><span className="tr-sep" /><span className="mono">v{it.version}</span></>}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---------- Handshake panel: the recurring UI on every dev detail ---------- */
function HandshakePanel({ obj, kind, go }) {
  const isPushedOut = ['pushed', 'investigating', 'inprogress', 'validating'].includes(obj.state);
  const isResolved = ['accepted', 'rejected', 'validated', 'returned', 'closed', 'findings'].includes(obj.state);
  const isIncoming = !!obj.pushedFrom;

  if (isIncoming && (obj.state === 'open' || obj.state === 'analysis')) {
    return (
      <Banner kind="info" icon="inbox" title={`Handshake from ${obj.pushedFrom.role} · ${obj.pushedFrom.by} · ${obj.pushedFrom.when}`}>
        {obj.pushedFrom.note}
      </Banner>
    );
  }
  if (isPushedOut && obj.pushedTo) {
    return (
      <Banner kind="info" icon="send" title={`Pushed to ${obj.pushedTo.role} · ${obj.pushedTo.when}`}>
        Awaiting response. {kind === 'recommendation' && 'Designer reviews and replies Accept / Reject / Investigate.'}
        {kind === 'rework' && 'Production executes the procedure and returns results.'}
        {kind === 'firmware' && 'Production validates the build and reports back.'}
      </Banner>
    );
  }
  if (kind === 'recommendation' && obj.response) {
    const colors = { accepted: 'info', rejected: 'danger', investigating: 'warn' };
    return (
      <Banner kind={colors[obj.response.decision]} icon={obj.response.decision === 'rejected' ? 'x' : 'check'} title={`${obj.response.decision.toUpperCase()} by ${obj.response.by} · ${obj.response.when}`}>
        {obj.response.note}
      </Banner>
    );
  }
  if (kind === 'rework' && obj.results) {
    return (
      <Banner kind="info" icon="check" title={`Returned by ${obj.results.returnedBy} · ${obj.results.returnedWhen}`}>
        {obj.results.note}
      </Banner>
    );
  }
  if (kind === 'firmware' && obj.results) {
    return (
      <Banner kind="info" icon="check" title={`Validated by ${obj.results.by} · ${obj.results.when}`}>
        {obj.results.note}
      </Banner>
    );
  }
  return null;
}

/* ---------- Detail screens ---------- */
function DevDetailShell({ kind, id, go, action, children }) {
  const obj = useStore(s => findObj(s, kind, id));
  if (!obj) return <div className="page"><EmptyState icon={DEV_KIND_META[kind].icon} title="Not found." /></div>;
  return (
    <div className="page page-wide">
      <div className="page-head" style={{ marginBottom: 4 }}>
        <div className="ph-titles">
          <button className="btn-link" style={{ marginBottom: 8 }} onClick={() => go({ screen: DEV_KIND_META[kind].listScreen })}>← {DEV_KIND_META[kind].label}s</button>
          <div className="h1">{obj.title}</div>
        </div>
        <div className="ph-actions">
          {action}
        </div>
      </div>
      <TraceabilityStrip name={obj.id} status={DEV_BADGE[kind][obj.state]} creator={obj.owner} role="development"
        project={PROJECTS[obj.project].name} updated={obj.updated} recordId={obj.id} onProject={() => go({ screen: 'projectDetail', id: obj.project })} />
      <RelatedLinks items={[
        { kind: 'PCB Project', label: PROJECTS[obj.project].name, icon: 'folder', onClick: () => go({ screen: 'projectDetail', id: obj.project }) },
        obj.relatedBom && { kind: 'BOM', label: obj.relatedBom, icon: 'boms', onClick: () => go({ screen: 'p.bomOverview', id: obj.relatedBom }) },
        obj.relatedCollection && { kind: 'Collection', label: obj.relatedCollection, icon: 'layers', onClick: () => go({ screen: 'd.collectionDetail', id: obj.relatedCollection }) },
      ]} />
      <HandshakePanel obj={obj} kind={kind} go={go} />
      <p className="secondary" style={{ margin: '10px 0 0', maxWidth: 760 }}>{obj.desc}</p>
      <div style={{ marginTop: 18 }}>{children(obj)}</div>
      <div style={{ marginTop: 26 }}><CommentThread entityId={obj.id} /></div>
    </div>
  );
}

function InvestigationDetail({ id, go }) {
  return <DevDetailShell kind="investigation" id={id} go={go}
    action={<button className="btn primary"><Icon name="check" size={15} />Post findings</button>}>
    {(obj) => (
      <div className="card" style={{ padding: 18 }}>
        <div className="h2" style={{ marginBottom: 10 }}>Findings</div>
        {obj.findings.length === 0 ? <p className="muted">No findings logged yet.</p>
          : <ul style={{ margin: 0, paddingLeft: 18 }}>{obj.findings.map((f, i) => <li key={i} style={{ marginBottom: 6 }}>{f}</li>)}</ul>}
      </div>
    )}
  </DevDetailShell>;
}

function RecommendationDetail({ id, go }) {
  const obj = useStore(s => s.recommendations.find(x => x.id === id));
  const [respond, setRespond] = useStateV(null); // 'accepted' | 'rejected' | 'investigating'
  const [note, setNote] = useStateV('');
  const activeRole = useStore(s => s.activeRole);
  const canRespond = activeRole === 'designer' && obj && (obj.state === 'pushed' || obj.state === 'investigating');
  const canPush = activeRole === 'development' && obj && obj.state === 'draft';

  return <DevDetailShell kind="recommendation" id={id} go={go}
    action={canRespond ? (
      <>
        <button className="btn danger" onClick={() => setRespond('rejected')}><Icon name="x" size={15} />Reject</button>
        <button className="btn" onClick={() => setRespond('investigating')}><Icon name="search" size={15} />Investigate</button>
        <button className="btn primary" onClick={() => setRespond('accepted')}><Icon name="check" size={15} />Accept</button>
      </>
    ) : canPush ? <button className="btn primary" onClick={() => storeActions.pushRecommendation(id)}><Icon name="send" size={15} />Push to Designer</button> : null}>
    {(obj) => (
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div className="card" style={{ padding: 16 }}>
          <div className="caption" style={{ fontWeight: 700, color: 'var(--danger)', textTransform: 'uppercase', fontSize: 10.5, letterSpacing: '.04em' }}>Current</div>
          <div className="mono" style={{ fontWeight: 700, fontSize: 18, marginTop: 4 }}>{obj.currentMpn || '—'}</div>
        </div>
        <div className="card" style={{ padding: 16 }}>
          <div className="caption" style={{ fontWeight: 700, color: 'var(--success)', textTransform: 'uppercase', fontSize: 10.5, letterSpacing: '.04em' }}>Proposed</div>
          <div className="mono" style={{ fontWeight: 700, fontSize: 18, marginTop: 4, color: 'var(--role-development)' }}>{obj.proposedMpn || '—'}</div>
        </div>
        {respond && <div className="modal-wrap"><div className="scrim" onClick={() => setRespond(null)} />
          <div className="modal" style={{ position: 'relative', zIndex: 95 }}>
            <div className="modal-head"><div className="mh-title">{respond[0].toUpperCase() + respond.slice(1)} recommendation</div></div>
            <div className="modal-body">
              <p style={{ marginTop: 0 }} className="secondary">A response is sent back to {obj.owner}. {respond === 'rejected' && 'A reason is required.'}</p>
              <textarea className="textarea" placeholder="Add a note for Development…" value={note} onChange={e => setNote(e.target.value)} />
            </div>
            <div className="modal-foot">
              <button className="btn" onClick={() => setRespond(null)}>Cancel</button>
              <button className={`btn ${respond === 'rejected' ? 'danger' : 'primary'}`}
                disabled={respond === 'rejected' && note.trim().length < 5}
                onClick={() => { storeActions.respondRecommendation(id, respond, note); setRespond(null); }}>
                Send {respond}
              </button>
            </div>
          </div>
        </div>}
      </div>
    )}
  </DevDetailShell>;
}

function ReworkDetail({ id, go }) {
  const obj = useStore(s => s.reworks.find(x => x.id === id));
  const [returnOpen, setReturnOpen] = useStateV(false);
  const [note, setNote] = useStateV('');
  const activeRole = useStore(s => s.activeRole);
  const canReturn = activeRole === 'production' && obj && (obj.state === 'pushed' || obj.state === 'inprogress');

  return <DevDetailShell kind="rework" id={id} go={go}
    action={canReturn ? <button className="btn primary" onClick={() => setReturnOpen(true)}><Icon name="check" size={15} />Mark validated & return</button> : null}>
    {(obj) => (
      <>
        <div className="card" style={{ padding: 18 }}>
          <div className="h2" style={{ marginBottom: 10 }}>Procedure · {obj.boards} units</div>
          <ol style={{ margin: 0, paddingLeft: 20 }}>{obj.procedure.map((s, i) => <li key={i} style={{ marginBottom: 5 }}>{s}</li>)}</ol>
          {obj.results && obj.results.progress != null && (
            <div style={{ marginTop: 14 }}>
              <div className="caption" style={{ fontWeight: 600, marginBottom: 5 }}>Production progress · {obj.results.progress} of {obj.results.ofTotal} units</div>
              <div className="progress"><i style={{ width: (obj.results.progress / obj.results.ofTotal * 100) + '%', background: 'var(--role-development)' }} /></div>
            </div>
          )}
        </div>
        {returnOpen && <div className="modal-wrap"><div className="scrim" onClick={() => setReturnOpen(false)} />
          <div className="modal" style={{ position: 'relative', zIndex: 95 }}>
            <div className="modal-head"><div className="mh-title">Return rework to Development</div></div>
            <div className="modal-body"><textarea className="textarea" placeholder="Results — pass/fail counts, anomalies, observations…" value={note} onChange={e => setNote(e.target.value)} /></div>
            <div className="modal-foot"><button className="btn" onClick={() => setReturnOpen(false)}>Cancel</button>
              <button className="btn primary" disabled={note.trim().length < 5} onClick={() => { storeActions.returnRework(id, note); setReturnOpen(false); }}>Return with results</button></div>
          </div>
        </div>}
      </>
    )}
  </DevDetailShell>;
}

function FirmwareDetail({ id, go }) {
  const obj = useStore(s => s.firmwares.find(x => x.id === id));
  const [openValidate, setOpenValidate] = useStateV(false);
  const [note, setNote] = useStateV('');
  const activeRole = useStore(s => s.activeRole);
  const canValidate = activeRole === 'production' && obj && obj.state === 'validating';
  const canPush = activeRole === 'development' && obj && (obj.state === 'released' || obj.state === 'draft');

  return <DevDetailShell kind="firmware" id={id} go={go}
    action={canValidate ? <button className="btn primary" onClick={() => setOpenValidate(true)}><Icon name="check" size={15} />Validate release</button>
      : canPush ? <button className="btn primary" onClick={() => storeActions.pushFirmware(id)}><Icon name="send" size={15} />Push for validation</button> : null}>
    {(obj) => (
      <>
        <div className="card" style={{ padding: 18 }}>
          <div className="h2" style={{ marginBottom: 8 }}>Changelog · v{obj.version}</div>
          <ul style={{ margin: 0, paddingLeft: 18 }}>{obj.changelog.map((c, i) => <li key={i} style={{ marginBottom: 4 }}>{c}</li>)}</ul>
        </div>
        {openValidate && <div className="modal-wrap"><div className="scrim" onClick={() => setOpenValidate(false)} />
          <div className="modal" style={{ position: 'relative', zIndex: 95 }}>
            <div className="modal-head"><div className="mh-title">Mark firmware validated</div></div>
            <div className="modal-body"><textarea className="textarea" placeholder="Validation results, units tested, observations…" value={note} onChange={e => setNote(e.target.value)} /></div>
            <div className="modal-foot"><button className="btn" onClick={() => setOpenValidate(false)}>Cancel</button>
              <button className="btn primary" disabled={note.trim().length < 5} onClick={() => { storeActions.validateFirmware(id, note); setOpenValidate(false); }}>Validate</button></div>
          </div>
        </div>}
      </>
    )}
  </DevDetailShell>;
}

Object.assign(window, { DevelopmentDashboard, DevListScreen, InvestigationDetail, RecommendationDetail, ReworkDetail, FirmwareDetail, DEV_BADGE });
