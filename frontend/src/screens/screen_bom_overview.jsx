/* global React, Icon, StatusBadge, RoleTag, SupplierTag, Banner, EmptyState, TraceabilityStrip,
   BomTable, Totals, bomById, useStore, storeActions, lockFor, PROJECTS, CATALOG, BOM_BADGE, fmtUSD, fmtInt, bomMeta */
const { useState: useStateBO } = React;

function BomOverviewScreen({ id, go, tab }) {
  const b = bomById(id);
  const activeRole = useStore(s => s.activeRole);
  const audit = useStore(s => s.audit.filter(a => a.entity === id));
  const curTab = tab || 'overview';
  const setTab = (t) => go({ screen: 'p.bomOverview', id, tab: t });
  if (!b) return <div className="page"><EmptyState icon="boms" title="BOM not found." /></div>;
  const m = bomMeta(b);
  const lock = lockFor('bom', b.state, activeRole);
  const isProd = activeRole === 'production';
  const editable = isProd && ['validated', 'normalised'].includes(b.state);

  // action bar (production only) — Run Sourcing is a constant; a state-specific next-step sits beside it.
  let action = null;
  if (isProd) {
    if (b.state === 'results' && m.exceptions > 0) action = { label: 'Resolve exceptions', icon: 'alert', go: { screen: 'p.results', id }, kind: 'danger' };
    else if (b.state === 'results') action = { label: 'Create package', icon: 'package', go: { screen: 'p.procurement', id }, kind: 'primary' };
    else if (b.state === 'packaged') action = { label: 'Submit to Purchasing', icon: 'send', go: { screen: 'p.procurement', id }, kind: 'primary' };
  }

  return (
    <div className="page page-wide">
      <div className="page-head" style={{ marginBottom: 4 }}>
        <div className="ph-titles">
          <button className="btn-link" style={{ marginBottom: 8 }} onClick={() => go(isProd ? { screen: 'projectDetail', id: b.project } : { screen: 'projects' })}>← {isProd ? 'PCB Project' : 'BOMs'}</button>
          <div className="h1">{b.name}</div>
        </div>
        <div className="ph-actions">
          {isProd && <button className={`btn ${action ? '' : 'primary'}`} onClick={() => go({ screen: 'p.sourcing', id })}><Icon name="refresh" size={15} />Run Sourcing</button>}
          {action && <button className={`btn ${action.kind === 'danger' ? 'danger' : 'primary'}`} onClick={() => go(action.go)}><Icon name={action.icon} size={15} />{action.label}</button>}
        </div>
      </div>
      <TraceabilityStrip name={b.name} status={BOM_BADGE[b.state]} creator={b.creator} role="production"
        project={projectName(b.project)} updated={b.updated} updatedBy={b.updatedBy} recordId={b.reqId || b.id}
        onProject={() => go({ screen: 'projectDetail', id: b.project })} />

      {window.RelatedLinks && <window.RelatedLinks items={[
        { kind: 'PCB Project', label: projectName(b.project), icon: 'folder', onClick: () => go({ screen: 'projectDetail', id: b.project }) },
        b.sourceCollection && { kind: 'Source Collection', label: b.sourceCollection, icon: 'layers', onClick: () => go({ screen: 'd.collectionDetail', id: b.sourceCollection }) },
        b.reqId && { kind: 'Request', label: b.reqId, icon: 'inbox', onClick: () => go({ screen: 'purchasingEmbed', tab: b.reqId }) },
      ]} />}

      {lock && <Banner kind="lock" title={lock.title}>{lock.body} Next action owned by <RoleTag role={lock.owner} />. You can still: {lock.canDo}.</Banner>}
      {b.state === 'exceptions' && b.pushback && (
        <Banner kind="warn" icon="alert" title={b.pushback.recommendation ? `Replacements recommended by ${b.pushback.recommendation.by} — awaiting Production Apply` : `Push-Back sent to ${b.pushback.to} · loop ${b.pushback.loop} of ${3}`}>
          {b.pushback.note}<div className="caption" style={{ marginTop: 4 }}>{b.pushback.recommendation ? 'Production applies the recommendation to commit it to the master BOM.' : 'Waiting for engineering recommendations — Designer resolves on their dashboard.'} {b.pushback.loop >= 3 && <strong style={{ color: 'var(--danger)' }}>Escalation threshold reached.</strong>}</div>
        </Banner>
      )}

      <div className="tabs" style={{ marginTop: 16 }}>
        {[['overview', 'Overview'], ['lines', `Lines · ${m.lines}`], ['history', 'History'], ['comments', `Comments · ${(useStore(s => s.comments[b.id]) || []).length}`]].map(([k, l]) => (
          <div key={k} className={`tab${curTab === k ? ' active' : ''}`} onClick={() => setTab(k)}>{l}</div>
        ))}
      </div>

      {curTab === 'overview' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, alignItems: 'start' }}>
          <div className="card" style={{ padding: 18 }}>
            <div className="h2" style={{ marginBottom: 12 }}>Details</div>
            <dl className="kv">
              <dt>Status</dt><dd><StatusBadge status={BOM_BADGE[b.state]} /></dd>
              <dt>PCB Project</dt><dd>{projectName(b.project)}</dd>
              <dt>Build quantity</dt><dd>{fmtInt(b.buildQty)} units +{b.overage}% overage</dd>
              <dt>Created by</dt><dd>{b.creator}</dd>
              <dt>Source</dt><dd>{b.sourceCollection ? <span className="mono" style={{ color: 'var(--action)', cursor: 'pointer' }} onClick={() => go({ screen: 'd.collectionDetail', id: b.sourceCollection })}>{b.sourceCollection}</span> : <span className="muted">Manual upload</span>}</dd>
              <dt>PartsBox</dt><dd>{b.partsbox ? <span className="mono">{b.partsbox}</span> : <span className="muted">Not created</span>}</dd>
              {b.reqId && <><dt>Request</dt><dd className="mono" style={{ color: 'var(--action)', cursor: 'pointer' }} onClick={() => go({ screen: 'purchasingEmbed', tab: b.reqId })}>{b.reqId}</dd></>}
            </dl>
          </div>
          <div className="card" style={{ padding: 18 }}>
            <div className="h2" style={{ marginBottom: 12 }}>Sourcing scorecard</div>
            <div className="scorecard" style={{ gridTemplateColumns: '1fr 1fr' }}>
              <div className="stat"><div className="st-label"><span className="dot" style={{ background: 'var(--supplier-mouser)' }} /> Mouser</div><div className="st-num" style={{ fontSize: 22, color: 'var(--supplier-mouser)' }}>{b.items.filter(i => i.supplier === 'mouser').length}</div></div>
              <div className="stat"><div className="st-label"><span className="dot" style={{ background: 'var(--supplier-digikey)' }} /> DigiKey</div><div className="st-num" style={{ fontSize: 22, color: 'var(--supplier-digikey)' }}>{b.items.filter(i => i.supplier === 'digikey').length}</div></div>
              <div className="stat"><div className="st-label"><Icon name="alert" size={13} style={{ color: 'var(--danger)' }} /> Needs review</div><div className="st-num" style={{ fontSize: 22, color: m.exceptions ? 'var(--danger)' : 'var(--success)' }}>{m.exceptions}</div></div>
              <div className="stat"><div className="st-label"><Icon name="dollar" size={13} /> Est. total</div><div className="st-num mono" style={{ fontSize: 20 }}>{fmtUSD(m.total)}</div></div>
            </div>
          </div>
        </div>
      )}

      {curTab === 'lines' && (<>
        {editable ? <ProdBomLines bom={b} /> : <BomTable items={b.items} editable={false} showSource defaultSort={{ col: 'no', dir: 1 }} />}
        <div className="tbl-wrap" style={{ borderTop: 0, borderRadius: 0, marginTop: -1 }}><Totals items={b.items} /></div>
      </>)}

      {curTab === 'history' && (
        <div className="tbl-wrap flow">
          {audit.length === 0 ? <EmptyState icon="history" title="No history yet for this item." />
          : <table className="bom"><thead><tr><th>When</th><th>User</th><th>Role</th><th>Action</th><th>Before</th><th>After</th></tr></thead><tbody>
            {audit.map((a, i) => <tr key={a.id} className={i % 2 ? 'alt' : ''}><td className="caption">{a.ts}</td><td>{a.user}</td><td><RoleTag role={a.role} /></td><td>{a.action}</td><td className="mono caption">{a.before}</td><td className="mono caption" style={{ fontWeight: 600 }}>{a.after}</td></tr>)}
          </tbody></table>}
        </div>
      )}

      {curTab === 'comments' && (
        <div style={{ marginTop: 10 }}><CommentThread entityId={b.id} /></div>
      )}
    </div>
  );
}

