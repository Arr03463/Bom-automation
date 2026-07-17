/* global React, Icon, SupplierTag, StatusBadge, Banner, EmptyState, useStore, storeActions, getState, CATALOG, PROJECTS, fmtUSD, fmtInt */
/* AutoBOM — Push-Back resolution (v4).
   Replaces the old manual InlinePartVerify flow. Designer resolves each flagged line
   (or a missing-component request) through a UNIFIED characteristic search running in
   `search_suppliers` mode (Mouser/DigiKey primary, PartsBox wall overlay behind a toggle).
   Designer's picks are RECOMMENDATIONS — Production applies them from their own Dashboard.

   Exports:
     PushbackReplaceLine   — one flagged line / added-component search widget
     PushbackResolvePanel  — the whole per-Push-Back resolution surface (dashboard-inline)
     REASON_META / URGENCY_META / PushbackBadges
*/
const { useState: usePR, useMemo: useMemoPR, useRef: useRefPR } = React;

/* ---- enums ---- */
const REASON_META = {
  obsolete:            { label: 'Obsolete', color: 'var(--danger)' },
  eol:                 { label: 'EOL', color: 'var(--danger)' },
  unsourceable:        { label: 'Unsourceable', color: 'var(--warning)' },
  'zero-stock':        { label: 'Zero stock', color: 'var(--warning)' },
  'missing-component': { label: 'Missing component', color: 'var(--action)' },
  other:               { label: 'Other', color: 'var(--text-muted)' },
};
const URGENCY_META = {
  blocking: { label: 'Blocking', color: 'var(--danger)' },
  standard: { label: 'Standard', color: 'var(--text-muted)' },
};
function PushbackBadges({ reason, urgency }) {
  const r = REASON_META[reason] || REASON_META.other;
  const u = URGENCY_META[urgency] || URGENCY_META.standard;
  return (
    <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
      <span className="badge outlined" style={{ color: r.color, borderColor: r.color }}>{r.label}</span>
      <span className="badge outlined" style={{ color: u.color, borderColor: u.color }}>{u.label === 'Blocking' ? '⏻ Blocking' : u.label}</span>
    </span>
  );
}

/* ---- characteristic model (mock of the sourcing engine's parametric extraction) ---- */
function parseChars(descOrObj) {
  if (descOrObj && typeof descOrObj === 'object') return descOrObj;
  const d = String(descOrObj || '');
  const pkg = (d.match(/\b(0201|0402|0603|0805|1206|1210|2010|2512|SOT-?\d+\w*|SOIC-?\d+|SO-?8|TO-?\d+\w*|QFN-?\d+|LQFP-?\d+|DFN-?\d+|TSSOP-?\d+|PowerPAD)\b/i) || [])[1] || null;
  const value = (d.match(/(\d+(?:\.\d+)?\s?(?:pF|nF|µF|uF|F|mΩ|kΩ|MΩ|Ω|Ohm|µH|uH|mH|A|MHz))/i) || [])[1] || null;
  const voltage = (d.match(/(\d+(?:\.\d+)?)\s?V\b/i) || [])[1] || null;
  const tolerance = (d.match(/±?\s?(\d+(?:\.\d+)?)\s?%/) || [])[1] || null;
  return { package: pkg, value, voltage: voltage ? voltage + 'V' : null, tolerance: tolerance ? tolerance + '%' : null };
}
const CHAR_LABEL = { package: 'Package', value: 'Value', voltage: 'Voltage', tolerance: 'Tolerance' };
/* Verdict per characteristic: match | improves | differs | unknown */
function compareChar(key, src, cand) {
  if (!src || !cand) return 'unknown';
  const n = (x) => parseFloat(String(x).replace(/[^0-9.]/g, ''));
  if (String(src).toLowerCase() === String(cand).toLowerCase()) return 'match';
  if (key === 'voltage') return n(cand) > n(src) ? 'improves' : 'differs';
  if (key === 'tolerance') return n(cand) < n(src) ? 'improves' : 'differs';
  return 'differs';
}
const VERDICT_META = {
  match:    { label: 'matches', color: 'var(--success)', icon: 'check' },
  improves: { label: 'improves', color: 'var(--success)', icon: 'arrow' },
  differs:  { label: 'differs', color: 'var(--danger)', icon: 'alert' },
  unknown:  { label: '—', color: 'var(--text-muted)', icon: 'circle' },
};

/* Mock datasheet URL — the sourcing engine returns one for most catalog parts. */
function datasheetUrl(mpn) { return mpn ? `https://www.mouser.com/datasheet/${encodeURIComponent(mpn)}.pdf` : null; }

