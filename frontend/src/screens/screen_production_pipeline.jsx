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
        project={projectName(b.project)} updated={b.updated} updatedBy={b.updatedBy} recordId={b.id}
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
/* Live sourcing — consumes the SSE stream from GET /api/sourcing/boms/:id/run,
   surfacing each line's real outcome (sourced / needs-review / check-wall) as a
   calm status. Rate-limit backoff happens server-side (honoring X-RateLimit-
   Reset), so a slow line just resolves later — never an error toast. */
const SOURCE_LABEL = {
  'sourced-mouser': { t: 'sourced · Mouser', c: 'ok' },
  'sourced-digikey': { t: 'sourced · DigiKey', c: 'ok' },
  'check-wall': { t: 'check wall inventory', c: 'warn' },
  'needs-review': { t: 'needs manual review', c: 'err' },
};
function SourcingProgressScreen({ id, go }) {
  const b = bomById(id);
  const [lines, setLines] = useStatePB([]);      // per-line events, in arrival order
  const [total, setTotal] = useStatePB((b && b.items.length) || 0);
  const [phase, setPhase] = useStatePB('run');    // run | done | interrupted | cancelled
  const esRef = useRefPB(null);

  const start = React.useCallback(() => {
    setLines([]); setPhase('run');
    const es = new EventSource('/api/sourcing/boms/' + id + '/run');
    esRef.current = es;
    es.onmessage = (e) => {
      let ev; try { ev = JSON.parse(e.data); } catch (_) { return; }
      if (ev.type === 'start') setTotal(ev.total);
      else if (ev.type === 'line') setLines(prev => [...prev, ev]);
      else if (ev.type === 'done') { es.close(); if (ev.bom) storeActions.applySourcingResult(ev.bom); setPhase('done'); }
      else if (ev.type === 'error') { es.close(); setPhase('interrupted'); }
    };
    es.onerror = () => { es.close(); setPhase(p => (p === 'done' ? p : 'interrupted')); };
  }, [id]);

  useEffPB(() => { start(); return () => { if (esRef.current) esRef.current.close(); }; }, [id]);

  if (!b) return <div className="page"><EmptyState icon="boms" title="BOM not found." /></div>;

  const done = lines.length;
  const pct = total ? Math.round(done / total * 100) : 0;
  const counts = {
    mouser: lines.filter(l => l.status === 'sourced-mouser').length,
    digikey: lines.filter(l => l.status === 'sourced-digikey').length,
    wall: lines.filter(l => l.status === 'check-wall').length,
    review: lines.filter(l => l.status === 'needs-review').length,
    pending: Math.max(0, total - done),
  };
  const head = phase === 'done' ? { bg: 'var(--success-soft)', fg: 'var(--success)', title: 'Sourcing complete' }
    : phase === 'interrupted' ? { bg: 'var(--warning-soft)', fg: 'var(--warning)', title: 'Sourcing interrupted' }
    : phase === 'cancelled' ? { bg: 'var(--warning-soft)', fg: 'var(--warning)', title: 'Sourcing cancelled' }
    : { bg: 'var(--info-soft)', fg: 'var(--info)', title: 'Sourcing in progress' };
  const cancel = () => { if (esRef.current) esRef.current.close(); setPhase('cancelled'); };

  return (
    <div className="page page-wide">
      <PipelineHeader b={b} go={go} stage="sourcing" />
      <div className="panel" style={{ marginTop: 16 }}>
        <div className="panel-head" style={{ background: head.bg }}>
          {phase === 'done' ? <Icon name="check" size={17} style={{ color: head.fg }} />
            : phase === 'interrupted' || phase === 'cancelled' ? <Icon name="alert" size={17} style={{ color: head.fg }} />
            : <span className="spinner" style={{ borderTopColor: head.fg }} />}
          <span className="ph-title" style={{ color: head.fg }}>{head.title}</span>
          <span className="ph-meta">{done} of {total} lines · {pct}%</span>
        </div>
        <div className="panel-body">
          <div className="progress" style={{ height: 10 }}><i style={{ width: pct + '%', background: head.fg }} /></div>
          <div className="sourcing-grid" style={{ marginTop: 16 }}>
            <div className="scount"><div className="sc-n" style={{ color: 'var(--supplier-mouser)' }}>{counts.mouser}</div><div className="sc-l"><span className="dot" style={{ background: 'var(--supplier-mouser)' }} />Mouser</div></div>
            <div className="scount"><div className="sc-n" style={{ color: 'var(--supplier-digikey)' }}>{counts.digikey}</div><div className="sc-l"><span className="dot" style={{ background: 'var(--supplier-digikey)' }} />DigiKey</div></div>
            <div className="scount"><div className="sc-n" style={{ color: 'var(--warning)' }}>{counts.wall}</div><div className="sc-l"><Icon name="alert" size={12} style={{ color: 'var(--warning)' }} />Check wall</div></div>
            <div className="scount"><div className="sc-n" style={{ color: 'var(--danger)' }}>{counts.review}</div><div className="sc-l"><Icon name="alert" size={12} style={{ color: 'var(--danger)' }} />Needs review</div></div>
            <div className="scount"><div className="sc-n">{counts.pending}</div><div className="sc-l"><Icon name="clock" size={12} />Pending</div></div>
          </div>
          <div className="logbox" style={{ marginTop: 16 }}>
            {lines.slice(-14).map((l, i) => {
              const meta = SOURCE_LABEL[l.status] || { t: l.status, c: '' };
              return <div key={i} className={`lg ${meta.c}`}><span className="lt">L{l.line_no}</span><span>{l.mpn || '—'} → {meta.t}{l.note && meta.c !== 'ok' ? ` (${l.note})` : ''}</span></div>;
            })}
            {phase === 'run' && <div className="lg"><span className="lt">····</span><span>Querying Mouser + DigiKey (live)…</span></div>}
            {phase === 'done' && <div className="lg ok"><span className="lt">done</span><span>Run finished — {counts.review} line(s) need engineering review, {counts.wall} on wall</span></div>}
          </div>
          {phase === 'interrupted' && (
            <Banner kind="warning" icon="alert" title="Sourcing interrupted"
              actions={<button className="btn sm" onClick={start}><Icon name="refresh" size={13} />Retry</button>}>
              The connection dropped mid-run. Completed lines are saved — retry to source the rest.
            </Banner>
          )}
          <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 16 }}>
            {phase === 'run' ? (
              <button className="btn danger" onClick={cancel}><Icon name="x" size={15} />Cancel run</button>
            ) : (
              <button className="btn primary" onClick={() => go({ screen: 'p.results', id: b.id })}>View results<Icon name="arrow" size={15} /></button>
            )}
            {(phase === 'cancelled' || phase === 'interrupted') && <button className="btn" onClick={start}><Icon name="refresh" size={15} />Re-run</button>}
          </div>
          {phase === 'cancelled' && (
            <Banner kind="info" icon="check" title="Partial results preserved">
              {done} of {total} lines sourced. Completed lines are saved — re-run for the rest, or proceed to results with partial data.
            </Banner>
          )}
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { BomValidationScreen, SourcingProgressScreen, PipelineHeader, bomById });
