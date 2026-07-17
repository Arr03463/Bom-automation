/* global React, Icon, SupplierTag, CATALOG, fmtUSD, fmtInt */
/* InlinePartVerify — reusable embedded part lookup.

   Used wherever a user enters a Manufacturer + MPN and needs to verify the part
   WITHOUT leaving the workflow (BOM exception response, Designer collection rejection
   response, Dev Collection candidate entry, Improvement Recommendation, Rework Package).

   Hard rules:
   - Never navigates. Never opens a modal. Never affects scroll position.
   - The result card renders inline beneath the inputs, replacing only the loading state.
   - On Use This Part, calls onConfirm({mpn, mfr, supplier, supplierPn, unit, lifecycle}).
   - View Full Details opens /designer/search?q=<mpn> in a NEW browser tab only.
   - On failure (no result, API down), user-entered data is preserved.

   Props:
     mpn / mfr           — controlled values (parent owns the inputs' text)
     onMpnChange(s)      — fires on every keystroke
     onMfrChange(s)      — fires on every keystroke
     onConfirm(part)     — fires when user clicks Use This Part
     compact             — render side-by-side (for narrow contexts like exception rows)
     scenario            — 'auto' (default) | 'no-match' | 'unavailable' | 'partial'
                            controls the simulated fetch outcome for demo purposes;
                            in production this would just be 'auto'
*/
const { useState: useStateIPV, useRef: useRefIPV, useEffect: useEffIPV } = React;

const IPV_PHASES = [
  { key: 'mouser', label: 'Searching Mouser…' },
  { key: 'digikey', label: 'Searching DigiKey…' },
  { key: 'lifecycle', label: 'Checking lifecycle status…' },
];

/* Simulate the lookup. In production this hits real supplier APIs. */
function ipvSimulate(mpn, scenarioOverride) {
  const key = (mpn || '').trim().toUpperCase();
  const part = CATALOG[key];

  // Allow callers / specific MPNs to force demo scenarios
  let scenario = scenarioOverride || 'auto';
  if (scenario === 'auto') {
    if (key === 'NORESULT' || key === 'NONE' || key === 'XXX') scenario = 'no-match';
    else if (key === 'OFFLINE' || key === 'APIDOWN') scenario = 'unavailable';
    else if (key === 'PARTIAL') scenario = 'partial';
    else scenario = part ? 'found' : 'no-match';
  }
  return { scenario, part };
}

