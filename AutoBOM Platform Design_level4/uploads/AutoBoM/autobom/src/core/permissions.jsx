/* AutoBOM — RBAC.
   Two layers:
     L1 — role defaults (CAPS[role])
     L2 — user-level overrides (additive, on top of one or more base roles)
   The production app uses both. The prototype role switcher only changes the ACTIVE role for review. */

/* v1.1 MVP scope flag.
   Development was fully designed in v1.0 and is now DEFERRED. Screens, store actions,
   routes, and seed data remain in the repo. Sidebar nav, role-switcher, dashboards,
   search results, notifications, and admin role assignment all read this flag.
   Flip to true to reactivate the role. */
/* v4 login-role model: the only roles a user logs in AS are Designer, Production, Admin.
   Purchasing and Inventory are NOT login roles — they are embedded surfaces inside the
   Designer and Production workspaces. Development is archived (flag below). */
const DEV_ROLE_ENABLED = false;
const ACTIVE_MVP_ROLES = ['designer', 'production', 'admin'];
const LOGIN_ROLES = ['designer', 'production', 'admin'];
window.DEV_ROLE_ENABLED = DEV_ROLE_ENABLED;
window.ACTIVE_MVP_ROLES = ACTIVE_MVP_ROLES;
window.LOGIN_ROLES = LOGIN_ROLES;

const ROLE_META = {
  designer:    { label: 'Designer',    color: '#7C3AED', home: 'd.dashboard', owns: 'Engineering intent' },
  production:  { label: 'Production',  color: '#0891B2', home: 'p.dashboard', owns: 'Sourcing readiness & assembly' },
  development: { label: 'Development', color: '#059669', home: 'v.dashboard', owns: 'Technical evolution & improvement' },
  manager:     { label: 'Manager',     color: '#0D9488', home: 'projects',    owns: 'Oversight & reporting' },
  executive:   { label: 'Executive',   color: '#475569', home: 'projects',    owns: 'Visibility & reporting' },
  readonly:    { label: 'Read-Only',   color: '#64748B', home: 'projects',    owns: 'View only' },
  admin:       { label: 'Admin',       color: '#B91C1C', home: 'a.dashboard', owns: 'System recovery & config' },
};

/* Capability groups (used by Admin permission UI). Keep in sync with CAPS below. */
const CAP_CATALOG = [
  { group: 'Collections', items: [
    ['collection.create',   'Create collection'],
    ['collection.edit',     'Edit collection'],
    ['collection.requestOrder', 'Request to order'],
  ]},
  { group: 'Parts & BOMs', items: [
    ['part.search',         'Part search'],
    ['part.addToCollection','Add part to collection'],
    ['bom.upload',          'Upload BOM'],
    ['bom.validate',        'Validate BOM'],
    ['bom.editLine',        'Edit BOM line'],
    ['bom.runSourcing',     'Run sourcing'],
    ['bom.sendException',   'Send exceptions to Designer'],
    ['bom.respondException','Respond to exceptions'],
    ['bom.createPackage',   'Create procurement package'],
    ['bom.submitToPurchasing', 'Submit to Purchasing'],
  ]},
  { group: 'Development', items: [
    ['dev.collection.create',      'Create Development Collections'],
    ['dev.collection.edit',        'Edit Development Collections'],
    ['dev.collection.generateOutcome', 'Generate outcome from collection'],
    ['dev.investigation.create',   'Create Investigations'],
    ['dev.recommendation.create',  'Create Improvement Recommendations'],
    ['dev.rework.create',          'Create Rework Packages'],
    ['dev.firmware.create',        'Create Firmware Releases'],
    ['dev.handshake.send',         'Push handshake to another team'],
    ['dev.handshake.respond',      'Respond to incoming handshake'],
  ]},
  { group: 'Administration', items: [
    ['admin.users',     'Manage users'],
    ['admin.roles',     'Assign roles'],
    ['admin.permissions', 'Manage permissions & overrides'],
    ['admin.workflow',  'Configure workflow'],
    ['admin.suppliers', 'Configure suppliers'],
    ['admin.settings',  'System settings'],
    ['admin.audit',     'View audit log'],
    ['admin.override',  'Override workflow state'],
  ]},
  { group: 'General', items: [
    ['comment',         'Comment on records'],
    ['project.create',  'Create project'],
  ]},
];

/* Role defaults — what each role can do straight out of the box. */
const CAPS = {
  designer: new Set([
    'collection.create', 'collection.edit', 'collection.requestOrder',
    'part.search', 'part.addToCollection', 'bom.respondException',
    'comment', 'project.create',
  ]),
  production: new Set([
    'part.search', 'bom.upload', 'bom.validate', 'bom.editLine', 'bom.runSourcing',
    'bom.sendException', 'bom.createPackage', 'bom.submitToPurchasing',
    'dev.handshake.respond', 'comment', 'project.create',
  ]),
  development: new Set([
    'part.search',
    'dev.collection.create', 'dev.collection.edit', 'dev.collection.generateOutcome',
    'dev.investigation.create', 'dev.recommendation.create',
    'dev.rework.create', 'dev.firmware.create',
    'dev.handshake.send', 'dev.handshake.respond',
    'comment',
  ]),
  manager:   new Set(['comment']),
  executive: new Set([]),
  readonly:  new Set([]),
  admin: new Set([
    'admin.users', 'admin.roles', 'admin.permissions', 'admin.workflow',
    'admin.suppliers', 'admin.settings', 'admin.audit', 'admin.override', 'comment',
  ]),
};

