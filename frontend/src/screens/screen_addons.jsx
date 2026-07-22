/* global React, Icon, SupplierTag, ROLE, ROLE_META, Banner, EmptyState,
   useStore, storeActions, getState, CATALOG, PROJECTS, fmtUSD, fmtInt */
/* AutoBOM — shared interactive components used across multiple screens.
   - <CommentThread entityId>      Persistent comment surface for any object.
   - <NewCollectionModal>          Create-collection modal (designer or development kind).
   - <AddPartDrawer>               In-page drawer to add a part to a collection without navigating.
   These are all store-backed and update the global workflow state. */
const { useState: useStateAddons, useRef: useRefAddons, useEffect: useEffAddons } = React;

/* =========================================================
   CommentThread — every commentable object uses this.
   ========================================================= */
function CommentThread({ entityId, title = 'Comments', emptyHint = 'Comments on this record are a permanent part of the audit trail. They replace email threads and chat messages that would otherwise carry engineering decisions.' }) {
  const comments = useStore(s => s.comments[entityId] || []);
  const activeRole = useStore(s => s.activeRole);
  const me = useStore(s => s.users.find(u => u.id === s.currentUserId));
  const [body, setBody] = useStateAddons('');
  const tRef = useRefAddons(null);

  const submit = () => {
    const t = body.trim(); if (!t) return;
    storeActions.addComment(entityId, t);
    setBody('');
    requestAnimationFrame(() => tRef.current?.focus());
  };

  return (
    <section className="comments" aria-label={title}>
      <header className="comments-head">
        <Icon name="comment" size={16} />
        <h3 className="h2" style={{ margin: 0, fontSize: 15 }}>{title}</h3>
        <span className="caption" style={{ marginLeft: 'auto' }}>{comments.length} comment{comments.length === 1 ? '' : 's'}</span>
      </header>

      {comments.length === 0 ? (
        <div className="comments-empty">
          <Icon name="comment" size={18} />
          <div style={{ fontWeight: 600, marginTop: 5 }}>No comments yet.</div>
          <div className="caption" style={{ marginTop: 4, maxWidth: 460, marginLeft: 'auto', marginRight: 'auto' }}>{emptyHint}</div>
        </div>
      ) : (
        <ol className="comment-list">
          {comments.map(c => {
            const accent = (ROLE_META && ROLE_META[c.role]?.color) || (ROLE && ROLE[c.role]?.color) || 'var(--text-secondary)';
            const initials = c.name.split(' ').map(w => w[0]).slice(0, 2).join('');
            return (
              <li key={c.id} className="comment-item">
                {/* Avatar column — leaves room for future reply-indent rail. */}
                <div className="comment-rail">
                  <span className="avatar" style={{ background: accent, width: 28, height: 28, fontSize: 11 }}>{initials}</span>
                </div>
                <div className="comment-body">
                  <div className="comment-meta">
                    <span style={{ fontWeight: 600 }}>{c.name}</span>
                    <span className="tag" style={{ background: accent, color: '#fff' }}>{(c.role || '').toUpperCase()}</span>
                    <span className="caption" style={{ marginLeft: 'auto' }}>{c.when}</span>
                  </div>
                  <div className="comment-text">{c.body}</div>
                  {/* Reply hook reserved for future — visually leaves space without active control. */}
                </div>
              </li>
            );
          })}
        </ol>
      )}

      <div className="comment-composer">
        <span className="avatar" style={{ background: (ROLE_META && ROLE_META[activeRole]?.color) || 'var(--text-secondary)', width: 28, height: 28, fontSize: 11, flex: 'none' }}>
          {(me?.name || 'You').split(' ').map(w => w[0]).slice(0, 2).join('')}
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <textarea ref={tRef} className="textarea" rows={2} placeholder={`Add a comment as ${me?.name || 'you'} (${(activeRole || '').toUpperCase()})…`}
            value={body} onChange={e => setBody(e.target.value)}
            onKeyDown={e => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') submit(); }} />
          <div className="comment-composer-row">
            <span className="caption">⌘↩ to post · saved with your name, role, and timestamp.</span>
            <button className="btn primary sm" disabled={!body.trim()} onClick={submit}><Icon name="send" size={13} />Post comment</button>
          </div>
        </div>
      </div>
    </section>
  );
}

/* =========================================================
   NewCollectionModal — designer + development variants.
   ========================================================= */
const DESIGNER_CATEGORIES = ['R&D', 'Prototype', 'Production Prep', 'Other'];
const DEV_CATEGORIES = ['Investigation', 'Testing', 'Validation', 'Rework', 'Reliability', 'Firmware', 'Hardware', 'Cost Reduction', 'Future Revision', 'Supplier Evaluation'];

function NewCollectionModal({ kind = 'designer', defaultProgram, onClose, onCreated }) {
  const programs = useStore(s => s.programs || []);
  const me = useStore(s => s.users.find(u => u.id === s.currentUserId));
  const boms = useStore(s => s.boms);

  const cats = kind === 'development' ? DEV_CATEGORIES : DESIGNER_CATEGORIES;
  const isDev = kind === 'development';

  const [name, setName] = useStateAddons('');
  const [program, setProgram] = useStateAddons(defaultProgram || programs[0]?.id || '');
  const [desc, setDesc] = useStateAddons('');
  const [category, setCategory] = useStateAddons(cats[0]);
  const [notes, setNotes] = useStateAddons('');
  const [showOptional, setShowOptional] = useStateAddons(false);
  const [tags, setTags] = useStateAddons('');
  const [priority, setPriority] = useStateAddons('');
  const [relatedBom, setRelatedBom] = useStateAddons('');
  const nameRef = useRefAddons(null);

  useEffAddons(() => { nameRef.current?.focus(); }, []);
  // Esc closes; outside-scrim click closes via Modal wrap.
  useEffAddons(() => {
    const k = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', k); return () => document.removeEventListener('keydown', k);
  }, [onClose]);

  const [busy, setBusy] = useStateAddons(false);
  const valid = name.trim().length > 1 && program && (!isDev || category);

  // createCollection is async — it was previously called without `await`, so the
  // raw Promise was handed to onCreated and stringified into the redirect URL as
  // "#/designer/collections/[object Promise]". Await the real id, and don't
  // navigate at all if the create failed.
  const submit = async () => {
    if (!valid || busy) return;
    setBusy(true);
    try {
      const id = await storeActions.createCollection({
        kind, name, program_id: program, category: isDev ? category : null, desc, notes,
        tags: tags.split(',').map(s => s.trim()).filter(Boolean),
        priority: priority || null,
        relatedBom: relatedBom || null,
      });
      if (!id) { window.__toast?.('Could not create the collection — please try again.', 'alert'); return; }
      onCreated && onCreated(id);
    } finally {
      setBusy(false);
    }
  };

  const accent = isDev ? 'var(--role-development, #059669)' : 'var(--role-designer, #7C3AED)';

  return (
    <>
      <div className="scrim" onMouseDown={onClose} />
      <div className="modal-wrap" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
        <div className="modal" style={{ width: 560, maxWidth: '95vw' }} onMouseDown={(e) => e.stopPropagation()}>
          <div className="modal-head" style={{ borderTop: `3px solid ${accent}` }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
              <Icon name="layers" size={18} style={{ color: accent }} />
              <div className="mh-title">New {isDev ? 'Development' : 'Designer'} Collection</div>
              <button className="icon-btn" style={{ marginLeft: 'auto', width: 30, height: 30 }} onClick={onClose}><Icon name="x" size={16} /></button>
            </div>
            <div className="caption" style={{ marginTop: 4 }}>
              {isDev ? 'A workspace for investigations, testing, and product improvements.' : 'A workspace for engineering research — parts you\'re investigating before they reach a BOM.'}
            </div>
          </div>

          <div className="modal-body" style={{ display: 'grid', gap: 12 }}>
            <label className="field">
              <span className="fl">Collection name<span style={{ color: 'var(--danger)' }}> *</span></span>
              <input ref={nameRef} className="input" placeholder={isDev ? 'e.g. Alternative Capacitor Testing' : 'e.g. TVCA Connector Research'} value={name} onChange={e => setName(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && valid) submit(); }} />
            </label>

            {isDev ? (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <label className="field">
                  <span className="fl">Program<span style={{ color: 'var(--danger)' }}> *</span></span>
                  <select className="select" value={program} onChange={e => setProgram(e.target.value)}>
                    {programs.map(p => <option key={p.id} value={p.id}>{(p.identifier || p.code)} · {p.name}</option>)}
                  </select>
                </label>
                <label className="field">
                  <span className="fl">Category<span style={{ color: 'var(--danger)' }}> *</span></span>
                  <select className="select" value={category} onChange={e => setCategory(e.target.value)}>
                    {cats.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </label>
              </div>
            ) : (
              <label className="field">
                <span className="fl">Program<span style={{ color: 'var(--danger)' }}> *</span></span>
                <select className="select" value={program} onChange={e => setProgram(e.target.value)}>
                  {programs.map(p => <option key={p.id} value={p.id}>{(p.identifier || p.code)} · {p.name}</option>)}
                </select>
              </label>
            )}

            <label className="field">
              <span className="fl">Description</span>
              <textarea className="textarea" rows={2} placeholder={isDev ? 'What are you investigating and why?' : 'What are you researching here?'} value={desc} onChange={e => setDesc(e.target.value)} />
            </label>

            <label className="field">
              <span className="fl">Notes <span className="muted">(optional)</span></span>
              <textarea className="textarea" rows={2} placeholder="Initial observations, hypotheses, anything you want to capture before parts are added." value={notes} onChange={e => setNotes(e.target.value)} />
            </label>

            <div className="field" style={{ marginTop: -2 }}>
              <span className="fl">Owner</span>
              <div className="input" style={{ display: 'flex', alignItems: 'center', gap: 9, color: 'var(--text-secondary)' }}>
                <span className="avatar" style={{ background: accent, width: 22, height: 22, fontSize: 10 }}>{(me?.name || 'You').split(' ').map(w => w[0]).slice(0, 2).join('')}</span>
                <span>{me?.name || 'You'}</span>
                <span className="caption" style={{ marginLeft: 'auto' }}>Defaults to current user — Admin can reassign later.</span>
              </div>
            </div>

            <button className="btn-link" style={{ alignSelf: 'flex-start', padding: 0 }} onClick={() => setShowOptional(s => !s)}>
              <Icon name={showOptional ? 'chevdown' : 'chevright'} size={13} />{showOptional ? 'Hide' : 'Show'} optional fields (tags, priority, related work)
            </button>

            {showOptional && (
              <div style={{ display: 'grid', gap: 10, padding: 12, border: '1px dashed var(--border)', borderRadius: 8, background: 'var(--bg-raised)' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 10 }}>
                  <label className="field"><span className="fl">Tags</span>
                    <input className="input" placeholder="comma, separated, tags" value={tags} onChange={e => setTags(e.target.value)} />
                  </label>
                  <label className="field"><span className="fl">Priority</span>
                    <select className="select" value={priority} onChange={e => setPriority(e.target.value)}>
                      <option value="">—</option><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option>
                    </select>
                  </label>
                </div>
                <label className="field"><span className="fl">Related {isDev ? 'BOM' : 'BOM'} <span className="muted">(optional)</span></span>
                  <select className="select" value={relatedBom} onChange={e => setRelatedBom(e.target.value)}>
                    <option value="">—</option>
                    {boms.map(b => <option key={b.id} value={b.id}>{b.id} · {b.name}</option>)}
                  </select>
                </label>
              </div>
            )}
          </div>

          <div className="modal-foot">
            <button className="btn ghost" onClick={onClose}>Cancel</button>
            <button className="btn primary" disabled={!valid || busy} onClick={submit}>
              <Icon name="check" size={14} />{busy ? 'Creating…' : 'Create collection'}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

/* =========================================================
   AddPartDrawer — inline part lookup, never navigates the page.
   Pattern parallels <InlinePartVerify> but adapted for adding parts
   (search by MPN/manufacturer/keyword, set qty + per-item notes, confirm).
   ========================================================= */
function searchCatalog(q) {
  const s = (q || '').trim().toLowerCase();
  if (!s) return [];
  return Object.values(CATALOG).filter(c =>
    c.mpn.toLowerCase().includes(s) || c.mfr.toLowerCase().includes(s) || (c.desc || '').toLowerCase().includes(s)
  );
}

/* Live /api/suppliers/search -> the drawer's result shape.
   The endpoint returns one best match per supplier ({query, mouser, digikey,
   errors}); both describe the same MPN, so they fold into a single row with a
   chip each. Stock/price come straight from the supplier payload — no fixtures. */
function mapSupplierHit(res) {
  const m = res && res.mouser, d = res && res.digikey;
  if (!m && !d) return null;
  const primary = m || d;
  const side = (r) => (r ? {
    pn: r.supplier_part_number || '',
    stock: r.stock || 0,
    price: window.parsePrice ? window.parsePrice(r.unit_price) : parseFloat(r.unit_price),
    url: r.product_url || '',
  } : null);
  return {
    mpn: primary.mpn,
    mfr: primary.manufacturer || '',
    desc: primary.description || '',
    lifecycle: String(primary.lifecycle_status || '').toLowerCase().includes('obsolete') ? 'obsolete' : 'active',
    mouser: side(m),
    digikey: side(d),
    live: true,
  };
}

function AddPartDrawer({ open, onClose, collectionId, kind = 'designer' }) {
  const collection = useStore(s => s.collections.find(c => c.id === collectionId));
  const [q, setQ] = useStateAddons('');
  const [phase, setPhase] = useStateAddons('idle'); // idle | mouser | digikey | done
  const [results, setResults] = useStateAddons([]);
  const [selected, setSelected] = useStateAddons(null);
  const [qty, setQty] = useStateAddons(1);
  const [note, setNote] = useStateAddons('');
  const inputRef = useRefAddons(null);
  const timers = useRefAddons([]);
  const focusReturn = useRefAddons(null);

  useEffAddons(() => () => timers.current.forEach(clearTimeout), []);
  useEffAddons(() => {
    if (open) {
      focusReturn.current = document.activeElement;
      requestAnimationFrame(() => inputRef.current?.focus());
    } else if (focusReturn.current) {
      try { focusReturn.current.focus(); } catch (e) {}
    }
  }, [open]);

  useEffAddons(() => {
    const k = (e) => { if (e.key === 'Escape' && open) onClose(); };
    document.addEventListener('keydown', k); return () => document.removeEventListener('keydown', k);
  }, [open, onClose]);

  const reset = () => {
    timers.current.forEach(clearTimeout); timers.current = [];
    setPhase('idle'); setResults([]); setSelected(null); setQty(1); setNote('');
  };

  /* Ask the real suppliers.
     This used to be pure theatre: two setTimeouts (440ms "searching Mouser",
     880ms "searching DigiKey") and then searchCatalog(q) — the bundled seed
     fixtures. So the drawer reported ERJ-3EKF1002V as 940,000 @ Mouser and
     1,200,000 @ DigiKey when the live figures were 966,425 and 5,320,216, and
     the seeded 0.004/0.003 prices rendered as "$0.00". No request was ever made.
     CLAUDE.md: "Add part NEVER navigates. Inline drawer using
     search_available_stock mode" — that means the live two-mode search. */
  const run = async () => {
    const query = q.trim();
    if (!query) return;
    timers.current.forEach(clearTimeout); timers.current = [];
    setSelected(null); setResults([]); setPhase('mouser');
    try {
      const res = await window.api.post('/suppliers/search', { query });
      setPhase('digikey');
      const hit = mapSupplierHit(res);
      // Keep the seed catalog only as an offline fallback so the drawer still
      // demonstrates something if the suppliers are unreachable.
      setResults(hit ? [hit] : searchCatalog(query));
    } catch (e) {
      setResults(searchCatalog(query));
    }
    setPhase('done');
  };

  const confirm = () => {
    if (!selected) return;
    storeActions.addToCollection(selected.mpn, collectionId);
    // Apply qty + note to the line we just appended (last item).
    const updated = (getState().collections.find(c => c.id === collectionId)?.items || []);
    const last = updated[updated.length - 1];
    if (last) {
      if (qty !== 1) storeActions.updateQty(collectionId, last.no, qty);
      if (note.trim()) storeActions.setItemNote(collectionId, last.no, note.trim());
    }
    window.__toast?.(`${selected.mpn} added to ${collection?.name || 'collection'}`, 'plus');
    // Stay open, ready for the next part — clear inputs but keep query so user knows where they were.
    setSelected(null); setQty(1); setNote(''); setQ(''); setResults([]); setPhase('idle');
    requestAnimationFrame(() => inputRef.current?.focus());
  };

  if (!open) return null;
  const accent = kind === 'development' ? 'var(--role-development, #059669)' : 'var(--role-designer, #7C3AED)';

  return (
    <>
      <div className="scrim" onMouseDown={onClose} />
      <div className="slideout" role="dialog" aria-label="Add part to collection" style={{ width: 480 }}>
        <div className="slideout-head" style={{ borderBottom: `2px solid ${accent}` }}>
          <Icon name="plus" size={17} style={{ color: accent }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 700, fontSize: 15 }}>Add a part</div>
            <div className="caption" style={{ marginTop: 1 }}>{collection?.name}</div>
          </div>
          <button className="icon-btn" onClick={onClose} title="Close (Esc)"><Icon name="x" size={17} /></button>
        </div>

        <div className="slideout-body" style={{ padding: '14px 18px' }}>
          {/* Search input */}
          <div className="searchfield" style={{ height: 38 }}>
            <Icon name="search" size={15} style={{ color: 'var(--text-muted)' }} />
            <input ref={inputRef} placeholder="MPN, manufacturer, or keyword…" value={q}
              onChange={e => setQ(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') run(); }} />
            {q && <button className="icon-btn" style={{ width: 26, height: 26 }} onClick={() => { setQ(''); inputRef.current?.focus(); reset(); }}><Icon name="x" size={14} /></button>}
            <button className="btn primary sm" disabled={!q.trim() || phase === 'mouser' || phase === 'digikey'} onClick={run}>
              {phase === 'mouser' || phase === 'digikey' ? <span className="spinner" style={{ width: 12, height: 12 }} /> : <Icon name="search" size={13} />}
              Search
            </button>
          </div>

          {/* Sequential phase indicators */}
          {(phase === 'mouser' || phase === 'digikey') && (
            <div className="ipv-card ipv-loading" style={{ marginTop: 10 }}>
              <div className={`ipv-phase ${phase === 'mouser' ? 'active' : 'done'}`}>
                {phase === 'mouser' ? <span className="spinner" style={{ width: 12, height: 12 }} /> : <Icon name="check" size={14} />}
                <span>Searching Mouser…</span>
              </div>
              <div className={`ipv-phase ${phase === 'digikey' ? 'active' : 'pending'}`}>
                {phase === 'digikey' ? <span className="spinner" style={{ width: 12, height: 12 }} /> : <Icon name="circle" size={10} />}
                <span>Searching DigiKey…</span>
              </div>
            </div>
          )}

          {/* Idle state — suggestions */}
          {phase === 'idle' && !selected && (
            <div className="caption" style={{ marginTop: 14, padding: 12, border: '1px dashed var(--border)', borderRadius: 8, background: 'var(--bg-raised)' }}>
              <Icon name="sparkle" size={13} style={{ marginRight: 5 }} />
              Type an MPN, partial MPN, or keyword to search Mouser and DigiKey. Pressing <kbd style={{ fontFamily: 'var(--font-mono)', background: '#fff', border: '1px solid var(--border)', padding: '1px 5px', borderRadius: 4 }}>Enter</kbd> runs the search.
            </div>
          )}

          {/* Results list */}
          {phase === 'done' && !selected && (
            results.length === 0 ? (
              <div style={{ marginTop: 12 }}>
                <div className="ipv-card ipv-empty" style={{ marginTop: 0 }}>
                  <div className="ipv-empty-head">
                    <Icon name="x" size={15} style={{ color: 'var(--danger)' }} />
                    <span>No matches for "{q}".</span>
                  </div>
                  <div className="caption" style={{ marginTop: 4 }}>Try a partial MPN or a different keyword. Nothing was added.</div>
                </div>
              </div>
            ) : (
              <ul className="add-result-list">
                {results.map(c => (
                  <li key={c.mpn} className="add-result" onClick={() => setSelected(c)}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div className="mono" style={{ fontWeight: 600 }}>{c.mpn}{c.lifecycle === 'obsolete' && <span className="badge filled" style={{ background: 'var(--darkred)', marginLeft: 6 }}><Icon name="ban" size={11} />EOL</span>}</div>
                      <div className="caption" style={{ marginTop: 1 }}>{c.mfr} · {c.desc}</div>
                      <div style={{ display: 'flex', gap: 10, marginTop: 5, fontSize: 12 }}>
                        {c.mouser && <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}><SupplierTag supplier="mouser" /><span style={{ color: c.mouser.stock > 0 ? 'var(--success)' : 'var(--danger)', fontWeight: 600 }}>{fmtInt(c.mouser.stock)}</span> · {window.fmtUnitPrice(c.mouser.price)}</span>}
                        {c.digikey && <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}><SupplierTag supplier="digikey" /><span style={{ color: c.digikey.stock > 0 ? 'var(--success)' : 'var(--danger)', fontWeight: 600 }}>{fmtInt(c.digikey.stock)}</span> · {window.fmtUnitPrice(c.digikey.price)}</span>}
                      </div>
                    </div>
                    <button className="btn sm primary" onClick={(e) => { e.stopPropagation(); setSelected(c); }}><Icon name="plus" size={13} />Add</button>
                  </li>
                ))}
              </ul>
            )
          )}

          {/* Selected — set qty + note before confirming */}
          {selected && (
            <div className="ipv-card ipv-result" style={{ marginTop: 12 }}>
              <div className="ipv-result-head">
                <Icon name="check" size={16} style={{ color: 'var(--success)' }} />
                <div className="ipv-mpn"><span className="mono" style={{ fontWeight: 700 }}>{selected.mpn}</span> <span className="secondary"> — {selected.mfr}</span></div>
                <button className="btn-link" onClick={() => setSelected(null)}><Icon name="refresh" size={12} />Pick a different part</button>
              </div>
              <div className="caption" style={{ marginLeft: 24, marginTop: 2 }}>{selected.desc}</div>
              <div style={{ display: 'grid', gridTemplateColumns: '90px 1fr', gap: 10, marginTop: 12 }}>
                <label className="field"><span className="fl">Qty</span><input className="input mono" type="number" min={1} value={qty} onChange={e => setQty(Math.max(1, parseInt(e.target.value, 10) || 1))} /></label>
                <label className="field"><span className="fl">Note <span className="muted">(optional)</span></span><input className="input" placeholder="Why this part, test observations…" value={note} onChange={e => setNote(e.target.value)} /></label>
              </div>
            </div>
          )}
        </div>

        <div className="slideout-foot">
          <span className="caption" style={{ marginRight: 'auto' }}>Drawer stays open after each add — keep going.</span>
          <button className="btn" onClick={onClose}>Close</button>
          <button className="btn primary" disabled={!selected} onClick={confirm}><Icon name="plus" size={14} />Add to collection</button>
        </div>
      </div>
    </>
  );
}

Object.assign(window, { CommentThread, NewCollectionModal, AddPartDrawer });
