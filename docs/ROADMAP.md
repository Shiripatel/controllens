# Roadmap

## v1.0 (done)

- ITGC library: 20 controls across APD, PC, CO, PD
- DE, OE and Reviewer agents with step-by-step trace
- Citation checks, downgrade of unsupported claims, code-only math
- Sampling engine with seeded selection and override rules
- Preparer / reviewer sign-off, segregation of duties, automatic revocation
- Review notes, exceptions, CSV export
- Hash-chained audit trail, evidence hashing, roles, lockout
- Docker + Postgres, CI, offline demo mode

## v1.1: production hardening

- [ ] SSO (OIDC: Azure AD, Okta) and MFA
- [ ] Alembic migrations
- [ ] Job queue for agent runs (Arq / Celery / Azure Service Bus), more than one worker, retry on restart
- [ ] Evidence in Azure Blob / S3 with encryption and malware scan
- [ ] Secure cookies instead of browser storage, plus rate limiting
- [ ] Daily audit-chain anchor to write-once storage

## v1.2: better agents

- [ ] Choose the model for each step (for example Haiku for planning, Sonnet for testing, Opus for evaluation and review)
- [ ] OCR for scanned PDFs, and image input for screenshots
- [ ] Evaluation set: gold-standard controls with known answers, re-run on every prompt change
- [ ] Prompt caching for large evidence sets
- [ ] Agent drafts the evidence request list (PBC list) from gaps

## v1.3: reporting

- [ ] Signed PDF work paper per control
- [ ] Deficiency summary and aggregation
- [ ] Engagement dashboard export for management

## v2: beyond ITGC

- [ ] Business process controls: P2P, O2C, R2R, payroll
- [ ] SOC 1 / SOC 2 control mapping
- [ ] Roll forward to the next period
- [ ] Continuous control monitoring on live data
- [ ] Multi-tenant (one firm, many clients) with data isolation and retention rules
