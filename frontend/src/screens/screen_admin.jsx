/* global React, Icon, StatusBadge, RoleTag, RoleDot, Banner, EmptyState, Avatar, Popover, NeedsAttention,
   useStore, storeActions, ROLE_META, CAPS, fmtUSD, fmtInt */
const { useState: useStateAdm, useRef: useRefAdm } = React;

/* v4 role model: the ONLY assignable login roles are Designer, Production and
   Admin (CLAUDE.md — "'purchasing' and 'development' strings should not appear
   in ALL_ROLES arrays used to render UI"). The permissions grid previously
   offered manager / executive / readonly / development, none of which are real
   roles in the platform. Development stays behind DEV_ROLE_ENABLED for the
   deferred reactivation path. */
const ALL_ROLES_FULL = ['designer', 'production', 'development', 'admin'];
const ALL_ROLES = ALL_ROLES_FULL.filter(r => r !== 'development' || window.DEV_ROLE_ENABLED);
const CAP_GROUPS_FULL = window.CAP_CATALOG;
/* Hide the Development capability group from the user-permission grid in MVP. */
const CAP_GROUPS = window.DEV_ROLE_ENABLED ? CAP_GROUPS_FULL : CAP_GROUPS_FULL.filter(g => g.group !== 'Development');

function StatusDot({ state }) {
  const c = { green: 'var(--success)', amber: 'var(--warning)', red: 'var(--danger)' }[state];
  return <span className="dot" style={{ background: c, width: 9, height: 9, boxShadow: `0 0 0 3px ${c}22` }} />;
}

/* ---- Admin Dashboard ---- */
function AdminDashboard({ go, flashId }) {
  const users = useStore(s => s.users) || [];
  const system = useStore(s => s.system);
  const audit = useStore(s => s.audit) || [];
  const [override, setOverride] = useStateAdm(false);
  // Every one of these was an unguarded read. A user with no `roles` array (the
  // directory serializer omits roles for non-Admin records, and inert seed users
  // can legitimately have none) threw "Cannot read properties of undefined
  // (reading 'length')" inside the reduce below and blanked the whole app.
  const systemStatus = (system && system.status) || [];
  const active = users.filter(u => u && u.active).length;
  const warn = systemStatus.filter(s => s.state !== 'green').length;
  const roleAssignments = users.reduce((a, u) => a + ((u && u.roles) ? u.roles.length : 0), 0);

  return (
    <div className="page page-wide">
      <div className="page-head">
        <div className="ph-titles"><div className="display">Administration</div>
          <div className="ph-sub">Users, roles, permissions, suppliers, and system health. You own system recovery and configuration.</div></div>
        <div className="ph-actions"><button className="btn danger" onClick={() => setOverride(true)}><Icon name="alert" size={15} />Admin override</button></div>
      </div>

      <div className="na-mount" style={{ marginBottom: 18 }}><NeedsAttention role="admin" go={go} flashId={flashId} /></div>

      <div className="stat-row" style={{ marginBottom: 18 }}>
        <div className="stat"><div className="st-label"><Icon name="user" size={13} /> Active users</div><div className="st-num">{active}</div><div className="st-sub">of {users.length} total</div></div>
        <div className="stat"><div className="st-label"><Icon name="lock" size={13} /> Role assignments</div><div className="st-num">{roleAssignments}</div><div className="st-sub">across all users</div></div>
        <div className="stat"><div className="st-label"><StatusDot state={warn ? 'amber' : 'green'} /> System health</div><div className="st-num" style={{ color: warn ? 'var(--warning)' : 'var(--success)' }}>{warn ? `${warn} warning` : 'All green'}</div><div className="st-sub">{systemStatus.length} services</div></div>
        <div className="stat"><div className="st-label"><Icon name="history" size={13} /> Audit events today</div><div className="st-num">{audit.length}</div><div className="st-sub">logged</div></div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 18, alignItems: 'start' }}>
        <div className="panel">
          <div className="panel-head"><Icon name="chart" size={16} /><span className="ph-title">System status</span>
            <button className="btn-link" style={{ marginLeft: 'auto' }} onClick={() => go({ screen: 'a.configuration', tab: 'system' })}>Configuration</button></div>
          {systemStatus.map(s => (
            <div key={s.id} className="attn-item" style={{ padding: '11px 16px' }}>
              <StatusDot state={s.state} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600 }}>{s.label}</div>
                <div className="caption">{s.detail}</div>
              </div>
              {s.action === 'refresh-digikey' && (
                <button className="btn sm" onClick={() => window.__toast?.('DigiKey OAuth token refreshed — valid 24h', 'check')}><Icon name="refresh" size={13} />Refresh</button>
              )}
            </div>
          ))}
        </div>
        <div className="panel">
          <div className="panel-head"><Icon name="history" size={16} /><span className="ph-title">Recent activity</span>
            <button className="btn-link" style={{ marginLeft: 'auto' }} onClick={() => go({ screen: 'a.audit' })}>Full log</button></div>
          {audit.slice(0, 6).map(a => (
            <div key={a.id} className="attn-item" style={{ padding: '11px 16px' }}>
              <div className="attn-main"><div style={{ fontWeight: 600, fontSize: 13.5 }}>{a.action}</div>
                <div className="am-meta">{a.user} · <RoleTag role={a.role} /> · <span className="mono">{a.entity}</span> · {a.ts}</div></div>
            </div>
          ))}
        </div>
      </div>
      {override && <AdminOverrideModal onClose={() => setOverride(false)} />}
    </div>
  );
}

