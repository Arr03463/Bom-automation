# AutoBOM — Full Documentation Package

This is the complete, current AutoBOM documentation set as of end-of-Note-4. Every file here is the authoritative version. Historical versions have been left out to reduce noise.

Suggested local folder structure: put this whole `AutoBOM_Full_Package/` folder wherever you keep your AutoBOM project files (e.g., alongside the `autobom/` prototype code).

---

## What's in each folder

### `CLAUDE.md` (top-level)

Operating context for Claude Architect (System Architect role). Contains the v1.5.1 platform locks, current state, and behavioral guidance. **Read this first if you're onboarding a new Claude session on this project.**

---

### `00_Core_Spec/` — The three anchor documents

These define WHAT AutoBOM is. Everything else builds on these.

- **`AutoBOM_PRD_v1.5.1.docx`** — Product Requirements Document. The definitive spec of every feature, workflow, and behavior. This is the single source of truth for the platform.
- **`AutoBOM_Permissions_Matrix_v1.5.docx`** — Who can do what. Every action per role, with fine-grained overrides. Referenced by Claude Design and Claude Code when building role-scoped behavior.
- **`AutoBOM_Claude_Design_Package_v1.5.1.docx`** — Master design contract. UI/UX principles, layout conventions, component patterns. Referenced by Claude Design as the anchor for every design decision.

---

### `01_Module_Packages/` — Feature area deep dives

Each of these is a Claude Design Package for a specific module. Referenced when working on that specific area of the platform.

- **`AutoBOM_Purchasing_v4.1_Claude_Design_Package.docx`** — Purchasing bucket, batch flush pipeline, Mouser/DigiKey cart building, OneDrive sheet integration
- **`AutoBOM_Inventory_Activation_v3.1_Claude_Design_Package.docx`** — PartsBox integration, project boxes vs wall bins, receiving flow, build execution
- **`AutoBOM_Designer_Workspace_Alignment_v1.1.1_Claude_Design_Package.docx`** — Designer role UX (Collections, sourcing, Push-Back resolution)
- **`AutoBOM_Production_Workspace_Alignment_v1.1.1_Claude_Design_Package.docx`** — Production role UX (Master BOM screen, Builds, Push-Back initiation, receiving)

---

### `02_Architecture/` — How the system is structured

These are how the platform is built and how the pieces connect. Referenced heavily by Claude Code.

- **`AutoBOM_Platform_Architecture.md`** — High-level system architecture. Services, databases, external APIs, deployment topology
- **`AutoBOM_Data_Flow_and_Sequencing.md`** — Data model, state flow, timing/sequencing rules (bucket timers, cache TTLs, etc.)
- **`AutoBOM_API_Responsibility_Map.md`** — Every API endpoint the backend will expose, what it does, who calls it, who's responsible for what layer
- **`AutoBOM_Code_to_Service_Connections.md`** — Maps existing POC code to the future service architecture. Useful for planning the POC → production refactoring
- **`AutoBOM_POC_Baseline_Analysis.md`** — Analysis of the existing Python POC (Mouser/DigiKey/PartsBox clients, sourcing engine, etc.) — what's reusable, what needs to change

---

### `03_Coordination_Notes/` — Change history

Each coordination note captures a specific set of changes handed to Claude Design. Notes 1-3 executed cleanly; Note 4 (Login Screen) had a rendering issue that was later resolved via standalone HTML.

- **`AutoBOM_Coordination_Note_1_Housekeeping.md`** — Cleanup and misc fixes
- **`AutoBOM_Coordination_Note_2_Forward_Layer.md`** — Push-Back model with recommendation objects, missing-component branch, characteristic-match auto-generation
- **`AutoBOM_Coordination_Note_3_Create_Flows_and_Baseline_Cleanup.md`** — Create Program/Project modals, sigil removal, continuous-identifier chain, scope pills, Class field retirement, Standalone Project retirement, Task Center deletion
- **`AutoBOM_Coordination_Note_4_Prototype_Login_Screen.md`** — Login screen, Model D landing, session persistence, role switcher rework, user menu
- **`AutoBOM_Coordination_Note_4_Rollback.md`** — Rollback instructions if Note 4 needs to be reverted (currently not needed — Note 4 is intact via standalone build)

---

### `04_Infrastructure/`

- **`AutoBOM_Azure_Requirements_Checklist.md`** — Everything to ask/verify with the company Microsoft 365 admin for Azure setup and SSO. Use this when talking to admin.

---

### `05_Reference/`

- **`AutoBOM_Product_Discovery_Report.md`** — Original discovery / problem-space document. Historical context for why AutoBOM exists and what problems it solves. Not required for daily work but useful background.

---

### `06_Prototype/`

- **`AutoBOM_STANDALONE.html`** — Fully self-contained HTML with all code inlined. Double-click to open in a browser and view the prototype. No installation required. This is your quick-look-at-the-app file.
- **`AutoBoM_working.zip`** — Multi-file prototype at end-of-Note-3 state (before Note 4 login screen). Extract if you want to edit individual files. Note 4 additions are NOT in this ZIP — use the standalone HTML above for the current state.

---

## How to use this locally

**In VS Code:**

1. Open the whole `AutoBOM_Full_Package/` folder in VS Code (`File → Open Folder`)
2. Read `CLAUDE.md` first for context
3. Read `00_Core_Spec/AutoBOM_PRD_v1.5.1.docx` for the platform spec (use Word/Docs viewer)
4. Reference module packages as you work on specific features
5. Reference coordination notes to understand what changed and when

**When talking to Claude Design or Claude Code:**

- Attach `CLAUDE.md` + relevant module package as the operating context
- Attach the specific coordination note you're executing

**When making a new coordination note:**

- Reference the existing notes for pattern
- Every note should reference the current baseline (v1.5.1)
- Explicit rejection criteria at the end

---

## What's NOT in this package

- Historical versions (v1.0-v1.4) of spec documents — superseded by v1.5.1
- Old coordination note drafts — superseded by Notes 1-4
- Old design brief docs — superseded by Claude Design Package v1.5.1
- Old flowchart JSX files — superseded by workflow architecture docs
- The Python POC code — that lives in your existing project files. This package is just the specs and design docs.

---

## Package generated at end of Note 4 (v1.5.1 baseline). Update as coordination notes land.
