/* global React */
const { useState, useRef, useEffect, useLayoutEffect } = React;

/* =========================================================
   ICONS — minimal stroke set (Lucide-style), currentColor
   ========================================================= */
const ICON_PATHS = {
  dashboard: 'M3 3h7v9H3zM14 3h7v5h-7zM14 12h7v9h-7zM3 16h7v5H3z',
  search: 'M11 11m-7 0a7 7 0 1 0 14 0a7 7 0 1 0-14 0|M21 21l-4.3-4.3',
  layers: 'M12 2 2 7l10 5 10-5-10-5z|M2 12l10 5 10-5|M2 17l10 5 10-5',
  folder: 'M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z',
  cart: 'M3 3h2l2.4 12.4a1 1 0 0 0 1 .8h9.7a1 1 0 0 0 1-.8L21 7H6|M10 21a1 1 0 1 0 0-2 1 1 0 0 0 0 2z|M18 21a1 1 0 1 0 0-2 1 1 0 0 0 0 2z',
  boms: 'M4 3h11l5 5v13a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z|M14 3v6h6|M8 13h8|M8 17h6',
  bell: 'M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9|M10.3 21a1.94 1.94 0 0 0 3.4 0',
  settings: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z|M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z',
  box: 'M21 8 12 3 3 8v8l9 5 9-5z|M3.3 7.5 12 12.5l8.7-5M12 22V12.5',
  chart: 'M3 3v18h18|M7 14v4|M12 10v8|M17 6v12',
  upload: 'M12 15V3|M7 8l5-5 5 5|M5 21h14',
  check: 'M20 6 9 17l-5-5',
  alert: 'M12 3 2 20h20L12 3z|M12 9v5|M12 17.5v.5',
  x: 'M18 6 6 18M6 6l12 12',
  refresh: 'M21 12a9 9 0 1 1-3-6.7|M21 4v4h-4',
  arrow: 'M5 12h14|M13 6l6 6-6 6',
  clock: 'M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0-18 0|M12 7v5l3 2',
  clipboard: 'M9 4h6a1 1 0 0 1 1 1v1h2a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h2V5a1 1 0 0 1 1-1z|M9 4a1 1 0 0 0-1 1v1h8V5a1 1 0 0 0-1-1',
  ban: 'M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0-18 0|M5.6 5.6l12.8 12.8',
  package: 'M21 8 12 3 3 8v8l9 5 9-5z|M3.3 7.5 12 12.5l8.7-5M12 22V12.5|M7.5 5.3l9 5',
  circle: 'M12 12m-8 0a8 8 0 1 0 16 0a8 8 0 1 0-16 0',
  chevdown: 'M6 9l6 6 6-6',
  chevright: 'M9 6l6 6-6 6',
  plus: 'M12 5v14M5 12h14',
  external: 'M14 4h6v6|M20 4 10 14|M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5',
  filter: 'M3 5h18l-7 8v6l-4 2v-8z',
  lock: 'M5 11h14a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-8a1 1 0 0 1 1-1z|M8 11V8a4 4 0 0 1 8 0v3',
  unlock: 'M5 11h14a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-8a1 1 0 0 1 1-1z|M8 11V8a4 4 0 0 1 7.5-2',
  comment: 'M21 11.5a8.4 8.4 0 0 1-9 8.4 9 9 0 0 1-4-1L3 20l1.1-4A8.4 8.4 0 0 1 12 3a8.4 8.4 0 0 1 9 8.5z',
  user: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8z|M4 21a8 8 0 0 1 16 0',
  logout: 'M9 21H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h4|M16 17l5-5-5-5|M21 12H9',
  more: 'M5 12h.01M12 12h.01M19 12h.01',
  info: 'M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0-18 0|M12 11v5|M12 8v.5',
  sparkle: 'M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z',
  tag: 'M3 11V4a1 1 0 0 1 1-1h7l9 9-8 8-9-9z|M7.5 7.5h.01',
  dollar: 'M12 2v20|M17 6.5C17 4.6 14.8 4 12 4S7 5 7 7.5 9 10.5 12 11s5 1.4 5 4-2.5 3.5-5 3.5-5-.8-5-2.5',
  truck: 'M3 6a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v10H3z|M15 9h4l3 3v4h-7|M7.5 18.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z|M18 18.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z',
  link: 'M10 14a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1.5 1.5|M14 10a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1.5-1.5',
  inbox: 'M22 12h-6l-2 3h-4l-2-3H2|M5.5 5h13l3.5 7v6a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1v-6z',
  history: 'M3 12a9 9 0 1 0 9-9 9 9 0 0 0-7 3.3|M3 4v4h4|M12 7v5l3 2',
  flag: 'M4 3v18|M4 4h13l-2 4 2 4H4',
  send: 'M22 2 11 13|M22 2 15 22l-4-9-9-4z',
};