function AdminOverrideModal({ onClose }) {
  const [entity, setEntity] = useStateAdm('');
  const [target, setTarget] = useStateAdm('');
  const [reason, setReason] = useStateAdm('');
  const [confirm, setConfirm] = useStateAdm(false);
  const ok = entity.trim() && target.trim() && reason.trim().length >= 10 && confirm;
  return (
    <div className="modal-wrap"><div className="scrim" onClick={onClose} />
      <div className="modal" style={{ position: 'relative', zIndex: 95, borderTop: '4px solid var(--danger)' }}>
        <div className="modal-head"><div className="mh-title" style={{ display: 'flex', alignItems: 'center', gap: 9, color: 'var(--danger)' }}><Icon name="alert" size={19} />Admin override — exceptional action</div></div>
        <div className="modal-body">
          <Banner kind="danger" icon="alert" title="This bypasses normal workflow ownership">Overrides are logged permanently with your identity, a before/after state, and your reason. Use only for stuck jobs, departed users, or duplicate records.</Banner>
          <label className="field" style={{ marginTop: 10 }}><span className="fl">Object ID</span><input className="input mono" placeholder="e.g. BOM-052" value={entity} onChange={e => setEntity(e.target.value)} /></label>
          <label className="field" style={{ marginTop: 10 }}><span className="fl">Force state to</span><input className="input mono" placeholder="e.g. RESULTS" value={target} onChange={e => setTarget(e.target.value.toUpperCase())} /></label>
          <label className="field" style={{ marginTop: 10 }}><span className="fl">Reason (required, min 10 chars)</span><textarea className="textarea" value={reason} onChange={e => setReason(e.target.value)} placeholder="Why is this override necessary?" /></label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10, fontSize: 13 }}><input type="checkbox" checked={confirm} onChange={e => setConfirm(e.target.checked)} />I understand this is a logged, exceptional action.</label>
        </div>
        <div className="modal-foot"><button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn danger" disabled={!ok} onClick={() => { storeActions.adminOverride(entity.trim(), target.trim(), reason.trim()); onClose(); }}><Icon name="alert" size={15} />Override & log</button></div>
      </div>
    </div>
  );
}

