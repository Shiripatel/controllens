# Data model

All tables are defined in `backend/app/models.py` (SQLAlchemy 2). The same model runs on Postgres and SQLite.

## Diagram

```mermaid
erDiagram
    USERS ||--o{ ENGAGEMENT_MEMBERS : "is member"
    ENGAGEMENTS ||--o{ ENGAGEMENT_MEMBERS : has
    ENGAGEMENTS ||--o{ SYSTEMS : "has in scope"
    ENGAGEMENTS ||--o{ CONTROLS : contains
    SYSTEMS ||--o{ CONTROLS : "tested on"
    CONTROLS ||--o{ EVIDENCE : has
    CONTROLS ||--o{ SAMPLES : has
    EVIDENCE ||--o| SAMPLES : "is population for"
    CONTROLS ||--o{ AGENT_RUNS : has
    CONTROLS ||--o{ REVIEW_NOTES : has
    CONTROLS ||--o{ EXCEPTIONS : has
    CONTROLS ||--o{ SIGNOFFS : has
    USERS ||--o{ SIGNOFFS : signs

    ENGAGEMENTS {
        int id PK
        string name
        string client
        string engagement_type
        date period_start
        date period_end
        string status "active | locked | archived"
    }
    SYSTEMS {
        int id PK
        int engagement_id FK
        string name
        string layer "Application | Database | OS | Network | Tool"
    }
    CONTROLS {
        int id PK
        int engagement_id FK
        int system_id FK
        string ref
        string domain "APD | PC | CO | PD"
        string frequency
        string nature
        string risk_rating
        json attributes
        string status
        json design_conclusion "set by a person"
        json operating_conclusion "set by a person"
        int row_version
    }
    EVIDENCE {
        int id PK
        int control_id FK
        string filename
        string sha256
        string purpose "design | operating | population | general"
        text extracted_text
        bool deleted
    }
    SAMPLES {
        int id PK
        int control_id FK
        int population_size
        int sample_size
        int seed
        json items
        bool active
    }
    AGENT_RUNS {
        int id PK
        int control_id FK
        string agent "design | operating | reviewer"
        string status
        string model
        string prompt_version
        string input_hash
        json steps
        json result
        json guardrail_flags
    }
    SIGNOFFS {
        int id PK
        int control_id FK
        int user_id FK
        string stage "design | operating"
        string kind "prepare | review"
        bool revoked
    }
    AUDIT_LOG {
        int id PK
        datetime at
        string action
        json details
        string prev_hash
        string hash
    }
```

## Tables

| Table | One row is... | Notes |
|---|---|---|
| `users` | A person who can sign in | `role`: viewer, preparer, reviewer, manager, admin. Tracks failed logins and lockout. |
| `engagements` | One audit engagement for one client and period | `status=locked` makes everything read-only |
| `engagement_members` | A user on an engagement | Preparers, reviewers and viewers only see engagements they're members of |
| `systems` | An in-scope application or layer | A library control can be added once per system |
| `controls` | One control tested on one system | A copy of the library template, then tailored. `library_ref` keeps the source. |
| `evidence` | One uploaded file | File on disk is named `<sha256 prefix>_<name>`. Text is stored for the agents. Soft delete only. |
| `samples` | One sample selection | Only one `active` sample per control. Older ones are kept. |
| `agent_runs` | One agent run | Full trace. See [AGENTS.md](AGENTS.md#what-a-run-stores). |
| `review_notes` | One review comment | `source`: human or reviewer_agent. `status`: open, addressed, closed. |
| `exceptions` | One failed test (item × attribute) | `severity`: deficiency, significant, material. `status`: open, accepted, remediated. |
| `signoffs` | One prepare or review sign-off | Never deleted, only marked `revoked` |
| `audit_log` | One action | Append-only and hash-chained. See [SECURITY.md](SECURITY.md#audit-trail). |

## Control statuses

| Status | Meaning |
|---|---|
| `not_started` | Nothing done yet |
| `design_in_progress` | Design Effectiveness agent run or Design conclusion confirmed |
| `design_prepared` | Preparer signed DE |
| `design_reviewed` | Reviewer signed DE |
| `operating_in_progress` | OE work started |
| `operating_prepared` | Preparer signed OE |
| `operating_reviewed` | Reviewer signed OE. The control is complete. |

## Conclusion values

| Field | Values |
|---|---|
| `design_conclusion.design` | `effective`, `not_effective`, `insufficient_evidence` |
| `design_conclusion.implementation` | `implemented`, `not_implemented`, `insufficient_evidence` |
| `operating_conclusion.operating` | `operating_effectively`, `not_operating_effectively`, `insufficient_evidence` |

Each conclusion also stores `rationale`, `run_id`, `overrode_agent` and `confirmed_by`.
