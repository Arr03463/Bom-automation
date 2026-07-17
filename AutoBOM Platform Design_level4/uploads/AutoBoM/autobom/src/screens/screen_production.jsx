/* global React, Icon, StatusBadge, RoleTag, SupplierTag, Banner, EmptyState, Avatar, NeedsAttention,
   useStore, storeActions, PROJECTS, BOM_BADGE, fmtUSD, fmtInt */
const { useState: useStateProd, useRef: useRefProd } = React;

function bomMeta(b) {
  const exceptions = b.items.filter(i => i.status === 'needs-review' || i.status === 'exception').length;
  const sourced = b.items.filter(i => i.supplier).length;
  const total = b.items.reduce((a, i) => a + (i.ext || 0), 0);
  return { exceptions, sourced, total, lines: b.items.length };
}

/* action a Production user can take on a BOM, given its state */
function bomAction(b) {
  const m = bomMeta(b);
  switch (b.state) {
    case 'validated': return { verb: 'Run sourcing', go: { screen: 'p.sourcing', id: b.id }, kind: 'primary' };
    case 'normalised': return { verb: 'Re-run sourcing', go: { screen: 'p.sourcing', id: b.id }, kind: 'primary', note: 'Replacements received' };
    case 'results': return m.exceptions > 0
      ? { verb: 'Resolve exceptions', go: { screen: 'p.results', id: b.id }, kind: 'danger', note: `${m.exceptions} need review` }
      : { verb: 'Create package', go: { screen: 'p.procurement', id: b.id }, kind: 'primary', note: 'All sourced' };
    case 'exceptions': return { verb: 'View', go: { screen: 'p.bomOverview', id: b.id }, kind: 'ghost', note: 'Waiting on designer' };
    case 'submitted': return { verb: 'Track', go: { screen: 'p.bomOverview', id: b.id }, kind: 'ghost', note: 'In purchasing bucket' };
    default: return { verb: 'Open', go: { screen: 'p.bomOverview', id: b.id }, kind: 'ghost' };
  }
}

