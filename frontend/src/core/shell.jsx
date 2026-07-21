/* global React, Icon, RoleDot, RoleTag, Avatar, StatusBadge, Popover, EmptyState,
   useStore, storeActions, ROLE_META, NAV_BY_ROLE, NAV_SHARED, NAV_SOON */
const { useState: useStateShell, useRef: useRefShell } = React;

/* Role switcher (Note 4) — scoped to the logged-in user's own roles.
   Single-role users see a static label; multi-role users get a switch menu. */
function RoleSwitcher({ activeRole }) {
  const ref = useRefShell(null);
  const [open, setOpen] = useStateShell(false);
  const user = useStore(s => s.users.find(u => u.id === s.currentUserId));
  const m = ROLE_META[activeRole];
  const myRoles = ((user && user.roles) || []).filter(r => ROLE_META[r] && (r !== 'development' || window.DEV_ROLE_ENABLED));
  if (!m) return null;
  if (myRoles.length <= 1) {
    return (
      <div className="role-switcher">
        <div className="role-chip role-chip-static">
          <RoleDot role={activeRole} size={9} />
          <div style={{ flex: 1 }}>
            <div className="rc-label">Your workspace</div>
            <div className="rc-role">{m.label}</div>
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className="role-switcher">
      <button ref={ref} className="role-chip" onClick={() => setOpen(o => !o)}>
        <RoleDot role={activeRole} size={9} />
        <div style={{ flex: 1 }}>
          <div className="rc-label">Your workspace</div>
          <div className="rc-role">{m.label}</div>
        </div>
        <Icon name="chevdown" size={15} />
      </button>
      <Popover anchorRef={ref} open={open} onClose={() => setOpen(false)} width={216}>
        <div className="menu-label">Switch workspace</div>
        {myRoles.map(r => (
          <div key={r} className="mi" onClick={() => { storeActions.setRole(r); setOpen(false); }}>
            <RoleDot role={r} size={8} /><span>{ROLE_META[r].label}</span>
            {r === activeRole && <Icon name="check" size={14} style={{ marginLeft: 'auto', color: 'var(--action)' }} />}
          </div>
        ))}
      </Popover>
    </div>
  );
}

/* Top-right user menu (Note 4): identity, active role, account settings, log out. */
function UserMenu({ go }) {
  const ref = useRefShell(null);
  const [open, setOpen] = useStateShell(false);
  const user = useStore(s => s.users.find(u => u.id === s.currentUserId));
  const activeRole = useStore(s => s.activeRole);
  if (!user) return null;
  return (
    <>
      <button ref={ref} className="user-menu-btn icon-btn" onClick={() => setOpen(o => !o)} title={user.name}>
        <Avatar name={user.name} role={activeRole} size={28} />
      </button>
      {/* The avatar sits at the far right of the top rail — a left-aligned
          popover ran 236px off the edge of the viewport and got clipped. */}
      <Popover anchorRef={ref} open={open} onClose={() => setOpen(false)} width={236} align="right">
        <div className="um-head" style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '4px 8px 10px' }}>
          <Avatar name={user.name} role={activeRole} size={36} />
          <div style={{ minWidth: 0 }}>
            <div style={{ fontWeight: 700, fontSize: 13.5 }}>{user.name}</div>
            <div className="caption mono" style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{user.email}</div>
          </div>
        </div>
        <div className="mi" onClick={() => { setOpen(false); go({ screen: 'settings' }); }}><Icon name="settings" size={15} /><span>Account settings</span></div>
        <div className="mi" style={{ color: 'var(--danger)', borderTop: '1px solid var(--border-soft)', marginTop: 4, paddingTop: 8 }} onClick={() => { setOpen(false); storeActions.logOut(); }}><Icon name="arrow" size={15} style={{ transform: 'rotate(180deg)' }} /><span>Log out</span></div>
      </Popover>
    </>
  );
}

