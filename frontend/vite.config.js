import { defineConfig } from 'vite';

// AutoBOM frontend — Vite config.
//
// Deliberately NO @vitejs/plugin-react: the prototype is a set of global-script
// modules that register components on `window` (not ES exports), which React
// Fast Refresh cannot track and would break. Instead we use Vite's built-in
// esbuild with the CLASSIC JSX transform so `<div/>` compiles to
// `React.createElement(...)` against the global React that src/globals.js
// installs. Editing a file triggers a full reload (acceptable, and faithful).

export default defineConfig({
  root: '.',
  server: {
    port: 3000,
    strictPort: true,
    // The prototype talks to the backend under /api; proxy it to FastAPI so the
    // browser sees a single origin (no CORS surprises in dev).
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
  esbuild: {
    jsx: 'transform',
    jsxFactory: 'React.createElement',
    jsxFragment: 'React.Fragment',
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
});
