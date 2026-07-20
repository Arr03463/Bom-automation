// AutoBOM frontend entry — Vite wrapper around the existing prototype.
//
// This file does NOT rewrite the prototype. It preserves it byte-for-byte and
// only replaces the old in-browser Babel + CDN loader with a real Vite build:
//
//   1. `./globals.js` runs first and installs window.React / window.ReactDOM.
//   2. The 27 prototype modules are side-effect-imported IN THE EXACT ORDER the
//      old index HTML loaded them (each registers its exports on `window`).
//   3. core/app.jsx is last; it self-mounts via ReactDOM.render on evaluation.
//
// Import order is load-bearing: e.g. store.jsx calls seedState() (from
// data.jsx) at module-eval time, so data.jsx must evaluate before store.jsx.
// Do not reorder these without matching the original load order.

import './globals.js'; // MUST be first — sets up React/ReactDOM globals

// Install the backend API helper as a global BEFORE the store loads (store.jsx
// calls window.api during boot to restore a session and hydrate from /bootstrap).
import api from './lib/api.js';
window.api = api;

// Styles (was a <link> in the old HTML; Vite bundles it here).
import '../assets/css/styles.css';

// ---- core (order matters) ----
import './core/ui.jsx';
import './core/permissions.jsx';
import './core/inventory_data.jsx';
import './core/data.jsx';
import './core/store.jsx';
import './core/nav.jsx';
import './core/shell.jsx';

// ---- screens + features (original load order preserved) ----
import './screens/screen_dashboard.jsx';
import './features/needs_attention.jsx';
import './screens/screen_search.jsx';
import './screens/screen_collections.jsx';
import './screens/screen_collection_detail.jsx';
import './screens/screen_production.jsx';
import './screens/screen_production_pipeline.jsx';
import './screens/screen_production_results.jsx';
import './screens/screen_bom_overview.jsx';
import './screens/screen_embedded.jsx';
import './screens/screen_admin.jsx';
import './screens/screen_development.jsx';
import './screens/screen_dev_collections.jsx';
import './features/inline_part_verify.jsx';
import './features/pushback_resolve.jsx';
import './screens/screen_addons.jsx';
import './screens/screen_shared.jsx';
import './screens/screen_login.jsx';
import './screens/screen_create_flows.jsx';
import './features/search.jsx';

// ---- app (last — self-mounts into #root via ReactDOM.render) ----
import './core/app.jsx';