function ProductionDashboard({ go, flashId }) {
  const [demo, setDemo] = useStateProd('default');
  const boms = useStore(s => s.boms.filter(b => b.state !== 'draft'));
  const sourcingActive = false; // toggled by demo
  const list = demo === 'empty' ? [] : boms;

  const inQueue = boms.filter(b => !['submitted', 'ordered'].includes(b.state)).length;
  const exceptionsOpen = boms.filter(b => b.state === 'exceptions').length;
  const readyProc = boms.filter(b => b.state === 'results' && bomMeta(b).exceptions === 0).length;
  const activeSourcing = demo === 'sourcing' ? 1 : 0;

  return (
    <div className="page">
      <div className="page-head">
        <div className="ph-titles"><div className="display">Production workspace</div>
          <div className="ph-sub">Validate, source, and package BOMs for purchasing. You own sourcing readiness.</div></div>
        <div className="ph-actions">
          <div style={{ display: 'inline-flex', border: '1px solid var(--border)', borderRadius: 7, overflow: 'hidden', marginRight: 4 }}>
            {[['default', 'Default'], ['sourcing', 'Active sourcing'], ['empty', 'Empty queue']].map(([v, l], i) => (
              <button key={v} onClick={() => setDemo(v)} style={{ border: 0, padding: '6px 11px', fontSize: 12.5, fontWeight: 600, cursor: 'pointer', background: demo === v ? 'var(--info-soft)' : 'var(--bg-surface)', color: demo === v ? 'var(--info)' : 'var(--text-secondary)', borderRight: i < 2 ? '1px solid var(--border)' : 0 }}>{l}</button>
            ))}
          </div>
          <button className="btn primary" onClick={() => go({ screen: 'p.upload' })}><Icon name="upload" size={15} />Upload BOM</button>
        </div>
      </div>

      {demo === 'sourcing' && (
        <div className="panel" style={{ marginBottom: 16, borderColor: 'var(--info)' }}>
          <div className="panel-head" style={{ background: 'var(--info-soft)' }}>
            <span className="spinner" style={{ borderTopColor: 'var(--info)' }} /><span className="ph-title" style={{ color: 'var(--info)' }}>Sourcing run in progress — Sensor Board Rev A</span>
            <button className="btn-link" style={{ marginLeft: 'auto' }} onClick={() => go({ screen: 'p.sourcing', id: 'BOM-055' })}>Open live view</button>
          </div>
          <div style={{ padding: '14px 16px' }}>
            <div className="progress"><i style={{ width: '64%' }} /></div>
            <div className="caption" style={{ marginTop: 7, display: 'flex', gap: 16 }}><span>16 of 25 lines</span><span>64%</span><span>~40s remaining</span></div>
          </div>
        </div>
      )}

      <div className="na-mount" style={{ marginBottom: 18 }}><NeedsAttention role="production" go={go} flashId={flashId} /></div>

      <div className="stat-row" style={{ marginBottom: 18 }}>
        <div className="stat"><div className="st-label"><Icon name="boms" size={13} /> BOMs in queue</div><div className="st-num">{demo === 'empty' ? 0 : inQueue}</div><div className="st-sub">in pipeline</div></div>
        <div className="stat"><div className="st-label"><Icon name="refresh" size={13} style={{ color: 'var(--info)' }} /> Active sourcing</div><div className="st-num">{activeSourcing}</div><div className="st-sub">running now</div></div>
        <div className="stat"><div className="st-label"><Icon name="alert" size={13} style={{ color: 'var(--danger)' }} /> Open exceptions</div><div className="st-num" style={{ color: exceptionsOpen ? 'var(--danger)' : undefined }}>{demo === 'empty' ? 0 : exceptionsOpen}</div><div className="st-sub">with designers</div></div>
        <div className="stat"><div className="st-label"><Icon name="check" size={13} style={{ color: 'var(--success)' }} /> Ready for procurement</div><div className="st-num">{demo === 'empty' ? 0 : readyProc}</div><div className="st-sub">to package</div></div>
      </div>

      <div className="panel">
        <div className="panel-head"><Icon name="boms" size={16} /><span className="ph-title">BOM Queue</span>
          <button className="btn-link" style={{ marginLeft: 'auto' }} onClick={() => go({ screen: 'projects' })}>View all</button></div>
        {list.length === 0 ? <EmptyState icon="boms" title="No BOMs in your queue." sub="Upload a BOM file to start the validation and sourcing pipeline."
          actions={<button className="btn primary sm" onClick={() => go({ screen: 'p.upload' })}><Icon name="upload" size={14} />Upload BOM</button>} />
        : list.map(b => { const m = bomMeta(b); return (
          <div key={b.id} className="attn-item" style={{ cursor: 'pointer' }} onClick={() => go({ screen: 'p.bomOverview', id: b.id })}>
            <div className="attn-main"><div style={{ display: 'flex', alignItems: 'center', gap: 9 }}><span style={{ fontWeight: 600, fontSize: 14 }}>{b.name}</span><StatusBadge status={BOM_BADGE[b.state]} /></div>
              <div className="am-meta">{PROJECTS[b.project].name} · build {fmtInt(b.buildQty)} · {m.lines} lines · updated {b.updated}</div></div>
            <Icon name="chevright" size={16} style={{ color: 'var(--text-muted)' }} />
          </div>
        ); })}
      </div>
    </div>
  );
}