function Icon({ name, size = 18, sw = 2, className = '', style }) {
  const raw = ICON_PATHS[name] || ICON_PATHS.circle;
  const segs = raw.split('|');
  return (
    <svg className={className} data-icon={name} width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"
      style={style} aria-hidden="true">
      {segs.map((d, i) => <path key={i} d={d} />)}
    </svg>
  );
}

/* Click feedback: any button whose icon is the sourcing/refresh glyph spins once on click. */
if (typeof document !== 'undefined' && !window.__sourcingSpinWired) {
  window.__sourcingSpinWired = true;
  document.addEventListener('click', (e) => {
    const btn = e.target.closest && e.target.closest('button');
    if (!btn) return;
    const svg = btn.querySelector('svg[data-icon="refresh"]');
    if (!svg) return;
    svg.classList.remove('spin-once');
    void svg.getBoundingClientRect();
    svg.classList.add('spin-once');
    svg.addEventListener('animationend', () => svg.classList.remove('spin-once'), { once: true });
  }, true);
}

/* =========================================================
   STATUS BADGES — single source of truth
   ========================================================= */
const STATUS = {
  'sourced-mouser': { label: 'SOURCED — MOUSER', style: 'filled', color: '#1A56DB', icon: 'check' },
  'sourced-digikey':{ label: 'SOURCED — DIGIKEY', style: 'filled', color: '#D91F1F', icon: 'check' },
  'needs-review':   { label: 'NEEDS REVIEW', style: 'filled', color: '#D97706', icon: 'alert' },
  'check-wall':     { label: 'CHECK WALL', style: 'outlined', color: '#D97706', icon: 'alert' },
  'exception':      { label: 'EXCEPTION', style: 'filled', color: '#DC2626', icon: 'alert' },
  'obsolete':       { label: 'OBSOLETE / EOL', style: 'filled', color: '#991B1B', icon: 'ban' },
  'active':         { label: 'ACTIVE', style: 'outlined', color: '#16A34A', icon: 'check' },
  'validated':      { label: 'VALIDATED', style: 'outlined', color: '#0891B2', icon: 'check' },
  'sourcing':       { label: 'SOURCING', style: 'outlined', color: '#0891B2', icon: 'refresh', spin: true },
  'ready':          { label: 'READY', style: 'filled', color: '#16A34A', icon: 'check' },
  'submitted':      { label: 'SUBMITTED', style: 'outlined', color: '#2563EB', icon: 'arrow' },
  'in-review':      { label: 'IN REVIEW', style: 'outlined', color: '#D97706', icon: 'clock' },
  'approved':       { label: 'APPROVED', style: 'filled', color: '#16A34A', icon: 'check' },
  'rejected':       { label: 'REJECTED', style: 'filled', color: '#DC2626', icon: 'x' },
  'ordered':        { label: 'ORDERED', style: 'filled', color: '#2563EB', icon: 'clipboard' },
  'partially-ordered': { label: 'PARTIALLY ORDERED', style: 'outlined', color: '#2563EB', icon: 'clipboard' },
  'shipped':        { label: 'SHIPPED', style: 'outlined', color: '#0891B2', icon: 'package' },
  'draft':          { label: 'DRAFT', style: 'outlined', color: '#64748B', icon: 'circle' },
  'order-requested':{ label: 'ORDER REQUESTED', style: 'outlined', color: '#D97706', icon: 'arrow' },
  'stale':          { label: 'STALE', style: 'outlined', color: '#D97706', icon: 'alert' },
  'in-stock':       { label: 'IN STOCK', style: 'outlined', color: '#16A34A', icon: 'check' },
  'zero-stock':     { label: 'ZERO STOCK', style: 'outlined', color: '#DC2626', icon: 'x' },
  /* BOM pipeline */
  'normalised':     { label: 'NORMALISED', style: 'outlined', color: '#0891B2', icon: 'check' },
  'packaged':       { label: 'READY FOR PROCUREMENT', style: 'filled', color: '#16A34A', icon: 'check' },
  'results':        { label: 'SOURCED', style: 'outlined', color: '#16A34A', icon: 'check' },
  'exceptions':     { label: 'EXCEPTIONS', style: 'filled', color: '#DC2626', icon: 'alert' },
  'sourcing-run':   { label: 'SOURCING', style: 'outlined', color: '#0891B2', icon: 'refresh', spin: true },
  'validating':     { label: 'VALIDATING', style: 'outlined', color: '#0891B2', icon: 'refresh', spin: true },
  'pending':        { label: 'PENDING', style: 'outlined', color: '#64748B', icon: 'clock' },
  'active-good':    { label: 'ACTIVE', style: 'outlined', color: '#16A34A', icon: 'check' },
  'inactive':       { label: 'INACTIVE', style: 'outlined', color: '#64748B', icon: 'ban' },
  'intern':         { label: 'INTERN', style: 'outlined', color: '#D97706', icon: 'user' },
  /* Development objects */
  'inv-open':       { label: 'OPEN', style: 'outlined', color: '#059669', icon: 'circle' },
  'inv-analysis':   { label: 'ANALYSIS', style: 'outlined', color: '#059669', icon: 'refresh', spin: true },
  'inv-findings':   { label: 'FINDINGS', style: 'filled', color: '#059669', icon: 'check' },
  'inv-closed':     { label: 'CLOSED', style: 'outlined', color: '#64748B', icon: 'check' },
  'rec-draft':      { label: 'DRAFT', style: 'outlined', color: '#64748B', icon: 'circle' },
  'rec-pushed':     { label: 'AWAITING DESIGNER', style: 'outlined', color: '#7C3AED', icon: 'arrow' },
  'rec-accepted':   { label: 'ACCEPTED', style: 'filled', color: '#16A34A', icon: 'check' },
  'rec-rejected':   { label: 'REJECTED', style: 'filled', color: '#DC2626', icon: 'x' },
  'rec-investigating': { label: 'INVESTIGATING', style: 'outlined', color: '#D97706', icon: 'refresh', spin: true },
  'rw-draft':       { label: 'DRAFT', style: 'outlined', color: '#64748B', icon: 'circle' },
  'rw-pushed':      { label: 'AWAITING PRODUCTION', style: 'outlined', color: '#0891B2', icon: 'arrow' },
  'rw-inprogress':  { label: 'IN PROGRESS', style: 'outlined', color: '#0891B2', icon: 'refresh', spin: true },
  'rw-validated':   { label: 'VALIDATED', style: 'filled', color: '#16A34A', icon: 'check' },
  'rw-returned':    { label: 'RETURNED', style: 'outlined', color: '#059669', icon: 'arrow' },
  'fw-draft':       { label: 'DRAFT', style: 'outlined', color: '#64748B', icon: 'circle' },
  'fw-released':    { label: 'RELEASED', style: 'outlined', color: '#059669', icon: 'check' },
  'fw-validating':  { label: 'VALIDATING', style: 'outlined', color: '#0891B2', icon: 'refresh', spin: true },
  'fw-validated':   { label: 'VALIDATED', style: 'filled', color: '#16A34A', icon: 'check' },
  /* Development Collection states (kind=development) */
  'dc-draft':       { label: 'DRAFT', style: 'outlined', color: '#64748B', icon: 'circle' },
  'dc-active':      { label: 'ACTIVE', style: 'outlined', color: '#059669', icon: 'refresh', spin: true },
  'dc-ready':       { label: 'READY FOR REVIEW', style: 'outlined', color: '#059669', icon: 'check' },
  'dc-rec-sent':    { label: 'RECOMMENDATION SENT', style: 'outlined', color: '#059669', icon: 'send' },
  'dc-accepted':    { label: 'ACCEPTED', style: 'filled', color: '#059669', icon: 'check' },
  'dc-rejected':    { label: 'REJECTED', style: 'filled', color: '#DC2626', icon: 'x' },
  'dc-closed':      { label: 'CLOSED', style: 'outlined', color: '#64748B', icon: 'check' },
  'dc-archived':    { label: 'ARCHIVED', style: 'outlined', color: '#475569', icon: 'box' },
};

