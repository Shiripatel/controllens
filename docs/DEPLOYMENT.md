# Deployment

## Settings

All settings are environment variables with the `CL_` prefix. Locally, you can put them in `backend/.env` (see `.env.example`).

| Variable | Default | What it does |
|---|---|---|
| `CL_ENV` | `dev` | Set to `prod` in production. This turns on strict secret checks. |
| `CL_DATABASE_URL` | `sqlite:///./controllens.db` | For Postgres: `postgresql+psycopg://user:pass@host:5432/db` |
| `CL_STORAGE_DIR` | `./storage` | Where evidence files are saved |
| `CL_MAX_UPLOAD_MB` | `25` | Largest upload allowed |
| `CL_CORS_ORIGINS` | `http://localhost:5173` | Comma-separated list of allowed web origins |
| `CL_JWT_SECRET` | dev value | **Must be set in prod** (32+ random characters) |
| `CL_JWT_EXPIRE_MINUTES` | `480` | Session length |
| `CL_ANTHROPIC_API_KEY` | empty | Empty = offline demo mode |
| `CL_LLM_PROVIDER` | `auto` | `auto`, `anthropic` or `mock` |
| `CL_LLM_MODEL` | `claude-sonnet-5-5` | Model used by every AI step |
| `CL_LLM_MODEL_PLAN` / `_EVALUATE` / `_TEST` / `_REVIEW` | empty | Optional model per kind of step. Empty uses `CL_LLM_MODEL`. |
| `CL_VISION_ENABLED` | `true` | Send screenshots and scanned PDFs to the model |
| `CL_MAX_VISUAL_FILES` / `CL_MAX_VISUAL_MB` | `10` / `4.5` | Limits for image files per AI call |
| `CL_MAX_RUNS_PER_HOUR` | `60` | Agent runs allowed per user per hour |
| `CL_LLM_MAX_TOKENS` | `8000` | Max output tokens per AI call |
| `CL_MAX_EVIDENCE_CHARS` | `60000` | Evidence text budget per AI call |
| `CL_SEED_ADMIN_EMAIL` | `admin@controllens.local` | First admin (created only if there are no users) |
| `CL_SEED_ADMIN_PASSWORD` | `Admin#12345` | **Change it.** |
| `CL_SEED_DEMO_PASSWORD` | `Demo#12345` | Password for the demo users. **Change it on any public site.** |
| `CL_SEED_DEMO` | `true` | Creates demo users and the Acme engagement. **Set to `false` in prod.** |

## Render

The repo has a `render.yaml` blueprint. Click **Deploy to Render** in the README, or in Render choose **New → Blueprint** and pick this repo.

It creates one always-on web service from the `Dockerfile`, with a 1 GB disk mounted at `/data`. The database (SQLite) and evidence files live on that disk, so they survive restarts and new deploys.

1. Enter the three values Render asks for: admin password, demo password, Anthropic key (optional).
2. Wait for the first build (about 5 minutes). Open the `onrender.com` link.
3. Sign in as `shirish@controllens.local` with your demo password.

Notes:
- Seed passwords are only used the **first** time the app starts on an empty disk. Later, change passwords in the Users page.
- Keep the service at **one instance**. Agent runs happen inside the app.
- To change the model or add the API key later: Render → your service → **Environment**.
- Every push to `main` on GitHub redeploys the app. Database migrations run on start.
- For a bigger setup, swap SQLite for Render Postgres by setting `CL_DATABASE_URL`.

## Local development

```bash
# terminal 1
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload --port 8000
# terminal 2
cd frontend && npm install && npm run dev
```

Vite (port 5173) forwards `/api` to the back end (port 8000).

## Single server, no Docker

```bash
cd frontend && npm ci && npm run build      # creates frontend/dist
cd ../backend && pip install -r requirements.txt
CL_ENV=prod CL_JWT_SECRET=... CL_DATABASE_URL=... uvicorn app.main:app --host 0.0.0.0 --port 8000
```

When `frontend/dist` exists, the back end also serves the web app, so you only need one process.

## Docker

```bash
cp .env.example .env    # set CL_JWT_SECRET, CL_ANTHROPIC_API_KEY, CL_SEED_DEMO
docker compose up --build -d
docker compose logs -f app
```

- `Dockerfile` builds the web app with Node, then installs the API on `python:3.12-slim`. It runs as a non-root user.
- `docker-compose.yml` runs Postgres 16 with a health check, plus the app on port 8000.
- Volumes: `pgdata` (database) and `evidence` (`/data/storage`).

## Production checklist

- [ ] `CL_ENV=prod` and a random `CL_JWT_SECRET` (`openssl rand -hex 32`)
- [ ] `CL_SEED_DEMO=false`, and the admin password changed after first sign-in
- [ ] Postgres with automatic backups. Evidence volume backed up on the same schedule.
- [ ] HTTPS at a reverse proxy or load balancer. `CL_CORS_ORIGINS` set to your real domain.
- [ ] Rate limiting on `/api/auth/login` at the proxy
- [ ] **One** app container (agent runs are in-process until a job queue is added)
- [ ] Logs shipped to your log tool. They're JSON lines with request IDs.
- [ ] Health check on `GET /api/health`
- [ ] AI data use approved for the client data you will upload
- [ ] Run `GET /api/audit/verify` on a schedule and alert if `valid` is false

## Upgrades

Database migrations use Alembic and run on every start (`backend/migrations/`). After changing `models.py`, create a new migration:

```bash
cd backend && alembic revision --autogenerate -m "what changed"
```

Commit the new file in `migrations/versions/`. It is applied on the next start.

## Back-ups and restore

Back up the database and the evidence folder **together**. The database stores each file's path and hash. On download, the hash is re-checked, so a restored file that doesn't match is caught.
