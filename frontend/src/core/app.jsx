/* global React, ReactDOM, Icon, EmptyState, RoleTag,
   useStore, storeActions, getState, ROLE_META,
   useHashRoute, buildCrumbs, navKeyForScreen, rememberScroll, restoreScroll,
   Sidebar, TopRail, Breadcrumbs, NotificationPanel, SearchOverlay */
const { useState, useRef, useEffect } = React;

/* Map a screen's role prefix (d./p./a./v.) to a role, so navigating to another
   role's screen auto-switches the active workspace (prototype view-as-any). */
const PREFIX_ROLE = { d: 'designer', p: 'production', a: 'admin', v: 'development' };
function screenRole(screen) {
  const m = /^([a-z])\./.exec(screen || '');
  return m ? PREFIX_ROLE[m[1]] : null;
}

function App() {
  const authed = useStore(s => s.authed);
  const booting = useStore(s => s.booting);
  // While restoring a possible backend session, show a calm splash (avoids a
  // login-screen flash for already-authenticated users).
  if (booting) return (
    <div style={{ position: 'fixed', inset: 0, display: 'grid', placeItems: 'center', background: '#0D1117' }}>
      <div style={{ width: 44, height: 44, borderRadius: 10, background: '#2563EB', color: '#fff',
        display: 'grid', placeItems: 'center', font: '800 22px Inter, sans-serif', animation: 'none' }}>A</div>
    </div>
  );
  if (!authed) return window.LoginScreen ? <window.LoginScreen /> : <EmptyState icon="lock" title="Sign in required" />;
  return <AuthedApp />;
}

/* The authed workspace. All of App's hooks live here so they only run when the
   user is signed in and always in the same order. This split fixes a
   Rules-of-Hooks violation in the original prototype: App called several hooks,
   early-returned <LoginScreen/> when unauthed, then called MORE hooks below —
   so logging in (authed flips false→true in place) grew the hook count between
   renders and crashed React with "Rendered more hooks than during the previous
   render." Behavior is otherwise unchanged. */