/* Map a Development Collection state → badge key */
const DC_BADGE = { draft: 'dc-draft', active: 'dc-active', ready: 'dc-ready',
  'recommendation-sent': 'dc-rec-sent', accepted: 'dc-accepted', rejected: 'dc-rejected',
  closed: 'dc-closed', archived: 'dc-archived' };
window.DC_BADGE = DC_BADGE;
/* Map a BOM lifecycle state → badge key */
const BOM_BADGE = { draft: 'draft', validated: 'validated', validating: 'validating', sourcing: 'sourcing-run',
  results: 'results', exceptions: 'exceptions', normalised: 'normalised', packaged: 'packaged', submitted: 'submitted',
  approved: 'approved', ordered: 'ordered', shipped: 'shipped', rejected: 'rejected' };
window.BOM_BADGE = BOM_BADGE;

function StatusBadge({ status, size }) {
  const s = STATUS[status];
  if (!s) return null;
  const isFilled = s.style === 'filled';
  const st = isFilled ? { background: s.color, borderColor: s.color } : { color: s.color };
  return (
    <span className={`badge ${s.style}`} style={st}>
      <Icon name={s.icon} size={12} sw={2.4} className={s.spin ? 'spin' : ''} />
      {s.label}
    </span>
  );
}

const ROLE = {
  designer:    { label: 'DESIGNER',    color: 'var(--role-designer)' },
  production:  { label: 'PRODUCTION',  color: 'var(--role-production)' },
  purchasing:  { label: 'PURCHASING',  color: 'var(--role-purchasing)' },
  development: { label: 'DEVELOPMENT', color: 'var(--role-development)' },
  admin:       { label: 'ADMIN',       color: '#475569' },
  manager:     { label: 'MANAGER',     color: '#0D9488' },
  executive:   { label: 'EXECUTIVE',   color: '#475569' },
  readonly:    { label: 'READ-ONLY',   color: '#64748B' },
};
function RoleTag({ role }) {
  const r = ROLE[role]; if (!r) return null;
  return <span className="tag role-tag" style={{ background: r.color }}>{r.label}</span>;
}
function RoleDot({ role, size = 8 }) {
  const r = ROLE[role] || ROLE.designer;
  return <span className="dot" style={{ background: r.color, width: size, height: size }} />;
}
function SupplierTag({ supplier }) {
  const map = { mouser: { label: 'MOUSER', c: 'var(--supplier-mouser)' }, digikey: { label: 'DIGIKEY', c: 'var(--supplier-digikey)' } };
  const s = map[supplier]; if (!s) return null;
  return <span className="tag" style={{ background: s.c, color: '#fff' }}>{s.label}</span>;
}