/* ---- User Management ---- */
function UserManagement({ go }) {
  const users = useStore(s => s.users);
  const [edit, setEdit] = useStateAdm(null);
  const [invite, setInvite] = useStateAdm(false);
  return (
    <div className="page page-wide">
      <div className="page-head">
        <div className="ph-titles"><div className="display">Users</div><div className="ph-sub">Create and manage users. New users are Read-Only by default until you assign a role.</div></div>
        <div className="ph-actions"><button className="btn primary" onClick={() => setInvite(true)}><Icon name="plus" size={15} />Invite user</button></div>
      </div>
      <div className="tbl-wrap flow"><table className="bom">
        <thead><tr><th>User</th><th>Title</th><th>Roles</th><th>Overrides</th><th>Last active</th><th>Status</th><th></th></tr></thead>
        <tbody>{users.map((u, i) => (
          <tr key={u.id} className={i % 2 ? 'alt' : ''}>
            <td><div style={{ display: 'flex', alignItems: 'center', gap: 9 }}><Avatar name={u.name} role={u.roles[0] || 'readonly'} size={28} /><div><div style={{ fontWeight: 600 }}>{u.name}{u.intern && <span className="badge outlined" style={{ color: 'var(--warning)', marginLeft: 7 }}><Icon name="user" size={11} />INTERN</span>}</div><div className="caption mono">{u.email}</div></div></div></td>
            <td className="secondary">{u.title}</td>
            <td><div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>{u.roles.map(r => <RoleTag key={r} role={r} />)}</div></td>
            <td>{u.overrides && u.overrides.length ? <span className="badge filled" style={{ background: 'var(--warning)' }}><Icon name="sparkle" size={11} />+{u.overrides.length}</span> : <span className="muted">—</span>}</td>
            <td className="caption">{u.lastActive}</td>
            <td>{u.active ? <StatusBadge status="active-good" /> : <StatusBadge status="inactive" />}</td>
            <td style={{ textAlign: 'right' }}><div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
              <button className="btn sm" onClick={() => setEdit(u)}>Permissions</button>
              <button className="btn sm ghost" onClick={() => storeActions.toggleUserActive(u.id)}>{u.active ? 'Deactivate' : 'Activate'}</button>
            </div></td>
          </tr>
        ))}</tbody>
      </table></div>
      {edit && <EditRolesModal user={edit} onClose={() => setEdit(null)} />}
      {invite && <InviteModal onClose={() => setInvite(false)} />}
    </div>
  );
}

