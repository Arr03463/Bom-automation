/* global React, Icon, StatusBadge, RoleTag, SupplierTag, Banner, EmptyState, InlinePartVerify,
   useStore, storeActions, getState, PROJECTS, fmtUSD, CATALOG */
/* AutoBOM — Needs Attention (v1.3-rev).
   The Task Center is removed. The Dashboard IS the operational inbox.
   This module derives every role's actionable items and renders interactive
   cards: the common action completes inline (expansion grows WITHIN page flow —
   never a modal/overlay), uncommon ones navigate. Clicking the title navigates
   to full detail. Notification clicks scroll the matching card into view + flash. */
const { useState: useStateNA, useRef: useRefNA, useEffect: useEffNA } = React;

/* ---- derive Needs Attention items for a role ---- */
function deriveAttention(state, role) {
  const items = [];
  const proj = (id) => state.projects[id]?.name || id;

  if (role === 'designer') {
    for (const b of state.boms) {
      if (b.state === 'exceptions' && b.pushback && !b.pushback.recommendation) {
        const pb = b.pushback;
        const count = (pb.flaggedLines ? pb.flaggedLines.length : 0) + (pb.addedComponentRequest ? 1 : 0);
        items.push({
          id: `att-ex-${b.id}`, kind: 'bom-exception', tone: 'danger',
          type: 'BOM EXCEPTION', icon: 'alert',
          title: b.name, badge: `${b.id}${b.version ? ' · v' + b.version : ''}`, project: proj(b.project),
          meta: `${count} item${count > 1 ? 's' : ''} need engineering review · from Production${pb.note ? ' · "' + pb.note + '"' : ''}`,
          reason: pb.reason, urgency: pb.urgency,
          verb: 'Resolve', tag: pb.reason === 'missing-component' ? 'Recommend component' : 'Recommend replacements',
          relatedId: b.id, bom: b,
          titleRoute: { screen: 'p.bomOverview', id: b.id },
        });
      }
    }
    // (No "collection rejected" card — Purchasing has no reject action, so this event
    //  cannot exist. Upstream checks block a bad request before it ever enters the bucket.)
    for (const c of state.collections) {
      if (c.role === 'designer' && c.state === 'active' && c.items.some(i => i.stale)) {
        const n = c.items.filter(i => i.stale).length;
        items.push({
          id: `att-stale-${c.id}`, kind: 'stale-sourcing', tone: 'warning',
          type: 'STALE SOURCING DATA', icon: 'clock',
          title: c.name, badge: c.id, project: proj(c.project),
          meta: `${n} item${n > 1 ? 's' : ''} with supplier data older than 24h`,
          verb: 'Resolve', tag: 'Re-check sourcing', relatedId: c.id, collection: c,
          titleRoute: { screen: 'd.collectionDetail', id: c.id },
        });
      }
    }
  }

  if (role === 'production') {
    for (const b of state.boms) {
      if (b.state === 'validated' || b.state === 'sourcing') {
        items.push({
          id: `att-src-${b.id}`, kind: 'awaiting-sourcing', tone: 'info',
          type: 'BOM AWAITING SOURCING', icon: 'search',
          title: b.name, badge: b.id, project: proj(b.project),
          meta: `${b.items.length} lines · in queue ${b.updated}`,
          verb: 'Resolve', tag: 'Run sourcing', relatedId: b.id, bom: b,
          titleRoute: { screen: 'p.bomOverview', id: b.id },
        });
      } else if (b.state === 'normalised') {
        const n = b.items.filter(i => i.status === 'needs-review' || i.status === 'exception').length;
        items.push({
          id: `att-resrc-${b.id}`, kind: 'replacements-received', tone: 'info',
          type: 'REPLACEMENTS RECEIVED', icon: 'refresh',
          title: b.name, badge: b.id, project: proj(b.project),
          meta: `${n} replaced line${n > 1 ? 's' : ''} from Designer ready to re-source`,
          verb: 'Resolve', tag: 'Re-source replaced lines', relatedId: b.id, bom: b,
          titleRoute: { screen: 'p.bomOverview', id: b.id },
        });
      } else if (b.state === 'draft') {
        const warn = b.items.filter(i => i.status === 'needs-review').length;
        items.push({
          id: `att-val-${b.id}`, kind: 'awaiting-validation', tone: 'warning',
          type: 'BOM AWAITING VALIDATION', icon: 'check',
          title: b.name, badge: b.id, project: proj(b.project),
          meta: `${warn} warning${warn === 1 ? '' : 's'} · uploaded ${b.updated}`,
          verb: 'Resolve', tag: 'Review', relatedId: b.id, bom: b, navigateOnly: true,
          titleRoute: { screen: 'p.validate', id: b.id },
        });
      } else if (b.state === 'exceptions' && b.pushback && b.pushback.recommendation && !b.pushback.appliedWhen) {
        const rec = b.pushback.recommendation;
        items.push({
          id: `att-rec-${b.id}`, kind: 'recommendations-recommended', tone: 'info',
          type: 'REPLACEMENTS RECOMMENDED', icon: 'sparkle',
          title: b.name, badge: b.id, project: proj(b.project),
          meta: `${rec.picks.length} replacement${rec.picks.length > 1 ? 's' : ''} recommended by ${rec.by} · review and apply to the master BOM`,
          reason: b.pushback.reason, urgency: b.pushback.urgency,
          verb: 'Resolve', tag: 'Apply replacements', relatedId: b.id, bom: b,
          titleRoute: { screen: 'p.bomOverview', id: b.id },
        });
      }
    }
    // (No "purchasing rejection" card — Purchasing cannot reject or return a request.
    //  Any problem is caught by an upstream check before submission, on Production's side.)
  }

  if (role === 'purchasing') {
  }

  if (role === 'purchasing') {
    // Purchasing is an embedded observation surface (v4), never a login role — deriveAttention
    // is never called with this role. No cards. (Order/shipment lifecycle retired in Session 1.)
  }

  if (role === 'admin') {
    for (const j of (state.system?.jobs || [])) {
      items.push({
        id: `att-job-${j.id}`, kind: 'failed-job', tone: 'danger',
        type: 'FAILED BACKGROUND JOB', icon: 'alert',
        title: j.label, badge: j.id, project: j.object || '—',
        meta: `${j.error} · failed ${j.when}`,
        verb: 'Resolve', tag: 'Retry', relatedId: j.id, job: j,
        titleRoute: { screen: 'a.configuration', tab: 'system' },
      });
    }
    for (const s of (state.system?.stuck || [])) {
      items.push({
        id: `att-stuck-${s.id}`, kind: 'stuck-workflow', tone: 'warning',
        type: 'STUCK WORKFLOW', icon: 'clock',
        title: s.name, badge: s.id, project: s.objType || '—',
        meta: `${s.status} · no activity for ${s.idle}`,
        verb: 'Resolve', tag: 'Reassign', relatedId: s.id, stuck: s,
        titleRoute: { screen: 'a.audit' },
      });
    }
    const dk = (state.system?.status || []).find(s => s.id === 'digikey' && s.tokenExpiry);
    if (dk) {
      items.push({
        id: 'att-token-digikey', kind: 'token-expiring', tone: 'warning',
        type: 'DIGIKEY TOKEN EXPIRING', icon: 'lock',
        title: 'DigiKey API token', badge: 'OAuth', project: 'Suppliers',
        meta: `Expires ${dk.tokenExpiry} · sourcing on DigiKey will fail when it lapses`,
        verb: 'Resolve', tag: 'Refresh token', relatedId: 'digikey-api',
        titleRoute: { screen: 'a.configuration', tab: 'suppliers' },
      });
    }
  }

  return items;
}