function AuthedApp() {
  const activeRole = useStore(s => s.activeRole);
  // Landing route must follow the signed-in user's role. useHashRoute used to
  // hardcode 'd.dashboard' when the URL had no hash, so a Production or Admin
  // user logged in and landed in the DESIGNER workspace. Resolve home first and
  // hand it to the router. (Hook order is unchanged - both are unconditional.)
  const roleHome = (ROLE_META[activeRole] && ROLE_META[activeRole].home) || 'd.dashboard';
  const [route, navigate] = useHashRoute(roleHome);
  const user = useStore(s => s.users.find(u => u.id === s.currentUserId));
  const notifications = useStore(s => s.notifications);

  const [notifOpen, setNotifOpen] = useState(false);
  const [search, setSearch] = useState({ open: false, mode: 'command', anchorRect: null, initialQuery: '' });
  const [switchBanner, setSwitchBanner] = useState(null);
  const searchAnchorRef = useRef(null);
  const lastRoute = useRef(route);

  /* The route must follow the SESSION IDENTITY, not outlive it.
     The shell (sidebar, avatar) reads the store and updates the instant a
     different user signs in — but the URL hash does not, and useHashRoute's
     role-home fallback only applies when there is NO hash. Signing in as
     another user therefore left the PREVIOUS user's screen mounted under the
     new user's shell (Admin nav + avatar, still rendering d.dashboard).

     Comparing identity against a ref cannot fix this: logOut() flips authed to
     false, which UNMOUNTS AuthedApp and destroys the ref, so the new identity
     looks unchanged on remount.

     Scope matters. An earlier version of this guard redirected away from ANY
     screen whose role the user did not hold — which broke cross-role
     navigation the prototype depends on: a Designer opening a BOM
     (p.bomOverview) got bounced straight back to #/designer, so BOM links from
     Projects and from search appeared to lead to the Dashboard. Designers must
     be able to open a BOM; that is how a Push-Back gets resolved.

     So only role HOME screens are guarded. Landing on another role's dashboard
     is the stale-hash symptom; landing on another role's detail screen is
     deliberate. Prefix-less shared screens (Purchasing, Inventory, Projects,
     Programs) are untouched either way. */
  useEffect(() => {
    const need = screenRole(route.screen);
    const isRoleHome = need && ROLE_META[need] && ROLE_META[need].home === route.screen;
    const roles = (user && user.roles) || [];
    if (isRoleHome && roles.length && !roles.includes(need)) {
      navigate({ screen: roleHome }, true);   // replace: no bogus history entry
    }
  }, [route.screen, user, roleHome]);

  // Scroll memory across navigations.
  useEffect(() => {
    rememberScroll(lastRoute.current);
    restoreScroll(route);
    lastRoute.current = route;
  }, [route.screen, route.id, route.tab]);

  // ⌘K / Ctrl-K opens the command palette from anywhere.
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        const rect = searchAnchorRef.current ? searchAnchorRef.current.getBoundingClientRect() : null;
        setSearch(s => ({ ...s, open: true, mode: 'command', anchorRect: rect }));
      }
      if (e.key === 'Escape') { setSearch(s => ({ ...s, open: false })); setNotifOpen(false); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const unread = notifications.filter(n => n.forRoles.includes(activeRole) && n.unread).length;

  // Navigate, auto-switching workspace when the target screen belongs to another
  // role the user actually holds.
  const go = (r) => {
    if (typeof r === 'string') r = { screen: r };
    const need = screenRole(r.screen);
    if (need && need !== activeRole) {
      storeActions.setRole(need);
    }
    navigate(r);
  };

  // Notification click → resolve where THIS user can act, switching role if needed.
  const onNavigate = (n) => {
    const routes = n.routes || (n.go ? { [n.targetRole || activeRole]: n.go } : {});
    const roles = (user && user.roles) || [];
    let dest = routes[activeRole], switchTo = null;
    if (!dest && n.targetRole && roles.includes(n.targetRole) && routes[n.targetRole]) { dest = routes[n.targetRole]; switchTo = n.targetRole; }
    if (!dest) for (const r of roles) if (routes[r]) { dest = routes[r]; switchTo = r; break; }
    if (!dest) dest = n.go || { screen: 'notifications' };
    if (switchTo && switchTo !== activeRole) {
      const from = activeRole;
      storeActions.setRole(switchTo);
      setSwitchBanner({ from, to: switchTo });
    }
    navigate(dest);
  };

  const roleOk = ROLE_META[activeRole] ? activeRole : 'designer';
  const home = ROLE_META[roleOk] ? (ROLE_META[roleOk].home || 'd.dashboard') : 'd.dashboard';
  const screenName = route.screen || home;
  const active = navKeyForScreen(screenName);

  const m = { go, route };
  const S = (name, props) => (window[name] ? React.createElement(window[name], { ...m, ...(props || {}) }) : <EmptyState icon="alert" title="Screen unavailable" description={name} />);
  // Guarded top-level chrome: a missing global (transpile error in its file) shows
  // a labeled placeholder instead of throwing and blanking the whole app.
  const G = (name, props, children) => (window[name] ? React.createElement(window[name], props || {}, children) : <div style={{ padding: 8, font: '12px ui-monospace, monospace', color: '#b91c1c' }}>missing: {name}</div>);

  const screen = (() => {
    switch (screenName) {
      case 'd.dashboard': return S('DashboardScreen');
      case 'd.collections': return S('CollectionListScreen');
      // CollectionDetailScreen looks the collection up from the store by id.
      // It previously took a `collection` object prop that nothing ever passed,
      // so every collection rendered "Collection not found".
      case 'd.collectionDetail': return S('CollectionDetailScreen', { id: route.id });
      case 'p.dashboard': return S('ProductionDashboard', { pushback: route.pushback });
      case 'p.boms': return S('BomListScreen');
      // Carry the originating PCB Project through so the upload form can
      // pre-select it instead of defaulting to an unrelated project.
      case 'p.upload': return S('BomUploadScreen', { preProject: route.project || route.id });
      case 'p.validate': return S('BomValidationScreen', { id: route.id });
      case 'p.sourcing': return S('SourcingProgressScreen', { id: route.id });
      case 'p.results': return S('SourcingResultsScreen', { id: route.id });
      case 'p.procurement': return S('ProcurementPackageScreen', { id: route.id });
      case 'p.bomOverview': return S('BomOverviewScreen', { id: route.id, tab: route.tab });
      case 'a.dashboard': return S('AdminDashboard');
      case 'a.users': return S('UserManagement');
      case 'a.configuration': return S('AdminConfiguration', { tab: route.tab });
      case 'a.forceWaivers': return S('ForceWaiversLog');
      case 'a.audit': return S('AuditLog');
      // EmbeddedPurchasing's prop is `focusReq`; passing `req`/`tab` left it
      // undefined, so "View in Purchasing" deep links (#/purchasing-view?tab=REQ-009)
      // were silently ignored and landed on the generic buckets view.
      // Request ids ride in `tab` per routeForHit() in search.jsx; a real tab
      // name ('buckets'/'archive') simply won't match a request and is ignored.
      case 'purchasingEmbed': return S('EmbeddedPurchasing', { focusReq: route.req || route.tab });
      case 'inventoryEmbed': return S('EmbeddedInventory');
      case 'receiving': return S('ReceivingScreen');
      // StorageDetailScreen's prop is `id`; passing `loc` made every
      // "Open storage location" click land on a not-found page.
      case 'storageDetail': return S('StorageDetailScreen', { id: route.id });
      case 'programs': return S('ProgramsScreen');
      case 'programDetail': return S('ProgramDetailScreen', { id: route.id });
      case 'projects': return S('ProjectsScreen');
      // `tab` must be forwarded or the Activity tab is inert: the URL updates
      // but curTab falls back to 'boms' on every render.
      case 'projectDetail': return S('ProjectDetailScreen', { id: route.id, tab: route.tab });
      case 'notifications': return S('NotificationsPage');
      case 'settings': return S('AccountSettings');
      case 'v.dashboard': return S('DevelopmentDashboard');
      case 'v.collections': return S('DevCollectionListScreen');
      case 'v.collectionDetail': return S('DevCollectionDetail', { id: route.id });
      case 'v.investigations': return S('DevListScreen', { kind: 'investigation' });
      case 'v.investigationDetail': return S('InvestigationDetail', { id: route.id });
      case 'v.recommendations': return S('DevListScreen', { kind: 'recommendation' });
      case 'v.recommendationDetail': return S('RecommendationDetail', { id: route.id });
      case 'v.rework': return S('DevListScreen', { kind: 'rework' });
      case 'v.reworkDetail': return S('ReworkDetail', { id: route.id });
      case 'v.firmware': return S('DevListScreen', { kind: 'firmware' });
      case 'v.firmwareDetail': return S('FirmwareDetail', { id: route.id });
      default: return <EmptyState icon="alert" title="Screen not found" description={`No route for: ${screenName}`} />;
    }
  })();

  const crumbs = (typeof buildCrumbs === 'function') ? buildCrumbs(route, getState()) : [];

  return (
    <div className="app">
      {G('Sidebar', { active, go })}
      <div className="main">
        {G('TopRail', {
          go, unread, searchAnchorRef,
          onBell: () => setNotifOpen(o => !o),
          onSearch: () => { const rect = searchAnchorRef.current ? searchAnchorRef.current.getBoundingClientRect() : null; setSearch(s => ({ ...s, open: true, mode: 'search', anchorRect: rect })); },
          onPalette: () => { const rect = searchAnchorRef.current ? searchAnchorRef.current.getBoundingClientRect() : null; setSearch(s => ({ ...s, open: true, mode: 'command', anchorRect: rect })); },
        })}
        {switchBanner && (
          <div className="switch-banner">
            <Icon name="refresh" size={14} />
            Switched to {ROLE_META[switchBanner.to]?.label || switchBanner.to} to handle this.
            <button className="btn-link" onClick={() => { storeActions.setRole(switchBanner.from); setSwitchBanner(null); }}>Switch back to {ROLE_META[switchBanner.from]?.label || switchBanner.from}</button>
            <button className="icon-btn" style={{ marginLeft: 'auto' }} onClick={() => setSwitchBanner(null)}><Icon name="x" size={14} /></button>
          </div>
        )}
        {G('Breadcrumbs', { crumbs })}
        <div className="content">
          <ErrorBoundary resetKey={`${screenName}:${route.id || ''}`}>{screen}</ErrorBoundary>
        </div>
      </div>
      {G('NotificationPanel', { open: notifOpen, onClose: () => setNotifOpen(false), onNavigate })}
      {G('SearchOverlay', { open: search.open, mode: search.mode, anchorRect: search.anchorRect, initialQuery: search.initialQuery, onClose: () => setSearch(s => ({ ...s, open: false })), go })}
    </div>
  );
}

