// AutoBOM prototype global shims.
//
// The prototype was written against the React 18 UMD build loaded from a CDN,
// so every component file expects `React` and `ReactDOM` to exist as globals
// (e.g. `const { useState } = React;` at the top of each file, and
// `ReactDOM.render(...)` in app.jsx). It also uses a window-based module
// registry: each file ends with `Object.assign(window, { ...exports })` and
// consumers read them back via `window[name]`.
//
// This module MUST be imported FIRST in main.jsx — ES-module evaluation runs
// in import order, so setting these globals here guarantees they exist before
// any component module's top-level code runs. Setting them inline in main.jsx
// would be too late: static imports are hoisted and evaluate before the rest
// of main.jsx's body.

import React from 'react';
import ReactDOM from 'react-dom';

window.React = React;
window.ReactDOM = ReactDOM; // provides the legacy ReactDOM.render used by app.jsx

export {};
