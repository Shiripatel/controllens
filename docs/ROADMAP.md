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

## v1.1 (done)

- Screenshots and scanned PDFs read by the AI as images
- Evidence intake check on every upload
- Citation viewer with the quote highlighted
- Evidence request list (per control and engagement, CSV export)
- Printable work paper export
- Model per kind of step, hourly run limit
- Alembic migrations, one-click Render deploy

## v1.2: production hardening

- [ ] SSO (OIDC: Azure AD, Okta) and MFA
- [ ] Job queue for agent runs (Arq / Celery / Azure Service Bus), more than one worker, retry on restart
- [ ] Evidence in Azure Blob / S3 with encryption and malware scan
- [ ] Secure cookies instead of browser storage, plus rate limiting
- [ ] Daily audit-chain anchor to write-once storage

## v1.3: better agents

- [ ] Evaluation set: gold-standard controls with known answers, re-run on every prompt change
- [ ] Prompt caching for large evidence sets
- [ ] Client portal: clients upload against requests with their own login

## v1.4: reporting

- [ ] Digitally signed PDF version of the work paper
- [ ] Deficiency summary and aggregation
- [ ] Engagement dashboard export for management

## v2: beyond ITGC

- [ ] Business process controls: P2P, O2C, R2R, payroll
- [ ] SOC 1 / SOC 2 control mapping
- [ ] Roll forward to the next period
- [ ] Continuous control monitoring on live data
- [ ] Multi-tenant (one firm, many clients) with data isolation and retention rules
