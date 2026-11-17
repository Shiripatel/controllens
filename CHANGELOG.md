# Changelog

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
