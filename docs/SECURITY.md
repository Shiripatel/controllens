# Security and controls

ControlLens holds audit evidence and sign-offs, so it has to meet the same standards it tests. This page covers what is built in and what is still to do.

## Roles

| Role | Can do |
|---|---|
| **viewer** | Read the engagements they're a member of |
| **preparer** | Upload evidence, run agents, select samples, confirm conclusions, sign as preparer, add review notes |
| **reviewer** | Everything a preparer can, plus sign as reviewer, close review notes, and reduce sample size below the methodology (with a reason) |
| **manager** | Everything a reviewer can, plus see all engagements, create and lock engagements, manage members, delete unstarted controls, view and verify the full audit trail |
| **admin** | Everything, plus create users and change roles |

Every rule is checked on the **server**. The web app only hides buttons for convenience.

## Segregation of duties

| Rule | Where it's enforced |
|---|---|
| The person who prepared a stage can't review it | `workflow.sign()` |
| Reviewer sign-off is blocked while review notes are open | `workflow.sign()` |
| Only reviewers and above can close review notes | `PATCH /notes/{id}` |
| Reducing a sample below methodology needs reviewer role and a reason | `POST /sampling` |
| Agents can't sign off or set final conclusions | Agents only write to `agent_runs`, `review_notes` and `exceptions` |
| Changing the agent's proposed conclusion needs a written reason | `POST /conclusion` |
| Admins can't deactivate or demote themselves | `PATCH /users/{id}` |

## Integrity of work papers

- **Automatic revocation.** When anything a sign-off relied on changes (the control definition, evidence, sample, exceptions or conclusion), those sign-offs are revoked and the status goes back. See [ARCHITECTURE.md](ARCHITECTURE.md#5-control-workflow).
- **Row versions.** Edits to a control must include the version the user loaded. If someone else saved first, the edit is rejected (409).
- **Engagement lock.** Locked or archived engagements reject all changes.
- **Nothing is hard-deleted** except unstarted controls. Evidence is soft-deleted, and sign-offs are marked revoked.

## Audit trail

Every important action writes a row to `audit_log` in the same transaction as the change itself: logins (and failed logins), engagement and control changes, uploads, downloads, removals, samples, agent starts and finishes, conclusions, sign-offs, revocations, notes, exceptions, exports and user changes.

**Hash chain.** Each row stores:

```
hash = SHA-256( prev_hash, time, user_id, action, entity, entity_id, details )
```

The first row's `prev_hash` is 64 zeros. Changing or deleting any row breaks every hash after it. `GET /api/audit/verify` (or **Verify integrity** in the UI) walks the whole chain and reports the first broken row.

> The chain detects tampering. It doesn't prevent someone with database access from rewriting the whole chain. For stronger protection, copy the latest hash to a separate system on a schedule (for example, a daily anchor in write-once storage). This is on the roadmap.

## Evidence

| Check | Detail |
|---|---|
| Allowed types | pdf, txt, csv, log, md, json, xml, xlsx, xlsm, docx, png, jpg, jpeg, eml |
| Size limit | `CL_MAX_UPLOAD_MB` (default 25 MB) |
| File name | Path parts stripped and unsafe characters replaced |
| Fingerprint | SHA-256 stored at upload. Re-checked on every download. A mismatch is blocked and logged as `evidence.integrity_failed`. |
| Duplicates | The same file can't be attached twice to one control |
| Access | Download needs engagement access, and every download is logged |

## Login and sessions

- Passwords hashed with **bcrypt** (cost 12).
- Strength: 10+ characters with upper case, lower case and a number.
- **Lockout:** 5 failed tries → locked for 15 minutes.
- JWT (HS256), signed with `CL_JWT_SECRET`. In `CL_ENV=prod` the app refuses to start without a random secret of 32+ characters.
- The web app keeps the token in `sessionStorage`, so it's cleared when the tab closes.

## HTTP

- Security headers on every response: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`.
- `Cache-Control: no-store` on API responses.
- CORS limited to `CL_CORS_ORIGINS`.
- Errors return a request ID and never return a stack trace.

## AI data handling

- Agents send only the selected control and its evidence text to the model, nothing from other controls or engagements.
- What was sent is traceable: the run stores the evidence IDs and an input hash.
- With no API key set, no data leaves the server (offline mode).
- Check your Anthropic data-retention terms and your client contracts before sending client data to any AI service.

## Known gaps (before real client data)

| Gap | Plan |
|---|---|
| Local passwords only | SSO via OIDC (Azure AD / Okta) with MFA |
| Token in browser storage | Move to secure, http-only cookies with CSRF protection |
| No rate limiting | Add at the reverse proxy and on `/auth/login` |
| Evidence not encrypted at rest by the app | Use encrypted object storage (Azure Blob / S3 with KMS) |
| No malware scan | Scan uploads (for example ClamAV or a cloud scanner) |
| Audit chain not anchored outside the database | Daily hash anchor to write-once storage |
| No formal pen test | Before production |

## Reporting a security issue

Please don't open a public issue. Contact the maintainer directly.
