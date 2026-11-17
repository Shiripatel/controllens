# API reference

Base URL: `/api`. All responses are JSON unless noted. Full interactive docs (Swagger): `http://localhost:8000/docs`.

## Authentication

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"priya.preparer@controllens.local","password":"Demo#12345"}'
# → {"token": "eyJ...", "user": {...}}
```

Send the token on every other call:

```
Authorization: Bearer eyJ...
```

Tokens expire after `CL_JWT_EXPIRE_MINUTES` (default 480 minutes).

## Errors

| Code | Meaning |
|---|---|
| 401 | Not signed in, or the token expired |
| 403 | Your role or engagement membership doesn't allow this, or segregation of duties blocks it |
| 404 | Not found |
| 409 | Conflict: wrong status for this step, someone else changed the record, duplicate file, open review notes, or engagement locked |
| 413 / 415 | File too large / file type not allowed |
| 422 | Input not valid (the message says what to fix) |
| 423 | Account locked after failed logins |

Error body: `{"detail": "Plain-English message"}`. Every response has an `X-Request-ID` header for tracing.

## Endpoints

"Min role" is the lowest role allowed. Write calls also need engagement membership (managers and admins see all) and an **active** (not locked) engagement.

### Auth and users

| Method | Path | Min role | What it does |
|---|---|---|---|
| POST | `/auth/login` | – | Sign in, get a token |
| GET | `/auth/me` | viewer | Current user |
| GET | `/users` | viewer | List users |
| POST | `/users` | admin | Create user `{email, name, role, password}` |
| PATCH | `/users/{uid}` | admin | Change name, role, active or password |

### Library and engagements

| Method | Path | Min role | What it does |
|---|---|---|---|
| GET | `/library` | viewer | ITGC library, domains, frequencies |
| GET | `/engagements` | viewer | Engagements you can see, with stats |
| POST | `/engagements` | manager | Create `{name, client, engagement_type, period_start, period_end}` |
| GET | `/engagements/{eid}` | viewer | Details, systems, members, stats |
| PATCH | `/engagements/{eid}` | manager | Rename, or set `status` to active / locked / archived |
| POST | `/engagements/{eid}/members` | manager | Add member `{user_id}` |
| DELETE | `/engagements/{eid}/members/{uid}` | manager | Remove member |
| POST | `/engagements/{eid}/systems` | preparer | Add system `{name, layer, description}` |
| DELETE | `/engagements/{eid}/systems/{sid}` | preparer | Remove system (only if it has no controls) |
| POST | `/engagements/{eid}/controls/from-library` | preparer | `{refs: ["APD-01"], system_ids: [1, 2], risk_rating}`. Creates one control per ref per system. |
| POST | `/engagements/{eid}/controls` | preparer | Create a custom control |
| GET | `/engagements/{eid}/controls` | viewer | List controls |
| GET | `/engagements/{eid}/export.csv` | viewer | CSV status export (file download) |

### Controls

| Method | Path | Min role | What it does |
|---|---|---|---|
| GET | `/controls/{cid}` | viewer | Full control, test type, sign-offs, AI provider |
| PATCH | `/controls/{cid}` | preparer | Edit. **Must send `row_version`.** Design changes revoke sign-offs. |
| DELETE | `/controls/{cid}` | manager | Delete (only if not started) |
| GET | `/controls/{cid}/activity` | viewer | Audit entries for this control |

### Evidence

| Method | Path | Min role | What it does |
|---|---|---|---|
| GET | `/controls/{cid}/evidence` | viewer | List files |
| POST | `/controls/{cid}/evidence` | preparer | Multipart upload: `file`, `purpose` (design / toe / population / general), `description` |
| GET | `/evidence/{id}/text` | viewer | Text the agents read |
| GET | `/evidence/{id}/download` | viewer | Original file. The hash is checked first. |
| DELETE | `/evidence/{id}` | preparer | Soft delete. Revokes affected sign-offs. |

### Sampling

| Method | Path | Min role | What it does |
|---|---|---|---|
| GET | `/controls/{cid}/sampling` | viewer | Test type, methodology size, current sample |
| POST | `/controls/{cid}/sampling` | preparer | `{population_evidence_id, seed?, override_size?, override_reason?}`. Going below the methodology size needs reviewer role and a reason. |

### Agents

| Method | Path | Min role | What it does |
|---|---|---|---|
| POST | `/controls/{cid}/runs` | preparer | Start `{agent: "dni" \| "toe" \| "reviewer"}` → **202** with run id |
| GET | `/controls/{cid}/runs?agent=toe` | viewer | Run history (summary) |
| GET | `/runs/{rid}` | viewer | Full run: steps, result, flags. Check this until `status` is `succeeded` or `failed`. |

Example:

```bash
RUN=$(curl -s -X POST localhost:8000/api/controls/1/runs -H "Authorization: Bearer $T" \
  -H "Content-Type: application/json" -d '{"agent":"dni"}' | jq .id)
curl -s localhost:8000/api/runs/$RUN -H "Authorization: Bearer $T" | jq '.status, .result.proposed_conclusion'
```

### Conclusions and sign-offs

| Method | Path | Min role | What it does |
|---|---|---|---|
| POST | `/controls/{cid}/conclusion` | preparer | `{stage, run_id?, conclusion: {...}, rationale}`. A rationale is required if you differ from the agent. |
| POST | `/controls/{cid}/signoffs` | preparer / reviewer | `{stage: "dni" \| "toe", kind: "prepare" \| "review", comment}` |

Sign-off rules:

| Kind | Rules |
|---|---|
| prepare | Status must be `<stage>_in_progress`. Conclusion must be confirmed. Only the assigned preparer or a manager. |
| review | Status must be `<stage>_prepared`. Reviewer role or higher. **Not the preparer.** No open review notes for the stage. |

### Review notes and exceptions

| Method | Path | Min role | What it does |
|---|---|---|---|
| GET | `/controls/{cid}/notes` | viewer | List notes |
| POST | `/controls/{cid}/notes` | preparer | `{stage, severity, text}` |
| PATCH | `/notes/{nid}` | preparer | `{response?, status?}`. Setting `status: closed` needs reviewer role. |
| GET | `/controls/{cid}/exceptions` | viewer | List exceptions |
| PATCH | `/exceptions/{xid}` | preparer | `{status?, severity?, description?}`. Revokes TOE sign-offs. |

### Audit and health

| Method | Path | Min role | What it does |
|---|---|---|---|
| GET | `/audit?engagement_id=&action=&limit=&before_id=` | viewer (own engagements) / manager (all) | Audit entries, newest first |
| GET | `/audit/verify` | manager | Check the hash chain → `{valid, checked, broken_at_id}` |
| GET | `/health` | – | `{status, ai_provider, model}` |
