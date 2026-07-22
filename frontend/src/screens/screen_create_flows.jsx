/* global React, Icon, useStore, storeActions */
/* AutoBOM — Create Program / Create Project modals (v4, Note 3).
   Program → Project enforced (Standalone retired). Live validation, empty-Programs
   blocker, PartsBox opt-in at Project save. */
const { useState: useCF } = React;

function CFField({ label, required, error, hint, children }) {
  return (
    <label className="field" style={{ marginBottom: 12 }}>
      <span className="fl">{label}{required && <span style={{ color: 'var(--danger)' }}> *</span>}{hint && <span className="muted" style={{ fontWeight: 400 }}> — {hint}</span>}</span>
      {children}
      {error && <span className="caption" style={{ color: 'var(--danger)', marginTop: 3 }}>{error}</span>}
    </label>
  );
}

/* ============================================================
   Create Program
   ============================================================ */
function CreateProgramModal({ onClose, go }) {
  const programs = useStore(s => s.programs || []);
  const users = useStore(s => s.users.filter(u => u.active && (u.roles || []).includes('designer')));
  const me = useStore(s => s.users.find(u => u.id === s.currentUserId));
  const defaultOwner = (me && (me.roles || []).includes('designer')) ? me.name : (users[0] && users[0].name) || (me && me.name) || '';

  const [identifier, setIdentifier] = useCF('');
  const [name, setName] = useCF('');
  const [owner, setOwner] = useCF(defaultOwner);
  const [customer, setCustomer] = useCF('');
  const [description, setDescription] = useCF('');

  const idfTrim = identifier.trim(), nameTrim = name.trim();
  const idfDup = idfTrim && programs.some(p => (p.identifier || p.code || '').toLowerCase() === idfTrim.toLowerCase());
  const nameDup = nameTrim && programs.some(p => p.name.toLowerCase() === nameTrim.toLowerCase());
  const idfError = !idfTrim ? null : idfDup ? 'A Program with this identifier already exists.' : null;
  const nameError = !nameTrim ? null : nameDup ? 'A Program with this name already exists.' : null;
  const valid = idfTrim && nameTrim && !idfDup && !nameDup && owner;

  const [busy, setBusy] = useCF(false);

  /* Same unawaited-async bug as Create Project: createProgram returns a Promise,
     which stringified into the redirect as #/programs/[object Promise]. */
  const submit = async () => {
    if (!valid || busy) return;
    setBusy(true);
    try {
      const id = await storeActions.createProgram({ identifier: idfTrim, name: nameTrim, owner, customer, description, tags: [] });
      if (!id) { window.__toast?.('Could not create the Program — please try again.', 'alert'); return; }
      onClose();
      go({ screen: 'programDetail', id });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-wrap"><div className="scrim" onClick={onClose} />
      <div className="modal" style={{ width: 560, position: 'relative', zIndex: 95 }}>
        <div className="modal-head"><div className="mh-title" style={{ display: 'flex', alignItems: 'center', gap: 9 }}><Icon name="folder" size={18} />New Program</div></div>
        <div className="modal-body">
          <p className="secondary" style={{ marginTop: 0 }}>A Program is the top of the hierarchy — it groups the Projects, Collections, and BOMs of one contract or product line.</p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 12 }}>
            <CFField label="Identifier" required error={idfError} hint="short, e.g. TVCA">
              <input className="input mono" value={identifier} onChange={e => setIdentifier(e.target.value)} autoFocus placeholder="TVCA" />
            </CFField>
            <CFField label="Name" required error={nameError}>
              <input className="input" value={name} onChange={e => setName(e.target.value)} placeholder="Terra Voyager Control Assembly" />
            </CFField>
          </div>
          <CFField label="Owner" required>
            <select className="select" value={owner} onChange={e => setOwner(e.target.value)}>
              {users.map(u => <option key={u.id} value={u.name}>{u.name}</option>)}
              {!users.some(u => u.name === owner) && owner && <option value={owner}>{owner}</option>}
            </select>
          </CFField>
          <CFField label="Customer" hint="external customer, or blank for internal R&D">
            <input className="input" value={customer} onChange={e => setCustomer(e.target.value)} placeholder="Customer X" />
          </CFField>
          <CFField label="Description">
            <textarea className="textarea" value={description} onChange={e => setDescription(e.target.value)} placeholder="What this Program covers…" />
          </CFField>
        </div>
        <div className="modal-foot">
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={!valid || busy} onClick={submit}><Icon name="plus" size={15} />{busy ? 'Creating…' : 'Create Program'}</button>
        </div>
      </div>
    </div>
  );
}

/* ============================================================
   Create Project — requires a Program parent
   ============================================================ */