const BOM_LIST_FILTERS = [
  { key: 'all', label: 'All' }, { key: 'validated', label: 'Validated' }, { key: 'results', label: 'Sourced' },
  { key: 'exceptions', label: 'Exceptions' }, { key: 'submitted', label: 'Submitted' },
];
function BomListScreen({ go }) {
  const [ls, setLs] = window.useListState('p.boms', { filter: 'all' });
  const filter = ls.filter; const setFilter = (v) => setLs({ filter: v });
  const boms = useStore(s => s.boms.filter(b => b.state !== 'draft'));
  const rows = boms.filter(b => filter === 'all' ? true : b.state === filter);
  const counts = {}; BOM_LIST_FILTERS.forEach(f => counts[f.key] = f.key === 'all' ? boms.length : boms.filter(b => b.state === f.key).length);
  return (
    <div className="page">
      <div className="page-head">
        <div className="ph-titles"><div className="display">BOMs</div><div className="ph-sub">Every BOM in the production pipeline. Upload, validate, source, and package for purchasing.</div></div>
        <div className="ph-actions"><button className="btn primary" onClick={() => go({ screen: 'p.upload' })}><Icon name="upload" size={15} />Upload BOM</button></div>
      </div>
      <div className="filterbar">
        {BOM_LIST_FILTERS.map(f => <button key={f.key} className={`fchip${filter === f.key ? ' active' : ''}`} onClick={() => setFilter(f.key)}>{f.label}<span className="fc-n">{counts[f.key]}</span></button>)}
      </div>
      <div className="tbl-wrap" style={{ borderRadius: '0 0 10px 10px', borderTop: 0 }}>
        {rows.length === 0 ? <EmptyState icon="boms" title="No BOMs match this filter." sub="Try a different state or upload a new BOM." actions={<button className="btn" onClick={() => setFilter('all')}>Clear filter</button>} />
        : rows.map(b => { const m = bomMeta(b); return (
          <div key={b.id} className="lrow" onClick={() => go({ screen: 'p.bomOverview', id: b.id })} style={m.exceptions > 0 ? { boxShadow: 'inset 3px 0 0 var(--danger)' } : undefined}>
            <div style={{ minWidth: 0 }}>
              <div className="lr-title">{b.name}<StatusBadge status={BOM_BADGE[b.state]} /></div>
              <div className="lr-meta"><span className="mono">{b.id}</span><span className="tr-sep" /><span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}><Icon name="folder" size={13} />{PROJECTS[b.project].name}</span>
                <span className="tr-sep" /><span>build {fmtInt(b.buildQty)} +{b.overage}%</span><span className="tr-sep" /><span>{m.lines} lines</span>
                {m.exceptions > 0 && <><span className="tr-sep" /><span style={{ color: 'var(--danger)', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: 4 }}><Icon name="alert" size={12} />{m.exceptions} exceptions</span></>}</div>
            </div>
            <div className="lr-right"><div className="lr-stats"><span>updated {b.updated}</span>{m.total > 0 && <span>est. <b className="mono">{fmtUSD(m.total)}</b></span>}</div></div>
          </div>
        ); })}
      </div>
    </div>
  );
}

