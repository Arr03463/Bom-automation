# AutoBOM — Coordination Note 4-Rollback (Undo Session 4)

## Purpose

Session 4 (Prototype Login Screen) attempted an integrated build of authentication across `store.jsx`, `app.jsx`, `shell.jsx`, `data.jsx`, and a new `screen_login.jsx`. The result: a Babel transpilation hang that couldn't be recovered in-place, leaving the prototype in a broken state.

This note undoes Session 4 completely. When it closes, the prototype is back at end-of-Note-3 state — Notes 1, 2, and 3 fully intact, zero Session 4 residue anywhere.

**This is not a redesign of Session 4.** This is a clean removal. When Session 4 is retried, it will happen in smaller sub-notes (4a through 4e) with render verification between each step. That planning is not part of this note.

**Prerequisites:** None. This note is a recovery operation. Sessions 1, 2, and 3 remain valid; only Session 4 is being reverted.

**Scope:** Fourteen actions across four groups. Every action removes something Session 4 added. Nothing new gets built.

---

## Group 1 — Remove Session 4 files

**1. Delete `screen_login.jsx` entirely.**

The file lives at `autobom/screen_login.jsx`. Remove it from disk.

**2. Remove the `screen_login.jsx` script tag from the HTML.**

In `autobom/AutoBOM Platform.html`, find the line:

```html
<script type="text/babel" src="screen_login.jsx"></script>
```

Delete that entire line. The script tag was added during Session 4 to load the LoginScreen component.

**3. Remove any Session 4 icon additions from `ui.jsx`.**

Check `ui.jsx` for icons added specifically for Session 4:
- `microsoft` icon (added for the "Log in with Microsoft" button)
- `sparkle` icon (added for the prototype note banner) — only remove if unused elsewhere

Remove these entries from the icon map. Keep any icons that are used outside Session 4 UI.

---

## Group 2 — Strip Session 4 auth code from `store.jsx`

**4. Remove the auth persistence block near the top of `store.jsx`.**

Delete these three items (all appear in the first ~40 lines of the file):

- `const AUTH_KEY = 'autobom.auth';`
- `const lastRoleKey = (userId) => ...`
- The `persistAuth()` function
- The `landingRoleFor(user)` function
- The `hydrateAuth()` IIFE (the `(function hydrateAuth() { ... })();` block)

None of these existed at end of Note 3. All were added by Session 4.

**5. Simplify `actorName()` back to its Note 3 form.**

Currently:
```javascript
const actorName = () => (STATE.users.find(u => u.id === STATE.currentUserId) || {}).name || 'You';
```

Revert to whatever was there at end of Note 3 — likely:
```javascript
const actorName = () => 'Aaron Jones';
```

Or whatever the pre-Session-4 implementation returned (a hardcoded name or role-based label). The point is: `actorName` should not depend on `STATE.currentUserId` or read from `STATE.users`.

**6. Delete the `logIn(email)` action.**

Find the action in the `actions` object (near the top of the actions block). Delete the entire action, including any comments introducing it as "prototype auth."

**7. Delete the `logOut()` action.**

Same as above — find and delete entirely.

**8. Revert `setRole(role)` to its Note 3 form.**

Currently:
```javascript
setRole(role) {
  const u = STATE.users.find(x => x.id === STATE.currentUserId);
  if (u && u.roles && !u.roles.includes(role)) return;
  STATE.activeRole = role;
  persistAuth();
  emit();
}
```

Revert to the simple form from Note 3:
```javascript
setRole(role) {
  STATE.activeRole = role;
  emit();
}
```

No user validation. No persistAuth call. Just switches the active role.

**9. Revert all `ownerId: STATE.currentUserId` references in create actions.**

Session 4 added `ownerId: STATE.currentUserId` to several create actions:
- `createProgram` action
- `createProject` action
- `createBOM` (or equivalent) action
- Any development-role create actions

Search for `STATE.currentUserId` across `store.jsx` and revert each to its Note 3 form. Depending on the original pattern, this is either:
- Removing the `ownerId` field entirely if it wasn't there before, OR
- Replacing `STATE.currentUserId` with a hardcoded string like `'u-aaron'`

Check git history or a backup ZIP from before Session 4 if the original form is unclear.

**10. Verify no other `STATE.authed` or `STATE.currentUserId` references remain in `store.jsx`.**

Grep the file. If any references exist, remove them. Zero occurrences of `STATE.authed` and `STATE.currentUserId` in `store.jsx` after this action.

---

## Group 3 — Strip Session 4 UI code from `shell.jsx`

**11. Revert `RoleSwitcher` to its Note 3 "view-as-any-role" form.**

