/* AutoBOM — seed data for the shared workflow store.
   One connected dataset: parts → collections → BOMs → requests → orders,
   plus users, notifications, audit, suppliers, system config. */

const fmtUSD = (n) => '$' + (n || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/* Unit prices, not totals. Component unit costs are routinely sub-cent — a 0603
   resistor is ~$0.0081 at DigiKey and less at volume — and fmtUSD's fixed 2
   decimals rendered every one of them as "$0.00", which reads as "no price
   data". Totals keep fmtUSD; only per-part unit prices use this. */
function fmtUnitPrice(n) {
  const v = typeof n === 'number' ? n : parseFloat(String(n == null ? '' : n).replace(/[$,\s]/g, ''));
  if (!Number.isFinite(v)) return '—';
  if (v === 0) return '$0.00';
  const dp = v < 0.01 ? 4 : 2;      // enough to distinguish 0.0081 from 0.0024
  return '$' + v.toLocaleString('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp });
}

/* Supplier unit_price arrives as "$0.10" (Mouser) or "0.0081" (DigiKey). */
function parsePrice(v) {
  const n = parseFloat(String(v == null ? '' : v).replace(/[$,\s]/g, ''));
  return Number.isFinite(n) ? n : null;
}
const fmtInt = (n) => (n || 0).toLocaleString('en-US');
/* Null-safe relative-time label. Timestamps can legitimately be absent (a row
   that has never been touched), and interpolating them raw printed literal
   "null" into the UI — "in queue null", "uploaded null", "Created ·". */
const fmtWhen = (v) => (v == null || v === '' ? '—' : v);
const uid = (p) => p + '-' + Math.random().toString(36).slice(2, 7);

/* ---- Component catalog keyed by MPN ---- */
const CATALOG = {
  'IRFB4110PBF': { mpn: 'IRFB4110PBF', mfr: 'Infineon', desc: 'MOSFET N-Ch 100V 180A TO-220AB', lifecycle: 'active',
    mouser: { pn: '942-IRFB4110PBF', stock: 4216, price: 1.92, url: '#' }, digikey: { pn: 'IRFB4110PBF-ND', stock: 8104, price: 1.87, url: '#' }, recommend: 'mouser', fresh: '6 min ago', stale: false },
  'TPS54560DDAR': { mpn: 'TPS54560DDAR', mfr: 'Texas Instruments', desc: 'Buck Converter 60V 5A SO-8 PowerPAD', lifecycle: 'active',
    mouser: { pn: '595-TPS54560DDAR', stock: 1890, price: 2.41, url: '#' }, digikey: { pn: '296-38814-1-ND', stock: 612, price: 2.58, url: '#' }, recommend: 'mouser', fresh: '11 min ago', stale: false },
  'UCC27201ADR': { mpn: 'UCC27201ADR', mfr: 'Texas Instruments', desc: 'Half-Bridge Gate Driver 120V 3A SOIC-8', lifecycle: 'active',
    mouser: { pn: '595-UCC27201ADR', stock: 0, price: 1.74, url: '#' }, digikey: { pn: '296-28649-1-ND', stock: 3320, price: 1.69, url: '#' }, recommend: 'digikey', fresh: '8 min ago', stale: false },
  'LM2596S-5.0': { mpn: 'LM2596S-5.0', mfr: 'onsemi', desc: 'Buck Regulator 5V 3A TO-263', lifecycle: 'obsolete',
    mouser: { pn: '863-LM2596S-5.0', stock: 0, price: 0, url: '#' }, digikey: { pn: 'LM2596S-5.0-ND', stock: 0, price: 0, url: '#' }, recommend: null, fresh: '2 min ago', stale: false, note: 'Manufacturer lifecycle: EOL. Last-time-buy passed 2024-11.' },
  'C3216X7R1H105K160AB': { mpn: 'C3216X7R1H105K160AB', mfr: 'TDK', desc: 'Cap Ceramic 1µF 50V X7R 1206', lifecycle: 'active',
    mouser: { pn: '810-C3216X7R1H105K', stock: 142000, price: 0.18, url: '#' }, digikey: { pn: '445-1421-1-ND', stock: 98500, price: 0.19, url: '#' }, recommend: 'mouser', fresh: '27 h ago', stale: true },
  'GRM188R71H104KA93D': { mpn: 'GRM188R71H104KA93D', mfr: 'Murata', desc: 'Cap Ceramic 0.1µF 50V X7R 0603', lifecycle: 'active',
    mouser: { pn: '81-GRM188R71H104KA93', stock: 503000, price: 0.012, url: '#' }, digikey: { pn: '490-1532-1-ND', stock: 720000, price: 0.011, url: '#' }, recommend: 'digikey', fresh: '14 min ago', stale: false },
  'STM32G431CBT6': { mpn: 'STM32G431CBT6', mfr: 'STMicroelectronics', desc: 'MCU Arm Cortex-M4 170MHz LQFP-48', lifecycle: 'active',
    mouser: { pn: '511-STM32G431CBT6', stock: 980, price: 4.12, url: '#' }, digikey: { pn: '497-STM32G431CBT6-ND', stock: 1240, price: 4.05, url: '#' }, recommend: 'mouser', fresh: '9 min ago', stale: false },
  '0039281043': { mpn: '0039281043', mfr: 'Molex', desc: 'Mini-Fit Jr. Header 4-pos 4.2mm R/A', lifecycle: 'active',
    mouser: { pn: '538-39-28-1043', stock: 24800, price: 0.41, url: '#' }, digikey: { pn: 'WM3702-ND', stock: 31200, price: 0.39, url: '#' }, recommend: 'mouser', fresh: '19 min ago', stale: false },
  'BAT54S-7-F': { mpn: 'BAT54S-7-F', mfr: 'Diodes Inc', desc: 'Schottky Diode Array 30V SOT-23', lifecycle: 'active',
    mouser: { pn: '621-BAT54S-7-F', stock: 88000, price: 0.06, url: '#' }, digikey: { pn: 'BAT54S-FDICT-ND', stock: 120000, price: 0.05, url: '#' }, recommend: 'digikey', fresh: '21 min ago', stale: false },
  'ERJ-3EKF1002V': { mpn: 'ERJ-3EKF1002V', mfr: 'Panasonic', desc: 'Res 10k 1% 1/10W 0603', lifecycle: 'active',
    mouser: { pn: '667-ERJ-3EKF1002V', stock: 940000, price: 0.004, url: '#' }, digikey: { pn: 'P10.0KHCT-ND', stock: 1200000, price: 0.003, url: '#' }, recommend: 'mouser', fresh: '15 min ago', stale: false },
};

const PROJECTS = {
  'tvca-rev2': { id: 'tvca-rev2', name: 'TVCA Rev 2', identifier: 'R2', lead: 'Aaron Jones', program_id: 'terra-voyager', desc: 'Traction voltage control assembly, second revision.', status: 'active', created: 'May 2' },
  'gate-eval': { id: 'gate-eval', name: 'Gate Driver Eval', identifier: 'EVAL', lead: 'Aaron Jones', program_id: 'gatekeeper', desc: 'Evaluation of half-bridge gate driver candidates.', status: 'active', created: 'Jun 1' },
  'wall-q2':   { id: 'wall-q2', name: 'Wall Replenishment', identifier: 'Q2', lead: 'Maria Chen', program_id: 'restock', desc: 'Quarterly restock of build-wall passives & connectors.', status: 'active', created: 'Apr 12' },
  'bldc':      { id: 'bldc', name: 'BLDC Motor Controller', identifier: 'MC1', lead: 'Aaron Jones', program_id: 'motor-control', desc: 'Brushless DC motor controller platform.', status: 'active', created: 'Jun 8' },
  'tvca-psu':  { id: 'tvca-psu', name: 'TVCA Power Supply v2', identifier: 'PSU', lead: 'Maria Chen', program_id: 'terra-voyager', desc: 'Auxiliary power supply board for TVCA Rev 2.', status: 'active', created: 'Jun 11' },
  'md-stage':  { id: 'md-stage', name: 'Motor Driver Stage', identifier: 'MD', lead: 'Maria Chen', program_id: 'motor-control', desc: 'Half-bridge motor driver power stage board.', status: 'active', created: 'Jun 15' },
  'sensor-a-draft': { id: 'sensor-a-draft', name: 'Sensor Board Rev A (draft)', identifier: 'SBA', lead: 'Maria Chen', program_id: 'motor-control', desc: 'Sensor front-end board — draft revision under bring-up.', status: 'active', created: 'Today' },
};

/* ---- Users (Admin workspace) ---- */
const USERS = [
  { id: 'u-aaron', name: 'Aaron Jones', email: 'aaron.jones@yanktech.com', roles: ['designer', 'production'], primaryRole: 'designer', overrides: ['dev.investigation.create', 'dev.rework.create'], active: true, intern: false, lastActive: '2 min ago', created: 'Jan 14, 2025', createdAt: 'Jan 14, 2025', invitedBy: null, title: 'Senior Hardware Engineer' },
  { id: 'u-maria', name: 'Maria Chen', email: 'maria.chen@yanktech.com', roles: ['production'], primaryRole: 'production', overrides: [], active: true, intern: false, lastActive: '18 min ago', created: 'Feb 3, 2025', createdAt: 'Feb 3, 2025', invitedBy: 'u-grace', title: 'Production Engineer' },
  { id: 'u-david', name: 'David Okafor', email: 'david.okafor@yanktech.com', roles: ['production'], primaryRole: 'production', overrides: [], active: true, intern: false, lastActive: '1 h ago', created: 'Jan 14, 2025', createdAt: 'Jan 14, 2025', invitedBy: 'u-grace', title: 'Procurement Lead' },
  { id: 'u-sara',  name: 'Sara Lindqvist', email: 'sara.l@yanktech.com', roles: ['designer'], primaryRole: 'designer', overrides: [], active: true, intern: false, lastActive: 'Yesterday', created: 'Mar 22, 2025', createdAt: 'Mar 22, 2025', invitedBy: 'u-grace', title: 'Hardware Engineer' },
  { id: 'u-tom',   name: 'Tom Becker', email: 'tom.becker@yanktech.com', roles: ['designer'], primaryRole: 'designer', overrides: [], active: true, intern: true, lastActive: '3 h ago', created: 'Jun 2, 2025', createdAt: 'Jun 2, 2025', invitedBy: 'u-aaron', title: 'Engineering Intern' },
  { id: 'u-priya', name: 'Priya Nair', email: 'priya.nair@yanktech.com', roles: ['manager'], primaryRole: 'manager', overrides: [], active: true, intern: false, lastActive: '5 h ago', created: 'Jan 14, 2025', createdAt: 'Jan 14, 2025', invitedBy: null, title: 'Engineering Manager' },
  { id: 'u-leo',   name: 'Leo Vargas', email: 'leo.vargas@yanktech.com', roles: ['readonly'], primaryRole: 'readonly', overrides: [], active: true, intern: false, lastActive: '2 days ago', created: 'May 30, 2025', createdAt: 'May 30, 2025', invitedBy: 'u-grace', title: 'Operations Analyst' },
  { id: 'u-grace', name: 'Grace Hill', email: 'grace.hill@yanktech.com', roles: ['admin'], primaryRole: 'admin', overrides: [], active: true, intern: false, lastActive: '40 min ago', created: 'Jan 14, 2025', createdAt: 'Jan 14, 2025', invitedBy: null, title: 'IT / Systems Admin' },
  { id: 'u-quinn', name: 'Quinn Alvarez', email: 'quinn.a@yanktech.com', roles: ['readonly'], primaryRole: 'readonly', overrides: [], active: false, intern: false, lastActive: '3 weeks ago', created: 'Apr 1, 2025', createdAt: 'Apr 1, 2025', invitedBy: 'u-grace', title: 'Contractor (offboarded)' },
  { id: 'u-noah', name: 'Noah Park', email: 'noah.park@yanktech.com', roles: ['development'], primaryRole: 'development', overrides: [], active: true, intern: false, lastActive: '7 min ago', created: 'Feb 11, 2025', createdAt: 'Feb 11, 2025', invitedBy: 'u-grace', title: 'Reliability Engineer' },
  { id: 'u-ava', name: 'Ava Patel', email: 'ava.patel@yanktech.com', roles: ['development'], primaryRole: 'development', overrides: ['part.search'], active: true, intern: false, lastActive: '22 min ago', created: 'Mar 5, 2025', createdAt: 'Mar 5, 2025', invitedBy: 'u-grace', title: 'Firmware Engineer' },
];
function userByName(name) { return USERS.find(u => u.name === name) || null; }
function userById(id) { return USERS.find(u => u.id === id) || null; }

/* line item builder */
function line(no, mpn, qty, status, opts = {}) {
  const c = CATALOG[mpn] || {};
  const sup = status === 'sourced-digikey' ? 'digikey' : status === 'sourced-mouser' ? 'mouser' : (opts.supplier || null);
  const off = sup && c[sup];
  const unit = off ? off.price : (opts.unit ?? null);
  return { no, mpn, mfr: c.mfr || opts.mfr || '—', desc: c.desc || opts.desc || '—', qty, status,
    supplier: sup, supplierPn: off ? off.pn : null, unit, ext: unit != null ? +(unit * qty).toFixed(2) : null,
    fresh: c.fresh, stale: c.stale || false, source: opts.source || null, sourceBy: opts.sourceBy || null,
    note: opts.note || null, exReason: opts.exReason || null, replacement: opts.replacement || null };
}

/* ---- Collections (Designer) ---- */
const COLLECTIONS = [
  { id: 'COL-031', name: 'TVCA Connector Research', project: 'tvca-rev2', state: 'active', creator: 'Aaron Jones', ownerId: 'u-aaron', role: 'designer', updated: '2h ago', updatedBy: 'Aaron Jones', created: 'Jun 12',
    desc: 'Evaluating power + signal interconnect options for the TVCA Rev 2 main board.',
    items: [ line(1, '0039281043', 12, 'sourced-mouser'), line(2, 'IRFB4110PBF', 8, 'sourced-digikey'), line(3, 'TPS54560DDAR', 4, 'sourced-mouser'),
      line(4, 'C3216X7R1H105K160AB', 40, 'needs-review', { note: 'Supplier data >24h old — re-check before ordering.' }), line(5, 'UCC27201ADR', 6, 'check-wall') ] },
  { id: 'COL-028', name: 'Buck Converter Investigation', project: 'tvca-rev2', state: 'order-requested', creator: 'Aaron Jones', ownerId: 'u-aaron', role: 'designer', updated: '1d ago', updatedBy: 'Aaron Jones', created: 'Jun 9', reqId: 'REQ-018',
    desc: 'R&D buy for buck-converter bring-up boards.',
    items: [ line(1, 'TPS54560DDAR', 10, 'sourced-mouser'), line(2, 'GRM188R71H104KA93D', 200, 'sourced-digikey'), line(3, 'STM32G431CBT6', 5, 'sourced-mouser') ] },
  { id: 'COL-024', name: 'Gate Driver Options', project: 'gate-eval', state: 'active', creator: 'Aaron Jones', ownerId: 'u-aaron', role: 'designer', updated: '4h ago', updatedBy: 'Aaron Jones', created: 'Jun 6',
    desc: 'Comparing half-bridge gate driver candidates for the TVCA power stage.',
    items: [ line(1, 'UCC27201ADR', 6, 'needs-review', { note: 'Zero stock at recommended supplier (Mouser) — must be resolved before Request to Order.' }), line(2, 'IRFB4110PBF', 12, 'sourced-digikey') ] },
  { id: 'COL-019', name: 'Wall Replenishment Q2', project: 'wall-q2', state: 'ordered', creator: 'Aaron Jones', ownerId: 'u-aaron', role: 'designer', updated: '3d ago', updatedBy: 'David Okafor', created: 'May 30', reqId: 'REQ-009', poId: 'PO-2041',
    desc: 'Restock of common passives and connectors for the build wall.',
    items: [ line(1, 'GRM188R71H104KA93D', 5000, 'sourced-digikey'), line(2, 'C3216X7R1H105K160AB', 2000, 'sourced-mouser'), line(3, '0039281043', 300, 'sourced-mouser') ] },
  { id: 'COL-033', name: 'Sensor Front-End', project: 'bldc', state: 'active', creator: 'Aaron Jones', ownerId: 'u-aaron', role: 'designer', updated: '20m ago', updatedBy: 'Aaron Jones', created: 'Today', desc: 'New research space — no parts added yet.', items: [] },
  /* Development Collections — emerald, category-tagged, outcome-producing */
  { id: 'DCOL-008', name: 'MOSFET Efficiency Improvement', project: 'tvca-rev2', state: 'ready', role: 'development',
    creator: 'Noah Park', ownerId: 'u-noah', category: 'Investigation', updated: '40m ago', updatedBy: 'Noah Park', created: 'Jun 14',
    desc: 'Comparing low-RDSon replacements for IRFB4110PBF. Goal: lower thermal headroom + cheaper BOM.',
    outcomes: [], notes: 'IPB014N06N looks best on bench — drop-in footprint, 30% lower conduction loss.',
    items: [
      line(1, 'IRFB4110PBF', 1, 'sourced-mouser', { note: 'Current part — baseline 4.5mΩ RDSon.' }),
      line(2, 'IPB014N06N', 1, 'sourced-mouser', { note: 'Candidate A — 3.0mΩ, identical TO-220, +$0.04.' }),
      line(3, 'IRFP4568PBF', 1, 'sourced-digikey', { note: 'Candidate B — 4.8mΩ, higher current rating but pricier.' }),
    ] },
  { id: 'DCOL-007', name: 'Bulk Cap Reliability Study', project: 'bldc', state: 'recommendation-sent', role: 'development',
    creator: 'Noah Park', ownerId: 'u-noah', category: 'Reliability', updated: 'Yesterday', updatedBy: 'Noah Park', created: 'Jun 8',
    desc: 'Field returns linked to under-sized bulk cap (INV-013). Evaluating replacement candidates and supply-side hardening.',
    outcomes: [
      { id: 'OUT-019', kind: 'rework', label: 'Rework Package', targetRole: 'production', linkedId: 'RWK-006', when: 'Jun 15', state: 'pushed' },
      { id: 'OUT-020', kind: 'recommendation', label: 'Improvement Recommendation', targetRole: 'designer', linkedId: 'REC-021', when: 'Jun 12', state: 'accepted' },
    ],
    notes: 'Tantalum + soft-start works. Recommend 47µF tantalum on dev fleet, then roll into Rev C.',
    items: [
      line(1, 'GRM188R71H104KA93D', 1, 'sourced-digikey', { note: 'Current 10µF — too small under inrush.' }),
      line(2, 'TPSE476K025R0150', 1, 'sourced-mouser', { note: 'Candidate 47µF tantalum, ESR 150mΩ — passes bench.' }),
    ] },
  { id: 'DCOL-006', name: 'BLDC Firmware v1.5 — Dual-Encoder Validation', project: 'bldc', state: 'active', role: 'development',
    creator: 'Ava Patel', ownerId: 'u-ava', category: 'Firmware', updated: '4h ago', updatedBy: 'Ava Patel', created: 'Jun 16',
    desc: 'Validating dual-encoder HAL on three bring-up units before pushing FW-1.5 for production validation.',
    outcomes: [], notes: 'Unit 2 throws encoder-sync warnings on cold-boot — needs investigation.', items: [] },
  { id: 'DCOL-005', name: 'Connector Supplier Evaluation', project: 'tvca-rev2', state: 'closed', role: 'development',
    creator: 'Noah Park', ownerId: 'u-noah', category: 'Supplier Evaluation', updated: 'Jun 10', updatedBy: 'Noah Park', created: 'May 22',
    desc: 'Evaluated 3 alternative connector suppliers. Recommended sticking with Molex.',
    outcomes: [{ id: 'OUT-014', kind: 'investigation-report', label: 'Investigation Report', targetRole: 'designer', linkedId: 'REC-018', when: 'Jun 8', state: 'rejected' }],
    notes: 'Closed — no change recommended for Rev 2. Revisit for Rev 3.',
    items: [
      line(1, '0039281043', 1, 'sourced-mouser', { note: 'Current Molex — baseline.' }),
      line(2, '0039301043', 1, 'sourced-mouser', { note: 'Alt connector — different footprint, not pin-compatible.' }),
    ] },
  { id: 'DCOL-009', name: 'Cost Reduction — Passives Sweep', project: 'tvca-rev2', state: 'draft', role: 'development',
    creator: 'Noah Park', ownerId: 'u-noah', category: 'Cost Reduction', updated: '5m ago', updatedBy: 'Noah Park', created: 'Today',
    desc: 'Identifying lower-cost passives without compromising spec margin.', outcomes: [], notes: '', items: [] },
];

/* ---- BOMs (Production pipeline) ---- */
function bomLines(arr) { return arr; }
const BOMS = [
  { id: 'BOM-055', name: 'Sensor Board Rev A', project: 'bldc', state: 'validated', creator: 'Maria Chen', ownerId: 'u-maria', role: 'production',
    updated: '35m ago', updatedBy: 'Maria Chen', created: 'Today', buildQty: 25, overage: 5, sourceCollection: 'COL-033',
    validation: { errors: 0, warnings: 2, notes: ['Line 4: quantity inferred from reference designators (4 → 4).', 'Lines 6–7: duplicate MPN consolidated.'] },
    items: bomLines([ line(1, 'STM32G431CBT6', 25, 'validated'), line(2, 'GRM188R71H104KA93D', 500, 'validated'),
      line(3, 'ERJ-3EKF1002V', 800, 'validated'), line(4, 'BAT54S-7-F', 50, 'validated'), line(5, 'TPS54560DDAR', 25, 'validated') ]) },
  { id: 'BOM-052', name: 'TVCA Main BOM v3', project: 'tvca-rev2', state: 'exceptions', creator: 'Aaron Jones', ownerId: 'u-aaron', role: 'production',
    updated: '38m ago', updatedBy: 'David sourced 41 of 44 lines', created: 'Jun 14', buildQty: 50, overage: 10, sourceCollection: 'COL-031',
    pushback: { by: 'Maria Chen', when: '38m ago', to: 'Aaron Jones', reason: 'eol', urgency: 'blocking',
      note: 'IRFB4110PBF may be discontinued — please confirm or supply a replacement. UCC27201ADR is zero-stock at the recommended supplier.', loop: 1,
      flaggedLines: [ { lineNo: 2, exReason: 'Possible EOL — confirm lifecycle or replace.', comments: [] }, { lineNo: 3, exReason: 'Zero stock at recommended supplier.', comments: [] }, { lineNo: 4, exReason: 'Stale pricing — re-check.', comments: [] } ],
      addedComponentRequest: null, recommendation: null, comments: [] },
    items: bomLines([ line(1, '0039281043', 50, 'sourced-mouser', { source: 'COL-031', sourceBy: 'Aaron Jones' }),
      line(2, 'IRFB4110PBF', 200, 'needs-review', { source: 'COL-031', sourceBy: 'Aaron Jones', exReason: 'Possible EOL — confirm lifecycle or replace.' }),
      line(3, 'UCC27201ADR', 100, 'needs-review', { source: 'COL-031', sourceBy: 'Aaron Jones', exReason: 'Zero stock at recommended supplier.' }),
      line(4, 'C3216X7R1H105K160AB', 400, 'needs-review', { source: 'COL-031', sourceBy: 'Aaron Jones', exReason: 'Stale pricing — re-check.' }),
      line(5, 'GRM188R71H104KA93D', 2000, 'sourced-digikey'), line(6, 'ERJ-3EKF1002V', 3000, 'sourced-mouser'), line(7, 'TPS54560DDAR', 50, 'sourced-mouser') ]) },
  { id: 'BOM-051', name: 'Motor Driver Stage', project: 'md-stage', state: 'results', creator: 'Maria Chen', ownerId: 'u-maria', role: 'production',
    updated: '1h ago', updatedBy: 'Maria Chen', created: 'Jun 15', buildQty: 30, overage: 10, sourceCollection: null, partsbox: null,
    items: bomLines([ line(1, 'IRFB4110PBF', 120, 'sourced-mouser'), line(2, 'UCC27201ADR', 60, 'sourced-digikey'),
      line(3, 'STM32G431CBT6', 30, 'sourced-mouser'), line(4, 'GRM188R71H104KA93D', 600, 'sourced-digikey'), line(5, 'ERJ-3EKF1002V', 900, 'sourced-mouser') ]) },
  { id: 'BOM-048', name: 'Power Supply v2', project: 'tvca-psu', state: 'submitted', creator: 'Maria Chen', ownerId: 'u-maria', role: 'production',
    updated: '5h ago', updatedBy: 'Maria Chen', created: 'Jun 11', buildQty: 40, overage: 5, reqId: 'REQ-016', partsbox: 'PB-PSU-V2',
    items: bomLines([ line(1, 'TPS54560DDAR', 40, 'sourced-mouser'), line(2, 'C3216X7R1H105K160AB', 320, 'sourced-mouser'),
      line(3, 'GRM188R71H104KA93D', 800, 'sourced-digikey'), line(4, 'BAT54S-7-F', 80, 'sourced-digikey') ]) },
  { id: 'BOM-060', name: 'Sensor Board Rev A — draft', project: 'sensor-a-draft', state: 'draft', creator: 'Maria Chen', ownerId: 'u-maria', role: 'production',
    updated: 'just now', updatedBy: 'Maria Chen', created: 'Today', buildQty: null, overage: null, items: [] },
];

/* ---- Procurement Requests (Purchasing inbox) ---- */
const REQUESTS = [
  { id: 'REQ-018', title: 'Buck Converter Investigation', kind: 'collection', sourceId: 'COL-028', project: 'tvca-rev2',
    from: 'Aaron Jones', fromRole: 'designer', submitted: 'Yesterday', age: 28, critical: true, bucketState: 'QUEUED_CRITICAL', note: 'R&D bring-up — blocking bench work. Budget code TVCA-RND-02.', resubmit: false,
    items: COLLECTIONS[1].items },
  { id: 'REQ-016', title: 'Power Supply v2', kind: 'bom', sourceId: 'BOM-048', project: 'tvca-psu',
    from: 'Maria Chen', fromRole: 'production', submitted: '5h ago', age: 5, critical: false, bucketState: 'QUEUED_MAIN', note: 'Validated and fully sourced. PartsBox PB-PSU-V2 created. Production build qty 40 + 5% overage.', resubmit: false,
    items: BOMS[3].items },
  { id: 'REQ-012', title: 'Motor Driver Stage', kind: 'bom', sourceId: 'BOM-051', project: 'md-stage',
    from: 'Maria Chen', fromRole: 'production', submitted: 'Jun 16', age: 2, critical: false, bucketState: 'WRITTEN', note: 'All lines sourced. Written to the Daily Purchasing List.', resubmit: false,
    items: BOMS[2].items },
  { id: 'REQ-009', title: 'Wall Replenishment Q2', kind: 'collection', sourceId: 'COL-019', project: 'wall-q2',
    from: 'Aaron Jones', fromRole: 'designer', submitted: 'May 30', age: 0, critical: false, bucketState: 'PURCHASED', note: 'Standard quarterly restock.', resubmit: false,
    items: COLLECTIONS[3].items },
];

/* ---- Development objects: Investigations, Improvement Recommendations, Rework Packages, Firmware Releases ---- */
const INVESTIGATIONS = [
  { id: 'INV-014', title: 'Field unit FA-2207 — gate driver failure', kind: 'investigation', project: 'tvca-rev2',
    owner: 'Noah Park', ownerId: 'u-noah', role: 'development', assignee: 'Noah Park',
    state: 'analysis', updated: '32m ago', created: 'Jun 14', priority: 'high',
    desc: 'Returned TVCA Rev 2 unit failed under load. Initial scope: UCC27201ADR gate driver and surrounding network.',
    relatedBom: 'BOM-052', relatedCollection: 'COL-031',
    findings: ['Driver IC reads 0\u03a9 between VDD and GND', 'Schottky D7 shorted', 'Likely cascade failure'], pushedFrom: null },
  { id: 'INV-013', title: 'STM32G4 brown-out under inrush', kind: 'investigation', project: 'bldc',
    owner: 'Noah Park', ownerId: 'u-noah', role: 'development', assignee: 'Noah Park',
    state: 'findings', updated: '2h ago', created: 'Jun 12', priority: 'medium',
    desc: 'Production reported intermittent MCU resets on power-up. Need root cause and recommended supply hardening.',
    relatedBom: 'BOM-055', relatedCollection: null,
    findings: ['10\u03bcF bulk cap undersized', 'Brown-out threshold @ 2.7V triggers under inrush', 'Recommend 47\u03bcF + soft-start'],
    pushedFrom: { role: 'production', by: 'Maria Chen', when: '3d ago', note: 'MCU resets on \u224820% of cold boots. We can\u2019t reproduce reliably on the bench; need RCA.' } },
  { id: 'INV-011', title: 'EMI noise on motor drive harness', kind: 'investigation', project: 'bldc',
    owner: 'Noah Park', ownerId: 'u-noah', role: 'development', assignee: 'Noah Park',
    state: 'closed', updated: 'Jun 10', created: 'May 28', priority: 'low', desc: 'Closed: ferrite on harness solved it.', relatedBom: null, relatedCollection: null, findings: ['Common-mode choke on harness reduced EMI by 14dB'], pushedFrom: null },
];

const RECOMMENDATIONS = [
  { id: 'REC-022', title: 'Replace IRFB4110PBF with IPB014N06N (better RDSon)', kind: 'recommendation', project: 'tvca-rev2',
    owner: 'Noah Park', ownerId: 'u-noah', role: 'development', assignee: 'Noah Park',
    state: 'pushed', updated: '1h ago', created: 'Jun 16',
    desc: 'New Infineon part — same package, 30% lower RDSon, identical drive characteristics. Net BOM cost +$0.04/unit but cuts thermal headroom requirement significantly.',
    relatedBom: 'BOM-052', proposedMpn: 'IPB014N06N', currentMpn: 'IRFB4110PBF',
    pushedTo: { role: 'designer', toUserId: 'u-aaron', when: '1h ago' }, response: null },
  { id: 'REC-021', title: 'Switch buck inductor to Coilcraft XAL1010-103', kind: 'recommendation', project: 'tvca-rev2',
    owner: 'Noah Park', ownerId: 'u-noah', role: 'development', assignee: 'Noah Park',
    state: 'accepted', updated: 'Yesterday', created: 'Jun 12',
    desc: 'Better saturation behavior under load step. Drop-in.', relatedBom: 'BOM-048',
    pushedTo: { role: 'designer', toUserId: 'u-aaron', when: '2d ago' },
    response: { decision: 'accepted', by: 'Aaron Jones', when: 'Yesterday', note: 'Approved \u2014 will roll into next rev.' } },
  { id: 'REC-019', title: 'Add TVS on USB-C VBUS line', kind: 'recommendation', project: 'bldc',
    owner: 'Ava Patel', ownerId: 'u-ava', role: 'development', assignee: 'Ava Patel',
    state: 'investigating', updated: '4h ago', created: 'Jun 14',
    desc: 'Reports of ESD damage to USB block on dev units.', relatedBom: 'BOM-055',
    pushedTo: { role: 'designer', toUserId: 'u-sara', when: 'Jun 14' },
    response: { decision: 'investigating', by: 'Sara Lindqvist', when: '4h ago', note: 'Pulling test data \u2014 want to confirm root cause before accepting.' } },
  { id: 'REC-018', title: 'Move to RoHS-3 connector revision', kind: 'recommendation', project: 'tvca-rev2',
    owner: 'Noah Park', ownerId: 'u-noah', role: 'development', assignee: 'Noah Park',
    state: 'rejected', updated: 'Jun 11', created: 'Jun 8',
    desc: 'Newer connector revision available with improved retention force.', relatedBom: null,
    pushedTo: { role: 'designer', toUserId: 'u-aaron', when: 'Jun 9' },
    response: { decision: 'rejected', by: 'Aaron Jones', when: 'Jun 11', note: 'Footprint differs \u2014 not pin-compatible. Reconsider in Rev 3.' } },
];

const REWORKS = [
  { id: 'RWK-007', title: 'Replace UCC27201ADR on field returns batch FA-22', kind: 'rework', project: 'tvca-rev2',
    owner: 'Noah Park', ownerId: 'u-noah', role: 'development', assignee: 'Maria Chen',
    state: 'pushed', updated: '20m ago', created: 'Today', boards: 6,
    desc: 'Replace failed gate driver IC on 6 returned units. Validate functionality before shipping replacement to customer.',
    relatedBom: 'BOM-052',
    procedure: ['Remove U7 (UCC27201ADR)', 'Inspect adjacent components for collateral damage', 'Reflow new U7', 'Functional test per TP-014', 'Burn-in 4h at 60\u00b0C'],
    pushedTo: { role: 'production', toUserId: 'u-maria', when: '20m ago' }, results: null },
  { id: 'RWK-006', title: 'Add bulk cap reinforcement \u2014 BLDC dev fleet', kind: 'rework', project: 'bldc',
    owner: 'Noah Park', ownerId: 'u-noah', role: 'development', assignee: 'Maria Chen',
    state: 'inprogress', updated: '3h ago', created: 'Jun 15', boards: 12,
    desc: 'Per INV-013 findings: add 47\u03bcF tantalum across VBUS on the 12 dev units.', relatedBom: 'BOM-055',
    procedure: ['Tack 47\u03bcF tantalum across C18', 'Verify orientation', 'Re-test cold-boot per TP-029 \u00d75'],
    pushedTo: { role: 'production', toUserId: 'u-maria', when: 'Jun 15' }, results: { progress: 7, ofTotal: 12 } },
  { id: 'RWK-005', title: 'Solder bridge inspection \u2014 lot 0524', kind: 'rework', project: 'tvca-rev2',
    owner: 'Noah Park', ownerId: 'u-noah', role: 'development', assignee: 'Maria Chen',
    state: 'returned', updated: 'Yesterday', created: 'Jun 9', boards: 40, relatedBom: null,
    desc: 'AOI flagged false positives on Q12. Confirm visually + retest electrical.', procedure: ['Visual inspect Q12', 'In-circuit test'],
    pushedTo: { role: 'production', toUserId: 'u-maria', when: 'Jun 9' },
    results: { progress: 40, ofTotal: 40, returnedBy: 'Maria Chen', returnedWhen: 'Yesterday', note: 'All 40 clean. AOI threshold needs adjustment.' } },
];

const FIRMWARES = [
  { id: 'FW-1.4.2', title: 'BLDC firmware v1.4.2', kind: 'firmware', project: 'bldc',
    owner: 'Ava Patel', ownerId: 'u-ava', role: 'development', assignee: 'Ava Patel',
    state: 'validating', updated: '45m ago', created: 'Today', version: '1.4.2', relatedBom: 'BOM-055',
    desc: 'Field-oriented control tuning + brown-out hardening (INV-013 follow-on).',
    changelog: ['FOC current loop bandwidth raised to 8kHz', 'Brown-out detection hardened', 'Telemetry: report supply rail dip events'],
    pushedTo: { role: 'production', toUserId: 'u-maria', when: '45m ago' }, results: null },
  { id: 'FW-1.4.1', title: 'BLDC firmware v1.4.1', kind: 'firmware', project: 'bldc',
    owner: 'Ava Patel', ownerId: 'u-ava', role: 'development', assignee: 'Ava Patel',
    state: 'validated', updated: 'Jun 10', created: 'Jun 8', version: '1.4.1', relatedBom: 'BOM-055',
    desc: 'CAN frame-rate fix.', changelog: ['CAN heartbeat back to 10Hz', 'Minor logging cleanup'],
    pushedTo: { role: 'production', toUserId: 'u-maria', when: 'Jun 8' },
    results: { by: 'Maria Chen', when: 'Jun 10', note: 'Validated on 4 units. Telemetry stable across 24h burn-in.' } },
  { id: 'FW-1.4.0', title: 'BLDC firmware v1.4.0', kind: 'firmware', project: 'bldc',
    owner: 'Ava Patel', ownerId: 'u-ava', role: 'development', assignee: 'Ava Patel',
    state: 'released', updated: 'Today', created: 'Today', version: '1.5.0-rc1', relatedBom: 'BOM-055',
    desc: 'Drafting next release \u2014 not yet pushed for validation.', changelog: ['Adds dual-encoder support', 'Refactors HAL'] },
];

/* ---- Notifications: add development-originated + development-receiving ---- */
/* ---- Notifications ----
   New shape (notification routing v2):
     routes: { [role]: { screen, id?, tab? } }   resolver picks the destination by viewer's role
     actionLabel:  what they need to DO ("Replace 3 parts", "Approve order")
     verb:         button label that matches ("Resolve" | "Respond" | "Review" |
                                              "Validate" | "Investigate" | "Track" | "View")
     sourceRole:   who sent it
     targetRole:   who must act (resolver). Resolver also derives from routes if absent.
     kind:         'action' | 'fyi'  — fyi notifs use "View" / "Track", never "ACTION REQUIRED"
   Legacy fields (go, type, actorRole) kept for back-compat; renderer prefers new shape. */
const NOTIFICATIONS = [
  // Production exception → Designer must replace parts.
  // Other roles get a status-tracking destination, never the originator's workspace.
  { id: 'n1', forRoles: ['designer'], group: 'Today', unread: true, kind: 'action',
    sourceRole: 'production', targetRole: 'designer',
    actionLabel: 'Replace 3 parts', verb: 'Resolve',
    body: 'TVCA Main BOM v3 · 3 lines flagged for engineering review.',
    who: 'Maria Chen', when: '38m ago', entity: 'BOM-052',
    type: 'BOM EXCEPTION', actorRole: 'production',
    routes: {
      designer: { screen: 'd.dashboard' },                                // dashboard-inline resolution (Needs Attention)
      production: { screen: 'p.bomOverview', id: 'BOM-052' },               // status
      development: { screen: 'p.bomOverview', id: 'BOM-052' },              // read-only context
      purchasing: { screen: 'p.bomOverview', id: 'BOM-052' },
    },
    go: { screen: 'd.dashboard' } },

  // Purchasing rejection → Designer must revise the collection.
  // Production tracking the BOM they sent — FYI, not a task. Verb=Track.
  { id: 'n3', forRoles: ['production'], group: 'Today', unread: true, kind: 'fyi',
    sourceRole: 'production', targetRole: 'production',
    actionLabel: 'Awaiting designer response', verb: 'Track',
    body: 'TVCA Main BOM v3 is waiting on replacements from Aaron Jones.',
    who: 'System', when: '38m ago', entity: 'BOM-052',
    type: 'REPLACEMENTS NEEDED', actorRole: 'production',
    routes: {
      production: { screen: 'p.bomOverview', id: 'BOM-052' },
      designer: { screen: 'd.dashboard' },
    },
    go: { screen: 'p.bomOverview', id: 'BOM-052' } },

  // NOTE: Purchasing receives NO "approve/reject/review" notifications. Dropping a request into
  // the bucket is not a permission request — Purchasing is a downstream observation surface. Any
  // pre-bucket review is the sender's own (within-role peer review or the Designer↔Production
  // exception handshake), never routed to Purchasing.

  // (Order-shipped / order-placed FYI notifications retired with the pre-v4 order lifecycle.)

  /* Handshakes — Development ↔ other teams */
  { id: 'nv1', forRoles: ['designer'], group: 'Today', unread: true, kind: 'action',
    sourceRole: 'development', targetRole: 'designer',
    actionLabel: 'Review proposed swap', verb: 'Review',
    body: 'Replace IRFB4110PBF with IPB014N06N on TVCA Rev 2.',
    who: 'Noah Park', when: '1h ago', entity: 'REC-022',
    type: 'IMPROVEMENT RECOMMENDATION', actorRole: 'development',
    routes: { designer: { screen: 'v.recommendationDetail', id: 'REC-022' }, development: { screen: 'v.recommendationDetail', id: 'REC-022' } },
    go: { screen: 'v.recommendationDetail', id: 'REC-022' } },

  { id: 'nv2', forRoles: ['production'], group: 'Today', unread: true, kind: 'action',
    sourceRole: 'development', targetRole: 'production',
    actionLabel: 'Execute rework on 6 units', verb: 'Resolve',
    body: 'Replace UCC27201ADR on 6 field-return units (RWK-007).',
    who: 'Noah Park', when: '20m ago', entity: 'RWK-007',
    type: 'REWORK PACKAGE', actorRole: 'development',
    routes: { production: { screen: 'v.reworkDetail', id: 'RWK-007' }, development: { screen: 'v.reworkDetail', id: 'RWK-007' } },
    go: { screen: 'v.reworkDetail', id: 'RWK-007' } },

  { id: 'nv3', forRoles: ['production'], group: 'Today', unread: true, kind: 'action',
    sourceRole: 'development', targetRole: 'production',
    actionLabel: 'Validate firmware', verb: 'Validate',
    body: 'BLDC firmware v1.4.2 awaiting your validation.',
    who: 'Ava Patel', when: '45m ago', entity: 'FW-1.4.2',
    type: 'FIRMWARE FOR VALIDATION', actorRole: 'development',
    routes: { production: { screen: 'v.firmwareDetail', id: 'FW-1.4.2' }, development: { screen: 'v.firmwareDetail', id: 'FW-1.4.2' } },
    go: { screen: 'v.firmwareDetail', id: 'FW-1.4.2' } },

  { id: 'nv4', forRoles: ['development'], group: 'Today', unread: true, kind: 'action',
    sourceRole: 'production', targetRole: 'development',
    actionLabel: 'Investigate brown-out', verb: 'Investigate',
    body: 'STM32G4 brown-out under inrush — RCA requested (INV-013).',
    who: 'Maria Chen', when: '3d ago', entity: 'INV-013',
    type: 'INVESTIGATION REQUESTED', actorRole: 'production',
    routes: { development: { screen: 'v.investigationDetail', id: 'INV-013' }, production: { screen: 'v.investigationDetail', id: 'INV-013' } },
    go: { screen: 'v.investigationDetail', id: 'INV-013' } },

  { id: 'nv5', forRoles: ['development'], group: 'Today', unread: false, kind: 'fyi',
    sourceRole: 'designer', targetRole: 'development',
    actionLabel: 'Recommendation accepted', verb: 'View',
    body: 'Aaron Jones accepted REC-021 — Coilcraft XAL1010-103 inductor swap.',
    who: 'Aaron Jones', when: 'Yesterday', entity: 'REC-021',
    type: 'RECOMMENDATION ACCEPTED', actorRole: 'designer',
    routes: { development: { screen: 'v.recommendationDetail', id: 'REC-021' }, designer: { screen: 'v.recommendationDetail', id: 'REC-021' } },
    go: { screen: 'v.recommendationDetail', id: 'REC-021' } },
];

/* ---- Audit log ---- */
const AUDIT = [
  { id: 'au1', ts: 'Today 14:22', user: 'Maria Chen', role: 'production', action: 'BOM exception sent', entity: 'BOM-052', before: 'SOURCING', after: 'EXCEPTIONS' },
  { id: 'au2', ts: 'Today 13:40', user: 'David Okafor', role: 'purchasing', action: 'Request approved', entity: 'REQ-012', before: 'SUBMITTED', after: 'APPROVED' },
  { id: 'au3', ts: 'Today 10:08', user: 'David Okafor', role: 'purchasing', action: 'Request rejected', entity: 'REQ-015', before: 'SUBMITTED', after: 'REJECTED' },
  { id: 'au4', ts: 'Yesterday 16:55', user: 'Aaron Jones', role: 'designer', action: 'Collection submitted to Purchasing', entity: 'COL-028', before: 'ACTIVE', after: 'ORDER REQUESTED' },
  { id: 'au5', ts: 'Jun 16 09:30', user: 'David Okafor', role: 'purchasing', action: 'Purchase order created', entity: 'PO-2038', before: '—', after: 'ORDERED' },
  { id: 'au6', ts: 'Jun 13 11:02', user: 'Grace Hill', role: 'admin', action: 'Role assigned (production)', entity: 'u-aaron', before: '[designer]', after: '[designer, production]' },
  { id: 'au7', ts: 'Today 14:55', user: 'Noah Park', role: 'development', action: 'Improvement Recommendation pushed to Designer', entity: 'REC-022', before: 'DRAFT', after: 'AWAITING DESIGNER' },
  { id: 'au8', ts: 'Today 15:40', user: 'Noah Park', role: 'development', action: 'Rework Package pushed to Production', entity: 'RWK-007', before: 'DRAFT', after: 'AWAITING PRODUCTION' },
  { id: 'au9', ts: 'Today 15:15', user: 'Ava Patel', role: 'development', action: 'Firmware Release pushed to Production', entity: 'FW-1.4.2', before: 'RELEASED', after: 'VALIDATING' },
  { id: 'au10', ts: 'Yesterday 11:20', user: 'Aaron Jones', role: 'designer', action: 'Recommendation accepted', entity: 'REC-021', before: 'AWAITING DESIGNER', after: 'ACCEPTED' },
];

/* ---- Suppliers ---- */
const SUPPLIERS = [
  { id: 'mouser', name: 'Mouser Electronics', color: '#1A56DB', enabled: true, priority: 1, api: 'connected', apiKey: '••••••••3F7A', lastSync: '6 min ago', mode: 'API + CSV fallback' },
  { id: 'digikey', name: 'DigiKey', color: '#D91F1F', enabled: true, priority: 2, api: 'connected', apiKey: '••••••••B214', lastSync: '8 min ago', mode: 'API + CSV fallback' },
];

/* ---- System status / config ---- */
const SYSTEM = {
  status: [
    { id: 'app', label: 'Application', state: 'green', detail: 'All services operational' },
    { id: 'mouser', label: 'Mouser API', state: 'green', detail: 'Avg latency 240ms · 6 min ago' },
    { id: 'digikey', label: 'DigiKey API', state: 'amber', detail: 'Rate-limit warnings (3 in last hour)', tokenExpiry: 'in 48 min' },
    { id: 'digikey-token', label: 'DigiKey OAuth token', state: 'amber', detail: 'Expires in 48 minutes — refresh before it lapses', action: 'refresh-digikey' },
    { id: 'partsbox', label: 'PartsBox API', state: 'green', detail: 'Connected · 2 imports today' },
    { id: 'jobs', label: 'Job queue', state: 'green', detail: '0 pending · 1 sourcing run active' },
    { id: 'db', label: 'Database', state: 'green', detail: 'Healthy · 38ms p95' },
  ],
  workflow: {
    maxExceptionLoops: 3, staleThresholdHours: 24, overdueHours: 24, autoOrder: false,
    requireBudgetCode: true, mouserFirst: true,
  },
  settings: { sessionTimeoutMin: 30, requireSupervisorForInterns: true, defaultRole: 'readonly', mfa: false },
  /* v2 bucket batching — Admin-configurable cadences (minutes) for the two purchasing streams.
     nextRunMin = simulated minutes until the next batch fires (for the observation-surface countdown). */
  batch: {
    main: { intervalMin: 360, nextRunMin: 142, lastRun: '2h 18m ago', writing: false },
    critical: { intervalMin: 180, nextRunMin: 47, lastRun: '2h 13m ago', writing: false },
  },
  /* v1.3-rev — Admin Dashboard Needs Attention sources */
  jobs: [
    { id: 'JOB-9821', label: 'Nightly supplier sync — DigiKey', object: 'All BOMs', error: 'DigiKey API timeout at 04:11 UTC', when: '6h ago' },
    { id: 'JOB-9844', label: 'Sourcing run — TVCA Main BOM v3', object: 'BOM-052', error: 'PartsBox export rejected (auth)', when: '2h ago' },
  ],
  stuck: [
    { id: 'REQ-031', name: 'Power Stage procurement', objType: 'Procurement Request', status: 'SUBMITTED', idle: '3 days' },
  ],
};

const RECENT_SEARCHES = ['IRFB4110PBF', 'TPS54560', 'UCC27201ADR', 'STM32G431'];

/* ---- Programs (v4 — top-level org layer above Project) ---- */
const PROGRAMS = [
  { id: 'terra-voyager', name: 'Terra Voyager', code: 'TV', identifier: 'TV', owner: 'Aaron Jones', status: 'Active',
    desc: 'Long-running traction-control platform contract. Multiple board revisions.',
    customer: 'Customer X', started: 'Jan 2025', target: 'Q4 2026', tags: ['contract', 'traction'],
    notifyOnEquivalentSwap: true, projects: ['tvca-rev2', 'tvca-psu'] },
  { id: 'gatekeeper', name: 'Gatekeeper R&D', code: 'GK', identifier: 'GK', owner: 'Aaron Jones', status: 'Active',
    desc: 'Internal R&D initiative exploring next-gen gate-driver topologies.',
    customer: null, started: 'May 2025', target: null, tags: ['r&d', 'internal'],
    notifyOnEquivalentSwap: true, projects: ['gate-eval'] },
  { id: 'restock', name: 'Build Wall Ops', code: 'BW', identifier: 'BW', owner: 'Maria Chen', status: 'Active',
    desc: 'Recurring replenishment of build-wall working stock.',
    customer: null, started: 'Apr 2025', target: null, tags: ['ops'],
    notifyOnEquivalentSwap: true, projects: ['wall-q2'] },
  { id: 'motor-control', name: 'Motor Control', code: 'MC', identifier: 'MC', owner: 'Aaron Jones', status: 'Active',
    desc: 'Brushless DC motor controller platform and derivatives.',
    customer: null, started: 'Jun 2025', target: null, tags: ['production', 'motor'],
    notifyOnEquivalentSwap: true, projects: ['bldc', 'md-stage', 'sensor-a-draft'] },
];

/* ---- Inventory (mock PartsBox dataset — parts, wall bins, project boxes, stock) ---- */
const INVENTORY = [
  { mpn: 'IRFB4110PBF', mfr: 'Infineon', desc: 'MOSFET N-Ch 100V 180A', onHand: 340, low: false,
    locations: [{ kind: 'project', name: 'TVCA Rev 2', qty: 240 }, { kind: 'wall', name: 'A-3-7', qty: 100 }], tags: ['autobom-managed', 'production'] },
  { mpn: 'TPS54560DDAR', mfr: 'Texas Instruments', desc: 'Buck converter 5A 60V', onHand: 62, low: true,
    locations: [{ kind: 'wall', name: 'B-1-4', qty: 62 }], tags: ['autobom-managed'] },
  { mpn: 'UCC27201ADR', mfr: 'Texas Instruments', desc: 'Half-bridge gate driver', onHand: 0, low: true,
    locations: [{ kind: 'wall', name: 'B-2-1', qty: 0 }], tags: ['autobom-managed'] },
  { mpn: 'GRM188R71H104KA93D', mfr: 'Murata', desc: 'MLCC 0.1uF 50V 0603', onHand: 4200, low: false,
    locations: [{ kind: 'project', name: 'TVCA Rev 2', qty: 3000 }, { kind: 'wall', name: 'R-0603-104', qty: 1200 }], tags: ['production'] },
  { mpn: 'STM32G431CBT6', mfr: 'STMicroelectronics', desc: 'MCU Cortex-M4 170MHz', onHand: 85, low: false,
    locations: [{ kind: 'project', name: 'BLDC Motor Controller', qty: 85 }], tags: ['autobom-managed', 'production'] },
  { mpn: 'RC0603FR-0710KL', mfr: 'Yageo', desc: 'Res 10K 1% 0603', onHand: 8800, low: false,
    locations: [{ kind: 'wall', name: 'R-0603-10K', qty: 8800 }], tags: ['local-part'] },
];

/* Shipments seed retired (v4: AutoBOM does not track order or shipment lifecycle —
   Purchasing ends at a human placing the order in the supplier's own UI). */

/* Customer Part Number (v4 — continuous-identifier model, NO sigils). READ-ONLY.
   The CPN IS the derived identifier chain: <program.identifier>-<project.identifier>-<line>,
   e.g. TVCA → TVCA-R2 → TVCA-R2-042. Wall-bound lines derive from the wall location instead.
   Scope ('project' | 'wall') is surfaced separately via cpnScope() and rendered as a pill.
   Accepts a source object (Request or Collection) + a line item. */
function cpnScope(sourceObj) {
  return (sourceObj && (sourceObj.destination === 'wall' || sourceObj.bucketWall)) ? 'wall' : 'project';
}
function cpnFor(sourceObj, lineItem) {
  if (lineItem && (lineItem.cpn)) return lineItem.cpn;
  if (!sourceObj) return '—';
  const ln = String((lineItem && (lineItem.no || lineItem.line)) || 1).padStart(3, '0');
  if (cpnScope(sourceObj) === 'wall') {
    const loc = sourceObj.wallLocation || 'A-3-7';
    return `${loc}-${ln}`;
  }
  const proj = PROJECTS[sourceObj.project];
  const prog = proj && proj.program_id ? PROGRAMS.find(p => p.id === proj.program_id) : null;
  const progId = (prog && prog.identifier) || (prog && prog.code) || 'PRG';
  const projId = (proj && proj.identifier) || (proj ? proj.name.replace(/[^A-Za-z0-9]/g, '').slice(0, 4).toUpperCase() : 'PRJ');
  return `${progId}-${projId}-${ln}`;
}

function seedState() {
  /* v1.3 — Development role is archived. Filter all Development-tagged
     notifications and audit-history entries out of the seed so the live
     UI never surfaces a notification or task originating from or routed
     to the archived role. Flipping DEV_ROLE_ENABLED back on restores them. */
  const devOn = window.DEV_ROLE_ENABLED;
  const devClean = (notif) => devOn || (notif.sourceRole !== 'development' && notif.targetRole !== 'development' && !(notif.forRoles || []).includes('development') && notif.actorRole !== 'development');
  return {
    authed: false,
    currentUserId: 'u-aaron',
    activeRole: 'designer',
    users: JSON.parse(JSON.stringify(USERS)),
    projects: JSON.parse(JSON.stringify(PROJECTS)),
    collections: JSON.parse(JSON.stringify(COLLECTIONS)).filter(c => devOn || c.role !== 'development'),
    boms: JSON.parse(JSON.stringify(BOMS)),
    requests: JSON.parse(JSON.stringify(REQUESTS)),
    programs: JSON.parse(JSON.stringify(PROGRAMS)),
    inventory: (window.PARTSBOX_INVENTORY ? window.PARTSBOX_INVENTORY.map(p => ({
      mpn: p.mpn, mfr: '', desc: p.desc, fp: p.fp, cat: p.cat, lastUsed: p.lastUsed,
      onHand: p.stock, low: p.stock <= 5,
      locations: (p.locs || []).map(l => ({ kind: l.kind, name: l.loc, qty: l.qty })),
      tags: [...new Set((p.locs || []).map(l => l.kind === 'project' ? 'production' : 'development').concat(p.cat ? [p.cat.toLowerCase()] : []))],
    })) : JSON.parse(JSON.stringify(INVENTORY))),
    notifications: JSON.parse(JSON.stringify(NOTIFICATIONS)).filter(devClean),
    audit: JSON.parse(JSON.stringify(AUDIT)).filter(a => devOn || a.role !== 'development'),
    suppliers: JSON.parse(JSON.stringify(SUPPLIERS)),
    system: JSON.parse(JSON.stringify(SYSTEM)),
    investigations: devOn ? JSON.parse(JSON.stringify(INVESTIGATIONS)) : [],
    recommendations: devOn ? JSON.parse(JSON.stringify(RECOMMENDATIONS)) : [],
    reworks: devOn ? JSON.parse(JSON.stringify(REWORKS)) : [],
    firmwares: devOn ? JSON.parse(JSON.stringify(FIRMWARES)) : [],
    comments: {},  // { entityId: [{ id, userId, name, role, when, body }] }
    datasheets: {},  // { mpn: url } — PartsBox datasheet attachments (attach-on-user-action)
    seq: { req: 19, po: 2042, bom: 61, col: 34, inv: 15, rec: 23, rwk: 8, fw: 0, cmt: 1, shp: 3012 },
  };
}

/* Safe project-name lookup - the ONE canonical helper.
   PROJECTS is the static seed catalog. Projects created at runtime (uploaded
   this session, or fetched from the backend) are NOT in it, so the direct
   PROJECTS[id].name form throws on undefined and blanks the entire screen.
   Falls back: static catalog -> live store -> 'Other'. */
function projectName(pid) {
  if (!pid) return 'Other';
  const st = (typeof getState === 'function' && getState().projects) || {};
  const pr = (typeof PROJECTS !== 'undefined' && PROJECTS[pid]) || st[pid];
  return (pr && pr.name) || 'Other';
}

Object.assign(window, { fmtUSD, fmtUnitPrice, parsePrice, fmtInt, fmtWhen, uid, CATALOG, PROJECTS, RECENT_SEARCHES, seedState, line, cpnFor, cpnScope, userByName, userById, projectName });
