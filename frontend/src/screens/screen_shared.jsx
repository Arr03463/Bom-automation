/* global React, Icon, StatusBadge, RoleTag, RoleDot, Avatar, Banner, EmptyState,
   useStore, storeActions, ROLE_META, PROJECTS, fmtUSD, fmtInt */
const { useState: useStateShared } = React;

/* ---- Projects List ---- */
function ProjectsScreen({ go }) {
  const projects = useStore(s => s.projects);
  const programs = useStore(s => s.programs || []);
  const boms = useStore(s => s.boms);
  const [modal, setModal] = useStateShared(null); // 'project' | 'program'
  const list = Object.values(projects);
  const progOf = (pid) => programs.find(p => p.id === pid);
  return (
    <div className="page">
      <div className="page-head"><div className="ph-titles"><div className="display">PCB Projects</div>
        <div className="ph-sub">Shared across all roles. Each PCB project rolls up its BOMs. Collections live under Programs.</div></div>
        <div className="ph-actions"><button className="btn primary" onClick={() => setModal('project')}><Icon name="plus" size={15} />New PCB Project</button></div></div>
      <div className="list">
        {list.map(p => {
          const bms = boms.filter(b => b.project === p.id && b.state !== 'draft').length;
          const prog = progOf(p.program_id);
          const ref = prog ? `${prog.identifier || prog.code}-${p.identifier || ''}` : (p.identifier || '');
          return (
            <div key={p.id} className="lrow" onClick={() => go({ screen: 'projectDetail', id: p.id })}>
              <div style={{ minWidth: 0 }}>
                <div className="lr-title"><Icon name="folder" size={16} style={{ color: 'var(--text-muted)' }} />{ref && <span className="mono caption" style={{ fontWeight: 700 }}>{ref}</span>}{p.name}</div>
                <div className="lr-meta"><span>Lead: {p.lead}</span><span className="tr-sep" /><span>{p.desc}</span></div>
              </div>
              <div className="lr-right"><div className="lr-stats"><span>{bms ? '1 BOM' : 'No BOM'}</span></div></div>
            </div>
          );
        })}
      </div>
      {modal === 'project' && <window.CreateProjectModal go={go} onClose={() => setModal(null)} onNeedProgram={() => setModal('program')} />}
      {modal === 'program' && <window.CreateProgramModal go={go} onClose={() => setModal(null)} />}
    </div>
  );
}