function EditRolesModal({ user, onClose }) {
  const [roles, setRoles] = useStateAdm([...user.roles]);
  const [overrides, setOverrides] = useStateAdm([...(user.overrides || [])]);
  const [tab, setTab] = useStateAdm('roles');
  const toggleRole = (r) => setRoles(rs => rs.includes(r) ? rs.filter(x => x !== r) : [...rs, r]);
  const toggleCap = (c) => setOverrides(os => os.includes(c) ? os.filter(x => x !== c) : [...os, c]);
  // capabilities the chosen roles already grant
  const baseCaps = new Set(); roles.forEach(r => (window.CAPS[r] || new Set()).forEach(c => baseCaps.add(c)));
  const effective = new Set([...baseCaps, ...overrides]);
  const overrideCount = overrides.filter(c => !baseCaps.has(c)).length;
  return (
    <div className="modal-wrap"><div className="scrim" onClick={onClose} />
      <div className="modal" style={{ position: 'relative', zIndex: 95, width: 720, maxWidth: '94vw' }}>
        <div className="modal-head"><div className="mh-title">Permissions — {user.name}</div>
          <div className="caption" style={{ marginTop: 4 }}>Base role grants the standard capability set. Per-user overrides add extra capabilities on top — for hybrid users without inventing a new role.</div></div>
        <div className="tabs" style={{ margin: '0 20px', borderBottom: '1px solid var(--border)' }}>
          {[['roles', `Base roles · ${roles.length}`], ['caps', `Capability overrides · ${overrideCount}`]].map(([k, l]) => (
            <div key={k} className={`tab${tab === k ? ' active' : ''}`} onClick={() => setTab(k)}>{l}</div>
          ))}
        </div>
        <div className="modal-body" style={{ maxHeight: '58vh', overflowY: 'auto' }}>
          {tab === 'roles' && (<>
            <p style={{ marginTop: 0 }} className="secondary">A user with no roles is Read-Only. Multiple roles enable the role switcher in their sidebar.</p>
            <div style={{ display: 'grid', gap: 6 }}>
              {ALL_ROLES.map(r => (
                <label key={r} className="role-row" style={{ borderColor: roles.includes(r) ? window.ROLE_META[r].color : 'var(--border-soft)', background: roles.includes(r) ? window.ROLE_META[r].color + '0e' : 'var(--bg-surface)' }}>
                  <input type="checkbox" checked={roles.includes(r)} onChange={() => toggleRole(r)} />
                  <RoleDot role={r} size={9} /><span style={{ fontWeight: 600, flex: 1 }}>{window.ROLE_META[r].label}</span>
                  <span className="caption">{window.ROLE_META[r].owns}</span>
                </label>
              ))}
            </div>
          </>)}
          {tab === 'caps' && (<>
            <p style={{ marginTop: 0 }} className="secondary">Capabilities granted by the user's base role are shown ticked and locked. Toggle additional capabilities below to grant them as user-level overrides.</p>
            {CAP_GROUPS.map(g => (
              <div key={g.group} className="cap-group">
                <div className="cap-group-label">{g.group}</div>
                {g.items.map(([cap, label]) => {
                  const inBase = baseCaps.has(cap);
                  const isOverride = overrides.includes(cap);
                  const on = inBase || isOverride;
                  return (
                    <label key={cap} className={`cap-row${inBase ? ' base' : ''}${isOverride && !inBase ? ' override' : ''}`}>
                      <input type="checkbox" checked={on} disabled={inBase} onChange={() => toggleCap(cap)} />
                      <span style={{ fontWeight: 500, flex: 1 }}>{label}</span>
                      {inBase ? <span className="caption" style={{ fontWeight: 600 }}>From base role</span>
                        : isOverride ? <span className="badge filled" style={{ background: 'var(--warning)' }}><Icon name="sparkle" size={11} />OVERRIDE — NOT IN BASE</span>
                          : <span className="caption">—</span>}
                    </label>
                  );
                })}
              </div>
            ))}
          </>)}
        </div>
        <div className="modal-foot">
          <span className="caption" style={{ marginRight: 'auto' }}>{effective.size} capabilities effective ({roles.length} role{roles.length !== 1 ? 's' : ''} + {overrideCount} override{overrideCount !== 1 ? 's' : ''})</span>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn primary" onClick={() => {
            const newRoles = roles.length ? roles : ['readonly'];
            storeActions.setUserRoles(user.id, newRoles);
            const newCaps = new Set(); newRoles.forEach(r => (window.CAPS[r] || new Set()).forEach(c => newCaps.add(c)));
            const trimmedOverrides = overrides.filter(c => !newCaps.has(c));
            storeActions.setUserOverrides(user.id, trimmedOverrides);
            onClose();
          }}>Save</button>
        </div>
      </div>
    </div>
  );
}

function InviteModal({ onClose }) {
  const [name, setName] = useStateAdm(''); const [email, setEmail] = useStateAdm(''); const [roles, setRoles] = useStateAdm([]);
  const toggle = (r) => setRoles(rs => rs.includes(r) ? rs.filter(x => x !== r) : [...rs, r]);
  return (
    <div className="modal-wrap"><div className="scrim" onClick={onClose} />
      <div className="modal" style={{ position: 'relative', zIndex: 95 }}>
        <div className="modal-head"><div className="mh-title">Invite user</div></div>
        <div className="modal-body">
          <label className="field" style={{ marginBottom: 10 }}><span className="fl">Name</span><input className="input" value={name} onChange={e => setName(e.target.value)} placeholder="Full name" /></label>
          <label className="field" style={{ marginBottom: 10 }}><span className="fl">Email</span><input className="input mono" value={email} onChange={e => setEmail(e.target.value)} placeholder="name@yanktech.com" /></label>
          <div className="field"><span className="fl">Roles <span className="muted">(leave empty for Read-Only)</span></span>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>{ALL_ROLES.filter(r => r !== 'admin').map(r => (
              <button key={r} className={`fchip${roles.includes(r) ? ' active' : ''}`} onClick={() => toggle(r)}><RoleDot role={r} size={7} />{ROLE_META[r].label}</button>
            ))}</div></div>
        </div>
        <div className="modal-foot"><button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={!name.trim() || !email.trim()} onClick={() => { storeActions.inviteUser({ name: name.trim(), email: email.trim(), roles }); onClose(); }}>Send invite</button></div>
      </div>
    </div>
  );
}