/* ---- search_suppliers mode: supplier-primary, PartsBox wall as overlay ---- */
function searchSuppliers(query, chars, includeWall) {
  const q = (query || '').trim().toLowerCase();
  const supplier = [];
  for (const c of Object.values(CATALOG)) {
    const hay = `${c.mpn} ${c.mfr} ${c.desc}`.toLowerCase();
    const match = q ? hay.includes(q) : true; // no query → characteristic-only browse
    if (!match) continue;
    supplier.push({
      section: 'supplier', mpn: c.mpn, mfr: c.mfr, desc: c.desc, lifecycle: c.lifecycle, recommend: c.recommend,
      mouser: c.mouser, digikey: c.digikey, chars: parseChars(c.desc), datasheet: datasheetUrl(c.mpn),
    });
  }
  let wall = [];
  if (includeWall) {
    const inv = getState().inventory || [];
    for (const p of inv) {
      const hay = `${p.mpn} ${p.desc || ''}`.toLowerCase();
      if (q && !hay.includes(q)) continue;
      const loc = (p.locations || []).find(l => l.kind === 'wall') || (p.locations || [])[0];
      if (!loc) continue;
      wall.push({ section: 'wall', mpn: p.mpn, mfr: p.mfr || '', desc: p.desc, onHand: p.onHand, location: loc.name, chars: parseChars(p.desc), datasheet: null });
    }
    wall = wall.slice(0, 20);
  }
  return { supplier: supplier.slice(0, 30), wall };
}

/* Distinct manufacturers (for the bidirectional typeahead) */
function allManufacturers() { return [...new Set(Object.values(CATALOG).map(c => c.mfr))].sort(); }

/* ============================================================
   PushbackReplaceLine — one flagged line, or a missing-component request.
   Unified surface: MPN input + bidirectional Manufacturer typeahead + characteristic
   filters (AND-combined), Include-wall toggle, comparison-annotated result cards.
   ============================================================ */