function Sidebar({ active, go }) {
  const activeRole = useStore(s => s.activeRole);
  const user = useStore(s => s.users.find(u => u.id === s.currentUserId));
  const roleNav = NAV_BY_ROLE[activeRole] || { section: '', items: [] };
  const roleColor = ROLE_META[activeRole].color;
  const collCount = useStore(s => s.collections.filter(c => c.role === 'designer').length);
  const bomCount = useStore(s => s.boms.filter(b => b.state !== 'draft').length);
  // v1.3-rev: Dashboard nav item is badged with the Needs Attention count for this role.
  const attentionCount = useStore(s => window.attCountForRole ? window.attCountForRole(s, activeRole) : 0);
  const counts = { 'd.collections': collCount, 'p.boms': bomCount };
  const dashKey = `${activeRole === 'admin' ? 'a' : activeRole === 'development' ? 'v' : activeRole === 'production' ? 'p' : 'd'}.dashboard`;
  counts[dashKey] = attentionCount;

  const NavItem = (n) => {
    if (n.soon) return (
      <div key={n.key} className="nav-item disabled" title="Coming soon">
        <Icon name={n.icon} size={17} className="ni-icon" /><span>{n.label}</span><span className="ni-soon">Soon</span>
      </div>
    );
    const c = counts[n.key];
    // Dashboard 'Needs Attention' badge uses the role's danger color to pull the eye.
    const badgeBg = n.attention && c ? 'var(--danger)' : roleColor;
    return (
      <div key={n.key} className={`nav-item${active === n.key ? ' active' : ''}${n.attention ? ' nav-attention' : ''}`} onClick={() => go({ screen: n.key })}
        style={active === n.key ? { '--accent': roleColor } : undefined}>
        <Icon name={n.icon} size={17} className="ni-icon" /><span>{n.label}</span>
        {c ? <span className="ni-count" style={{ background: badgeBg }}>{c}</span> : null}
      </div>
    );
  };

  return (
    <aside className="sidebar">
      <div className="sb-brand">
        <div className="sb-logo">A</div>
        <div><div className="sb-brandname">AutoBOM</div><div className="sb-brandsub">Engineering Operations</div></div>
      </div>
      <RoleSwitcher activeRole={activeRole} />
      <nav className="sb-nav">
        {roleNav.items.length > 0 && <>
          <div className="sb-section-label">{roleNav.section}</div>
          {roleNav.items.map(NavItem)}
        </>}
        {roleNav.items.length === 0 && (
          <div style={{ padding: '10px 12px', margin: '4px 0', fontSize: 12, color: 'var(--text-on-dark-dim)', lineHeight: 1.5 }}>
            This role is visibility-only. Use Projects and Reports to review work across departments.
          </div>
        )}
        <div className="sb-section-label">General</div>
        {NAV_SHARED.map(NavItem)}
        <div className="sb-section-label">Coming Soon</div>
        {NAV_SOON.map(NavItem)}
      </nav>
      <div className="sb-user" onClick={() => go({ screen: 'settings' })}>
        <Avatar name={user.name} role={activeRole} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="su-name">{user.name}</div>
          <div className="su-role" style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <span className="dot" style={{ background: roleColor, width: 7, height: 7 }} />{ROLE_META[activeRole].label}
          </div>
        </div>
        <Icon name="settings" size={16} style={{ color: 'var(--text-on-dark-dim)' }} />
      </div>
    </aside>
  );
}

function TopRail({ onSearch, onPalette, onBell, unread, searchAnchorRef, go }) {
  return (
    <div className="toprail">
      <button className="icon-btn" title="Back" onClick={() => window.history.back()}><Icon name="chevright" size={18} style={{ transform: 'rotate(180deg)' }} /></button>
      <button className="icon-btn" title="Forward" onClick={() => window.history.forward()}><Icon name="chevright" size={18} /></button>
      <div className="rail-search" ref={searchAnchorRef} onClick={onSearch}>
        <div className="rs-box"><Icon name="search" size={15} /><span>Search parts, BOMs, projects…</span><span className="kbd">⌘K</span></div>
      </div>
      <div className="rail-actions">
        <button className="icon-btn" title="Command palette (⌘K)" onClick={onPalette}><Icon name="search" size={18} /></button>
        <button className="icon-btn" title="Notifications" onClick={onBell}>
          <Icon name="bell" size={18} />{unread > 0 && <span className="bell-badge">{unread}</span>}
        </button>
        <UserMenu go={go} />
      </div>
    </div>
  );
}

