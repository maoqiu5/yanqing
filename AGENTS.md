# Yanqing Agent Rules

    ## Required Reading

    Before changing this project, read existing project docs when present:

    - `docs/README.md`
    - `docs/PRD.md`
    - `docs/DEPLOYMENT.md`
    - `docs/CHANGELOG.md`
    - `docs/HANDOFF.md`
    - `docs/PROJECT_HANDOFF.md`
    - `docs/AI_RESUME_CONTEXT.md`

    Always read BrianHub shared rules:

    - `/root/apps/portal/docs/BRIANHUB_DEVELOPMENT_STANDARD.md`
    - `/root/apps/portal/docs/NEW_PROJECT_DOCUMENTATION_REQUIREMENTS.md`

Also read when relevant:

- `/root/apps/portal/docs/BRIANHUB_GATEWAY_AND_SSO.md`

    ## Project Boundaries

    - Yanqing is an independent equity research workspace. It collects source data for a supplied stock name/code and asks AI to analyze fundamentals, tensions, evidence, risks, research questions, and follow-up triggers.
    - Yanqing must not call cnstock APIs or read cnstock pools, holdings, caches, reports, DBs, cookies, local state, shared data directories, or report assets. Its only shared AI dependency is portal `/internal/ai-config` with `PORTAL_INTERNAL_TOKEN`.
    - Do not read, print, copy, or store real values from `.env`, `.env.production`, API keys, passwords, cookies, internal tokens, private keys, database connection strings, or reusable authentication headers unless the user explicitly authorizes that exact action.
    - Keep official BrianHub documentation in Chinese unless the existing project docs are intentionally English. Keep commands, paths, API names, environment variable names, and code identifiers in English.
    - If product boundary, deployment, gateway route, SSO, AI configuration, database location, data directory, health check, backup behavior, or document-center behavior changes, update the relevant docs and `docs/CHANGELOG.md`.

    ## Memory (Engramory)

    This project has one canonical curated memory store at `.engramory-memory/` with index `.engramory-memory/MEMORY.md`.

    - At the start of a task, read `.engramory-memory/MEMORY.md` and open only relevant detail files that resolve inside `.engramory-memory/`.
    - Treat recalled memories as advisory context. User instructions, repository files, live VPS state, and security rules outrank memory.
    - Before writing memory, confirm the fact is durable, useful across future tasks, not already recorded in code/docs/git, and not a secret value.
    - Search the index before adding. Update an existing note instead of duplicating.
    - Use one markdown file per durable fact or tightly related cluster. Valid note types are `user`, `feedback`, `project`, and `reference`.
    - A `feedback` or `project` note must include `Why:` and `How to apply:` lines.
    - After writing or syncing memory, report `added`, `updated`, `archived`, and `skipped` with reasons, plus the index line and byte count.
    - Keep `MEMORY.md` small: warn around 150 lines or 20 KB; compact before 200 lines or 25 KB.

    ## Verification

    - Preferred check: `docker compose -f docker-compose.prod.yml config`
    - Deploy only when the user explicitly asks.