function PushbackReplaceLine({ flaggedPart, addedComponentRequest, picked, onSelectCandidate, onClear }) {
  const isMissing = !!addedComponentRequest;
  const sourceChars = useMemoPR(() => isMissing
    ? parseChars(addedComponentRequest.characteristics || addedComponentRequest.description || '')
    : parseChars((CATALOG[flaggedPart?.mpn]?.desc) || flaggedPart?.desc || ''), [flaggedPart, addedComponentRequest]);

  const [mpn, setMpn] = usePR(isMissing ? (addedComponentRequest.mpn || '') : '');
  const [mfr, setMfr] = usePR('');
  const [chars, setChars] = usePR(sourceChars);           // refinable characteristic filters
  const [includeWall, setIncludeWall] = usePR(false);
  const [mfrOpen, setMfrOpen] = usePR(false);

  // Bidirectional constraint: manufacturers filtered by the current MPN text.
  const mfrOptions = useMemoPR(() => {
    const base = allManufacturers();
    if (!mpn.trim()) return base;
    const ql = mpn.trim().toLowerCase();
    const constrained = [...new Set(Object.values(CATALOG).filter(c => `${c.mpn} ${c.desc}`.toLowerCase().includes(ql)).map(c => c.mfr))];
    return constrained.length ? constrained.sort() : base;
  }, [mpn]);

  // Results: MPN text AND characteristic filters, constrained by selected manufacturer.
  const results = useMemoPR(() => {
    const { supplier, wall } = searchSuppliers(mpn, chars, includeWall);
    const byMfr = (arr) => mfr ? arr.filter(r => (r.mfr || '').toLowerCase() === mfr.toLowerCase()) : arr;
    return { supplier: byMfr(supplier), wall };
  }, [mpn, mfr, chars, includeWall]);

  if (picked) {
    return (
      <div className="pbrl picked">
        <div className="pbrl-picked-row">
          <Icon name="check" size={16} style={{ color: 'var(--success)' }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <span className="mono" style={{ fontWeight: 700 }}>{picked.mpn}</span> <span className="secondary">— {picked.mfr || '—'}</span>
            <div className="caption">{picked.section === 'wall' ? `Recommend from wall · ${picked.location}` : 'Supplier recommendation'}{picked.datasheet ? ' · datasheet queued for PartsBox' : ''}</div>
          </div>
          <button className="btn sm" onClick={onClear}><Icon name="refresh" size={13} />Change</button>
        </div>
      </div>
    );
  }

  const charChips = ['package', 'value', 'voltage', 'tolerance'].filter(k => chars[k]);

  return (
    <div className="pbrl">
      <div className="pbrl-fields">
        <label className="ipv-field">
          <span className="ipv-label">MPN {isMissing ? '(if known)' : ''}</span>
          <input className="input mono" placeholder="smart-match MPN…" value={mpn} onChange={e => setMpn(e.target.value)} />
        </label>
        <label className="ipv-field" style={{ position: 'relative' }}>
          <span className="ipv-label">Manufacturer</span>
          <input className="input" placeholder="constrained typeahead…" value={mfr}
            onChange={e => { setMfr(e.target.value); setMfrOpen(true); }} onFocus={() => setMfrOpen(true)}
            onBlur={() => setTimeout(() => setMfrOpen(false), 150)} />
          {mfrOpen && (
            <div className="pbrl-typeahead">
              {mfr && <div className="mi" onMouseDown={() => { setMfr(''); }}><Icon name="x" size={12} />Any manufacturer</div>}
              {mfrOptions.filter(m => !mfr || m.toLowerCase().includes(mfr.toLowerCase())).slice(0, 8).map(m => (
                <div key={m} className="mi" onMouseDown={() => { setMfr(m); setMfrOpen(false); }}>{m}</div>
              ))}
            </div>
          )}
        </label>
      </div>

      <div className="pbrl-charbar">
        <span className="caption" style={{ fontWeight: 600 }}>Characteristics</span>
        {charChips.length === 0 && <span className="caption">none extracted — search by MPN</span>}
        {charChips.map(k => (
          <span key={k} className="char-chip">{CHAR_LABEL[k]}: <strong>{chars[k]}</strong>
            <button className="char-x" onClick={() => setChars(c => ({ ...c, [k]: null }))} title="Remove filter">×</button>
          </span>
        ))}
        <label className="pbrl-wall">
          <input type="checkbox" checked={includeWall} onChange={e => setIncludeWall(e.target.checked)} /> Include wall
        </label>
      </div>

      <div className="pbrl-results">
        <div className="pbrl-sec-head"><SupplierTag supplier="mouser" /><SupplierTag supplier="digikey" /><span className="caption">Available from suppliers · {results.supplier.length}</span></div>
        {results.supplier.length === 0 ? <div className="caption" style={{ padding: '6px 0' }}>No supplier matches — refine the MPN or characteristics.</div>
          : results.supplier.slice(0, 6).map(r => <CandidateCard key={'s' + r.mpn} cand={r} sourceChars={isMissing ? sourceChars : parseChars((CATALOG[flaggedPart?.mpn]?.desc) || flaggedPart?.desc)} onRecommend={() => onSelectCandidate(r)} />)}
        {includeWall && (
          <>
            <div className="pbrl-sec-head" style={{ marginTop: 10 }}><span className={'loc-chip development'}>wall</span><span className="caption">On the development wall · {results.wall.length} — both sections shown, never deduped</span></div>
            {results.wall.length === 0 ? <div className="caption" style={{ padding: '6px 0' }}>No wall matches.</div>
              : results.wall.slice(0, 5).map(r => <CandidateCard key={'w' + r.mpn} cand={r} sourceChars={sourceChars} onRecommend={() => onSelectCandidate(r)} />)}
          </>
        )}
      </div>
    </div>
  );
}

function CandidateCard({ cand, sourceChars, onRecommend }) {
  const eol = cand.lifecycle === 'obsolete';
  const off = cand.recommend ? cand[cand.recommend] : (cand.mouser || cand.digikey);
  const keys = ['package', 'value', 'voltage', 'tolerance'].filter(k => sourceChars && sourceChars[k]);
  return (
    <div className={`cand-card${eol ? ' eol' : ''}`}>
      <div className="cand-head">
        <div style={{ minWidth: 0, flex: 1 }}>
          <span className="mono" style={{ fontWeight: 700 }}>{cand.mpn}</span> <span className="secondary">{cand.mfr}</span>
          {eol && <span className="badge filled" style={{ background: 'var(--darkred)', marginLeft: 8 }}><Icon name="ban" size={11} />EOL</span>}
          <div className="caption" style={{ marginTop: 1 }}>{cand.desc}</div>
        </div>
        <button className="btn sm primary" disabled={eol} onClick={onRecommend}>
          <Icon name="check" size={13} />{cand.section === 'wall' ? `Recommend from wall · ${cand.location}` : 'Recommend this replacement'}
        </button>
      </div>
      {keys.length > 0 && (
        <div className="cand-chars">
          {keys.map(k => {
            const v = compareChar(k, sourceChars[k], cand.chars[k]);
            const m = VERDICT_META[v];
            return <span key={k} className="cand-char" style={{ color: m.color }}><Icon name={m.icon} size={11} />{CHAR_LABEL[k]} {cand.chars[k] || '?'} · {m.label}</span>;
          })}
        </div>
      )}
      <div className="cand-foot">
        {cand.section === 'wall'
          ? <span className="caption">{cand.onHand} on hand · {cand.location}</span>
          : <span className="caption">{off ? `${fmtInt(off.stock)} in stock · ${fmtUSD(off.price)}` : 'stock —'}</span>}
        {cand.datasheet
          ? <a className="caption" href={cand.datasheet} target="_blank" rel="noopener noreferrer" style={{ marginLeft: 'auto', color: 'var(--action)' }}><Icon name="external" size={12} /> Datasheet</a>
          : <span className="caption" style={{ marginLeft: 'auto' }}>No datasheet</span>}
      </div>
    </div>
  );
}

/* ============================================================
   PushbackResolvePanel — Designer's inline resolution surface.
   Iterates flagged lines (+ a missing-component request), collects RECOMMENDATIONS,
   and submits them for Production to apply. Never mutates the master BOM.
   Secondary paths: comment (per Push-Back thread), defer, reassign.
   ============================================================ */
function PushbackResolvePanel({ bom, go, close }) {
  const pb = bom.pushback || {};
  const flagged = (pb.flaggedLines && pb.flaggedLines.length)
    ? pb.flaggedLines.map(fl => ({ ...fl, part: bom.items.find(i => i.no === fl.lineNo) || { no: fl.lineNo, mpn: '(line ' + fl.lineNo + ')' } }))
    : bom.items.filter(i => i.status === 'needs-review' || i.status === 'exception').map(i => ({ lineNo: i.no, exReason: i.exReason, part: i }));
  const added = pb.addedComponentRequest || null;

  const [picks, setPicks] = usePR({});          // key -> candidate  (key = 'L<lineNo>' or 'ADD')
  const [note, setNote] = usePR('');
  const [secondary, setSecondary] = usePR(null); // 'comment' | 'defer' | 'reassign'
  const [sent, setSent] = usePR(false);

  const totalSlots = flagged.length + (added ? 1 : 0);
  const doneCount = Object.keys(picks).length;
  const allDone = doneCount >= totalSlots && totalSlots > 0;

  const setPick = (key, cand) => setPicks(p => ({ ...p, [key]: cand }));
  const clearPick = (key) => setPicks(p => { const n = { ...p }; delete n[key]; return n; });

  const submit = () => {
    const recommendations = [];
    flagged.forEach(fl => { const c = picks['L' + fl.lineNo]; if (c) recommendations.push({ lineNo: fl.lineNo, candidate: c }); });
    if (added && picks['ADD']) recommendations.push({ added: true, candidate: picks['ADD'], request: added });
    storeActions.resolvePushback(bom.id, { recommendations, note });
    setSent(true);
  };

  if (sent) return (
    <div className="na-phase" style={{ color: 'var(--success)' }}>
      <Icon name="check" size={15} />Recommendations sent to Production. They'll review and Apply them to the master BOM — the BOM isn't changed until they do.
    </div>
  );

  return (
    <div className="na-exp-body pb-resolve">
      <div className="caption" style={{ marginBottom: 8, display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <PushbackBadges reason={pb.reason} urgency={pb.urgency} />
        <span>Pick a replacement per line via characteristic search. Your picks are <strong>recommendations</strong> — Production applies them.</span>
      </div>

      {flagged.map(fl => (
        <div key={fl.lineNo} className="pb-line">
          <div className="pb-line-head">
            <span className="mono" style={{ fontWeight: 600 }}>Line {fl.lineNo} · {fl.part.mpn}</span>
            <span className="caption">· {fl.exReason || 'Needs engineering review'}</span>
          </div>
          <PushbackReplaceLine flaggedPart={fl.part} picked={picks['L' + fl.lineNo]}
            onSelectCandidate={(c) => { storeActions.attachDatasheet(c.mpn, c.datasheet); setPick('L' + fl.lineNo, c); }}
            onClear={() => clearPick('L' + fl.lineNo)} />
        </div>
      ))}

      {added && (
        <div className="pb-line missing">
          <div className="pb-line-head">
            <span className="badge outlined" style={{ color: 'var(--action)', borderColor: 'var(--action)' }}>MISSING COMPONENT</span>
            <span className="caption">{added.description}{added.designator ? ` · ${added.designator}` : ''}{added.quantityPerBoard ? ` · qty/board ${added.quantityPerBoard}` : ''}</span>
          </div>
          <div className="caption" style={{ margin: '2px 0 6px' }}>No source line to compare — recommend a new component to add to the master BOM.</div>
          <PushbackReplaceLine addedComponentRequest={added} picked={picks['ADD']}
            onSelectCandidate={(c) => { storeActions.attachDatasheet(c.mpn, c.datasheet); setPick('ADD', c); }}
            onClear={() => clearPick('ADD')} />
        </div>
      )}

      {secondary === 'comment' && <SecondaryBox label="Comment to Production (adds to the Push-Back thread)" confirm="Post comment"
        onCancel={() => setSecondary(null)} onConfirm={(t) => { storeActions.commentPushback(bom.id, t); setSecondary(null); }} />}
      {secondary === 'defer' && <SecondaryBox label="Reason for deferring this Push-Back" confirm="Defer"
        onCancel={() => setSecondary(null)} onConfirm={(t) => { storeActions.deferPushback(bom.id, t); setSecondary(null); close && close(); }} />}
      {secondary === 'reassign' && <SecondaryBox label="Note for the Designer you're reassigning to" confirm="Reassign"
        onCancel={() => setSecondary(null)} onConfirm={(t) => { storeActions.reassignPushback(bom.id, t); setSecondary(null); close && close(); }} />}

      <textarea className="input" style={{ marginTop: 10, minHeight: 48 }} placeholder="Optional note to Production…" value={note} onChange={e => setNote(e.target.value)} />

      <div className="na-confirm" style={{ marginTop: 10, flexWrap: 'wrap', gap: 8 }}>
        <div style={{ display: 'flex', gap: 6 }}>
          <button className="btn sm ghost" onClick={() => setSecondary(s => s === 'comment' ? null : 'comment')}><Icon name="comment" size={13} />Comment</button>
          <button className="btn sm ghost" onClick={() => setSecondary(s => s === 'defer' ? null : 'defer')}><Icon name="clock" size={13} />Defer</button>
          <button className="btn sm ghost" onClick={() => setSecondary(s => s === 'reassign' ? null : 'reassign')}><Icon name="arrow" size={13} />Reassign</button>
        </div>
        <div style={{ display: 'flex', gap: 8, marginLeft: 'auto', alignItems: 'center' }}>
          <span className="caption">{doneCount}/{totalSlots} recommended</span>
          <button className="btn sm ghost" onClick={close}>Cancel</button>
          <button className="btn sm primary" disabled={!allDone} onClick={submit}><Icon name="send" size={13} />Send recommendations to Production</button>
        </div>
      </div>
    </div>
  );
}

function SecondaryBox({ label, confirm, onCancel, onConfirm }) {
  const [t, setT] = usePR('');
  return (
    <div className="card" style={{ padding: 10, marginTop: 8, background: 'var(--bg-raised)' }}>
      <div className="caption" style={{ marginBottom: 4 }}>{label}</div>
      <textarea className="input" style={{ minHeight: 44 }} value={t} onChange={e => setT(e.target.value)} autoFocus />
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 6 }}>
        <button className="btn sm ghost" onClick={onCancel}>Cancel</button>
        <button className="btn sm primary" disabled={!t.trim()} onClick={() => onConfirm(t.trim())}>{confirm}</button>
      </div>
    </div>
  );
}

/* Characteristic-match check (Production inline-edit). Returns { ok, unknown, diffs, candMfr, candChars }.
   Match rule: package + nominal value must match; voltage equal-or-higher; tolerance equal-or-tighter. */
function characteristicMatch(sourceDesc, candMpn) {
  const src = parseChars(sourceDesc);
  const cand = CATALOG[candMpn];
  if (!cand) return { ok: false, unknown: true, diffs: ['not found at suppliers — verify manually'], candMfr: null, candChars: null };
  const cch = parseChars(cand.desc);
  const diffs = [];
  ['package', 'value'].forEach(k => { if (src[k] && cch[k] && String(src[k]).toLowerCase() !== String(cch[k]).toLowerCase()) diffs.push(CHAR_LABEL[k]); });
  ['voltage', 'tolerance'].forEach(k => { if (src[k] && cch[k] && compareChar(k, src[k], cch[k]) === 'differs') diffs.push(CHAR_LABEL[k]); });
  return { ok: diffs.length === 0, unknown: false, diffs, candMfr: cand.mfr, candChars: cch, lifecycle: cand.lifecycle };
}

Object.assign(window, { PushbackReplaceLine, PushbackResolvePanel, PushbackBadges, REASON_META, URGENCY_META, parseChars, characteristicMatch });
