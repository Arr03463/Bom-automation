/* global React, Icon, StatusBadge, RoleTag, SupplierTag, Banner, EmptyState, TraceabilityStrip,
   RelatedLinks, BomTable, Totals, useStore, storeActions, PROJECTS, DC_BADGE, fmtUSD, fmtInt */
const { useState: useStateDC, useRef: useRefDC } = React;

const DC_CATEGORIES = ['Investigation', 'Testing', 'Validation', 'Rework', 'Reliability', 'Firmware', 'Hardware', 'Cost Reduction', 'Future Revision', 'Supplier Evaluation'];
const DC_CATEGORY_COLOR = {
  Investigation: '#059669', Testing: '#0891B2', Validation: '#0891B2', Rework: '#D97706',
  Reliability: '#7C3AED', Firmware: '#1A56DB', Hardware: '#059669',
  'Cost Reduction': '#16A34A', 'Future Revision': '#475569', 'Supplier Evaluation': '#EA580C',
};

const OUTCOME_TYPES = [
  { kind: 'recommendation', label: 'Improvement Recommendation', targetRole: 'designer', icon: 'sparkle',
    blurb: 'Suggest a part swap or design improvement to the Designer.' },
  { kind: 'rework', label: 'Rework Package', targetRole: 'production', icon: 'refresh',
    blurb: 'Send a structured rework procedure to Production for a batch of units.' },
  { kind: 'firmware', label: 'Firmware Release', targetRole: 'production', icon: 'upload',
    blurb: 'Push a firmware build to Production for validation.' },
  { kind: 'investigation-report', label: 'Investigation Report', targetRole: 'designer', icon: 'search',
    blurb: 'Publish findings — root cause, evidence, recommendation.' },
  { kind: 'eng-change', label: 'Engineering Change Recommendation', targetRole: 'designer', icon: 'flag',
    blurb: 'Formal engineering change request to the design team.' },
];

function CategoryChip({ category, size = 'sm' }) {
  const c = DC_CATEGORY_COLOR[category] || 'var(--role-development)';
  const h = size === 'lg' ? 24 : 20;
  return <span className="badge outlined" style={{ color: c, borderColor: c, height: h, fontSize: size === 'lg' ? 12 : 11 }}>
    <Icon name="tag" size={size === 'lg' ? 12 : 11} />{category}
  </span>;
}

function DevKindGlyph({ kind = 'development', size = 16 }) {
  // Visual marker to distinguish at-a-glance from Designer collections.
  const isDev = kind === 'development';
  return <span style={{ display: 'inline-grid', placeItems: 'center', width: size + 6, height: size + 6, borderRadius: 6, background: isDev ? 'var(--role-development)' : 'var(--role-designer)', color: '#fff', flex: 'none' }}>
    <Icon name={isDev ? 'sparkle' : 'layers'} size={size - 2} />
  </span>;
}

/* ---------- Development Collection List ---------- */
const DC_LIST_FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'draft', label: 'Draft' },
  { key: 'active', label: 'Active' },
  { key: 'ready', label: 'Ready for review' },
  { key: 'recommendation-sent', label: 'Recommendation sent' },
  { key: 'accepted', label: 'Accepted' },
  { key: 'rejected', label: 'Rejected' },
  { key: 'closed', label: 'Closed' },
];