/* ---- Project Detail (tabs) ---- */
function ProjectDetailScreen({ id, go, tab }) {
  const p = useStore(s => s.projects[id]);
  const isProd = useStore(s => s.activeRole === 'production');
  const boms = useStore(s => s.boms.filter(b => b.project === id && b.state !== 'draft'));
  const audit = useStore(s => s.audit);
  const curTab = tab || 'boms';
  const setTab = (t) => go({ screen: 'projectDetail', id, tab: t });
  if (!p) return <div className="page"><EmptyState icon="folder" title="PCB Project not found." /></div>;

  return (
    <div className="page page-wide">
      <div className="page-head" style={{ marginBottom: 6 }}><div className="ph-titles">
        <button className="btn-link" style={{ marginBottom: 8 }} onClick={() => go({ screen: 'projects' })}>← PCB Projects</button>
        <div className="h1">{p.name}</div><div className="ph-sub">{p.desc} · Lead: {p.lead} · Created {window.fmtWhen(p.created)}</div></div></div>
      {p.partsbox && !p.partsbox.created && (
        <div className="card" style={{ padding: '11px 14px', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 12, background: 'var(--bg-raised)', border: '1px solid var(--border-soft)' }}>
          <Icon name="box" size={16} style={{ color: p.partsbox.pending ? 'var(--danger)' : 'var(--text-muted)' }} />
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 600, fontSize: 13.5 }}>{p.partsbox.pending ? 'PartsBox creation is pending' : "This Project isn't tracked in PartsBox yet."}</div>
            <div className="caption">{p.partsbox.pending ? 'The last attempt failed — retry to create the PartsBox project + storage location.' : 'Create a PartsBox project + storage location to track inventory for this Project.'}</div>
          </div>
          <button className="btn sm primary" onClick={() => storeActions.createProjectPartsBox(id)}><Icon name={p.partsbox.pending ? 'refresh' : 'plus'} size={13} />{p.partsbox.pending ? 'Retry' : 'Create PartsBox project'}</button>
        </div>
      )}
      <div className="tabs">
        {[['boms', 'BOM'], ['activity', 'Activity']].map(([k, l]) => (
          <div key={k} className={`tab${curTab === k ? ' active' : ''}`} onClick={() => setTab(k)}>{l}</div>
        ))}
      </div>
      {curTab === 'boms' && (boms.length ? <div className="list">{boms.map(b => {
        const m = window.bomMeta ? window.bomMeta(b) : { lines: b.items.length, exceptions: 0, total: 0 };
        return (
        <div key={b.id} className="lrow" onClick={() => go({ screen: 'p.bomOverview', id: b.id })} style={m.exceptions > 0 ? { boxShadow: 'inset 3px 0 0 var(--danger)' } : undefined}>
          <div style={{ minWidth: 0 }}><div className="lr-title">{b.name}<StatusBadge status={window.BOM_BADGE[b.state]} /></div>
            <div className="lr-meta"><span className="mono">{b.id}</span><span className="tr-sep" /><span>build {window.fmtInt(b.buildQty)} +{b.overage}%</span><span className="tr-sep" /><span>{m.lines} lines</span>
              {m.exceptions > 0 && <><span className="tr-sep" /><span style={{ color: 'var(--danger)', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: 4 }}><Icon name="alert" size={12} />{m.exceptions} exceptions</span></>}</div></div>
          <div className="lr-right"><div className="lr-stats"><span>updated {b.updated}</span>{m.total > 0 && <span>est. <b className="mono">{window.fmtUSD(m.total)}</b></span>}</div><Icon name="chevright" size={16} style={{ color: 'var(--text-muted)' }} /></div>
        </div>); })}</div>
      : <EmptyState icon="boms" title="No BOM for this PCB yet." sub="Each PCB Project holds exactly one BOM. Upload it to start validation and sourcing."
          actions={isProd ? <button className="btn primary" onClick={() => go({ screen: 'p.upload', project: id })}><Icon name="upload" size={15} />Upload BOM</button> : null} />)}
      {curTab === 'activity' && <div className="tbl-wrap flow"><table className="bom"><thead><tr><th>When</th><th>User</th><th>Action</th><th>Entity</th></tr></thead>
        <tbody>{audit.slice(0, 10).map((a, i) => <tr key={a.id} className={i % 2 ? 'alt' : ''}><td className="caption">{a.ts}</td><td>{a.user}</td><td>{a.action}</td><td className="mono caption">{a.entity}</td></tr>)}</tbody></table></div>}
    </div>
  );
}

/* ---- Account Settings ---- */
function AccountSettings() {
  const user = useStore(s => s.users.find(u => u.id === s.currentUserId));
  const role = useStore(s => s.activeRole);
  return (
    <div className="page">
      <div className="page-head"><div className="ph-titles"><div className="display">Account Settings</div></div></div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 18, alignItems: 'start', maxWidth: 880 }}>
        <div className="card" style={{ padding: 18 }}>
          <div className="h2" style={{ marginBottom: 14 }}>Profile</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}><Avatar name={user.name} role={role} size={48} /><div><div style={{ fontWeight: 700, fontSize: 16 }}>{user.name}</div><div className="caption mono">{user.email}</div></div></div>
          <label className="field" style={{ marginBottom: 10 }}><span className="fl">Display name</span><input className="input" defaultValue={user.name} /></label>
          <label className="field"><span className="fl">Title</span><input className="input" defaultValue={user.title} /></label>
          <div style={{ marginTop: 14 }}><span className="fl">Assigned roles</span><div style={{ display: 'flex', gap: 6, marginTop: 6 }}>{user.roles.map(r => <RoleTag key={r} role={r} />)}</div>
            <div className="caption" style={{ marginTop: 6 }}>Roles are assigned by an administrator and cannot be changed here.</div></div>
        </div>
        <div className="card" style={{ padding: 18 }}>
          <div className="h2" style={{ marginBottom: 14 }}>Notification preferences</div>
          <div className="cfg-row" style={{ padding: '10px 0' }}><div><div style={{ fontWeight: 600, fontSize: 13.5 }}>In-app notifications</div><div className="caption">Always on</div></div><div className="cfg-ctl"><window.AdminToggle /></div></div>
          {[['Email digest', 'Daily summary of activity'], ['Microsoft Teams', 'Real-time alerts to Teams']].map(([l, s]) => (
            <div key={l} className="cfg-row" style={{ padding: '10px 0' }}><div><div style={{ fontWeight: 600, fontSize: 13.5 }}>{l} <span className="badge outlined" style={{ color: 'var(--text-muted)', marginLeft: 4 }}>SOON</span></div><div className="caption">{s}</div></div></div>
          ))}
        </div>
      </div>
    </div>
  );
}
function AdminToggle() { return <button className="toggle on" disabled><span className="toggle-knob" /></button>; }