function grandOf(items) { return items.reduce((a, i) => a + (i.ext || 0), 0); }

function attCountForRole(state, role) { return deriveAttention(state, role).length; }

/* ---- tone → colors ---- */
const TONE = {
  danger:  { color: 'var(--danger)',  soft: 'var(--danger-soft)' },
  warning: { color: 'var(--warning)', soft: 'var(--warning-soft)' },
  info:    { color: 'var(--action)',  soft: 'var(--action-soft)' },
};

/* ============================================================
   <NeedsAttention role go flashId />
   Renders the interactive Needs Attention panel for a role.
   ============================================================ */
function NeedsAttention({ role, go, flashId }) {
  const items = useStore(s => deriveAttention(s, role));

  return (
    <div className="panel na-panel" style={{ marginBottom: 18 }}>
      <div className="panel-head">
        <Icon name="flag" size={16} style={{ color: 'var(--danger)' }} />
        <span className="ph-title">Needs Attention</span>
        {items.length > 0 && <span className="ph-meta">{items.length} item{items.length > 1 ? 's' : ''} require your action</span>}
      </div>
      {items.length === 0 ? (
        <div className="na-clear">
          <div className="na-clear-badge"><Icon name="check" size={26} /></div>
          <div className="h2" style={{ margin: '12px 0 2px' }}>All caught up</div>
          <div className="secondary">Nothing needs your attention right now.</div>
        </div>
      ) : (
        <div className="na-list">
          {items.map(it => <AttentionCard key={it.id} item={it} role={role} go={go} flash={flashId === it.relatedId || flashId === it.id} />)}
        </div>
      )}
    </div>
  );
}