function DevCollectionListScreen({ go }) {
  const all = useStore(s => s.collections.filter(c => c.role === 'development'));
  const [ls, setLs] = window.useListState('v.collections', { filter: 'all', cat: 'all', q: '' });
  const [showNew, setShowNew] = React.useState(false);
  let rows = all;
  if (ls.filter !== 'all') rows = rows.filter(c => c.state === ls.filter);
  if (ls.cat !== 'all') rows = rows.filter(c => c.category === ls.cat);
  if (ls.q.trim()) { const s = ls.q.toLowerCase(); rows = rows.filter(c => (c.name + (c.category || '') + PROJECTS[c.project].name).toLowerCase().includes(s)); }
  const counts = {}; DC_LIST_FILTERS.forEach(f => counts[f.key] = f.key === 'all' ? all.length : all.filter(c => c.state === f.key).length);

  return (
    <div className="page page-wide">
      <div className="page-head">
        <div className="ph-titles">
          <div className="display" style={{ display: 'flex', alignItems: 'center', gap: 12 }}><DevKindGlyph kind="development" size={20} />Development Collections</div>
          <div className="ph-sub">Investigations, testing, reliability studies — work that produces an outcome, not an order. Owned by Development.</div>
        </div>
        <div className="ph-actions">
          <button className="btn primary" style={{ background: 'var(--role-development)', borderColor: 'var(--role-development)' }} onClick={() => setShowNew(true)}><Icon name="plus" size={15} />New Development Collection</button>
        </div>
      </div>

      <div className="filterbar">
        {DC_LIST_FILTERS.map(f => <button key={f.key} className={`fchip${ls.filter === f.key ? ' active' : ''}`} onClick={() => setLs({ filter: f.key })}>{f.label}<span className="fc-n">{counts[f.key]}</span></button>)}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
          <select className="select" value={ls.cat} onChange={e => setLs({ cat: e.target.value })} style={{ height: 32, padding: '0 28px 0 10px', fontSize: 12.5, width: 180 }}>
            <option value="all">All categories</option>
            {DC_CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          <div className="searchfield" style={{ minWidth: 230 }}>
            <Icon name="search" size={15} style={{ color: 'var(--text-muted)' }} />
            <input value={ls.q} placeholder="Filter by name, category, project…" onChange={e => setLs({ q: e.target.value })} />
          </div>
        </div>
      </div>

      <div className="tbl-wrap flow" style={{ borderRadius: '0 0 10px 10px', borderTop: 0 }}>
        {rows.length === 0 ? <EmptyState icon="search" title="No Development Collections match these filters." sub="Clear the filter or create a new collection to start an investigation."
          actions={<button className="btn" onClick={() => setLs({ filter: 'all', cat: 'all', q: '' })}>Clear filters</button>} />
        : rows.map(c => {
          const outcome = c.outcomes && c.outcomes[0];
          return (
            <div key={c.id} className="lrow" style={{ boxShadow: 'inset 3px 0 0 var(--role-development)' }} onClick={() => go({ screen: 'v.collectionDetail', id: c.id })}>
              <div style={{ minWidth: 0 }}>
                <div className="lr-title" style={{ display: 'flex', alignItems: 'center', gap: 9, flexWrap: 'wrap' }}>
                  <DevKindGlyph kind="development" size={13} />
                  <span>{c.name}</span>
                  <StatusBadge status={DC_BADGE[c.state]} />
                  <CategoryChip category={c.category} />
                </div>
                <div className="lr-meta">
                  <span className="mono">{c.id}</span><span className="tr-sep" />
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}><Icon name="folder" size={13} />{PROJECTS[c.project].name}</span>
                  <span className="tr-sep" /><span>{c.items.length} part{c.items.length !== 1 ? 's' : ''}</span>
                  <span className="tr-sep" /><span>{c.creator}</span>
                  <span className="tr-sep" /><span>updated {c.updated}</span>
                </div>
              </div>
              <div className="lr-right">
                <div className="lr-stats">
                  {outcome ? <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}><Icon name="send" size={12} style={{ color: 'var(--role-development)' }} /><b>{outcome.label}</b> → {outcome.targetRole}</span>
                    : <span className="muted">No outcome yet</span>}
                </div>
              </div>
            </div>
          );
        })}
      </div>
      {showNew && <NewCollectionModal kind="development" onClose={() => setShowNew(false)} onCreated={(id) => { setShowNew(false); go({ screen: 'v.collectionDetail', id }); }} />}
    </div>
  );
}

