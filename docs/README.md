# Yanqing Documentation

Yanqing is an independent equity research workspace deployed at `/yanqing`.

## Documentation Index

- `PRD.md`: product goals, current scope, and boundaries.
- `DEPLOYMENT.md`: deployment paths, gateway SSO, configuration, and health checks.
- `CHANGELOG.md`: planned and completed changes.
- `specs/`: approved feature specifications.
- `plans/`: reviewed implementation plans.
- `reports/`: verification and release reports.
- `runbooks/`: operational procedures.
- `archive/`: historical documentation.
- `/root/apps/portal/docs`: BrianHub portal documentation standards.

## Boundaries

- Yanqing does not use cnstock APIs, login, database, cookies, local state, shared data directories, or report assets.
- Yanqing uses portal AI configuration only through `/internal/ai-config` with the `PORTAL_INTERNAL_TOKEN` environment variable.
- Documentation never contains real secret values.