function InlinePartVerify({ mpn, mfr, onMpnChange, onMfrChange, onConfirm, scenario, compact, originalMpn, autoFocusMpn }) {
  // Lookup-state machine — completely independent of parent.
  // null = idle, 'running' = phases playing, anything else = a result mode
  const [phase, setPhase] = useStateIPV(null);     // null | 0 | 1 | 2  during 'running'
  const [running, setRunning] = useStateIPV(false);
  const [result, setResult] = useStateIPV(null);   // {scenario, part}
  const mpnRef = useRefIPV(null);
  const timers = useRefIPV([]);

  // Cleanup outstanding timers on unmount so a parent re-render won't strand them.
  useEffIPV(() => () => timers.current.forEach(clearTimeout), []);
  useEffIPV(() => { if (autoFocusMpn) mpnRef.current?.focus(); }, [autoFocusMpn]);

  const reset = () => {
    timers.current.forEach(clearTimeout); timers.current = [];
    setPhase(null); setRunning(false); setResult(null);
  };

  const run = () => {
    if (!mpn || !mpn.trim()) return;
    reset();
    setRunning(true); setPhase(0);
    // Sequential phases — purely visual; the click never causes a navigation.
    timers.current.push(setTimeout(() => setPhase(1), 380));
    timers.current.push(setTimeout(() => setPhase(2), 760));
    timers.current.push(setTimeout(() => {
      setRunning(false);
      setResult(ipvSimulate(mpn, scenario));
    }, 1180));
  };

  // Edits to MPN after a result has rendered clear the result (so it's not stale).
  // But we DO NOT clear other state — manufacturer text, the rest of the form, etc.
  const handleMpn = (v) => {
    onMpnChange && onMpnChange(v);
    if (result) reset();
  };

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !running) { e.preventDefault(); run(); }
  };

  // View Full Details opens in a NEW browser tab — the current workflow is preserved.
  const openInNewTab = () => {
    const url = window.location.origin + window.location.pathname + '#/designer/search?q=' + encodeURIComponent(mpn || '');
    window.open(url, '_blank', 'noopener');
  };

  return (
    <div className="ipv">
      {/* Inputs — parent controls values; we never reset them */}
      <div className={`ipv-fields ${compact ? 'compact' : ''}`}>
        <label className="ipv-field">
          <span className="ipv-label">Manufacturer</span>
          <input className="input" placeholder="e.g. Texas Instruments" value={mfr || ''} onChange={e => onMfrChange && onMfrChange(e.target.value)} onKeyDown={onKeyDown} />
        </label>
        <label className="ipv-field">
          <span className="ipv-label">MPN</span>
          <input ref={mpnRef} className="input mono" placeholder="e.g. LMR33630FDDAR" value={mpn || ''} onChange={e => handleMpn(e.target.value)} onKeyDown={onKeyDown} />
        </label>
        <button className="btn primary" disabled={!mpn || !mpn.trim() || running} onClick={run}>
          {running ? <span className="spinner" style={{ width: 14, height: 14 }} /> : <Icon name="check" size={15} />}
          {running ? 'Verifying…' : 'Verify Part'}
        </button>
      </div>

      {/* Loading state — renders inline; everything around stays put */}
      {running && (
        <div className="ipv-card ipv-loading">
          {IPV_PHASES.map((p, i) => {
            const state = i < phase ? 'done' : i === phase ? 'active' : 'pending';
            return (
              <div key={p.key} className={`ipv-phase ${state}`}>
                {state === 'done' ? <Icon name="check" size={14} />
                  : state === 'active' ? <span className="spinner" style={{ width: 12, height: 12 }} />
                    : <Icon name="circle" size={10} />}
                <span>{p.label}</span>
              </div>
            );
          })}
        </div>
      )}

      {/* Result — found */}
      {result && result.scenario === 'found' && (
        <IpvResultFound mpn={mpn} mfr={mfr} part={result.part} onUse={(p) => { onConfirm && onConfirm(p); reset(); }} onAgain={() => { reset(); mpnRef.current?.focus(); }} onView={openInNewTab} originalMpn={originalMpn} />
      )}

      {/* Result — partial: only one supplier responded */}
      {result && result.scenario === 'partial' && result.part && (
        <IpvResultFound mpn={mpn} mfr={mfr} part={{ ...result.part, digikey: null }} partial="digikey"
          onUse={(p) => { onConfirm && onConfirm(p); reset(); }} onAgain={() => { reset(); mpnRef.current?.focus(); }} onView={openInNewTab} originalMpn={originalMpn} />
      )}

      {/* Result — no match */}
      {result && result.scenario === 'no-match' && (
        <div className="ipv-card ipv-empty">
          <div className="ipv-empty-head">
            <Icon name="x" size={16} style={{ color: 'var(--danger)' }} />
            <span>No matching component found for <span className="mono">{mpn}</span>.</span>
          </div>
          <div className="caption" style={{ marginTop: 4 }}>Check the MPN spelling, try a partial MPN, or open advanced search to look more broadly. Your entries above were not cleared.</div>
          <div className="ipv-actions">
            <button className="btn sm" onClick={() => { mpnRef.current?.focus(); mpnRef.current?.select(); }}><Icon name="refresh" size={13} />Edit MPN</button>
            <button className="btn sm" onClick={() => { reset(); mpnRef.current?.focus(); }}>Search Again</button>
            <button className="btn sm ghost" onClick={openInNewTab}><Icon name="external" size={13} />Open Advanced Search</button>
          </div>
        </div>
      )}

      {/* Result — supplier API unavailable */}
      {result && result.scenario === 'unavailable' && (
        <div className="ipv-card ipv-warn">
          <div className="ipv-empty-head">
            <Icon name="alert" size={16} style={{ color: 'var(--warning)' }} />
            <span>Supplier information currently unavailable.</span>
          </div>
          <div className="caption" style={{ marginTop: 4 }}>Mouser and DigiKey both timed out. <strong>Your entries above have been preserved.</strong> You can retry now, or save and resolve this exception later.</div>
          <div className="ipv-actions">
            <button className="btn sm primary" onClick={run}><Icon name="refresh" size={13} />Retry</button>
            <button className="btn sm" onClick={reset}>Save and Continue Later</button>
          </div>
        </div>
      )}
    </div>
  );
}