/* ---------- Generate Outcome modal ---------- */
function GenerateOutcomeModal({ collection, onClose, onDone }) {
  const [kind, setKind] = useStateDC(null);
  const [title, setTitle] = useStateDC(collection.name);
  const [note, setNote] = useStateDC(collection.notes || '');
  const [boards, setBoards] = useStateDC('');
  const [version, setVersion] = useStateDC('');
  const [proposedMpn, setProposedMpn] = useStateDC('');
  const [currentMpn, setCurrentMpn] = useStateDC('');

  const meta = OUTCOME_TYPES.find(t => t.kind === kind);
  const canSubmit = !!kind && title.trim().length > 2 && (kind !== 'rework' || +boards > 0) && (kind !== 'firmware' || version.trim()) && (kind !== 'recommendation' || (proposedMpn.trim() && currentMpn.trim()));
  const submit = () => {
    const id = storeActions.generateOutcome(collection.id, { kind, title: title.trim(), desc: collection.desc, note: note.trim(),
      proposedMpn: proposedMpn.trim(), currentMpn: currentMpn.trim(), boards: +boards || 0, version: version.trim(),
      procedure: note.split('\n').filter(Boolean), changelog: note.split('\n').filter(Boolean) });
    onDone(id, meta);
  };

  return (
    <div className="modal-wrap"><div className="scrim" onClick={onClose} />
      <div className="modal" style={{ position: 'relative', zIndex: 95, width: 640, maxWidth: '94vw' }}>
        <div className="modal-head"><div className="mh-title" style={{ display: 'flex', alignItems: 'center', gap: 9 }}><Icon name="send" size={18} style={{ color: 'var(--role-development)' }} />Generate Outcome — {collection.name}</div>
          <div className="caption" style={{ marginTop: 4 }}>Pick the outcome type. This pushes a handshake to the receiving role with notification, audit, and ownership transfer.</div></div>
        <div className="modal-body" style={{ maxHeight: '60vh', overflowY: 'auto' }}>
          {!kind ? (
            <div style={{ display: 'grid', gap: 8 }}>
              {OUTCOME_TYPES.map(o => (
                <button key={o.kind} className="role-row" style={{ textAlign: 'left', cursor: 'pointer', borderColor: 'var(--border-soft)', background: 'var(--bg-surface)' }} onClick={() => setKind(o.kind)}>
                  <span style={{ width: 36, height: 36, borderRadius: 8, background: 'var(--success-soft)', color: 'var(--role-development)', display: 'grid', placeItems: 'center', flex: 'none' }}><Icon name={o.icon} size={18} /></span>
                  <div style={{ flex: 1 }}><div style={{ fontWeight: 600 }}>{o.label}</div><div className="caption" style={{ marginTop: 2 }}>{o.blurb}</div></div>
                  <span className="tag" style={{ color: '#fff', background: 'var(--role-' + o.targetRole + ')' }}>→ {o.targetRole.toUpperCase()}</span>
                </button>
              ))}
            </div>
          ) : (
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '8px 11px', background: 'var(--bg-overlay)', borderRadius: 7, marginBottom: 14 }}>
                <Icon name={meta.icon} size={16} style={{ color: 'var(--role-development)' }} />
                <span style={{ fontWeight: 600 }}>{meta.label}</span>
                <span className="tag" style={{ marginLeft: 'auto', color: '#fff', background: 'var(--role-' + meta.targetRole + ')' }}>→ {meta.targetRole.toUpperCase()}</span>
                <button className="btn ghost sm" onClick={() => setKind(null)}>Change</button>
              </div>
              <label className="field" style={{ marginBottom: 10 }}><span className="fl">Title</span>
                <input className="input" value={title} onChange={e => setTitle(e.target.value)} /></label>
              {kind === 'recommendation' && (
                <>
                  <label className="field" style={{ marginBottom: 10 }}><span className="fl">Current MPN <span className="muted">(being replaced)</span></span>
                    <input className="input mono" value={currentMpn} onChange={e => setCurrentMpn(e.target.value)} placeholder="e.g. IRFB4110PBF" /></label>
                  <div className="field" style={{ marginBottom: 10 }}>
                    <span className="fl">Proposed MPN <span className="muted">(verify before pushing)</span></span>
                    {proposedMpn && proposedMpn.trim() && false /* confirmed view handled by IPV reset */}
                    <InlinePartVerify
                      mpn={proposedMpn}
                      mfr={''}
                      onMpnChange={setProposedMpn}
                      onMfrChange={() => {}}
                      originalMpn={currentMpn}
                      onConfirm={(part) => { setProposedMpn(part.mpn); }}
                    />
                  </div>
                </>
              )}
              {kind === 'rework' && (
                <label className="field" style={{ marginBottom: 10 }}><span className="fl">Units to rework</span>
                  <input className="input" type="number" value={boards} onChange={e => setBoards(e.target.value)} placeholder="e.g. 12" /></label>
              )}
              {kind === 'firmware' && (
                <label className="field" style={{ marginBottom: 10 }}><span className="fl">Version</span>
                  <input className="input mono" value={version} onChange={e => setVersion(e.target.value)} placeholder="e.g. 1.5.0" /></label>
              )}
              <label className="field"><span className="fl">{kind === 'rework' ? 'Procedure' : kind === 'firmware' ? 'Changelog' : 'Note to receiving role'} <span className="muted">(one per line)</span></span>
                <textarea className="textarea" rows={5} value={note} onChange={e => setNote(e.target.value)} placeholder={kind === 'rework' ? 'Step 1…\nStep 2…' : kind === 'firmware' ? 'Changelog item…' : 'Context, findings, recommendation…'} /></label>
            </>
          )}
        </div>
        <div className="modal-foot">
          <button className="btn" onClick={onClose}>Cancel</button>
          {kind && <button className="btn primary" disabled={!canSubmit} style={{ background: 'var(--role-development)', borderColor: 'var(--role-development)' }} onClick={submit}><Icon name="send" size={15} />Push to {meta.targetRole}</button>}
        </div>
      </div>
    </div>
  );
}