function AttentionCard({ item, role, go, flash }) {
  const [open, setOpen] = useStateNA(false);
  const [busy, setBusy] = useStateNA(null); // null | 'running' | 'done'
  const ref = useRefNA(null);
  const t = TONE[item.tone] || TONE.info;

  // Notification deep-link: scroll into view + amber flash.
  useEffNA(() => {
    if (flash && ref.current) {
      ref.current.scrollIntoView({ block: 'center', behavior: 'smooth' });
      ref.current.classList.remove('na-flash'); void ref.current.offsetWidth;
      ref.current.classList.add('na-flash');
    }
  }, [flash]);

  const primary = () => {
    if (item.navigateOnly) { go(item.titleRoute); return; }
    setOpen(o => !o);
  };

  return (
    <div ref={ref} className={`na-card${item.overdue ? ' overdue' : ''}${open ? ' open' : ''}`}>
      <div className="na-row">
        <div className="na-icon" style={{ background: t.soft, color: t.color }}><Icon name={item.icon} size={18} /></div>
        <div className="na-main">
          <div className="na-type" style={{ color: t.color }}>{item.type}</div>
          <div className="na-title">
            <button className="na-titlelink" onClick={() => go(item.titleRoute)} title="Open full detail">{item.title}</button>
            <span className="mono caption na-badge">{item.badge}</span>
          </div>
          {item.reason && <div style={{ marginTop: 4 }}><PushbackBadges reason={item.reason} urgency={item.urgency} /></div>}
          <div className="na-meta">{item.project} · {item.meta}</div>
        </div>
        <div className="na-actions">
          <AttentionAction item={item} open={open} busy={busy} onPrimary={primary} />
        </div>
      </div>
      {open && !item.navigateOnly && (
        <div className="na-expand">
          <AttentionExpansion item={item} role={role} go={go} busy={busy} setBusy={setBusy} close={() => setOpen(false)} />
        </div>
      )}
    </div>
  );
}

/* The primary button rendered on the card row. For inline-immediate kinds it
   shows a progress/working state; for expand kinds it toggles the panel. */
function AttentionAction({ item, open, busy, onPrimary }) {
  const t = TONE[item.tone] || TONE.info;
  if (busy === 'running') return <span className="na-working"><span className="spinner" style={{ width: 14, height: 14 }} /> Working…</span>;
  if (busy === 'done') return <span className="na-done" style={{ color: 'var(--success)' }}><Icon name="check" size={14} /> Done</span>;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      {item.tag && <span className="na-actiontag">{item.tag}</span>}
      <button className={`btn sm ${item.tone === 'danger' ? 'danger' : 'primary'}`} onClick={onPrimary}>
        Resolve<Icon name={open ? 'chevdown' : 'arrow'} size={13} style={open ? { transform: 'rotate(180deg)' } : undefined} />
      </button>
    </div>
  );
}