function IpvResultFound({ mpn, mfr, part, partial, onUse, onAgain, onView, originalMpn }) {
  const isObsolete = part.lifecycle === 'obsolete';
  const recommended = part.recommend;
  const supplier = recommended || (part.mouser ? 'mouser' : 'digikey');
  const off = part[supplier];
  const handleUse = () => onUse({
    mpn: part.mpn, mfr: part.mfr, supplier,
    supplierPn: off?.pn, unit: off?.price, lifecycle: part.lifecycle,
    desc: part.desc,
  });

  return (
    <div className={`ipv-card ipv-result ${isObsolete ? 'eol' : ''}`}>
      <div className="ipv-result-head">
        <Icon name={isObsolete ? 'alert' : 'check'} size={16} style={{ color: isObsolete ? 'var(--danger)' : 'var(--success)' }} />
        <div className="ipv-mpn">
          <span className="mono" style={{ fontWeight: 700 }}>{part.mpn}</span>
          <span className="secondary"> — {part.mfr}</span>
        </div>
        <span className={`badge ${isObsolete ? 'filled' : 'outlined'}`} style={{ color: isObsolete ? '#fff' : 'var(--success)', background: isObsolete ? 'var(--darkred)' : 'transparent', borderColor: isObsolete ? 'var(--darkred)' : 'var(--success)' }}>
          <Icon name={isObsolete ? 'ban' : 'check'} size={11} />
          {isObsolete ? 'OBSOLETE / EOL' : 'ACTIVE'}
        </span>
      </div>
      {part.desc && <div className="caption" style={{ marginLeft: 24, marginTop: 2 }}>{part.desc}</div>}

      <div className="ipv-suppliers">
        {part.mouser ? (
          <IpvSupplierLine supplier="mouser" off={part.mouser} recommended={recommended === 'mouser'} />
        ) : (
          <IpvSupplierLine supplier="mouser" unavailable />
        )}
        {part.digikey ? (
          <IpvSupplierLine supplier="digikey" off={part.digikey} recommended={recommended === 'digikey'} />
        ) : (
          <IpvSupplierLine supplier="digikey" unavailable={partial === 'digikey'} />
        )}
      </div>

      {recommended && <div className="ipv-recommended">Recommended: <SupplierTag supplier={recommended} /></div>}
      {isObsolete && <div className="caption" style={{ marginTop: 6, color: 'var(--danger)' }}>This part is end-of-life. Not recommended as a replacement for a production BOM.</div>}
      {originalMpn && part.mpn === originalMpn && <div className="caption" style={{ marginTop: 6, color: 'var(--warning)' }}>⚠ This is the same MPN that was flagged. Pick a different replacement.</div>}

      <div className="ipv-actions">
        <button className="btn primary sm" disabled={isObsolete || (originalMpn && part.mpn === originalMpn)} onClick={handleUse}><Icon name="check" size={13} />Use This Part</button>
        <button className="btn sm" onClick={onAgain}><Icon name="refresh" size={13} />Search Again</button>
        <button className="btn sm ghost" onClick={onView}><Icon name="external" size={13} />View Full Details</button>
      </div>
    </div>
  );
}

function IpvSupplierLine({ supplier, off, recommended, unavailable }) {
  if (unavailable) return (
    <div className="ipv-sup ipv-sup-unavail">
      <SupplierTag supplier={supplier} />
      <span className="muted" style={{ marginLeft: 'auto' }}>Unavailable — retry later</span>
    </div>
  );
  const zero = off.stock === 0;
  return (
    <div className={`ipv-sup ${recommended ? 'rec' : ''}`}>
      <SupplierTag supplier={supplier} />
      <span className="ipv-stock" style={{ color: zero ? 'var(--danger)' : 'var(--success)', fontWeight: 600 }}>{zero ? '0 — no stock' : fmtInt(off.stock) + ' in stock'}</span>
      <span className="ipv-price mono">{off.price ? fmtUSD(off.price) : '—'}</span>
      <span className="ipv-pn mono caption">{off.pn}</span>
      {recommended && <span className="ipv-rec-flag">Recommended</span>}
    </div>
  );
}

Object.assign(window, { InlinePartVerify });