function BomUploadScreen({ go, preProject }) {
  const availableProjects = useStore(s => Object.values(s.projects).filter(p => !s.boms.some(b => b.project === p.id && b.state !== 'draft')));
  const backTo = preProject ? { screen: 'projectDetail', id: preProject } : { screen: 'projects' };
  const [phase, setPhase] = useStateProd('idle'); // idle | selected | error
  const [form, setForm] = useStateProd({ name: '', project: preProject || (availableProjects[0] && availableProjects[0].id) || '', buildQty: '', overage: '10' });
  const [touched, setTouched] = useStateProd(false);
  const fileName = 'sensor_board_rev_a.xlsx';
  const errs = { name: !form.name.trim(), buildQty: !form.buildQty || +form.buildQty <= 0, project: !form.project };
  const hasErr = errs.name || errs.buildQty || errs.project;

  const submit = () => {
    setTouched(true); if (hasErr) return;
    const id = storeActions.createBom({ name: form.name, project: form.project, buildQty: +form.buildQty, overage: +form.overage });
    if (id) go({ screen: 'p.validate', id });
  };

  return (
    <div className="page">
      <div className="page-head"><div className="ph-titles">
        <button className="btn-link" style={{ marginBottom: 8 }} onClick={() => go(backTo)}>← {preProject ? 'PCB Project' : 'PCB Projects'}</button>
        <div className="h1">Upload BOM</div><div className="ph-sub">Upload a CSV or XLSX. Validation runs automatically after upload.</div></div></div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.3fr 1fr', gap: 22, alignItems: 'start', maxWidth: 980 }}>
        <div>
          {phase === 'idle' && (
            <div className="dropzone" onClick={() => setPhase('selected')}>
              <div className="em-icon" style={{ margin: '0 auto 14px' }}><Icon name="upload" size={24} /></div>
              <div style={{ fontWeight: 700, fontSize: 16 }}>Drop a BOM file here, or click to browse</div>
              <div className="caption" style={{ marginTop: 6 }}>CSV or XLSX · up to 5,000 lines · first row treated as headers</div>
              <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginTop: 16 }}>
                <button className="btn" onClick={(e) => { e.stopPropagation(); setPhase('selected'); }}>Browse files</button>
                <button className="btn ghost" onClick={(e) => { e.stopPropagation(); setPhase('error'); }}>Simulate bad file</button>
              </div>
            </div>
          )}
          {phase === 'error' && (
            <div className="dropzone error">
              <div className="em-icon" style={{ margin: '0 auto 14px', background: 'var(--danger-soft)', color: 'var(--danger)' }}><Icon name="x" size={24} /></div>
              <div style={{ fontWeight: 700, fontSize: 16, color: 'var(--danger)' }}>Couldn't read that file</div>
              <div className="caption" style={{ marginTop: 6, maxWidth: 360, marginInline: 'auto' }}>The file appears to be a PDF, not a spreadsheet. Export your BOM as CSV or XLSX and try again.</div>
              <button className="btn" style={{ marginTop: 16 }} onClick={() => setPhase('idle')}>Try another file</button>
            </div>
          )}
          {phase === 'selected' && (
            <div className="card" style={{ padding: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div className="attn-icon" style={{ background: 'var(--success-soft)', color: 'var(--success)' }}><Icon name="check" size={18} /></div>
                <div style={{ flex: 1 }}><div style={{ fontWeight: 600 }} className="mono">{fileName}</div><div className="caption">44 rows detected · 9 columns · headers in row 1</div></div>
                <button className="btn ghost sm" onClick={() => setPhase('idle')}><Icon name="x" size={15} />Remove</button>
              </div>
              <div className="divider" />
              <div className="caption" style={{ marginBottom: 8, fontWeight: 600, color: 'var(--text-secondary)' }}>Column mapping (auto-detected)</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 8 }}>
                {[['MPN', 'Part Number'], ['Manufacturer', 'Mfr'], ['Qty', 'Quantity'], ['Description', 'Desc'], ['Reference', 'RefDes'], ['—', 'Notes']].map(([k, v]) => (
                  <div key={k} className="map-chip"><span className="caption">{v}</span><Icon name="arrow" size={12} /><span style={{ fontWeight: 600 }}>{k}</span></div>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="card" style={{ padding: 16 }}>
          <div className="h2" style={{ marginBottom: 12 }}>BOM details</div>
          <label className="field" style={{ marginBottom: 12 }}><span className="fl">BOM name</span>
            <input className="input" value={form.name} placeholder="e.g. Sensor Board Rev A" onChange={e => setForm({ ...form, name: e.target.value })} />
            {touched && errs.name && <span className="err-msg"><Icon name="alert" size={12} />Name is required</span>}</label>
          <label className="field" style={{ marginBottom: 12 }}><span className="fl">PCB Project</span>
            <select className="select" value={form.project} onChange={e => setForm({ ...form, project: e.target.value })}>
              {availableProjects.length === 0 && <option value="">No PCB Projects without a BOM</option>}
              {availableProjects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
            <span className="caption" style={{ marginTop: 3 }}>One BOM per PCB — only PCB Projects without a BOM are listed.</span>
            {touched && errs.project && <span className="err-msg"><Icon name="alert" size={12} />Pick a PCB Project</span>}</label>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
            <label className="field"><span className="fl">Build quantity</span>
              <input className="input" type="number" value={form.buildQty} placeholder="25" onChange={e => setForm({ ...form, buildQty: e.target.value })} />
              {touched && errs.buildQty && <span className="err-msg"><Icon name="alert" size={12} />Required</span>}</label>
            <label className="field"><span className="fl">Overage %</span>
              <input className="input" type="number" value={form.overage} onChange={e => setForm({ ...form, overage: e.target.value })} /></label>
          </div>
          <div className="caption" style={{ marginBottom: 14, display: 'flex', gap: 6, alignItems: 'flex-start' }}><Icon name="info" size={14} style={{ marginTop: 1 }} />Overage adds buffer stock on top of build quantity to cover assembly loss.</div>
          <button className="btn primary lg" style={{ width: '100%' }} disabled={phase !== 'selected'} onClick={submit}><Icon name="check" size={16} />Validate BOM</button>
          {phase !== 'selected' && <div className="caption" style={{ textAlign: 'center', marginTop: 8 }}>Select a file to continue</div>}
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { ProductionDashboard, BomListScreen, BomUploadScreen, bomMeta, bomAction });
