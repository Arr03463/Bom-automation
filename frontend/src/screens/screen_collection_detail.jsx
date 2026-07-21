/* global React, Icon, StatusBadge, RoleTag, SupplierTag, Banner, EmptyState, Freshness,
   TraceabilityStrip, Popover, CommentThread, AddPartDrawer,
   useStore, storeActions, PROJECTS, fmtUSD, fmtInt */
const { useState: useStateCD, useRef: useRefCD, useEffect: useEffCD } = React;

/* ============================================================
   BomTable — used by Collections and BOM detail.
   editable      → qty cells become inline-editable
   onRemove(no)  → trash icon per row (with confirm). Activates "manage" col.
   onNote        → per-row note editor (collection edit mode)
   onRefresh(no) → refresh sourcing for that line
   ============================================================ */
const LINE_FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'exception', label: 'Needs review', test: i => i.status === 'needs-review' || i.status === 'exception' },
  { key: 'check-wall', label: 'Check wall', test: i => i.status === 'check-wall' },
  { key: 'mouser', label: 'Mouser', test: i => i.supplier === 'mouser' },
  { key: 'digikey', label: 'DigiKey', test: i => i.supplier === 'digikey' },
];

function BomTable({ items, editable, onQty, onRemove, onNote, onRefresh, selectable, selected, onToggle, showSource, showCpn, sourceObj, defaultSort }) {
  const [filter, setFilter] = useStateCD('all');
  const [q, setQ] = useStateCD('');
  const [sort, setSort] = useStateCD(defaultSort || { col: 'no', dir: 1 });
  const [editing, setEditing] = useStateCD(null);
  const [draft, setDraft] = useStateCD('');
  const [editingNote, setEditingNote] = useStateCD(null);
  const [noteDraft, setNoteDraft] = useStateCD('');
  const [confirmRemove, setConfirmRemove] = useStateCD(null);
  const sel = selected || new Set();
  const showManage = !!(onRemove || onRefresh);

  const f = LINE_FILTERS.find(x => x.key === filter);
  let rows = items.filter(i => filter === 'all' ? true : (f.test ? f.test(i) : true));
  if (q.trim()) { const s = q.toLowerCase(); rows = rows.filter(i => (i.mpn + i.mfr + i.desc).toLowerCase().includes(s)); }
  const val = (i, c) => c === 'status' ? i.status : c === 'unit' ? (i.unit || 0) : c === 'ext' ? (i.ext || 0) : i[c];
  rows = [...rows].sort((a, b) => { const x = val(a, sort.col), y = val(b, sort.col); return (x > y ? 1 : x < y ? -1 : 0) * sort.dir; });
  const counts = {}; LINE_FILTERS.forEach(x => counts[x.key] = x.key === 'all' ? items.length : items.filter(x.test).length);

  const Th = ({ col, children, num }) => (
    <th className="sortable" style={num ? { textAlign: 'right' } : null}
      onClick={() => setSort(s => ({ col, dir: s.col === col ? -s.dir : 1 }))}>
      <span className="th-inner">{children}{sort.col === col && <Icon name="chevdown" size={12} style={{ transform: sort.dir < 0 ? 'rotate(180deg)' : 'none' }} />}</span>
    </th>
  );
  const commit = (i) => { const n = parseInt(draft, 10); if (!isNaN(n) && n > 0) onQty(i.no, n); setEditing(null); };
  const commitNote = (i) => { onNote && onNote(i.no, noteDraft); setEditingNote(null); };

  return (
    <>
      <div className="filterbar">
        {LINE_FILTERS.map(x => (
          <button key={x.key} className={`fchip${filter === x.key ? ' active' : ''}`} onClick={() => setFilter(x.key)}>
            {x.label}<span className="fc-n">{counts[x.key]}</span>
          </button>
        ))}
        <div className="searchfield" style={{ marginLeft: 'auto', minWidth: 230 }}>
          <Icon name="search" size={15} style={{ color: 'var(--text-muted)' }} />
          <input value={q} placeholder="Filter MPN, manufacturer, description…" onChange={e => setQ(e.target.value)} />
        </div>
      </div>
      <div className="tbl-wrap flow" style={{ borderRadius: '0 0 10px 10px', borderTop: 0 }}>
        <table className="bom">
          <thead><tr>
            {selectable && <th style={{ width: 34 }}></th>}
            <Th col="no" num>#</Th>
            <Th col="mpn">MPN</Th>
            <Th col="mfr">Manufacturer</Th>
            <th>Description</th>
            {showSource && <th>Source</th>}
            {showCpn && <th>CPN</th>}
            <Th col="qty" num>Qty</Th>
            <th>Supplier</th>
            <Th col="unit" num>Unit</Th>
            <Th col="ext" num>Ext.</Th>
            <Th col="status">Status</Th>
            {showManage && <th style={{ width: 96, textAlign: 'right' }}>Manage</th>}
          </tr></thead>
          <tbody>
            {rows.map((i, idx) => {
              const rowCls = i.status === 'needs-review' || i.status === 'exception' ? 'exception'
                : i.status === 'check-wall' || i.stale ? 'warn' : (sel.has(i.no) ? 'selected' : (idx % 2 ? 'alt' : ''));
              return (
                <React.Fragment key={i.no}>
                  <tr className={rowCls}>
                    {selectable && <td><input type="checkbox" checked={sel.has(i.no)} onChange={() => onToggle(i.no)} disabled={!(i.status === 'needs-review' || i.status === 'exception')} /></td>}
                    <td className="num muted">{i.no}</td>
                    <td className="mono" style={{ fontWeight: 600 }}>{i.mpn}{i.replacement && <span className="caption" style={{ display: 'block', color: 'var(--success)', fontFamily: 'var(--font-sans)' }}>↳ replaced {i.replacement.from}</span>}</td>
                    <td>{i.mfr}</td>
                    <td className="secondary" style={{ maxWidth: 230 }}>{i.desc}{i.exReason && <span className="caption" style={{ display: 'block', color: 'var(--danger)' }}>{i.exReason}</span>}</td>
                    {showSource && <td className="caption">{i.source ? <span title={`Selected by ${i.sourceBy || ''}`}><span className="mono">{i.source}</span></span> : <span className="muted">—</span>}</td>}
                    {showCpn && <td><span className="cpn-cell"><span className="mono caption" title="Customer Part Number — read-only">{window.cpnFor ? window.cpnFor(sourceObj, i) : (i.cpn || '—')}</span>{window.cpnScope && <span className={`scope-pill ${window.cpnScope(sourceObj)}`}>{window.cpnScope(sourceObj)}</span>}</span></td>}
                    <td className="num">
                      {editable ? (
                        editing === i.no
                          ? <input className="cell-edit" autoFocus value={draft} onChange={e => setDraft(e.target.value)}
                              onBlur={() => commit(i)} onKeyDown={e => { if (e.key === 'Enter') commit(i); if (e.key === 'Escape') setEditing(null); }} />
                          : <span className="cell-editable" onClick={() => { setEditing(i.no); setDraft(String(i.qty)); }}>{i.qty}</span>
                      ) : i.qty}
                    </td>
                    <td>{i.supplier ? <SupplierTag supplier={i.supplier} /> : <span className="muted">—</span>}</td>
                    <td className="num mono">{i.unit != null ? fmtUSD(i.unit) : '—'}</td>
                    <td className="num mono" style={{ fontWeight: 600 }}>{i.ext != null ? fmtUSD(i.ext) : '—'}</td>
                    <td><StatusBadge status={i.status} /></td>
                    {showManage && (
                      <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                        {onRefresh && <button className="icon-btn" style={{ width: 28, height: 28 }} title="Refresh sourcing" onClick={() => onRefresh(i.no)}><Icon name="refresh" size={14} /></button>}
                        {onNote && <button className="icon-btn" style={{ width: 28, height: 28, color: i.note ? 'var(--action)' : undefined }} title={i.note ? `Note: ${i.note}` : 'Add note'} onClick={() => { setEditingNote(i.no); setNoteDraft(i.note || ''); }}><Icon name="comment" size={14} /></button>}
                        {onRemove && <button className="icon-btn" style={{ width: 28, height: 28, color: 'var(--danger)' }} title="Remove from collection" onClick={() => setConfirmRemove(i)}><Icon name="x" size={14} /></button>}
                      </td>
                    )}
                  </tr>
                  {editingNote === i.no && (
                    <tr className={rowCls}>
                      <td colSpan={99} style={{ padding: '8px 14px', background: 'var(--bg-raised)' }}>
                        <div style={{ display: 'flex', gap: 9, alignItems: 'center' }}>
                          <Icon name="comment" size={14} style={{ color: 'var(--text-muted)' }} />
                          <input className="input" autoFocus placeholder="Per-line note — observations, test conditions, why this part…" value={noteDraft} onChange={e => setNoteDraft(e.target.value)}
                            onKeyDown={e => { if (e.key === 'Enter') commitNote(i); if (e.key === 'Escape') setEditingNote(null); }}
                            style={{ flex: 1 }} />
                          <button className="btn sm" onClick={() => setEditingNote(null)}>Cancel</button>
                          <button className="btn sm primary" onClick={() => commitNote(i)}>Save note</button>
                        </div>
                      </td>
                    </tr>
                  )}
                  {!editing && i.note && editingNote !== i.no && (
                    <tr className={rowCls} style={{ background: 'var(--bg-raised)' }}>
                      <td colSpan={99} style={{ padding: '4px 14px 6px', fontSize: 12.5, color: 'var(--text-secondary)' }}>
                        <Icon name="comment" size={11} style={{ marginRight: 5, verticalAlign: -1 }} />
                        <em>Note:</em> {i.note}
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      {confirmRemove && (
        <>
          <div className="scrim" onMouseDown={() => setConfirmRemove(null)} />
          <div className="modal-wrap"><div className="modal">
            <div className="modal-head"><div className="mh-title">Remove this part?</div></div>
            <div className="modal-body">
              <p><strong className="mono">{confirmRemove.mpn}</strong> ({confirmRemove.mfr}) will be removed from this collection. This action is recorded in the audit trail.</p>
            </div>
            <div className="modal-foot">
              <button className="btn" onClick={() => setConfirmRemove(null)}>Cancel</button>
              <button className="btn danger" onClick={() => { onRemove(confirmRemove.no); setConfirmRemove(null); }}><Icon name="x" size={14} />Remove part</button>
            </div>
          </div></div>
        </>
      )}
    </>
  );
}

function Totals({ items }) {
  const sum = sup => items.filter(i => i.supplier === sup).reduce((a, i) => a + (i.ext || 0), 0);
  const m = sum('mouser'), d = sum('digikey'), g = m + d;
  return (
    <div style={{ display: 'flex', gap: 26, justifyContent: 'flex-end', padding: '14px 16px', borderTop: '1px solid var(--border)', flexWrap: 'wrap' }}>
      <div style={{ textAlign: 'right' }}><div className="caption" style={{ display: 'flex', alignItems: 'center', gap: 5, justifyContent: 'flex-end' }}><span className="dot" style={{ background: 'var(--supplier-mouser)' }} />Mouser</div><div className="mono" style={{ fontWeight: 600 }}>{fmtUSD(m)}</div></div>
      <div style={{ textAlign: 'right' }}><div className="caption" style={{ display: 'flex', alignItems: 'center', gap: 5, justifyContent: 'flex-end' }}><span className="dot" style={{ background: 'var(--supplier-digikey)' }} />DigiKey</div><div className="mono" style={{ fontWeight: 600 }}>{fmtUSD(d)}</div></div>
      <div style={{ textAlign: 'right' }}><div className="caption">Estimated total</div><div className="mono" style={{ fontWeight: 700, fontSize: 17 }}>{fmtUSD(g)}</div></div>
    </div>
  );
}

function RequestToOrder({ collection, onClose, onConfirm }) {
  const programName = (() => { const st = window.getState && window.getState(); const pr = st && (st.programs || []).find(p => p.id === (collection.program || collection.program_id)); return pr ? pr.name : (PROJECTS[collection.project] ? PROJECTS[collection.project].name : '—'); })();
  const total = collection.items.reduce((a, i) => a + (i.ext || 0), 0);
  return <SendToBucketPanel title="Send to purchasing bucket" sourceId={collection.id} items={collection.items}
    summaryRows={[['Collection', collection.name], ['Program', programName], ['Parts', collection.items.length], ['Estimated total', <span className="mono" style={{ fontWeight: 600 }}>{fmtUSD(total)}</span>]]}
    onClose={onClose} onConfirm={onConfirm} />;
}
function SendToBucketPanel({ title = 'Send to purchasing bucket', sourceId, items, summaryRows, allowRecheck = true, onClose, onConfirm }) {
  const [note, setNote] = useStateCD('');
  const [critical, setCritical] = useStateCD(false); // Critical flag — replaces Required By/Urgency entirely. Default off.
  const [staleChoice, setStaleChoice] = useStateCD(null); // null | 'rechecked' | 'proceed'
  const [rechecking, setRechecking] = useStateCD(false);
  const stale = allowRecheck && items.some(i => i.stale);
  const review = items.filter(i => i.status === 'needs-review').length;
  const total = items.reduce((a, i) => a + (i.ext || 0), 0);
  /* FR-D06 — Stale-data gate.
     If any item's sourcing is >24h old, the user MUST choose: Re-check now (refreshes
     stale items, clears the gate) or Proceed with current data (writes a note onto the
     request). Submit is disabled until one path is taken. We never silently submit stale. */
  const recheckNow = async () => {
    setRechecking(true);
    await new Promise(r => setTimeout(r, 1100));
    window.storeActions.refreshSourcing(sourceId, null);
    setRechecking(false);
    setStaleChoice('rechecked');
  };
  const proceedAnyway = () => setStaleChoice('proceed');
  const gateBlocking = (stale && !staleChoice); // Critical flag defaults off; nothing else is mandatory
  const submitNote = staleChoice === 'proceed'
    ? `${note ? note + '\n\n' : ''}[Submitted with stale sourcing data — designer acknowledged]`
    : note;
  return (
    <>
      <div className="scrim" onClick={onClose} />
      <div className="slideout" role="dialog" aria-label={title}>
        <div className="slideout-head">
          <Icon name="cart" size={18} /><span style={{ fontWeight: 700, fontSize: 16, flex: 1 }}>{title}</span>
          <button className="icon-btn" onClick={onClose}><Icon name="x" size={18} /></button>
        </div>
        <div className="slideout-body">
          {review > 0 && <Banner kind="warn" title={`${review} item${review > 1 ? 's' : ''} still need review`}>These lines aren't fully sourced yet. You can still send them to the bucket, but sourcing them first is recommended.</Banner>}
          {stale && !staleChoice && (
            <div className="card" style={{ padding: 14, border: '1px solid var(--warning)', background: 'rgba(217, 119, 6, .06)', marginBottom: 12 }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                <Icon name="alert" size={18} style={{ color: 'var(--warning)', flex: 'none', marginTop: 2 }} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 700, marginBottom: 4 }}>Sourcing data is more than 24 hours old</div>
                  <p className="caption" style={{ margin: 0, lineHeight: 1.55 }}>Sending stale pricing to the bucket means the Daily Purchasing List may be out of date. Choose how to proceed before sending — you can't send without a decision.</p>
                  <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
                    <button className="btn sm primary" disabled={rechecking} onClick={recheckNow}>
                      {rechecking ? <><span className="spinner" style={{ width: 13, height: 13 }} />Re-checking…</> : <><Icon name="refresh" size={13} />Re-check now</>}
                    </button>
                    <button className="btn sm" onClick={proceedAnyway}><Icon name="arrow" size={13} />Proceed with current data</button>
                  </div>
                </div>
              </div>
            </div>
          )}
          {staleChoice === 'rechecked' && <Banner kind="info" icon="check" title="Sourcing re-checked">All supplier data was refreshed. Pricing and stock are now current.</Banner>}
          {staleChoice === 'proceed' && <Banner kind="warn" icon="alert" title="Sending with stale data">A note will be attached so the purchasing list shows the sourcing data was older than 24h when it entered the bucket.</Banner>}
          <dl className="kv" style={{ margin: '6px 0 16px' }}>
            {summaryRows.map(([label, node], i) => (<React.Fragment key={i}><dt>{label}</dt><dd style={i === 0 ? { fontWeight: 600 } : undefined}>{node}</dd></React.Fragment>))}
            <dt>Goes to</dt><dd>Shared purchasing bucket</dd>
          </dl>
          {/* Critical flag — replaces Required By / Urgency entirely (v2 bucket model).
             Per-line urgency is meaningless once items consolidate into 2 supplier carts.
             Default off → request enters the Main bucket. On → Critical bucket (faster batch cadence). */}
          <div className="crit-toggle">
            <button type="button" role="switch" aria-checked={critical} className={`switch${critical ? ' on' : ''}`} onClick={() => setCritical(c => !c)}><span className="knob" /></button>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: 7 }}>Mark as Critical{critical && <span className="badge filled" style={{ background: 'var(--danger)' }}><Icon name="alert" size={11} />CRITICAL</span>}</div>
              <div className="caption" style={{ marginTop: 2 }}>{critical
                ? 'Enters the Critical bucket — batched to the purchasing list on the faster cadence.'
                : 'Off by default — enters the Main bucket on the normal batch cadence.'}</div>
            </div>
          </div>
          <label className="field" style={{ marginTop: 14 }}><span className="fl">Note to Purchasing <span className="muted">(optional)</span></span>
            <textarea className="textarea" placeholder="Add context for the purchasing team — budget code, R&D vs production…" value={note} onChange={e => setNote(e.target.value)} /></label>
          <div className="caption" style={{ marginTop: 12, display: 'flex', gap: 7, alignItems: 'flex-start' }}><Icon name="external" size={14} style={{ marginTop: 1, color: 'var(--success)' }} /><span>On submit, these rows pool into the shared purchasing bucket and are batched to the live <strong>Daily Purchasing List</strong> on the next {critical ? 'Critical' : 'Main'} timer — no export, no manual handoff.</span></div>
          <div className="caption" style={{ marginTop: 8, display: 'flex', gap: 7, alignItems: 'flex-start' }}><Icon name="lock" size={14} style={{ marginTop: 1 }} />Sending locks these lines so they stay stable in the bucket. You can still view and comment.</div>
        </div>
        <div className="slideout-foot">
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={gateBlocking} onClick={() => onConfirm(submitNote, critical)} title={gateBlocking ? 'Resolve the stale-data warning above first' : ''}><Icon name="send" size={15} />Send to purchasing bucket</button>
        </div>
      </div>
    </>
  );
}

/* Inline-editable title and description.
   The title behaves like a normal heading until clicked/focused.
   Edits commit on blur; Esc reverts. */
function InlineTitle({ value, onChange, disabled }) {
  const [text, setText] = useStateCD(value);
  useEffCD(() => setText(value), [value]);
  return (
    <input className="inline-edit-title" value={text} disabled={disabled}
      onChange={e => setText(e.target.value)}
      onBlur={() => { if (text.trim() && text !== value) onChange(text.trim()); else setText(value); }}
      onKeyDown={e => { if (e.key === 'Enter') e.target.blur(); if (e.key === 'Escape') { setText(value); e.target.blur(); } }}
      aria-label="Collection name (click to edit)"
      title={disabled ? '' : 'Click to rename'} />
  );
}
function InlineDescription({ value, onChange, disabled, placeholder }) {
  const [text, setText] = useStateCD(value || '');
  useEffCD(() => setText(value || ''), [value]);
  return (
    <textarea className="inline-edit-desc" rows={1} value={text} disabled={disabled} placeholder={placeholder || 'Click to add a description…'}
      onChange={e => setText(e.target.value)}
      onBlur={() => { if (text !== (value || '')) onChange(text); }}
      onKeyDown={e => { if (e.key === 'Escape') { setText(value || ''); e.target.blur(); } }} />
  );
}

function CollectionDetailScreen({ id, collection, go, onSubmitOrder }) {
  const [panel, setPanel] = useStateCD(false);
  const [addOpen, setAddOpen] = useStateCD(false);
  const [projectDraft, setProjectDraft] = useStateCD(null);
  // Resolve the record from the store by id. This screen used to require a
  // `collection` OBJECT prop that the router never passed (it passes `id`), so
  // every collection — seed or freshly created — rendered "Collection not
  // found". The `collection` prop is still honored for any direct callers.
  const fromStore = useStore(s => (s.collections || []).find(x => x.id === id));
  const c = collection || fromStore;
  const projectsById = useStore(s => s.projects || {});
  const programs = useStore(s => s.programs || []);
  if (!c) return <div className="page"><EmptyState icon="layers" title="Collection not found." /></div>;

  const editable = c.state === 'active' || c.state === 'draft';
  // The API serializes these as `project` / `program`; `program_id` was never a
  // field on the record, so the program lookup silently returned undefined.
  const programId = c.program || c.program_id || '';
  const proj = projectsById[c.project] || PROJECTS[c.project];
  const program = programs.find(p => p.id === programId);
  const scopeLabel = proj ? proj.name : (program ? program.name : '—');
  const stale = c.items.some(i => i.stale);

  return (
    <div className="page page-wide">
      <div className="page-head" style={{ marginBottom: 4 }}>
        <div className="ph-titles" style={{ minWidth: 0, flex: 1 }}>
          <button className="btn-link" style={{ marginBottom: 8, display: 'inline-flex', alignItems: 'center', gap: 5 }} onClick={() => go({ screen: 'd.collections' })}><Icon name="chevright" size={14} style={{ transform: 'rotate(180deg)' }} />Collections</button>
          <InlineTitle value={c.name} disabled={!editable} onChange={(v) => storeActions.renameCollection(c.id, v)} />
        </div>
        <div className="ph-actions">
          {c.items.length > 0 && <button className="btn" onClick={() => storeActions.refreshSourcing(c.id, null)} title="Re-check Mouser + DigiKey for every line"><Icon name="refresh" size={15} />Run Sourcing</button>}
          {editable && <button className="btn" onClick={() => setAddOpen(true)}><Icon name="plus" size={15} />Add parts</button>}
          {c.state === 'active' && <button className="btn primary" onClick={() => setPanel(true)} disabled={c.items.length === 0}><Icon name="cart" size={15} />Send to Purchasing</button>}
          {c.state === 'ordered' && c.poId && <button className="btn" onClick={() => go({ screen: 'purchasingEmbed', tab: c.reqId })}><Icon name="cart" size={15} />View in Purchasing <span className="mono" style={{ marginLeft: 4 }}>{c.poId}</span></button>}
        </div>
      </div>

      <TraceabilityStrip name={c.name} status={c.state} creator={c.creator} role={c.role}
        project={scopeLabel} updated={c.updated} updatedBy={c.updatedBy} recordId={c.reqId || c.id}
        onProject={() => go({ screen: proj ? 'projects' : 'programs' })} />

      {/* Inline description + project association */}
      <div style={{ margin: '10px 0 6px', maxWidth: 820 }}>
        <InlineDescription value={c.desc} disabled={!editable} onChange={(v) => storeActions.setCollectionDescription(c.id, v)} placeholder="Add a description for this collection…" />
      </div>
      {editable && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginTop: 4, marginBottom: 8 }}>
          <span className="caption">Program:</span>
          <select className="select" style={{ width: 'auto', padding: '4px 8px', fontSize: 12.5 }} value={programId}
            onChange={(e) => storeActions.setCollectionProgram(c.id, e.target.value)}>
            {!programId && <option value="">Select a program…</option>}
            {programs.map(p => <option key={p.id} value={p.id}>{(p.identifier || p.code)} · {p.name}</option>)}
          </select>
          <span className="caption">· Changes save automatically</span>
        </div>
      )}

      {/* State banners */}
      {c.state === 'order-requested' && (
        <Banner kind="lock" title="This collection is in the shared purchasing bucket"
          actions={<button className="btn sm" onClick={() => go({ screen: 'purchasingEmbed', tab: c.reqId })}>View in bucket</button>}>
          Its lines are pooling toward the next batch on the Daily Purchasing List. Parts are locked while it's in the bucket — you can still view and comment. Request <span className="mono">{c.reqId}</span>.
        </Banner>
      )}
      {c.state === 'ordered' && (
        <Banner kind="info" icon="check" title="This collection has been ordered"
          actions={<button className="btn sm" onClick={() => go({ screen: 'purchasingEmbed', tab: c.reqId })}>View in Purchasing</button>}>
          All content is read-only. Order <span className="mono">{c.poId}</span> · request <span className="mono">{c.reqId}</span>.
        </Banner>
      )}
      {stale && editable && (
        <Banner kind="warn" title="Some supplier data is stale" actions={<button className="btn sm" onClick={() => storeActions.refreshSourcing(c.id, null)}><Icon name="refresh" size={13} />Refresh now</button>}>
          One or more parts have sourcing data older than 24h. Refresh before requesting an order so Purchasing sees current stock and pricing.
        </Banner>
      )}

      <div style={{ marginTop: 16 }}>
        {c.items.length === 0 ? (
          <div className="card"><EmptyState icon="search" title="This collection is empty."
            sub="Search for a part and add it to your collection. You can keep adding without leaving this page."
            actions={<button className="btn primary" onClick={() => setAddOpen(true)}><Icon name="plus" size={14} />Add a part</button>} /></div>
        ) : (
          <>
            <BomTable
              items={c.items}
              editable={editable}
              onQty={(no, qty) => storeActions.updateQty(c.id, no, qty)}
              onRemove={editable ? (no) => storeActions.removeFromCollection(c.id, no) : null}
              onNote={editable ? (no, note) => storeActions.setItemNote(c.id, no, note) : null}
              onRefresh={editable ? (no) => storeActions.refreshSourcing(c.id, no) : null}
            />
            <div className="tbl-wrap" style={{ borderTop: 0, borderRadius: 0, marginTop: -1 }}><Totals items={c.items} /></div>
          </>
        )}
      </div>

      {/* Comments — permanent record, shown on every collection */}
      <div style={{ marginTop: 26 }}>
        <CommentThread entityId={c.id} />
      </div>

      {panel && <RequestToOrder collection={c} onClose={() => setPanel(false)} onConfirm={(note, critical) => { setPanel(false); onSubmitOrder(c.id, note, critical); }} />}
      <AddPartDrawer open={addOpen} onClose={() => setAddOpen(false)} collectionId={c.id} kind={c.kind || c.role} />
    </div>
  );
}

Object.assign(window, { CollectionDetailScreen, BomTable, Totals, SendToBucketPanel });