/* =========================================================
   TRACEABILITY STRIP — required on every detail view
   ========================================================= */
function TraceabilityStrip({ name, status, creator, role, project, updated, updatedBy, recordId, onProject, onRecord }) {
  return (
    <div className="trace">
      <span className="tr-name">{name}</span>
      {status && <StatusBadge status={status} />}
      <span className="tr-sep" />
      <span>Created by <strong style={{ fontWeight: 600 }}>{creator}</strong></span>
      <RoleTag role={role} />
      <span className="tr-sep" />
      <span className="chip" onClick={onProject}><Icon name="folder" size={13} /> {project}</span>
      <span className="tr-sep" />
      <span className="muted">Updated {updated}{updatedBy ? ` by ${updatedBy}` : ''}</span>
      {recordId && <><span className="tr-sep" /><span className="tr-id" onClick={onRecord}>{recordId}</span></>}
    </div>
  );
}

/* =========================================================
   Small reusable bits
   ========================================================= */
function Banner({ kind = 'lock', icon, title, children, actions }) {
  const defIcon = { lock: 'lock', warn: 'alert', danger: 'alert', info: 'info' }[kind];
  return (
    <div className={`banner ${kind}`}>
      <Icon name={icon || defIcon} size={17} />
      <div style={{ flex: 1 }}>
        {title && <div className="bn-title">{title}</div>}
        <div className="bn-body">{children}</div>
      </div>
      {actions && <div className="bn-actions">{actions}</div>}
    </div>
  );
}