/* ---- Notifications full page ---- */
function NotificationsPage({ go }) {
  const role = useStore(s => s.activeRole);
  const all = useStore(s => s.notifications.filter(n => n.forRoles.includes(role)));
  const groups = {}; all.forEach(n => { (groups[n.group] = groups[n.group] || []).push(n); });
  const cssRole = (r) => (ROLE_META[r] || {}).color || 'var(--text-secondary)';
  return (
    <div className="page" style={{ maxWidth: 820 }}>
      <div className="page-head"><div className="ph-titles"><div className="display">Notifications</div></div>
        <div className="ph-actions"><button className="btn" onClick={() => storeActions.markAllRead()}>Mark all read</button></div></div>
      {all.length === 0 ? <div className="card"><EmptyState icon="check" title="You're all caught up." sub="New activity for your role will appear here." /></div>
      : <div className="panel">{Object.keys(groups).map(g => (
        <div key={g}>
          <div className="notif-group-label">{g}</div>
          {groups[g].map(n => (
            <div key={n.id} className={`notif${n.unread ? ' unread' : ''}`}>
              <span className={`nf-dot${n.unread ? '' : ' read'}`} />
              <div style={{ flex: 1 }}><div className="nf-type" style={{ color: cssRole(n.actorRole) }}>{n.type}</div>
                <div className="nf-body">{n.body}</div><div className="nf-meta">{n.who} · {n.when} · <span className="mono">{n.entity}</span></div>
                {n.reject && <div className="nf-reject"><strong>Reason:</strong> {n.reject}</div>}
                {n.verb && <div className="nf-action"><button className="btn sm primary" onClick={() => { storeActions.markRead(n.id); go(n.go); }}>{n.verb}<Icon name="arrow" size={13} /></button></div>}
              </div>
            </div>
          ))}
        </div>
      ))}</div>}
    </div>
  );
}

Object.assign(window, { ProjectsScreen, ProjectDetailScreen, AccountSettings, NotificationsPage, AdminToggle });

/* Two visually distinct groups inside a Project's Collections tab — Designer vs Development.
   They share a project but answer different questions, so they must never be mixed. */
function ProjectCollectionsTab({ collections, go }) {
  const designer = collections.filter(c => c.role === 'designer');
  const development = collections.filter(c => c.role === 'development');
  if (collections.length === 0) return <EmptyState icon="layers" title="No collections in this project." />;

  const Group = ({ kind, items }) => {
    const isDev = kind === 'development';
    const color = isDev ? 'var(--role-development)' : 'var(--role-designer)';
    const label = isDev ? 'Development Collections' : 'Designer Collections';
    const sub = isDev ? 'What improvements should be investigated?' : 'What parts should be used?';
    const detailScreen = isDev ? 'v.collectionDetail' : 'd.collectionDetail';
    if (items.length === 0) return null;
    return (
      <div style={{ marginBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
          {window.DevKindGlyph && <window.DevKindGlyph kind={isDev ? 'development' : 'designer'} size={14} />}
          <div>
            <div style={{ fontWeight: 700, fontSize: 14, letterSpacing: '-.1px', color }}>{label}</div>
            <div className="caption">{sub} · {items.length} collection{items.length !== 1 ? 's' : ''}</div>
          </div>
        </div>
        <div className="list">
          {items.map(c => (
            <div key={c.id} className="lrow" style={{ boxShadow: `inset 3px 0 0 ${color}` }} onClick={() => go({ screen: detailScreen, id: c.id })}>
              <div>
                <div className="lr-title" style={{ display: 'flex', alignItems: 'center', gap: 9, flexWrap: 'wrap' }}>
                  <span>{c.name}</span>
                  <StatusBadge status={isDev ? window.DC_BADGE[c.state] : c.state} />
                  {isDev && window.CategoryChip && <window.CategoryChip category={c.category} />}
                </div>
                <div className="lr-meta">
                  <span className="mono">{c.id}</span><span className="tr-sep" />
                  <span>{c.items.length} part{c.items.length !== 1 ? 's' : ''}</span>
                  <span className="tr-sep" /><span>{c.creator}</span>
                  <span className="tr-sep" /><span>updated {c.updated}</span>
                </div>
              </div>
              <Icon name="chevright" size={16} style={{ color: 'var(--text-muted)' }} />
            </div>
          ))}
        </div>
      </div>
    );
  };
  return (
    <>
      <Group kind="designer" items={designer} />
      {window.DEV_ROLE_ENABLED && <Group kind="development" items={development} />}
      {designer.length === 0 && <div className="caption">No Designer Collections in this project yet.</div>}
    </>
  );
}