/* A real error boundary. The previous SafeApp wrapped React.createElement(App)
   in try/catch, which never fires for errors thrown during a CHILD's render —
   so one bad screen (e.g. a null field in a stat card) unmounted the entire
   tree to a white page with no way back except a hard reload. A class boundary
   is the only thing React honors here.

   `resetKey` clears the error when the user navigates elsewhere, so a single
   broken screen never strands the session. */
class ErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { error: null }; }
  static getDerivedStateFromError(error) { return { error }; }
  componentDidCatch(error, info) { console.error('AutoBOM render error:', error, info); }
  componentDidUpdate(prev) {
    if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null });
  }
  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div className="page">
        <div className="panel" style={{ padding: 20, borderTop: '3px solid var(--danger, #b91c1c)' }}>
          <div style={{ fontWeight: 700, marginBottom: 6 }}>This screen hit an error</div>
          <div className="caption" style={{ marginBottom: 12 }}>
            The rest of the app is still running — use the sidebar to go elsewhere, or retry.
          </div>
          <pre style={{ font: '12px/1.6 ui-monospace, monospace', color: '#b91c1c', whiteSpace: 'pre-wrap', margin: '0 0 12px' }}>
            {(error && (error.stack || error.message)) || String(error)}
          </pre>
          <button className="btn" onClick={() => this.setState({ error: null })}>Retry</button>
        </div>
      </div>
    );
  }
}

function SafeApp() {
  return (
    <ErrorBoundary resetKey="root">
      <App />
    </ErrorBoundary>
  );
}

if (typeof window !== 'undefined') { window.App = App; window.SafeApp = SafeApp; }
if (typeof window !== 'undefined' && typeof ReactDOM !== 'undefined') {
  const root = document.getElementById('root');
  if (root) {
    try {
      ReactDOM.render(<SafeApp />, root);
    } catch (e) {
      root.innerHTML = '<div style="font:13px/1.6 ui-monospace,monospace;color:#b91c1c;padding:24px;white-space:pre-wrap">\u26a0 Mount error\n' + ((e && (e.stack || e.message)) || String(e)) + '</div>';
    }
  }
}
