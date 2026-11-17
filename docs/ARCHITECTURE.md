# Architecture

This page explains how ControlLens is built and why it is built that way.

- [1. Big picture](#1-big-picture)
- [2. Components](#2-components)
- [3. How a request flows](#3-how-a-request-flows)
- [4. How an agent run flows](#4-how-an-agent-run-flows)
- [5. Control workflow](#5-control-workflow)
- [6. Key design choices](#6-key-design-choices)
- [7. Deployment view](#7-deployment-view)
- [8. Limits of version 1](#8-limits-of-version-1)

---

## 1. Big picture

ControlLens has three layers: a web app, an API, and the agents. Everything is stored in one database and one evidence folder. Every API module writes to the audit log through `audit.py`.

```mermaid
flowchart TB
    subgraph Client
        UI["React web app<br/>(Vite, TypeScript)"]
    end

    subgraph Server["FastAPI server"]
        MW["Middleware<br/>request ID · security headers · logging"]
        AUTH["Auth & roles<br/>JWT · bcrypt · lockout"]
        R1["Engagements API"]
        R2["Controls API<br/>evidence · sampling · conclusions · sign-offs · notes"]
        R3["Audit API"]
        WF["Workflow rules<br/>SoD · status · revocation"]
        SAM["Sampling engine"]
        EXT["Text extraction"]
        RUN["Agent runner"]
        AUD["Audit logger<br/>(hash chain)"]
    end

    subgraph Agents
        DNI["D&I agent"]
        TOE["TOE agent"]
        REV["Reviewer agent"]
        GR["Guardrails<br/>citation check · downgrade"]
        LLM["LLM layer<br/>Claude or offline mock"]
    end

    subgraph Storage
        DB[("Database<br/>Postgres / SQLite")]
        FS[("Evidence files")]
    end

    UI -->|HTTPS + Bearer token| MW --> AUTH
    AUTH --> R1 & R2 & R3
    R2 --> WF & SAM & EXT
    R2 -->|start run| RUN
    RUN --> DNI & TOE & REV
    DNI & TOE --> GR
    DNI & TOE & REV --> LLM
    LLM -->|API| CLAUDE(("Anthropic API"))
    WF & RUN --> AUD
    Server -->|"SQL, one transaction per request"| DB
    R2 --> FS
```

---

## 2. Components

### Front end (`frontend/`)

| Part | File | Job |
|---|---|---|
| API client | `src/api.ts` | Adds the token, handles errors, signs out on 401 |
| Shared UI | `src/components/ui.tsx` | Toasts, modals, tabs, badges, data loading hooks |
| App shell | `src/App.tsx` | Routes, sign-in state, side bar, role checks |
| Control workspace | `src/pages/ControlWorkspace.tsx` | The main screen: control, evidence, D&I, sampling, TOE, review, activity |

The front end has no business rules of its own. It shows or hides buttons based on role and status, but **the server checks everything again**.

### Back end (`backend/app/`)

| Module | Job |
|---|---|
| `main.py` | Starts the app, creates tables, seeds data, marks stuck runs as failed, serves the built web app |
| `config.py` | All settings come from environment variables with the `CL_` prefix |
| `security.py` | Password hashing, tokens, role ranks, engagement access checks |
| `routers/` | REST endpoints. Thin: they check input and access, then call the modules below |
| `workflow.py` | Status changes, sign-off rules, segregation of duties, revoking sign-offs |
| `sampling.py` | Test type, sample size table, reading population files, seeded selection |
| `extraction.py` | Gets text from PDF, Excel, Word, CSV and text files |
| `audit.py` | Writes and checks the hash-chained audit log |
| `library.py` | The 20 standard ITGCs |
| `agents/` | The three agents, the runner, the LLM layer and the prompts |

---

## 3. How a request flows

Example: a preparer uploads an evidence file.

```mermaid
sequenceDiagram
    autonumber
    participant UI as Web app
    participant API as FastAPI
    participant SEC as security.py
    participant WF as workflow.py
    participant FS as Evidence store
    participant DB as Database
    participant AUD as audit.py

    UI->>API: POST /api/controls/12/evidence (file, purpose)
    API->>SEC: Check token, role, engagement membership, engagement not locked
    API->>API: Check file type, size, not empty
    API->>API: SHA-256 hash, block duplicates
    API->>FS: Save file as <hash>_<name>
    API->>API: Extract text
    API->>DB: Insert evidence row
    API->>WF: Revoke sign-offs this file affects
    API->>AUD: Log "evidence.uploaded" (hash, size, purpose)
    API->>DB: Commit (one transaction)
    API-->>UI: 201 + evidence record
```

All the database changes for one request, including the audit row, are saved in **one transaction**. Either everything is saved or nothing is.

---

## 4. How an agent run flows

Agent runs can take a minute or more, so they run in the background. The web app checks progress every 1.5 seconds.

```mermaid
sequenceDiagram
    autonumber
    participant UI as Web app
    participant API as FastAPI
    participant RUN as Agent runner
    participant AG as Agent (D&I / TOE / Reviewer)
    participant LLM as Claude
    participant DB as Database

    UI->>API: POST /controls/12/runs {agent: "toe"}
    API->>DB: Block if a run of this agent is already active
    API->>DB: Create run (queued, prompt version, input hash)
    API-->>UI: 202 Accepted (run id)
    API->>RUN: Start in background
    RUN->>DB: status = running
    loop Each step
        RUN->>DB: Save step as "running"
        AG->>LLM: Forced tool call with JSON schema
        LLM-->>AG: Structured result
        AG->>AG: Guardrails (check citations, downgrade unsupported)
        RUN->>DB: Save step output as "done"
    end
    RUN->>DB: Save result, flags, tokens, status = succeeded
    RUN->>DB: Audit log entry
    loop Every 1.5 s until done
        UI->>API: GET /runs/{id}
        API-->>UI: Steps so far
    end
```

**Input hash.** Before a run starts, the platform hashes the prompt version, the control definition and the hashes of all evidence files. If two runs have the same input hash, they had the same inputs. The reviewer agent also compares the evidence used by a run with the evidence attached now, and flags runs that are out of date.

---

## 5. Control workflow

```mermaid
stateDiagram-v2
    [*] --> not_started
    not_started --> dni_in_progress: run D&I agent / confirm D&I
    dni_in_progress --> dni_prepared: preparer signs<br/>(needs confirmed conclusion)
    dni_prepared --> dni_reviewed: reviewer signs<br/>(different person, no open notes)
    dni_reviewed --> toe_in_progress: run TOE agent / confirm TOE
    toe_in_progress --> toe_prepared: preparer signs
    toe_prepared --> toe_reviewed: reviewer signs
    toe_reviewed --> [*]

    dni_prepared --> dni_in_progress: control or design evidence changed
    dni_reviewed --> dni_in_progress: control or design evidence changed
    toe_prepared --> toe_in_progress: sample, TOE evidence or exception changed
    toe_reviewed --> toe_in_progress: sample, TOE evidence or exception changed
```

What revokes which sign-offs:

| Change | D&I sign-offs | TOE sign-offs |
|---|---|---|
| Control definition edited (attributes, risk, frequency, nature, system...) | Revoked | Revoked |
| Design or general evidence added / removed | Revoked | Revoked |
| D&I conclusion changed | Revoked | Revoked |
| Population or TOE evidence added / removed | – | Revoked |
| New sample selected | – | Revoked |
| Exception status / severity changed | – | Revoked |
| TOE conclusion changed | – | Revoked |

Revoked sign-offs stay in the database (marked revoked), so the history is never lost.

---

## 6. Key design choices

| Choice | Why |
|---|---|
| **AI proposes, people decide** | Audit standards hold people responsible. The `controls.dni_conclusion` / `toe_conclusion` fields are only written by a person through `/conclusion`. Agents write to `agent_runs` only. |
| **Forced tool calls with a schema** | The model must answer in a fixed JSON shape. There's no free-text parsing. Missing fields cause a retry. |
| **Citations checked by code** | The model can be wrong about what a document says. Code checks that each quote really exists in the cited file. |
| **Math in code** | Sample sizes and roll-ups must be repeatable and explainable to a regulator. A seeded random generator means anyone can re-create the sample. |
| **Each step saved as it runs** | Auditors can see what the agent did at each step, and the UI can show live progress. |
| **Versioned prompts** | Every run records `prompt_version`. If results change, you can tell whether the prompt changed. |
| **Hash-chained audit log** | A plain log can be edited without trace. A chain can't be edited without breaking it. |
| **Soft delete for evidence** | Removing a file from a control keeps the record and the file, so the audit trail stays complete. |
| **Row versions on controls** | Stops one person silently overwriting another person's edits. |
| **Offline mock provider** | The full flow can be demoed and tested in CI with no API key and no cost. |
| **One image for API + web app** | Simple to deploy. The web app can also be hosted separately (it only needs `/api`). |

---

## 7. Deployment view

```mermaid
flowchart LR
    B[Browser] -->|HTTPS| LB["Load balancer / reverse proxy<br/>(TLS ends here)"]
    LB --> APP["ControlLens container<br/>uvicorn · API + web app"]
    APP --> PG[("Postgres")]
    APP --> VOL[("Evidence volume")]
    APP -->|HTTPS| AN(("Anthropic API"))
```

See [DEPLOYMENT.md](DEPLOYMENT.md) for settings and the production checklist.

---

## 8. Limits of version 1

These are known and planned (see [ROADMAP.md](ROADMAP.md)):

- Agent runs use FastAPI background tasks inside the web process. Run **one** app container until a job queue is added. If the server restarts mid-run, that run is marked failed.
- Tables are created at start-up. There are no migration scripts yet (planned: Alembic).
- Evidence is stored on local disk or a mounted volume, not cloud object storage.
- Scanned PDFs and images are stored but not read (no OCR yet).
- Login is email + password. SSO is planned.
