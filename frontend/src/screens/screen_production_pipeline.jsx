/* global React, Icon, StatusBadge, RoleTag, SupplierTag, Banner, EmptyState, TraceabilityStrip,
   BomTable, Totals, useStore, storeActions, getState, PROJECTS, CATALOG, BOM_BADGE, fmtUSD, fmtInt, bomMeta */
const { useState: useStatePB, useRef: useRefPB, useEffect: useEffPB } = React;

function bomById(id) { return useStore(s => s.boms.find(b => b.id === id)); }

function PipelineHeader({ b, go, stage }) {
  const stages = ['Upload', 'Validate', 'Source', 'Resolve', 'Package', 'Submit'];
  const idx = { upload: 0, validate: 1, sourcing: 2, results: 3, procurement: 4, submit: 5 }[stage] ?? 1;
  return (
    <>
      <div className="page-head" style={{ marginBottom: 4 }}>
        <div className="ph-titles">
          <button className="btn-link" style={{ marginBottom: 8 }} onClick={() => go({ screen: 'p.bomOverview', id: b.id })}>← {b.name}</button>
          <div className="h1">{b.name}</div>
        </div>
      </div>
      <TraceabilityStrip name={b.name} status={BOM_BADGE[b.state]} creator={b.creator} role="production"
        project={PROJECTS[b.project].name} updated={b.updated} updatedBy={b.updatedBy} recordId={b.id}
        onProject={() => go({ screen: 'projects' })} />
      <div className="pipeline-rail">
        {stages.map((s, i) => (
          <div key={s} className={`pl-node${i < idx ? ' done' : i === idx ? ' active' : ''}`}>
            <span className="pl-dot">{i < idx ? <Icon name="check" size={12} /> : i + 1}</span>
            <span className="pl-label">{s}</span>
          </div>
        ))}
      </div>
    </>
  );
}

/* ---- Validation Review ---- */
function BomValidationScreen({ id, go }) {
  const b = bomById(id);
  if (!b) return <div className="page"><EmptyState icon="boms" title="BOM not found." /></div>;
  const v = b.validation || { errors: 0, warnings: 0, notes: [] };
  const blocked = v.errors > 0;
  return (
    <div className="page page-wide">
      <PipelineHeader b={b} go={go} stage="validate" />
      <div style={{ marginTop: 16 }}>
        {blocked ? (
          <Banner kind="danger" icon="x" title={`${v.errors} validation error${v.errors > 1 ? 's' : ''} — sourcing blocked`}>
            Fix the highlighted lines (missing MPN or manufacturer) before this BOM can be sourced. You can edit inline or push the BOM back to the designer.
          </Banner>
        ) : v.warnings > 0 ? (
          <Banner kind="warn" title={`Validation passed with ${v.warnings} warning${v.warnings > 1 ? 's' : ''}`}>
            <ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>{v.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
          </Banner>
        ) : (
          <Banner kind="info" icon="check" title="Validation passed — no errors or warnings">This BOM is clean and ready to source.</Banner>
        )}
      </div>
      <div style={{ marginTop: 14 }}>
        <BomTable items={b.items} editable={true} showSource onQty={(no, qty) => storeActions.updateQty(b.id, no, qty)} />
      </div>
      <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 18 }}>
        <button className="btn"><Icon name="arrow" size={15} style={{ transform: 'rotate(180deg)' }} />Push back to designer</button>
        <button className="btn primary" disabled={blocked} onClick={() => go({ screen: 'p.sourcing', id: b.id })}><Icon name="refresh" size={15} />Run Sourcing</button>
      </div>
    </div>
  );
}