function CreateProjectModal({ onClose, go, onNeedProgram }) {
  const programs = useStore(s => s.programs || []);
  const projects = useStore(s => s.projects);
  const users = useStore(s => s.users.filter(u => u.active && (u.roles || []).includes('production')));
  const me = useStore(s => s.users.find(u => u.id === s.currentUserId));
  const defaultLead = (me && (me.roles || []).includes('production')) ? me.name : (users[0] && users[0].name) || (me && me.name) || '';

  const [identifier, setIdentifier] = useCF('');
  const [name, setName] = useCF('');
  const [lead, setLead] = useCF(defaultLead);
  const [programId, setProgramId] = useCF(programs[0] ? programs[0].id : '');
  const [description, setDescription] = useCF('');
  const [partsBoxNow, setPartsBoxNow] = useCF(true);

  const idfTrim = identifier.trim(), nameTrim = name.trim();
  const nameDup = nameTrim && Object.values(projects).some(p => p.name.toLowerCase() === nameTrim.toLowerCase());
  const nameError = !nameTrim ? null : nameDup ? 'A Project with this name already exists.' : null;
  const valid = idfTrim && nameTrim && !nameDup && programId && lead;

  const [busy, setBusy] = useCF(false);

  /* createProject is async. It was called WITHOUT await, so `id` was a Promise
     and the redirect became #/projects/[object Promise] -> "PCB Project not
     found". The project itself had been created correctly all along; only the
     redirect key was wrong. Await the real id, and don't navigate on failure. */
  const submit = async () => {
    if (!valid || busy) return;
    setBusy(true);
    try {
      const id = await storeActions.createProject({
        identifier: idfTrim, name: nameTrim, lead, program_id: programId,
        description, createPartsBoxNow: partsBoxNow,
      });
      if (!id) { window.__toast?.('Could not create the PCB Project — please try again.', 'alert'); return; }
      onClose();
      go({ screen: 'projectDetail', id });
    } finally {
      setBusy(false);
    }
  };

  if (programs.length === 0) {
    return (
      <div className="modal-wrap"><div className="scrim" onClick={onClose} />
        <div className="modal" style={{ width: 460, position: 'relative', zIndex: 95 }}>
          <div className="modal-head"><div className="mh-title" style={{ display: 'flex', alignItems: 'center', gap: 9 }}><Icon name="folder" size={18} />New Project</div></div>
          <div className="modal-body" style={{ textAlign: 'center', padding: '28px 20px' }}>
            <Icon name="folder" size={34} style={{ color: 'var(--text-muted)' }} />
            <div style={{ fontWeight: 700, fontSize: 16, marginTop: 12 }}>You need to create a Program first.</div>
            <div className="secondary" style={{ marginTop: 6 }}>Every Project belongs to a Program. Create one, then come back to add Projects under it.</div>
          </div>
          <div className="modal-foot">
            <button className="btn" onClick={onClose}>Cancel</button>
            <button className="btn primary" onClick={() => { onClose(); onNeedProgram && onNeedProgram(); }}><Icon name="plus" size={15} />Create Program</button>
          </div>
        </div>
      </div>
    );
  }

  const parentProg = programs.find(p => p.id === programId);
  const derivedRef = parentProg ? `${parentProg.identifier || parentProg.code}-${idfTrim || '…'}` : '';

  return (
    <div className="modal-wrap"><div className="scrim" onClick={onClose} />
      <div className="modal" style={{ width: 560, position: 'relative', zIndex: 95 }}>
        <div className="modal-head"><div className="mh-title" style={{ display: 'flex', alignItems: 'center', gap: 9 }}><Icon name="folder" size={18} />New Project</div></div>
        <div className="modal-body">
          <CFField label="Program" required hint="every Project belongs to one">
            <select className="select" value={programId} onChange={e => setProgramId(e.target.value)}>
              {programs.map(p => <option key={p.id} value={p.id}>{(p.identifier || p.code)} · {p.name}</option>)}
            </select>
          </CFField>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 12 }}>
            <CFField label="Identifier" required hint="short, e.g. R2">
              <input className="input mono" value={identifier} onChange={e => setIdentifier(e.target.value)} autoFocus placeholder="R2" />
            </CFField>
            <CFField label="Name" required error={nameError}>
              <input className="input" value={name} onChange={e => setName(e.target.value)} placeholder="TVCA Rev 2" />
            </CFField>
          </div>
          {idfTrim && <div className="caption" style={{ margin: '-4px 0 12px' }}>Reference: <span className="mono" style={{ fontWeight: 700 }}>{derivedRef}</span></div>}
          <CFField label="Lead" required>
            <select className="select" value={lead} onChange={e => setLead(e.target.value)}>
              {users.map(u => <option key={u.id} value={u.name}>{u.name}</option>)}
              {!users.some(u => u.name === lead) && lead && <option value={lead}>{lead}</option>}
            </select>
          </CFField>
          <CFField label="Description">
            <textarea className="textarea" value={description} onChange={e => setDescription(e.target.value)} placeholder="What this Project builds…" />
          </CFField>
          <label style={{ display: 'flex', alignItems: 'flex-start', gap: 9, padding: '10px 12px', border: '1px solid var(--border-soft)', borderRadius: 8, background: 'var(--bg-raised)' }}>
            <input type="checkbox" checked={partsBoxNow} onChange={e => setPartsBoxNow(e.target.checked)} style={{ marginTop: 2 }} />
            <span><span style={{ fontWeight: 600 }}>Create PartsBox project + storage location now</span>
              <span className="caption" style={{ display: 'block' }}>Uncheck for a placeholder Project — you can create the PartsBox side later from the Project page.</span></span>
          </label>
        </div>
        <div className="modal-foot">
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={!valid || busy} onClick={submit}><Icon name="plus" size={15} />{busy ? 'Creating…' : 'Create Project'}</button>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { CreateProgramModal, CreateProjectModal });