/* ---- Roles & Permissions matrix ---- */
function RolesPermissions() {
  return (
    <div className="page page-wide">
      <div className="page-head"><div className="ph-titles"><div className="display">Roles & Permissions</div>
        <div className="ph-sub">The permission matrix that drives the production app. The prototype role switcher only previews these — in production, access follows this matrix.</div></div></div>
      <Banner kind="info" icon="info" title="Read-only by default, separated from visibility">
        Every user can view project context. Actions are granted by role. A user with no role can see but not act. Visibility and edit rights are always separate.
      </Banner>
      <div className="tbl-wrap flow" style={{ marginTop: 6 }}><table className="bom">
        <thead><tr><th style={{ minWidth: 200 }}>Capability</th>{ALL_ROLES.map(r => <th key={r} style={{ textAlign: 'center' }}><div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3 }}><RoleDot role={r} size={8} /><span style={{ fontSize: 10.5 }}>{ROLE_META[r].label}</span></div></th>)}</tr></thead>
        <tbody>
          {CAP_GROUPS.map(g => (
            <React.Fragment key={g.group}>
              <tr><td colSpan={ALL_ROLES.length + 1} style={{ background: 'var(--bg-overlay)', fontWeight: 700, fontSize: 11.5, textTransform: 'uppercase', letterSpacing: '.04em', color: 'var(--text-secondary)' }}>{g.group}</td></tr>
              {g.items.map(([cap, label]) => (
                <tr key={cap}>
                  <td>{label}</td>
                  {ALL_ROLES.map(r => {
                    const allowed = r === 'admin' ? cap.startsWith('admin') || cap === 'comment' : window.CAPS[r] && window.CAPS[r].has(cap);
                    const yes = r === 'admin' ? cap.startsWith('admin') || cap === 'comment' : !!allowed;
                    return <td key={r} style={{ textAlign: 'center' }}>{yes ? <Icon name="check" size={15} style={{ color: 'var(--success)' }} /> : <span style={{ color: 'var(--border)' }}>—</span>}</td>;
                  })}
                </tr>
              ))}
            </React.Fragment>
          ))}
        </tbody>
      </table></div>
      <div className="caption" style={{ marginTop: 10 }}>Admin holds all administrative capabilities and can override workflow state with a logged reason. Interns see “Request Supervisor Approval” in place of submit actions.</div>
    </div>
  );
}

