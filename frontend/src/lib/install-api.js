// Installs the backend API helper as `window.api`.
//
// This exists as its own SIDE-EFFECT MODULE for one reason: ES `import`
// declarations are hoisted. Every imported module is evaluated before ANY
// top-level statement in the importing module runs. main.jsx previously did:
//
//     import api from './lib/api.js';
//     window.api = api;            // <-- a STATEMENT
//     ...
//     import './core/store.jsx';   // <-- hoisted, evaluates FIRST
//
// so store.jsx (which calls boot() at module-eval time) ran while `window.api`
// was still undefined. `window.api.get('/auth/me')` threw a TypeError, boot()'s
// catch swallowed it, and session restore silently never happened - every tab
// showed the login form even with a valid session cookie.
//
// Assigning inside an imported module makes the assignment part of module
// evaluation, so import ORDER now genuinely controls it. Same pattern as
// globals.js. Keep this imported BEFORE ./core/store.jsx.
import api from './api.js';

window.api = api;

export default api;
