/* global React, Icon, useStore, storeActions */
/* AutoBOM — Prototype login (Note 4). Email-only auth against seed users.
   Microsoft SSO is a disabled placeholder for the Phase 2 real path. */
const { useState: useLoginState } = React;

const SEED_HINTS = [
  { email: 'aaron.jones@yanktech.com', label: 'Aaron Jones', role: 'Designer + Production' },
  { email: 'maria.chen@yanktech.com', label: 'Maria Chen', role: 'Production' },
  { email: 'grace.hill@yanktech.com', label: 'Grace Hill', role: 'Admin' },
  { email: 'noah.park@yanktech.com', label: 'Noah Park', role: 'Development' },
];

function LoginScreen() {
  const [email, setEmail] = useLoginState('');
  const [error, setError] = useLoginState(null);

  const submit = async (e) => {
    if (e) e.preventDefault();
    const res = await storeActions.logIn(email);
    if (res && !res.ok) setError(res.error);
  };

  return (
    <div className="login-wrap">
      <div className="login-card">
        <div className="login-brand">
          <div className="login-logo">A</div>
          <div>
            <div className="login-title">AutoBOM</div>
            <div className="login-sub">Engineering workflow platform</div>
          </div>
        </div>
        <form onSubmit={submit}>
          <label className="field" style={{ marginBottom: 12 }}>
            <span className="fl">Work email</span>
            <input className="input" type="email" autoFocus value={email}
              onChange={(ev) => { setEmail(ev.target.value); if (error) setError(null); }}
              placeholder="you@yanktech.com" />
          </label>
          {error && <div className="login-error"><Icon name="alert" size={13} />{error}</div>}
          <button type="submit" className="btn primary login-submit">Sign in</button>
        </form>
        <div className="login-divider"><span>or</span></div>
        <button className="btn login-ms" disabled title="Coming in Phase 2">
          <Icon name="grid" size={15} />Log in with Microsoft
          <span className="badge outlined" style={{ marginLeft: 'auto' }}>SOON</span>
        </button>
        <div className="login-hints">
          <div className="caption" style={{ marginBottom: 6 }}>Prototype seed users — click to fill:</div>
          <div className="login-hint-row">
            {SEED_HINTS.map((h) => (
              <button key={h.email} type="button" className="login-hint" onClick={() => { setEmail(h.email); setError(null); }}>
                <span className="lh-name">{h.label}</span>
                <span className="lh-role">{h.role}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

if (typeof window !== 'undefined') window.LoginScreen = LoginScreen;