/* ---- Workflow Config ---- */
function ConfigRow({ label, sub, children }) {
  return <div className="cfg-row"><div><div style={{ fontWeight: 600, fontSize: 13.5 }}>{label}</div><div className="caption">{sub}</div></div><div className="cfg-ctl">{children}</div></div>;
}
function Toggle({ on, onChange, locked }) {
  return <button className={`toggle${on ? ' on' : ''}${locked ? ' locked' : ''}`} disabled={locked} onClick={() => !locked && onChange(!on)}><span className="toggle-knob" /></button>;
}
function WorkflowConfig() {
  const wf = useStore(s => s.system.workflow);
  return (
    <div className="page">
      <div className="page-head"><div className="ph-titles"><div className="display">Workflow Configuration</div>
        <div className="ph-sub">Rules that govern how work moves between departments.</div></div></div>
      <div className="card">
        <ConfigRow label="Max exception loops" sub="Escalate after this many Production ↔ Designer cycles"><input className="input" style={{ width: 80 }} type="number" value={wf.maxExceptionLoops} onChange={e => storeActions.setConfig('workflow.maxExceptionLoops', +e.target.value)} /></ConfigRow>
        <ConfigRow label="Stale sourcing threshold" sub="Flag supplier data older than this (hours)"><input className="input" style={{ width: 80 }} type="number" value={wf.staleThresholdHours} onChange={e => storeActions.setConfig('workflow.staleThresholdHours', +e.target.value)} /></ConfigRow>
        <ConfigRow label="Overdue request threshold" sub="Mark purchasing inbox items overdue after (hours)"><input className="input" style={{ width: 80 }} type="number" value={wf.overdueHours} onChange={e => storeActions.setConfig('workflow.overdueHours', +e.target.value)} /></ConfigRow>
        <ConfigRow label="Require budget code on requests" sub="Block submission without a project budget code"><Toggle on={wf.requireBudgetCode} onChange={v => storeActions.setConfig('workflow.requireBudgetCode', v)} /></ConfigRow>
        <ConfigRow label="Mouser-first sourcing" sub="Prefer Mouser, fall back to DigiKey"><Toggle on={wf.mouserFirst} onChange={v => storeActions.setConfig('workflow.mouserFirst', v)} /></ConfigRow>
        <ConfigRow label="Automated order placement" sub="Permanently disabled — AutoBOM never places orders automatically"><Toggle on={false} locked onChange={() => {}} /></ConfigRow>
      </div>
      <div className="caption" style={{ marginTop: 10, display: 'flex', gap: 6, alignItems: 'center' }}><Icon name="lock" size={13} />Automated ordering is a permanent MVP constraint and cannot be enabled here.</div>
    </div>
  );
}