/* ---- Sourcing Progress (live) ---- */
const LOG_LINES = [
  { t: '00:00', m: 'Sourcing run started — 25 lines queued', c: '' },
  { t: '00:01', m: 'STM32G431CBT6 → Mouser 980 @ $4.12 ✓', c: 'ok' },
  { t: '00:03', m: 'GRM188R71H104KA93D → DigiKey 720k @ $0.011 ✓', c: 'ok' },
  { t: '00:05', m: 'ERJ-3EKF1002V → Mouser 940k @ $0.004 ✓', c: 'ok' },
  { t: '00:07', m: 'Rate limit on DigiKey — waiting 4s', c: 'warn' },
  { t: '00:12', m: 'BAT54S-7-F → DigiKey 120k @ $0.05 ✓', c: 'ok' },
  { t: '00:14', m: 'TPS54560DDAR → Mouser 1,890 @ $2.41 ✓', c: 'ok' },
];
function SourcingProgressScreen({ id, go }) {
  const b = bomById(id);
  const [pct, setPct] = useStatePB(b && b.state === 'normalised' ? 40 : 12);
  const [running, setRunning] = useStatePB(true);
  const [phase, setPhase] = useStatePB('run'); // run | ratelimit | done | cancelled
  const timer = useRefPB(null);
  useEffPB(() => {
    if (!running) return;
    timer.current = setInterval(() => setPct(p => {
      const np = Math.min(100, p + 6);
      if (np >= 100) { clearInterval(timer.current); setRunning(false); setPhase('done'); }
      else if (np >= 52 && np < 64) setPhase('ratelimit'); else setPhase('run');
      return np;
    }), 420);
    return () => clearInterval(timer.current);
  }, [running]);
  if (!b) return <div className="page"><EmptyState icon="boms" title="BOM not found." /></div>;
  const total = b.items.length, done = Math.round(total * pct / 100);
  const counts = { mouser: Math.round(done * 0.5), digikey: Math.round(done * 0.35), wall: Math.max(0, Math.round(done * 0.08)), review: phase === 'done' ? b.items.filter(i => i.exReason).length : 0, pending: total - done };

  return (
    <div className="page page-wide">
      <PipelineHeader b={b} go={go} stage="sourcing" />
      <div className="panel" style={{ marginTop: 16 }}>
        <div className="panel-head" style={{ background: phase === 'done' ? 'var(--success-soft)' : 'var(--info-soft)' }}>
          {phase === 'done' ? <Icon name="check" size={17} style={{ color: 'var(--success)' }} /> : <span className="spinner" style={{ borderTopColor: 'var(--info)' }} />}
          <span className="ph-title" style={{ color: phase === 'done' ? 'var(--success)' : 'var(--info)' }}>
            {phase === 'done' ? 'Sourcing complete' : phase === 'ratelimit' ? 'Rate-limit wait — DigiKey' : phase === 'cancelled' ? 'Sourcing cancelled' : 'Sourcing in progress'}</span>
          <span className="ph-meta">{done} of {total} lines · {pct}%{phase !== 'done' ? ` · ~${Math.max(1, Math.round((100 - pct) / 6 * 0.42))}s remaining` : ''}</span>
        </div>
        <div className="panel-body">
          <div className="progress" style={{ height: 10 }}><i style={{ width: pct + '%', background: phase === 'done' ? 'var(--success)' : phase === 'ratelimit' ? 'var(--warning)' : 'var(--action)' }} /></div>
          <div className="sourcing-grid" style={{ marginTop: 16 }}>
            <div className="scount"><div className="sc-n" style={{ color: 'var(--supplier-mouser)' }}>{counts.mouser}</div><div className="sc-l"><span className="dot" style={{ background: 'var(--supplier-mouser)' }} />Mouser</div></div>
            <div className="scount"><div className="sc-n" style={{ color: 'var(--supplier-digikey)' }}>{counts.digikey}</div><div className="sc-l"><span className="dot" style={{ background: 'var(--supplier-digikey)' }} />DigiKey</div></div>
            <div className="scount"><div className="sc-n" style={{ color: 'var(--warning)' }}>{counts.wall}</div><div className="sc-l"><Icon name="alert" size={12} style={{ color: 'var(--warning)' }} />Check wall</div></div>
            <div className="scount"><div className="sc-n" style={{ color: 'var(--danger)' }}>{counts.review}</div><div className="sc-l"><Icon name="alert" size={12} style={{ color: 'var(--danger)' }} />Needs review</div></div>
            <div className="scount"><div className="sc-n">{counts.pending}</div><div className="sc-l"><Icon name="clock" size={12} />Pending</div></div>
          </div>
          <div className="logbox" style={{ marginTop: 16 }}>
            {LOG_LINES.slice(0, Math.max(2, Math.round(done))).map((l, i) => (
              <div key={i} className={`lg ${l.c}`}><span className="lt">{l.t}</span><span>{l.m}</span></div>
            ))}
            {phase === 'ratelimit' && <div className="lg warn"><span className="lt">····</span><span>Backing off — DigiKey rate limit, retrying…</span></div>}
            {phase === 'done' && <div className="lg ok"><span className="lt">done</span><span>Run finished — {counts.review} line(s) need engineering review</span></div>}
          </div>
          <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 16 }}>
            {phase !== 'done' ? (
              <button className="btn danger" onClick={() => { clearInterval(timer.current); setRunning(false); setPhase('cancelled'); }}><Icon name="x" size={15} />Cancel run</button>
            ) : (
              <button className="btn primary" onClick={() => { storeActions.completeSourcing(b.id); go({ screen: 'p.results', id: b.id }); }}>View results<Icon name="arrow" size={15} /></button>
            )}
            {phase === 'cancelled' && <button className="btn" onClick={() => { setPhase('run'); setRunning(true); }}><Icon name="refresh" size={15} />Re-run on unsourced lines</button>}
            {phase === 'cancelled' && <button className="btn primary" onClick={() => { storeActions.completeSourcing(b.id); go({ screen: 'p.results', id: b.id }); }}>View partial results<Icon name="arrow" size={15} /></button>}
          </div>
          {phase === 'cancelled' && (
            /* FR-P05 — Cancel sourcing preserves completed lines. BOM returns to NORMALISED.
               User can re-run sourcing on the remaining unsourced lines only, or proceed
               with what we have. We never lose work already done. */
            <Banner kind="info" icon="check" title="Partial results preserved"
              actions={<button className="btn sm" onClick={() => { setPhase('run'); setRunning(true); }}><Icon name="refresh" size={13} />Re-run unsourced lines</button>}>
              {Math.max(0, Math.round(done))} of {LOG_LINES.length} lines sourced. The remaining lines are unsourced — re-run sourcing on just those, or proceed to results with partial data.
            </Banner>
          )}
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { BomValidationScreen, SourcingProgressScreen, PipelineHeader, bomById });