/* ---- Production inline-edit table (v4) — non-structural free edit + MPN characteristic-match check ---- */
function ProdBomLines({ bom }) {
  return (
    <>
      <div className="banner info" style={{ marginBottom: 8 }}>
        <Icon name="info" size={16} />
        <div style={{ flex: 1 }}>
          <div className="bn-title">Inline editing{bom.version ? ` · master BOM v${bom.version}` : ''}</div>
          <div className="bn-body">Notes, description, and designator edit freely. Changing an <strong>MPN</strong> runs a characteristic-match check: an equivalent part swaps silently (version bumps); a mismatch offers <em>Send to Designer</em> or <em>Continue as override</em>.</div>
        </div>
      </div>
      <div className="tbl-wrap flow"><table className="bom">
        <thead><tr><th>#</th><th>MPN</th><th>Manufacturer</th><th>Description</th><th>Designator</th><th className="num">Qty</th><th>Status</th></tr></thead>
        <tbody>{bom.items.map(i => <ProdBomRow key={i.no} bom={bom} item={i} />)}</tbody>
      </table></div>
    </>
  );
}

function ProdBomRow({ bom, item }) {
  const [edit, setEdit] = useStateBO(null);
  const [draft, setDraft] = useStateBO('');
  const [flag, setFlag] = useStateBO(null);   // { newMpn, newMfr, diffs, unknown }
  const [mode, setMode] = useStateBO(null);   // 'override' → reason entry
  const [reason, setReason] = useStateBO('');

  const begin = (field, cur) => { setEdit(field); setDraft(cur == null ? '' : String(cur)); };
  const commitMeta = (field) => { const v = draft.trim(); setEdit(null); if (v !== (item[field] == null ? '' : String(item[field]))) storeActions.editBomLineField(bom.id, item.no, field, v); };
  const commitQty = () => { const n = parseInt(draft, 10); setEdit(null); if (!isNaN(n) && n > 0) storeActions.updateQty(bom.id, item.no, n); };
  const commitMpn = () => {
    const newMpn = draft.trim(); setEdit(null);
    if (!newMpn || newMpn === item.mpn) return;
    const res = window.characteristicMatch((window.CATALOG[item.mpn] && window.CATALOG[item.mpn].desc) || item.desc, newMpn);
    if (res.ok) storeActions.commitEquivalentSwap(bom.id, item.no, newMpn, res.candMfr, 'spec-matched');
    else setFlag({ newMpn, newMfr: res.candMfr, diffs: res.diffs, unknown: res.unknown });
  };

  const Cell = ({ field, structural, onCommit, val }) => edit === field
    ? <input className="cell-edit" autoFocus value={draft} onChange={e => setDraft(e.target.value)} onBlur={onCommit} onKeyDown={e => { if (e.key === 'Enter') onCommit(); if (e.key === 'Escape') setEdit(null); }} />
    : <span className="cell-editable" style={structural ? { borderBottom: '1px dashed var(--action)' } : undefined} onClick={() => begin(field, val)} title={structural ? 'Structural — runs a characteristic-match check' : 'Click to edit'}>{val == null || val === '' ? '—' : val}</span>;

  const rowCls = flag ? 'warn' : (item.status === 'needs-review' || item.status === 'exception' ? 'exception' : '');
  return (
    <>
      <tr className={rowCls}>
        <td className="num muted">{item.no}</td>
        <td className="mono" style={{ fontWeight: 600 }}><Cell field="mpn" structural val={item.mpn} onCommit={commitMpn} />{item.replacement && <span className="caption" style={{ display: 'block', color: 'var(--success)', fontFamily: 'var(--font-sans)' }}>↳ was {item.replacement.from}</span>}</td>
        <td><Cell field="mfr" val={item.mfr} onCommit={() => commitMeta('mfr')} /></td>
        <td className="secondary" style={{ maxWidth: 240 }}><Cell field="desc" val={item.desc} onCommit={() => commitMeta('desc')} /></td>
        <td className="mono caption"><Cell field="designator" val={item.designator} onCommit={() => commitMeta('designator')} /></td>
        <td className="num"><Cell field="qty" val={item.qty} onCommit={commitQty} /></td>
        <td><StatusBadge status={item.status} /></td>
      </tr>
      {flag && (
        <tr className="warn"><td colSpan={7} style={{ padding: '10px 14px', background: 'var(--warning-soft)' }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
            <Icon name="alert" size={18} style={{ color: 'var(--warning)', marginTop: 2 }} />
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 700 }}>{flag.unknown ? `Can't verify ${flag.newMpn} against suppliers` : `This differs from the original in ${flag.diffs.join(', ')}`}</div>
              <div className="caption" style={{ marginTop: 2 }}><span className="mono">{item.mpn}</span> → <span className="mono">{flag.newMpn}</span>{flag.newMfr ? ` · ${flag.newMfr}` : ''}. Send it to Designer for engineering judgment, or continue as an override (the edit is not committed until you choose).</div>
              {mode === 'override' ? (
                <div style={{ marginTop: 8 }}>
                  <textarea className="input" style={{ minHeight: 44 }} placeholder="Audit reason (required, min 10 chars)…" value={reason} onChange={e => setReason(e.target.value)} />
                  <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 6 }}>
                    <button className="btn sm ghost" onClick={() => { setMode(null); setReason(''); }}>Back</button>
                    <button className="btn sm danger" disabled={reason.trim().length < 10} onClick={() => { storeActions.commitOverride(bom.id, item.no, flag.newMpn, flag.newMfr, reason.trim()); setFlag(null); setMode(null); setReason(''); }}>Commit override &amp; log</button>
                  </div>
                </div>
              ) : (
                <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
                  <button className="btn sm ghost" onClick={() => setFlag(null)}>Cancel</button>
                  <button className="btn sm" onClick={() => { storeActions.pushbackFromEdit(bom.id, item.no, flag.newMpn, flag.diffs); setFlag(null); }}><Icon name="send" size={13} />Send to Designer</button>
                  <button className="btn sm primary" onClick={() => setMode('override')}>Continue as override</button>
                </div>
              )}
            </div>
          </div>
        </td></tr>
      )}
    </>
  );
}

Object.assign(window, { BomOverviewScreen });