/* ---- the inline expansion bodies, per kind ---- */
function AttentionExpansion({ item, role, go, busy, setBusy, close }) {
  switch (item.kind) {
    case 'bom-exception': return <PushbackResolvePanel bom={item.bom} go={go} close={close} />;
    case 'recommendations-recommended': return <ExpApplyRecommendation item={item} go={go} close={close} />;
    case 'stale-sourcing': return <ExpImmediate label="Re-checking sourcing on stale items…" run={() => storeActions.recheckCollectionSourcing(item.collection.id)} setBusy={setBusy} close={close} doneMsg="Sourcing refreshed — timestamps updated." />;
    case 'awaiting-sourcing': return <ExpSourcing item={item} setBusy={setBusy} close={close} />;
    case 'replacements-received': return <ExpImmediate label="Re-sourcing replaced lines…" run={() => storeActions.resourceReplacedLines(item.bom.id)} setBusy={setBusy} close={close} doneMsg="Replaced lines re-sourced." />;
    case 'failed-job': return <ExpImmediate label="Retrying job…" run={() => storeActions.retryJob(item.job.id)} setBusy={setBusy} close={close} doneMsg="Job re-queued." />;
    case 'stuck-workflow': return <ExpReassign item={item} close={close} />;
    case 'token-expiring': return <ExpImmediate label="Refreshing DigiKey token…" run={() => storeActions.refreshDigiKeyToken()} setBusy={setBusy} close={close} doneMsg="Token refreshed." />;
    default: return null;
  }
}

/* Generic immediate action with an inline progress→done flow. */
function ExpImmediate({ label, run, setBusy, close, doneMsg }) {
  const [phase, setPhase] = useStateNA('idle');
  const start = () => {
    setPhase('running'); setBusy('running');
    setTimeout(() => { run(); setPhase('done'); setBusy('done'); }, 1100);
  };
  return (
    <div className="na-exp-body">
      {phase === 'idle' && (
        <div className="na-confirm">
          <span className="secondary">{label.replace(/…$/, '')} — run now?</span>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn sm ghost" onClick={close}>Cancel</button>
            <button className="btn sm primary" onClick={start}><Icon name="refresh" size={13} />Run now</button>
          </div>
        </div>
      )}
      {phase === 'running' && <div className="na-phase"><span className="spinner" style={{ width: 15, height: 15 }} />{label}</div>}
      {phase === 'done' && <div className="na-phase" style={{ color: 'var(--success)' }}><Icon name="check" size={15} />{doneMsg}</div>}
    </div>
  );
}

/* Production: review Designer's recommendations, then Apply to the master BOM. */
function ExpApplyRecommendation({ item, go, close }) {
  const bom = item.bom; const rec = bom.pushback && bom.pushback.recommendation;
  const [applied, setApplied] = useStateNA(false);
  if (!rec) return null;
  if (applied) return <div className="na-phase" style={{ color: 'var(--success)' }}><Icon name="check" size={15} />Applied to the master BOM. Re-run sourcing on the updated lines.</div>;
  return (
    <div className="na-exp-body">
      <div className="caption" style={{ marginBottom: 8 }}>Designer <strong>{rec.by}</strong> recommended {rec.picks.length} replacement{rec.picks.length > 1 ? 's' : ''}. Review, then Apply to commit them to the master BOM — the version increments on Apply.</div>
      <div className="tbl-wrap flow" style={{ marginBottom: 10 }}><table className="bom">
        <thead><tr><th>Line</th><th>Recommended</th><th>Source</th></tr></thead>
        <tbody>{rec.picks.map((p, idx) => (
          <tr key={idx}><td className="mono">{p.added ? 'NEW' : 'Line ' + p.lineNo}</td>
            <td><span className="mono" style={{ fontWeight: 600 }}>{p.mpn}</span> <span className="caption">{p.mfr}</span></td>
            <td className="caption">{p.section === 'wall' ? 'Wall · ' + p.location : 'Supplier'}{p.datasheet ? ' · datasheet' : ''}</td></tr>
        ))}</tbody></table></div>
      {rec.note && <div className="caption" style={{ marginBottom: 8 }}><em>Note from {rec.by}:</em> {rec.note}</div>}
      <div className="na-confirm">
        <button className="btn sm ghost" onClick={() => go({ screen: 'p.bomOverview', id: bom.id })}>Open BOM</button>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn sm ghost" onClick={close}>Later</button>
          <button className="btn sm primary" onClick={() => { storeActions.applyPushbackRecommendation(bom.id); setApplied(true); }}><Icon name="check" size={13} />Apply to master BOM</button>
        </div>
      </div>
    </div>
  );
}

