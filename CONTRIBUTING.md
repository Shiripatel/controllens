# Contributing

## Set up

```bash
cd backend && pip install -r requirements.txt
cd ../frontend && npm install
```

## Before you push

```bash
cd backend && pytest -q          # must pass
cd ../frontend && npm run build  # must type-check and build
```

CI runs both on every push and pull request.

## Rules

1. **Keep the core rules.** Agents propose and people decide. Every claim cites evidence. Code does the math. Don't let an agent write a final conclusion or a sign-off.
2. **Log it.** Any new action that changes data must call `audit.log(...)` in the same transaction.
3. **Check on the server.** Never rely on the web app alone to block an action by role or status.
4. **Version prompts.** If you change a prompt in `agents/prompts.py`, bump its version.
5. **Think about sign-offs.** If a new change affects tested work, call `workflow.invalidate(...)`.
6. **Test offline.** New agent steps need a mock so the tests run with no API key.
7. **Plain English.** UI text, prompts and docs should use simple words.

## Branches and commits

- Branch from `main`: `feature/<name>` or `fix/<name>`.
- One topic per pull request. Describe what changed and how you tested it.