Currently `RoleSwitcher` reads `useStore(s => s.users.find(u => u.id === s.currentUserId))` and filters its options to only the current user's `roles[]`.

Revert to the Note 3 form: a prototype switcher that shows Designer, Production, and Admin as options regardless of any user context. Session 3's "PROTOTYPE — VIEW AS ANY ROLE" affordance is what should be here.

**12. Remove the `UserMenu` component entirely from `shell.jsx`.**

The `UserMenu` function was added in Session 4 to render the top-right avatar dropdown with log-out. Delete the entire function.

**13. Remove the `<UserMenu>` invocation from `TopRail`.**

In the `TopRail` function, find `<UserMenu go={go} />` and delete that line. The top-right area of the top rail goes back to just the search overlay button and notification bell — no user identity display.

Also remove any imports or destructures referencing `UserMenu` that become dead code after the removal.

---

## Group 4 — Strip Session 4 seed data changes from `data.jsx`

**14. Revert the `USERS` seed array to its Note 3 form.**

Session 4 added `primaryRole`, `invitedBy`, and `createdAt` fields to each user object during Group 1 seed reconciliation. Remove these three fields from every user entry in the `USERS` const.

Also verify:
- `seedState()` return object still has `activeRole: 'designer'` (or whatever Note 3 initial role was)
- `seedState()` still exports `currentUserId: 'u-aaron'` — this can stay as it existed pre-Session-4 as the "default actor" concept
- `seedState()` should NOT contain `authed:` — remove that field if Session 4 added it

If `Project.lead`, `Collection.owner`, or `Program.owner` fields were converted from name strings to user IDs during Session 4 Group 1, revert them to their Note 3 form (whatever was there before — likely name strings).

---

## Rejection criteria for the whole session

If any of these are true at the end of the session, the rollback did not close:

- `screen_login.jsx` still exists in the `autobom/` folder
- Any HTML file still references `screen_login.jsx` via a script tag
- `store.jsx` contains any of: `AUTH_KEY`, `persistAuth`, `landingRoleFor`, `hydrateAuth`, `logIn(`, `logOut(`, `STATE.authed`, `STATE.currentUserId`
- `actorName()` reads from `STATE.users` or references `STATE.currentUserId`
- `setRole` contains user validation logic or a `persistAuth` call
- `shell.jsx` contains a `UserMenu` function definition
- `TopRail` still renders `<UserMenu />`
- `RoleSwitcher` filters options by user roles (should be "view-as-any-role" again)
- Any user entry in `USERS` still has `primaryRole`, `invitedBy`, or `createdAt` fields
- `seedState()` contains an `authed:` field
- Any file except spec docs (`.md`, `.docx`) contains the identifier `LoginScreen` or `currentUserId` or `logIn` or `logOut`
- The prototype fails to render when `AutoBOM Platform.html` is opened in a browser

---

## Success criteria

When the rollback closes:

- The prototype opens cleanly in a browser with all Note 1, 2, and 3 functionality intact
- Programs, Projects, Collections, BOMs, sourcing, purchasing bucket, continuous-identifier chain, scope pills — all working
- The prototype "VIEW AS ANY ROLE" switcher is back in the sidebar (from Note 3)
- No login screen anywhere
- No user menu in the top rail
- Actor names in audit and comments default to a hardcoded value (matching Note 3 behavior)
- Grepping the entire `autobom/` folder for `Session 4` markers returns zero hits in `.jsx` files

The state after this rollback is exactly the end-of-Note-3 state. Nothing more, nothing less.

---

## What this rollback does NOT include

To keep scope tight:

- **No planning for Session 4 retry.** That's a separate conversation. This note only removes.
- **No architectural changes to the prototype.** All Note 1-3 architecture stays.
- **No new features.** Only removal of Session 4 additions.
- **No CLAUDE.md updates.** The operating context can stay as-is until the retry is planned.

---

## Notes for execution

- **Grep before you delete.** Before removing something, grep the entire codebase to confirm it's only used in Session 4 contexts. If a reference exists elsewhere, understand why before removing.
- **One file at a time.** Complete one file's rollback (all edits, all removals) before moving to the next. Don't stitch changes across files partially.
- **Verify render between files.** After each file's rollback is complete, refresh the prototype in a browser and confirm it still renders. If it breaks partway through, isolate the problem before continuing.
- **Do not "improve" during rollback.** If you notice something you'd want to fix in Note 3 code while doing this rollback, don't. Note that observation separately for a future coordination note. This note is pure removal.

---

## After this note lands

The prototype is back at end-of-Note-3 state. Session 4 becomes a topic for future re-attempt with a chunked approach (probably Notes 4a through 4e, each adding one piece of the login system with render verification between each). That planning is a separate conversation.