/* (ExpResubmit removed — no rejection card exists to respond to; Purchasing never returns a request.) */

/* Production: run sourcing inline with a live progress bar. */
function ExpSourcing({ item, setBusy, close }) {
  const [phase, setPhase] = useStateNA('idle');
  const [pct, setPct] = useStateNA(0);
  const total = item.bom.items.length;
  const start = () => {
    setPhase('running'); setBusy('running'); setPct(0);
    let p = 0;
    const iv = setInterval(() => {
      p += Math.random() * 16 + 8; if (p >= 100) { p = 100; clearInterval(iv); setTimeout(() => { storeActions.runBomSourcing(item.bom.id); setPhase('done'); setBusy('done'); }, 350); }
      setPct(Math.round(p));
    }, 260);
  };
  if (phase === 'done') return <div className="na-phase" style={{ color: 'var(--success)' }}><Icon name="check" size={15} />Sourcing complete — results ready on the BOM.</div>;
  if (phase === 'running') return (
    <div className="na-exp-body">
      <div className="na-phase"><span className="spinner" style={{ width: 15, height: 15 }} />Sourcing Mouser → DigiKey…</div>
      <div className="progress" style={{ marginTop: 8 }}><i style={{ width: pct + '%' }} /></div>
      <div className="caption" style={{ marginTop: 6, display: 'flex', gap: 16 }}><span>{Math.round(total * pct / 100)} of {total} lines</span><span>{pct}%</span><span>~{Math.max(1, Math.round((100 - pct) / 12))}s remaining</span></div>
    </div>
  );
  return (
    <div className="na-exp-body">
      <div className="na-confirm">
        <span className="secondary">Run Mouser + DigiKey sourcing on all {total} lines?</span>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn sm ghost" onClick={close}>Cancel</button>
          <button className="btn sm primary" onClick={start}><Icon name="search" size={13} />Run sourcing</button>
        </div>
      </div>
    </div>
  );
}

/* Admin: reassign a stuck workflow inline. */
function ExpReassign({ item, close }) {
  const users = useStore(s => s.users.filter(u => u.active));
  const [to, setTo] = useStateNA('');
  const [done, setDone] = useStateNA(false);
  if (done) return <div className="na-phase" style={{ color: 'var(--success)' }}><Icon name="check" size={15} />Reassigned to {to}. They've been notified.</div>;
  return (
    <div className="na-exp-body">
      <label className="fl" style={{ display: 'block', marginBottom: 4 }}>Reassign to</label>
      <select className="select" value={to} onChange={e => setTo(e.target.value)} style={{ width: '100%' }}>
        <option value="">Select a user…</option>
        {users.map(u => <option key={u.id} value={u.name}>{u.name} — {(u.roles || []).join(', ')}</option>)}
      </select>
      <div className="na-confirm" style={{ marginTop: 8 }}>
        <button className="btn sm ghost" onClick={close}>Cancel</button>
        <button className="btn sm primary" disabled={!to} onClick={() => { storeActions.reassignWorkflow(item.stuck.id, to); setDone(true); }}><Icon name="arrow" size={13} />Confirm reassignment</button>
      </div>
    </div>
  );
}

Object.assign(window, { NeedsAttention, deriveAttention, attCountForRole });
