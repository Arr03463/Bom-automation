# AutoBOM — Coordination Note 4 (Prototype Login Screen)

## Purpose

This note delivers the prototype login screen. Users identify themselves before entering the workspace. The session state, current-user identity, and last-active-role persist via sessionStorage. The existing "PROTOTYPE — VIEW AS ANY ROLE" role switcher becomes a real per-user role switcher that only shows the roles the current user actually has.

**This is prototype-only auth.** No real Microsoft SSO yet. No backend. No password hashing. Hardcoded seed users represent Aaron's real team; picking one simulates login. When Claude Code implements real SSO in Phase 2, this UX contract is what the real auth wires up against — same login screen shape, same session model, same role behavior — only the source of user data changes from hardcoded seeds to backend API calls.

**Prerequisites:** Coordination Notes 1, 2, and 3 must be complete and their rejection criteria confirmed clean. This note assumes:

- Three login roles locked (Designer / Production / Admin) with proper embedded Purchasing/Inventory surfaces
- Continuous-identifier model applied across Program → Project → BOM → CPN
- Create Program and Create Project flows functional
- All dead controls resolved
- CLAUDE.md is the current v4 operating context

If any of Notes 1, 2, or 3 didn't close, stop this note and return to earlier work.

**Scope:** Eighteen actions across seven groups plus coordination. One new capability (prototype login), one behavioral rework (role switcher becomes per-user-scoped), and cleanup of one retired prototype affordance (VIEW AS ANY ROLE pill).

## Elicitation pattern

Same as previous sessions. One question at a time. Wait for answer. Then execute.

Explicit elicitation points flagged inline. Everything else is pre-locked in the coordination cycle.

---

## Group 1 — User data model + seed users

**1. Add the User object to the data model.**

Add a `users` seed array to `data.jsx` at the same level as `programs`, `projects`, `boms`, etc. User object shape:

```javascript
user: {
  id,                  // string, unique — used as sessionStorage key
  name,                // display name (e.g., "Aaron Jones")
  email,               // email address (matches company Microsoft account when real SSO lands)
  roles,               // array of role strings — subset of ['designer', 'production', 'admin']
  primaryRole,         // string — one of the values in roles[]; landing role on first login
  avatar,              // optional — path to avatar image, or null (initials-based fallback)
  createdAt,           // ISO timestamp
  invitedBy,           // string user.id of whoever invited them, or null for founders
}
```

**2. Seed the initial user list.**

Hardcoded seed users representing Aaron's real team. Adjust names, roles, or additions to match reality before Claude Design executes.

**Starting seed (edit as needed):**

| Name | Roles | Primary Role |
|------|-------|--------------|
| Aaron Jones | Designer + Admin | Designer |
| Josh (CEO) | Admin | Admin |
| Maria Chen | Production | Production |

Additional seed users can be added later as the real team grows via Coordination Note 5's Admin User Management work (deferred to a future note).

Store as `users` array in `data.jsx` seedState. Each user gets a stable `id` (e.g., `usr_aaron`, `usr_josh`, `usr_maria`). Use these IDs in existing seed data wherever a user reference is needed (e.g., `Project.lead`, `Collection.owner`, `Program.owner`) — replace name strings with user IDs.

---

## Group 2 — Session state and current-user identity

**3. Add `currentUser` to the store state.**

Add three related state fields:

- `currentUserId` (string or null) — the ID of the currently logged-in user, or null if logged out
- `lastActiveRole` (string or null) — the role the current user was in when they last logged out (Model D persistence)
- `sessionStartedAt` (ISO timestamp) — when the current session began, for audit surface

**4. Derive `activeRole` from `currentUserId` + `lastActiveRole`.**

Currently `state.activeRole` is a top-level field. Rework so it's derived:

- If `currentUserId` is null → no active role (user is on login screen)
- If `currentUserId` is set → `activeRole = lastActiveRole` (if set and in user's `roles[]`) or `user.primaryRole` (fallback for first login)

Every existing screen reading `state.activeRole` continues working without change. Just make sure the derivation lives in one place (e.g., a `getActiveRole(state)` selector).

**5. Add session persistence via sessionStorage.**

- On login: write `currentUserId` and `lastActiveRole` to sessionStorage under keys `autobom.currentUserId` and `autobom.lastActiveRole`
- On role switch: update `autobom.lastActiveRole` in sessionStorage
- On logout: clear both keys
- On app boot (in `app.jsx` initialization): read from sessionStorage. If a valid `currentUserId` exists, restore session automatically. Otherwise, render login screen.

Session persists across browser tab close+reopen (that's what sessionStorage does). Restart of the entire browser clears it (behaves like a real login system — reasonable prototype fidelity).

---

## Group 3 — Login screen UI

**6. Build the login screen component.**

New component: `screen_login.jsx`. Renders when `currentUserId` is null. Full-page layout, centered.

Elements:

- **AutoBOM logo/title** — prominent header
- **Tagline** — short (e.g., "Bill of Materials + Purchasing + Inventory")
- **Email input field** — required, validated on submit
- **"Log in with Microsoft" button** — visible, disabled with a small message ("Coming soon — use email for now") to set expectations for the production auth path
- **Submit button** — labeled "Continue" or "Log in"
- **Error surface** — appears below the input if the email doesn't match any seed user

**Submit behavior:**

- Trim whitespace + lowercase the input
- Look up user by email in `state.users`
- If match → dispatch `logIn(userId)` action → route to landing (Group 4)
- If no match → show error: "No user found with that email. Contact your admin."

**Elicit:** the login screen shows only an email input with no password field. For prototype, entering the correct email is enough to log in. When real SSO lands, this becomes the "Log in with Microsoft" button instead. Is that acceptable, or do you want a placeholder password field (accepting any non-empty value) to more closely simulate a real login flow?

**Recommendation:** email-only. Prototype-appropriate. Adding a fake password field is theater without value; the real SSO flow won't have a password on AutoBOM anyway (Microsoft handles that).

**7. Route to login screen when logged out.**

In `app.jsx`, before dispatching to any workspace screen, check `currentUserId`:

- If null → render `<LoginScreen>` regardless of the URL hash
- If set → render the workspace as normal

The URL hash is preserved during logout+re-login (so if a user tries to visit a specific page while logged out, they get redirected to login, and after logging in, they land on the intended page — deferred to a nice-to-have; MVP: always land on dashboard after login).

---

## Group 4 — Model D landing behavior

**8. Implement Model D on login.**

When a user successfully logs in via the email input:

- Check sessionStorage for `autobom.lastActiveRole` under this user's ID
- If found AND the role is in the user's `roles[]` → land in that role
- Otherwise → land in the user's `primaryRole` (first login case, or role no longer valid)

Landing means: `activeRole` is set, and `location.hash` is set to the dashboard of that role (`#designer/dashboard`, `#production/dashboard`, or `#admin/dashboard`).

**9. Add `logIn(userId)` store action.**

Signature: `logIn(userId)`

Behavior:
- Validate `userId` exists in `state.users`
- Set `currentUserId = userId`
- Determine landing role (Model D logic from Action 8)
- Set `lastActiveRole = <landing role>`
- Set `sessionStartedAt = now`
- Write to sessionStorage
- Write audit event: `User logged in` with `actor: userId`, `timestamp: now`
- Route to dashboard of landing role

**10. Add `logOut()` store action.**

Behavior:
- Write audit event: `User logged out` with `actor: currentUserId`, `timestamp: now`, `sessionDuration: now - sessionStartedAt`
- Clear `currentUserId`, `lastActiveRole`, `sessionStartedAt` from state
- Clear sessionStorage keys
- Route to login screen

---

## Group 5 — Role switcher rework (per-user scoped)

The current sidebar has a "PROTOTYPE — VIEW AS ANY ROLE" pill that lets anyone switch to any role for prototype testing. Now that real users exist with defined roles, this becomes a real per-user role switcher.

**11. Retire the "PROTOTYPE — VIEW AS ANY ROLE" pill.**

Delete the pill from the sidebar entirely. It was a prototype affordance for viewing role variants without an auth system; now that logins exist, it's misleading.

**12. Rework the role switcher to filter to current user's roles.**

The existing "Viewing workspace" dropdown in the sidebar top area (Designer / Production / Admin) becomes user-scoped:

- **Single-role users** (e.g., Maria who is only Production): dropdown is hidden entirely. She sees no switcher, no dropdown affordance. Her sidebar shows the Production workspace directly.
- **Multi-role users** (e.g., Aaron who is Designer + Admin): dropdown shows ONLY the roles she/he has. Aaron sees Designer + Admin as options, not Production.
- Current role is highlighted in the dropdown.

**13. Wire the switcher to `switchRole(role)` action.**

Signature: `switchRole(role)`

Behavior:
- Validate `role` is in `currentUser.roles[]` (reject if not — defense against direct dispatch)
- Set `lastActiveRole = role`
- Persist to sessionStorage
- Route to dashboard of the new role
- Write audit event: `Role switched` with actor + from + to + timestamp

**14. Add auto-switch banner for notification-triggered role changes.**

Per CLAUDE.md: when a multi-role user clicks a notification that targets a role different from their current role, auto-switch to that role and show a banner ("Switched to Production context — task assigned to Production. [Switch back to Designer]").

**Elicit:** is the auto-switch behavior already implemented in the prototype from prior sessions? If yes, verify it works with the new role-scoped logic. If no, add it as part of Action 14. Check the notification click handler in `store.jsx` and route dispatcher in `app.jsx`.

**Recommendation:** verify first, then extend. Most likely: the routing exists but the "banner" affordance may not — add a short-lived top-of-page notice if not present.

---

## Group 6 — User menu + logout affordance

**15. Add a user menu to the top-right of the top rail.**

Currently the top rail has no user identity display. Add a user menu positioned in the top-right (aligned with breadcrumbs to the left).

Layout:
- **Avatar** — small circle showing user's initials (from `user.name`) or `user.avatar` image if present
- **Name** — user's display name
- **Small role indicator** — current role in a subtle chip (e.g., "Designer")
- **Chevron** — indicates dropdown

Click opens dropdown:
- User email (readonly)
- Current role display
- **"Log out"** button — dispatches `logOut()` action

**Optional secondary items in the dropdown (deferred to future notes):**
- Profile settings
- Notification preferences
- Help / About

Only Log out is needed in MVP.

---

## Group 7 — Cleanup + rejection criteria

**16. Update seed data to remove any `state.activeRole` initial values.**

If `data.jsx` seedState sets `activeRole: 'designer'` or similar, remove it. Active role now derives from `currentUser + lastActiveRole` at runtime.

**17. Handle URL hashes for unauthorized roles.**

If a user tries to visit `#production/dashboard` but their `roles` array doesn't include `production`:

- Redirect to `<primary role>/dashboard`
- Show a short toast/banner: "You don't have access to Production; redirected to Designer."

This handles the edge case of bookmarked URLs, shared links across roles, or direct hash editing.

**18. Update audit surface to include login/logout events.**

The audit view (Admin → Audit Log) should now show:
- `User logged in` events with actor + timestamp
- `User logged out` events with actor + session duration
- `Role switched` events with actor + from + to + timestamp

Same shape as existing audit entries; just add these event types.

---

## Group Zero — Coordination

**Elicit upfront if anything is ambiguous.**

Explicit elicitation points already flagged:

- Action 6: email-only login screen vs email+placeholder-password
- Action 14: auto-switch banner exists or needs to be added

Any other ambiguity — same one-question-at-a-time pattern.

---

## Rejection criteria for the whole session

If any of these are true at the end of the session, the note did not close:

- No login screen exists (`screen_login.jsx` missing)
- Login screen renders even when `currentUserId` is set (route guard broken)
- Workspace renders when `currentUserId` is null (route guard broken)
- `logIn(userId)` action doesn't exist in `store.jsx`
- `logOut()` action doesn't exist
- `switchRole(role)` action doesn't validate that `role` is in `currentUser.roles`
- sessionStorage keys `autobom.currentUserId` and `autobom.lastActiveRole` don't persist across page reloads
- `users` seed array doesn't exist in `data.jsx` seedState
- User references in seed data (Project.lead, Collection.owner, Program.owner) still use plain name strings instead of user IDs
- Single-role users still see the role switcher dropdown
- Multi-role users' dropdown shows roles they don't have
- "PROTOTYPE — VIEW AS ANY ROLE" pill still visible anywhere
- User menu missing from top-right of top rail
- User menu missing "Log out" action
- Model D landing broken: users don't land in `lastActiveRole` on subsequent login
- First-login users don't land in their `primaryRole`
- URL hash for unauthorized role doesn't redirect (e.g., Maria visiting `#designer/dashboard` should redirect to `#production/dashboard`)
- Login/logout/role-switch events not appearing in Admin → Audit Log

---

## What this note does NOT include

To keep the scope tight:

- **Real Microsoft SSO integration.** Deferred to Phase 2 (Claude Code backend work). This note is prototype-only.
- **User CRUD (Admin → Users → Invite).** Deferred to a future coordination note. For now, users are hardcoded in `data.jsx`. Adding a user means editing that file.
- **Password reset, MFA, 2FA.** Not applicable in prototype. Comes with real auth.
- **Session timeout / auto-logout.** Not applicable in prototype. Comes with real auth.
- **User profile editing.** Deferred. User records are read-only in the prototype.
- **Avatar upload.** Deferred. Initials-based fallback is sufficient.
- **"Remember me" / persistent cross-browser sessions.** sessionStorage is enough for prototype (persists across tabs, clears on browser restart).
- **Notification preferences per user.** Deferred to future Admin work.

---

## After this note lands

The prototype demonstrates a functional login experience end-to-end:

1. **Fresh visit → login screen.** User types email, lands in their role.
2. **Return visit → resumed session.** User lands in their last active role automatically.
3. **Multi-role users can switch contexts** via the sidebar switcher (scoped to their roles only).
4. **Single-role users have a simpler UI** — no switcher clutter.
5. **User identity is visible in the top rail** at all times via the user menu.
6. **Logout returns to the login screen** and clears session state.
7. **Audit surface tracks all login/logout/role-switch events** for later review.

At that point, the prototype's UX contract for authentication is complete. When Claude Code implements real SSO in the backend phase, the frontend contract stays identical — `logIn(userId)` becomes an API call returning a session token, `state.currentUserId` gets populated from the session, but every downstream component still reads the same fields. Zero frontend changes needed to swap prototype auth for real auth.

This is the seamless-migration principle applied to authentication: build the UX contract now against fake data, replace the data source with real backend later, everything else stays.