/* ---------- Development Collection Detail ---------- */
function DevCollectionDetail({ id, go }) {
  const c = useStore(s => s.collections.find(x => x.id === id && x.role === 'development'));
  const [outcomeOpen, setOutcomeOpen] = useStateDC(false);
  const [addOpen, setAddOpen] = useStateDC(false);
  const [editingNote, setEditingNote] = useStateDC(null);
  const [noteDraft, setNoteDraft] = useStateDC('');
  if (!c) return <div className="page"><EmptyState icon="search" title="Development Collection not found." /></div>;
  const PROJ = PROJECTS[c.project];
  const stateNext = c.state === 'draft' ? 'active' : c.state === 'active' ? 'ready' : null;
  const canPushOutcome = c.state === 'ready';
  const isLocked = ['accepted', 'closed', 'archived'].includes(c.state);

  return (
    <div className="page page-wide">
      <div className="page-head" style={{ marginBottom: 4 }}>
        <div className="ph-titles">
          <button className="btn-link" style={{ marginBottom: 8 }} onClick={() => go({ screen: 'v.collections' })}>← Development Collections</button>
          <div className="h1" style={{ display: 'flex', alignItems: 'center', gap: 11 }}><DevKindGlyph kind="development" size={18} />{c.name}</div>
        </div>
        <div className="ph-actions">
          {!isLocked && stateNext && <button className="btn" onClick={() => storeActions.setDevCollectionState(c.id, stateNext)}>
            <Icon name="arrow" size={15} />Mark {stateNext === 'ready' ? 'Ready for Review' : 'Active'}
          </button>}
          {canPushOutcome && <button className="btn primary" style={{ background: 'var(--role-development)', borderColor: 'var(--role-development)' }} onClick={() => setOutcomeOpen(true)}>
            <Icon name="send" size={15} />Generate Outcome
          </button>}
        </div>
      </div>
      <TraceabilityStrip name={c.name} status={DC_BADGE[c.state]} creator={c.creator} role="development"
        project={PROJ.name} updated={c.updated} updatedBy={c.updatedBy} recordId={c.id}
        onProject={() => go({ screen: 'projectDetail', id: c.project, tab: 'collections' })} />

      <div style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '10px 0 2px' }}>
        <CategoryChip category={c.category} size="lg" />
        <span className="caption">·</span>
        <span className="caption">Development Collection · feeds into <strong style={{ color: 'var(--role-development)' }}>Improvement Recommendation / Rework / Firmware / Investigation Report / Engineering Change</strong></span>
      </div>

      <RelatedLinks items={[
        { kind: 'PCB Project', label: PROJ.name, icon: 'folder', onClick: () => go({ screen: 'projectDetail', id: c.project }) },
        ...(c.outcomes || []).map(o => ({ kind: o.label, label: o.linkedId, icon: 'send',
          onClick: () => go(o.kind === 'rework' ? { screen: 'v.reworkDetail', id: o.linkedId }
            : o.kind === 'firmware' ? { screen: 'v.firmwareDetail', id: o.linkedId }
            : o.kind === 'investigation-report' ? { screen: 'v.investigationDetail', id: o.linkedId }
            : { screen: 'v.recommendationDetail', id: o.linkedId }) })),
      ]} />

      {c.state === 'draft' && <Banner kind="info" icon="circle" title="Draft — work in progress"
        actions={<button className="btn sm" onClick={() => storeActions.setDevCollectionState(c.id, 'active')}>Start investigation</button>}>
        Add candidate components and notes. When you're ready, mark the collection Active to record progress and stale-check supplier data.
      </Banner>}
      {c.state === 'recommendation-sent' && c.outcomes[0] && <Banner kind="info" icon="send" title={`${c.outcomes[0].label} pushed to ${c.outcomes[0].targetRole} · ${c.outcomes[0].when}`}
        actions={<button className="btn sm" onClick={() => go(c.outcomes[0].kind === 'rework' ? { screen: 'v.reworkDetail', id: c.outcomes[0].linkedId } : c.outcomes[0].kind === 'firmware' ? { screen: 'v.firmwareDetail', id: c.outcomes[0].linkedId } : c.outcomes[0].kind === 'investigation-report' ? { screen: 'v.investigationDetail', id: c.outcomes[0].linkedId } : { screen: 'v.recommendationDetail', id: c.outcomes[0].linkedId })}>Track outcome →</button>}>
        Linked outcome: <span className="mono">{c.outcomes[0].linkedId}</span>. Awaiting response from the receiving role.
      </Banner>}
      {isLocked && <Banner kind="lock" title={`${c.state[0].toUpperCase() + c.state.slice(1)} — read-only`}>
        This collection is preserved as historical record. Knowledge stays in the system forever.
      </Banner>}

      <p className="secondary" style={{ margin: '10px 0 0', maxWidth: 760 }}>{c.desc}</p>

      {/* Investigation notes — distinct from per-item notes */}
      <div className="card" style={{ padding: 14, marginTop: 16 }}>
        <div className="caption" style={{ fontWeight: 700, textTransform: 'uppercase', fontSize: 10.5, letterSpacing: '.04em', color: 'var(--text-muted)' }}>Investigation Notes</div>
        {isLocked
          ? <p style={{ margin: '6px 0 0' }} className="secondary">{c.notes || 'No notes.'}</p>
          : <textarea className="textarea" style={{ marginTop: 8, minHeight: 56, border: 'none', padding: 0, background: 'transparent', resize: 'vertical' }} defaultValue={c.notes} onBlur={e => storeActions.setDevCollectionNotes(c.id, e.target.value)} placeholder="Capture observations, test results, hypotheses…" />}
      </div>

      {/* Candidate components */}
      <div style={{ marginTop: 16, display: 'flex', alignItems: 'center', gap: 10 }}>
        <div className="h2" style={{ margin: 0 }}>Candidate components · {c.items.length}</div>
        <span className="caption" style={{ marginLeft: 6 }}>Run sourcing check on any candidate.</span>
        {!isLocked && <button className="btn sm" style={{ marginLeft: 'auto' }} onClick={() => setAddOpen(true)}><Icon name="plus" size={13} />Add component</button>}
      </div>

      {c.items.length === 0 ? (
        <div className="card" style={{ marginTop: 8 }}><EmptyState icon="search" title="No candidates yet."
          sub="Search a part and add it as a candidate to record observations." actions={<button className="btn primary" onClick={() => setAddOpen(true)}><Icon name="plus" size={14} />Add a candidate</button>} /></div>
      ) : (
        <div className="tbl-wrap flow" style={{ marginTop: 8 }}>
          <table className="bom">
            <thead><tr><th style={{ width: 36 }}>#</th><th>MPN</th><th>Manufacturer</th><th>Description</th><th className="num">Qty</th><th>Supplier</th><th>Test note</th><th>Status</th></tr></thead>
            <tbody>
              {c.items.map((i, idx) => (
                <tr key={i.no} className={idx % 2 ? 'alt' : ''}>
                  <td className="num muted">{i.no}</td>
                  <td className="mono" style={{ fontWeight: 600 }}>{i.mpn}</td>
                  <td>{i.mfr}</td>
                  <td className="secondary" style={{ maxWidth: 220 }}>{i.desc}</td>
                  <td className="num">{i.qty}</td>
                  <td>{i.supplier ? <SupplierTag supplier={i.supplier} /> : <span className="muted">—</span>}</td>
                  <td style={{ minWidth: 260 }}>
                    {editingNote === i.no && !isLocked ? (
                      <input className="input" autoFocus value={noteDraft} onChange={e => setNoteDraft(e.target.value)}
                        onBlur={() => { storeActions.setDevItemNote(c.id, i.no, noteDraft); setEditingNote(null); }}
                        onKeyDown={e => { if (e.key === 'Enter') { storeActions.setDevItemNote(c.id, i.no, noteDraft); setEditingNote(null); } if (e.key === 'Escape') setEditingNote(null); }} />
                    ) : (
                      <span className={`cell-editable${isLocked ? '' : ''}`} style={{ cursor: isLocked ? 'default' : 'text' }}
                        onClick={() => { if (!isLocked) { setEditingNote(i.no); setNoteDraft(i.note || ''); } }}>
                        {i.note ? <span style={{ color: 'var(--text-primary)' }}>{i.note}</span> : <span className="muted">Click to add observation…</span>}
                      </span>
                    )}
                  </td>
                  <td><StatusBadge status={i.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Outcome history */}
      <div className="h2" style={{ marginTop: 22 }}>Outcome history</div>
      {(c.outcomes && c.outcomes.length) ? (
        <div className="list" style={{ marginTop: 8 }}>
          {c.outcomes.map(o => {
            const stateBadge = o.state === 'accepted' ? 'accepted' : o.state === 'rejected' ? 'rejected' : 'submitted';
            return (
              <div key={o.id} className="lrow" onClick={() => go(o.kind === 'rework' ? { screen: 'v.reworkDetail', id: o.linkedId } : o.kind === 'firmware' ? { screen: 'v.firmwareDetail', id: o.linkedId } : o.kind === 'investigation-report' ? { screen: 'v.investigationDetail', id: o.linkedId } : { screen: 'v.recommendationDetail', id: o.linkedId })}>
                <div style={{ minWidth: 0 }}>
                  <div className="lr-title" style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                    <Icon name="send" size={15} style={{ color: 'var(--role-development)' }} />
                    <span>{o.label}</span>
                    <span className="mono caption">{o.linkedId}</span>
                    <StatusBadge status={stateBadge} />
                  </div>
                  <div className="lr-meta">Pushed to <RoleTag role={o.targetRole} /> · {o.when}</div>
                </div>
                <Icon name="chevright" size={16} style={{ color: 'var(--text-muted)' }} />
              </div>
            );
          })}
        </div>
      ) : (
        <div className="comment-empty" style={{ marginTop: 8 }}>No outcomes generated yet. Once your investigation is complete, mark it Ready for Review then push the outcome to the receiving role.</div>
      )}

      {outcomeOpen && <GenerateOutcomeModal collection={c} onClose={() => setOutcomeOpen(false)}
        onDone={(id, meta) => { setOutcomeOpen(false); window.__toast?.(`${meta.label} pushed to ${meta.targetRole} · ${id}`, 'send'); }} />}
      <AddPartDrawer open={addOpen} onClose={() => setAddOpen(false)} collectionId={c.id} kind="development" />
      <div style={{ marginTop: 26 }}><CommentThread entityId={c.id} /></div>
    </div>
  );
}

Object.assign(window, { DevCollectionListScreen, DevCollectionDetail, DC_CATEGORIES, CategoryChip, DevKindGlyph });