function Freshness({ ts, stale }) {
  return (
    <span className={`fresh${stale ? ' stale' : ''}`}>
      <Icon name={stale ? 'alert' : 'clock'} size={12} /> {stale ? 'Stale · ' : ''}Updated {ts}
    </span>
  );
}

function Avatar({ name, role, size = 30 }) {
  const initials = name.split(' ').map(w => w[0]).slice(0, 2).join('');
  const bg = (ROLE[role] || ROLE.designer).color;
  return <span className="avatar" style={{ background: bg, width: size, height: size, fontSize: size * .4 }}>{initials}</span>;
}

/* Lightweight popover that positions under an anchor and closes on outside click */
function Popover({ anchorRef, open, onClose, children, align = 'left', width }) {
  const ref = useRef(null);
  const [pos, setPos] = useState(null);
  useLayoutEffect(() => {
    if (open && anchorRef.current) {
      const r = anchorRef.current.getBoundingClientRect();
      setPos({ top: r.bottom + 6, left: align === 'right' ? r.right - (width || 240) : r.left });
    }
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const h = (e) => { if (ref.current && !ref.current.contains(e.target) && anchorRef.current && !anchorRef.current.contains(e.target)) onClose(); };
    const k = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('mousedown', h); document.addEventListener('keydown', k);
    return () => { document.removeEventListener('mousedown', h); document.removeEventListener('keydown', k); };
  }, [open]);
  if (!open || !pos) return null;
  return <div ref={ref} className="menu" style={{ top: pos.top, left: pos.left, minWidth: width || 240 }}>{children}</div>;
}

function EmptyState({ icon = 'inbox', title, sub, actions }) {
  return (
    <div className="empty">
      <div className="em-icon"><Icon name={icon} size={24} /></div>
      <div className="em-title">{title}</div>
      {sub && <div className="em-sub">{sub}</div>}
      {actions && <div className="em-actions">{actions}</div>}
    </div>
  );
}

/* RelatedLinks — direct links to related objects on a detail view (no dead ends). */
function RelatedLinks({ items }) {
  const real = items.filter(Boolean);
  if (!real.length) return null;
  return (
    <div className="related">
      <span className="related-label"><Icon name="link" size={13} /> Related</span>
      {real.map((it, i) => (
        <button key={i} className="related-chip" onClick={it.onClick}>
          <Icon name={it.icon || 'arrow'} size={13} />
          <span className="related-kind">{it.kind}</span>
          <span className="related-val">{it.label}</span>
        </button>
      ))}
    </div>
  );
}

Object.assign(window, {
  Icon, StatusBadge, STATUS, RoleTag, RoleDot, SupplierTag, ROLE,
  TraceabilityStrip, Banner, Freshness, Avatar, Popover, EmptyState, RelatedLinks,
});