function Breadcrumbs({ crumbs }) {
  return (
    <nav className="breadcrumbs" aria-label="Breadcrumb">
      {crumbs.map((c, i) => (
        <React.Fragment key={i}>
          {i > 0 && <Icon name="chevright" size={13} className="bc-sep" />}
          {c.go ? <button className="bc-link" onClick={c.go}>{c.label}</button>
                : <span className="bc-current">{c.label}</span>}
        </React.Fragment>
      ))}
    </nav>
  );
}

function NotificationPanel({ open, onClose, onNavigate }) {
  const activeRole = useStore(s => s.activeRole);
  const all = useStore(s => s.notifications);
  if (!open) return null;
  const notes = all.filter(n => n.forRoles.includes(activeRole));
  const groups = {}; notes.forEach(n => { (groups[n.group] = groups[n.group] || []).push(n); });
  return (
    <>
      <div className="scrim" onClick={onClose} />
      <div className="notif-panel" role="dialog" aria-label="Notifications">
        <div className="notif-head">
          <Icon name="bell" size={17} /><span style={{ fontWeight: 700, fontSize: 15 }}>Notifications</span>
          <button className="btn-link" style={{ marginLeft: 'auto' }} onClick={() => storeActions.markAllRead()}>Mark all read</button>
          <button className="icon-btn" onClick={onClose}><Icon name="x" size={17} /></button>
        </div>
        <div className="notif-list">
          {notes.length === 0 ? <EmptyState icon="check" title="You're all caught up." sub="New activity that needs your attention will appear here." />
          : Object.keys(groups).map(g => (
            <div key={g}>
              <div className="notif-group-label">{g}</div>
              {groups[g].map(n => {
                const isAction = n.kind !== 'fyi';
                const accent = isAction ? (n.actorRole || n.sourceRole || 'designer') : (n.sourceRole || n.actorRole || 'production');
                const accentColor = window.ROLE_META?.[accent]?.color || 'var(--text-secondary)';
                return (
                  <div key={n.id} className={`notif${n.unread ? ' unread' : ''}`} onClick={() => { storeActions.markRead(n.id); onClose(); onNavigate(n); }} style={{ cursor: 'pointer' }}>
                    <span className={`nf-dot${n.unread ? '' : ' read'}`} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div className="nf-type" style={{ color: isAction ? 'var(--danger)' : 'var(--text-muted)' }}>
                        {isAction ? 'ACTION REQUIRED' : 'UPDATE'}{n.actionLabel ? ' — ' + n.actionLabel : ''}
                      </div>
                      <div className="nf-body">{n.body}</div>
                      <div className="nf-meta">
                        <span className="mono">{n.entity}</span> · Sent by <span style={{ color: accentColor, fontWeight: 600 }}>{(window.ROLE_META?.[n.sourceRole || n.actorRole]?.label || '—')}</span> · {n.who} · {n.when}
                      </div>
                      {n.reject && <div className="nf-reject"><strong>Reason:</strong> {n.reject}</div>}
                      <div className="nf-action">
                        <button className={`btn sm ${isAction ? 'primary' : ''}`} onClick={(e) => { e.stopPropagation(); storeActions.markRead(n.id); onClose(); onNavigate(n); }}>
                          {n.verb || 'View'}<Icon name="arrow" size={13} />
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

Object.assign(window, { Sidebar, TopRail, Breadcrumbs, NotificationPanel });