/* ---- Suppliers ---- */
function SupplierConfig() {
  const suppliers = useStore(s => s.suppliers);
  return (
    <div className="page">
      <div className="page-head"><div className="ph-titles"><div className="display">Suppliers</div>
        <div className="ph-sub">Manage supplier integrations and sourcing priority. The sourcing engine supports adding suppliers without redesign.</div></div></div>
      <div style={{ display: 'grid', gap: 12 }}>
        {suppliers.map(s => (
          <div key={s.id} className="card" style={{ padding: 16, display: 'flex', alignItems: 'center', gap: 16 }}>
            <span className="tag" style={{ background: s.color, color: '#fff', height: 24, fontSize: 12 }}>{s.name.toUpperCase()}</span>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><span style={{ fontWeight: 600 }}>{s.name}</span><StatusBadge status={s.api === 'connected' ? 'active-good' : 'inactive'} /></div>
              {/* `apiKey` / `lastSync` are not fields the API returns, so these
                  rendered as dangling "key" / "last sync" labels with nothing
                  after them. Credentials are never surfaced in the UI at all
                  (they stay server-side); the rest renders only when present. */}
              <div className="caption" style={{ marginTop: 3 }}>
                Priority {s.priority}{s.mode ? ` · ${s.mode}` : ''}
                {s.api ? ` · ${s.api === 'connected' ? 'credentials configured' : s.api}` : ''}
                {s.lastSync ? ` · last sync ${s.lastSync}` : ''}
              </div>
            </div>
            <Toggle on={s.enabled} onChange={() => storeActions.toggleSupplier(s.id)} />
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---- System Settings ---- */
function SystemSettings() {
  const st = useStore(s => s.system.settings);
  const batch = useStore(s => s.system.batch);
  return (
    <div className="page">
      <div className="page-head"><div className="ph-titles"><div className="display">System Settings</div><div className="ph-sub">Account, session, and purchasing-batch policy.</div></div></div>

      {/* Purchasing bucket batch cadences — both Admin-configurable, never hard-coded (v2). */}
      <div className="h2" style={{ margin: '4px 0 8px' }}>Purchasing batch timers</div>
      <div className="card" style={{ marginBottom: 20 }}>
        <ConfigRow label="Critical bucket interval" sub={`How often Critical requests batch to the Daily Purchasing List · currently every ${Math.round(batch.critical.intervalMin / 60 * 10) / 10}h`}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input className="input" style={{ width: 90 }} type="number" min="5" step="5" value={batch.critical.intervalMin} onChange={e => storeActions.setBatchInterval('critical', +e.target.value)} />
            <span className="caption">min</span>
            <button className="btn sm ghost" onClick={() => storeActions.flushBucket('critical')} title="Manual escape hatch — run the batch now"><Icon name="refresh" size={13} />Flush now</button>
          </div>
        </ConfigRow>
        <ConfigRow label="Main bucket interval" sub={`How often Main requests batch to the Daily Purchasing List · currently every ${Math.round(batch.main.intervalMin / 60 * 10) / 10}h`}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input className="input" style={{ width: 90 }} type="number" min="5" step="5" value={batch.main.intervalMin} onChange={e => storeActions.setBatchInterval('main', +e.target.value)} />
            <span className="caption">min</span>
            <button className="btn sm ghost" onClick={() => storeActions.flushBucket('main')} title="Manual escape hatch — run the batch now"><Icon name="refresh" size={13} />Flush now</button>
          </div>
        </ConfigRow>
        <div className="cfg-row" style={{ color: 'var(--text-muted)' }}><Icon name="info" size={14} /><span className="caption">Writes are atomic — a batch completes fully or rolls back, never interleaves, and never leaves a half-written row on the sheet. A failed batch surfaces to the Admin Dashboard and retries on the next run.</span></div>
      </div>

      <div className="h2" style={{ margin: '4px 0 8px' }}>Account & session</div>
      <div className="card">
        <ConfigRow label="Session timeout" sub="Auto sign-out after inactivity (minutes)"><input className="input" style={{ width: 80 }} type="number" value={st.sessionTimeoutMin} onChange={e => storeActions.setConfig('settings.sessionTimeoutMin', +e.target.value)} /></ConfigRow>
        <ConfigRow label="Default role for new users" sub="New accounts start with this role"><span className="badge outlined" style={{ color: 'var(--text-muted)' }}><Icon name="user" size={11} />READ-ONLY</span></ConfigRow>
        <ConfigRow label="Require supervisor approval for interns" sub="Interns request approval instead of submitting directly"><Toggle on={st.requireSupervisorForInterns} onChange={v => storeActions.setConfig('settings.requireSupervisorForInterns', v)} /></ConfigRow>
        <ConfigRow label="Multi-factor authentication" sub="Coming soon"><Toggle on={false} locked onChange={() => {}} /></ConfigRow>
      </div>
    </div>
  );
}

/* ---- Audit Log ---- */
function AuditLog() {
  const audit = useStore(s => s.audit);
  const [q, setQ] = useStateAdm('');
  const rows = q.trim() ? audit.filter(a => (a.action + a.user + a.entity).toLowerCase().includes(q.toLowerCase())) : audit;
  return (
    <div className="page page-wide">
      <div className="page-head"><div className="ph-titles"><div className="display">Audit Log</div><div className="ph-sub">Every workflow transition and admin action — permanent, with before/after state.</div></div>
        <div className="ph-actions"><div className="searchfield" style={{ minWidth: 240 }}><Icon name="search" size={15} style={{ color: 'var(--text-muted)' }} /><input value={q} placeholder="Filter audit events…" onChange={e => setQ(e.target.value)} /></div></div></div>
      <div className="tbl-wrap flow">{rows.length === 0 ? <EmptyState icon="history" title="No history yet." />
        : <table className="bom"><thead><tr><th>When</th><th>User</th><th>Role</th><th>Action</th><th>Entity</th><th>Before</th><th>After</th></tr></thead>
          <tbody>{rows.map((a, i) => (
            <tr key={a.id} className={i % 2 ? 'alt' : ''}>
              <td className="caption" style={{ whiteSpace: 'nowrap' }}>{a.ts}</td><td>{a.user}</td><td><RoleTag role={a.role} /></td>
              <td style={{ fontWeight: a.action.includes('OVERRIDE') ? 700 : 400, color: a.action.includes('OVERRIDE') ? 'var(--danger)' : undefined }}>{a.action}</td>
              <td className="mono caption">{a.entity}</td><td className="mono caption">{a.before}</td><td className="mono caption" style={{ fontWeight: 600 }}>{a.after}</td>
            </tr>
          ))}</tbody></table>}</div>
    </div>
  );
}

/* ---- Configuration (v4) ----
   Single tabbed screen consolidating the four former Admin sub-screens
   (Roles & Permissions, Workflow, Suppliers, System Settings) plus a
   Decision Traces tab (runtime observability — full build in a later layer).
   Tab rides in ?tab=; sub-screens render as panels. */
function DecisionTracesStub() {
  return (
    <div className="page">
      <div className="page-head"><div className="ph-titles"><div className="display">Decision Traces</div>
        <div className="ph-sub">Runtime observability — structured decision traces on every decision-engine invocation, plus dry-run mode against real inputs.</div></div></div>
      <Banner kind="info" icon="info" title="Arrives in a later layer">
        Decision-trace capture and dry-run observability are part of the Bounded-Admin runtime-observability build. This tab is reserved so the Configuration structure matches the platform spec; the trace viewer is not wired up in this baseline.
      </Banner>
    </div>
  );
}

function AdminConfiguration({ tab, go }) {
  const cur = tab || 'roles';
  const TABS = [['roles', 'Roles & Permissions'], ['workflow', 'Workflow'], ['suppliers', 'Suppliers'], ['system', 'System Settings'], ['traces', 'Decision Traces']];
  const panel = cur === 'workflow' ? <WorkflowConfig />
    : cur === 'suppliers' ? <SupplierConfig />
    : cur === 'system' ? <SystemSettings />
    : cur === 'traces' ? <DecisionTracesStub />
    : <RolesPermissions />;
  return (
    <>
      <div style={{ padding: '14px 0 0' }}>
        <div className="tabs">
          {TABS.map(([k, l]) => (
            <div key={k} className={`tab${cur === k ? ' active' : ''}`} onClick={() => go({ screen: 'a.configuration', tab: k })}>{l}</div>
          ))}
        </div>
      </div>
      {panel}
    </>
  );
}

/* ---- Force-Waivers log (v4) ----
   Audit entries filtered to force-waive / override actions. Bounded Admin Authority:
   every waiver of a workflow gate is logged with actor, reason, before/after, timestamp. */
function ForceWaiversLog({ go }) {
  const audit = useStore(s => s.audit);
  const rows = audit.filter(a => /waiv|override|force[- ]?waive/i.test(a.action));
  return (
    <div className="page page-wide">
      <div className="page-head"><div className="ph-titles"><div className="display">Force-Waivers Log</div>
        <div className="ph-sub">Every override of a workflow gate — Run-Build waivers and admin overrides — with actor, reason, and before/after state. Permanent.</div></div></div>
      <Banner kind="info" icon="lock" title="Bounded Admin Authority">
        Force-waives bypass a workflow block (for example, running a Build while a Push-Back is unresolved). Each requires a reason and is recorded here for review.
      </Banner>
      <div className="tbl-wrap flow" style={{ marginTop: 6 }}>{rows.length === 0 ? <EmptyState icon="unlock" title="No force-waivers logged." sub="When an Admin waives a workflow gate, it appears here with the reason and affected object." />
        : <table className="bom"><thead><tr><th>When</th><th>Actor</th><th>Role</th><th>Action / reason</th><th>Entity</th><th>Before</th><th>After</th></tr></thead>
          <tbody>{rows.map((a, i) => (
            <tr key={a.id} className={i % 2 ? 'alt' : ''}>
              <td className="caption" style={{ whiteSpace: 'nowrap' }}>{a.ts}</td><td>{a.user}</td><td><RoleTag role={a.role} /></td>
              <td style={{ fontWeight: 600, color: 'var(--danger)' }}>{a.action}</td>
              <td className="mono caption">{a.entity}</td><td className="mono caption">{a.before}</td><td className="mono caption" style={{ fontWeight: 600 }}>{a.after}</td>
            </tr>
          ))}</tbody></table>}</div>
    </div>
  );
}

Object.assign(window, { AdminDashboard, UserManagement, RolesPermissions, WorkflowConfig, SupplierConfig, SystemSettings, AuditLog, AdminConfiguration, ForceWaiversLog });