/* Resolve effective capability set for a user (one or more roles + overrides). */
function effectiveCaps(user) {
  const set = new Set();
  if (user && user.roles) for (const r of user.roles) (CAPS[r] || new Set()).forEach(c => set.add(c));
  if (user && user.overrides) for (const c of user.overrides) set.add(c);
  return set;
}
function inBaseRole(user, cap) {
  if (!user || !user.roles) return false;
  return user.roles.some(r => (CAPS[r] || new Set()).has(cap));
}

/* can(action, ctx): production code calls this everywhere.
   ctx may be { role } (legacy), { user }, or { role, user } — we honor whichever is most specific. */
function can(actionOrRole, action, user) {
  // legacy 2-arg form: can(role, action)
  if (typeof action === 'string' && !user) return !!(CAPS[actionOrRole] && CAPS[actionOrRole].has(action));
  // new form: can(action, user)
  const a = actionOrRole;
  const u = action;
  return effectiveCaps(u).has(a);
}

/* Navigation per role. The Development workspace shows Investigations/Recommendations/Rework/Firmware. */
const NAV_BY_ROLE = {
  designer: { section: 'Designer', items: [
    { key: 'd.dashboard', label: 'Dashboard', icon: 'dashboard', attention: true },
    { key: 'programs', label: 'Programs', icon: 'folder' },
    { key: 'd.collections', label: 'Collections', icon: 'layers' },
    { key: 'purchasingEmbed', label: 'Purchasing', icon: 'cart', embed: true },
    { key: 'inventoryEmbed', label: 'Inventory', icon: 'box', embed: true },
  ]},
  production: { section: 'Production', items: [
    { key: 'p.dashboard', label: 'Dashboard', icon: 'dashboard', attention: true },
    { key: 'projects', label: 'PCB Projects', icon: 'folder' },
    { key: 'purchasingEmbed', label: 'Purchasing', icon: 'cart', embed: true },
    { key: 'inventoryEmbed', label: 'Inventory', icon: 'box', embed: true },
  ]},
  development: { section: 'Development', items: [
    { key: 'v.dashboard', label: 'Dashboard', icon: 'dashboard' },
    { key: 'v.collections', label: 'Collections', icon: 'layers' },
    { key: 'v.investigations', label: 'Investigations', icon: 'search' },
    { key: 'v.recommendations', label: 'Improvements', icon: 'sparkle' },
    { key: 'v.rework', label: 'Rework Packages', icon: 'refresh' },
    { key: 'v.firmware', label: 'Firmware Releases', icon: 'upload' },
  ]},
  manager:   { section: 'Oversight', items: [] },
  executive: { section: 'Oversight', items: [] },
  readonly:  { section: 'Read-Only', items: [] },
  admin: { section: 'Administration', items: [
    { key: 'a.dashboard', label: 'Dashboard', icon: 'dashboard', attention: true },
    { key: 'a.configuration', label: 'Configuration', icon: 'settings' },
    { key: 'programs', label: 'Programs', icon: 'folder' },
    { key: 'a.users', label: 'Users', icon: 'user' },
    { key: 'purchasingEmbed', label: 'Purchasing', icon: 'cart', embed: true },
    { key: 'inventoryEmbed', label: 'Inventory', icon: 'box', embed: true },
    { key: 'a.forceWaivers', label: 'Force-Waivers log', icon: 'unlock' },
    { key: 'a.audit', label: 'Audit Log', icon: 'history' },
  ]},
};

const NAV_SHARED = [
  { key: 'notifications', label: 'Notifications', icon: 'bell' },
];
const NAV_SOON = [
  { key: 'reports', label: 'Reports', icon: 'chart', soon: true },
];

/* State-based lock resolver (unchanged in spec). */
function lockFor(objectType, state, role) {
  const D = role === 'designer', P = role === 'production';
  if (objectType === 'collection') {
    if (state === 'order-requested' && D) return { title: 'In the purchasing bucket', owner: 'purchasing', body: 'Its lines are pooling toward the next batch on the Daily Purchasing List. Parts are locked while it’s in the bucket.', canDo: 'View, comment, track status' };
    if (state === 'ordered' && (D || P)) return { title: 'Ordered — read-only', owner: 'purchasing', body: 'This collection has been ordered. All content is read-only.', canDo: 'View order status, track' };
  }
  if (objectType === 'bom') {
    if (state === 'submitted' && (P || D)) return { title: 'In the purchasing bucket', owner: 'purchasing', body: 'Engineering content is locked while its lines pool toward the next purchasing batch.', canDo: 'View, comment, track status' };
    if (state === 'exceptions' && P) return { title: 'Exception report sent to Designer', owner: 'designer', body: 'Waiting for replacement parts from engineering.', canDo: 'View, track' };
    if ((state === 'ordered' || state === 'approved') && (P || D)) return { title: 'Approved & ordered — read-only', owner: 'purchasing', body: 'This BOM has been ordered. All content is read-only.', canDo: 'View order status, track' };
  }
  if (objectType === 'request') {
    if ((state === 'approved' || state === 'ordered') && (D || P)) return { title: 'Approved & ordered — read-only', owner: 'purchasing', body: 'This request has been approved and ordered. All content is read-only.', canDo: 'View order status, track' };
  }
  return null;
}

Object.assign(window, { ROLE_META, CAPS, CAP_CATALOG, NAV_BY_ROLE, NAV_SHARED, NAV_SOON, can, effectiveCaps, inBaseRole, lockFor });
