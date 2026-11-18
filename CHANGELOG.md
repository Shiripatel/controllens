# Changelog

## [1.3.0] - 2026-11-17

### Added
- "My work" home page: controls to prepare, controls to review, open review notes and open requests
- Next-step bar on each control that says what to do next, with a button to do it
- Evidence opens in a side panel beside the results when you click a quote
- Results show one line per attribute; open a row for the full reasoning and quotes
- Live step progress in the agents panel while an agent runs

### Changed
- Cleaner look: smaller text, more space, lighter headings, softer green, flat tables, dot-and-text status

## [1.2.0] - 2026-11-17

### Changed
- Engagements page is now a list with status counts, filters, a controls progress bar and request counts per engagement
- Matrix rows show files, request status and sign-offs; a Columns menu picks which columns to show
- Controls list is now a risk & control matrix (risk, control, system, conclusions), grouped by domain; rows open the workspace
- Control page is now a three-pane testing workspace: editable control details, work area, and an agents panel with run status
- Previous / next control buttons; side panels can be hidden; app menu shrinks to icons on the workspace

## [1.1.0] - 2026-11-17

### Added
- Screenshots (PNG / JPG) and scanned PDFs are sent to the model as images
- Evidence intake check after every upload: type, period, system, attributes supported, quality issues
- Citation viewer: click a quote to open the evidence with the quote highlighted
- Evidence request list per control and per engagement, drafted from agent gaps, with CSV export
- Printable work paper export per control
- Optional model per kind of step (`CL_LLM_MODEL_PLAN` / `_EVALUATE` / `_TEST` / `_REVIEW`); model shown on each step
- Limit on agent runs per user per hour
- Alembic database migrations, run on start
- One-click Render deploy (`render.yaml`), configurable demo password, container fixes data disk ownership

## [1.0.0] - 2026-11-17

First release.

### Added
- ITGC control library with 20 controls across Access to Programs & Data, Program Change, Computer Operations and Program Development
- Engagements, systems, team members, adding controls from the library per system
- Evidence upload with text extraction (PDF, Excel, Word, CSV, text), SHA-256 hashing and soft delete
- Design Effectiveness agent (5 steps), Operating Effectiveness agent (7 steps) and Reviewer agent (3 steps)
- Guardrails: forced structured output, citation verification, downgrade of unsupported claims
- Sampling engine: frequency and risk-based sizes, seeded selection, override rules
- Human conclusions with a required reason when they differ from the agent
- Preparer / reviewer sign-offs, segregation of duties, automatic revocation on change
- Review notes and exceptions
- Hash-chained audit trail with an integrity check
- Roles (viewer, preparer, reviewer, manager, admin), lockout, password rules
- React web app, CSV export, Docker + Postgres, GitHub Actions CI
- Offline demo mode and demo data (Acme Corp FY2026)
