# Yanqing Deployment

## BrianHub Deployment Baseline

- Project slug: `yanqing`
- Page path: `https://brianhub.net/yanqing/`
- API path: `https://brianhub.net/yanqing/api/*`
- VPS directory: `/root/apps/yanqing`
- Data directory: `/root/apps/yanqing/data`
- Evidence directory: `/root/apps/yanqing/data/evidence`
- Docker network: `brianhub_edge`
- SSO: the page and business APIs use gateway `forward_auth` to call portal `/auth/check?redirect=1`
- Health check: `https://brianhub.net/yanqing/api/health`

## Local Paths

- Local project: `C:\Users\12514\Documents\研擎`
- Production compose file: `docker-compose.prod.yml`
- Production service: `yanqing_app:8000`

## AI Configuration

- `PORTAL_AI_CONFIG_URL=http://portal_frontend:3000/internal/ai-config`
- `PORTAL_INTERNAL_TOKEN`: supplied by the portal; never write its value to docs, logs, responses, or source control.

## Gateway

- The `/yanqing*` route strips `/yanqing` and proxies to `yanqing_app:8000` after portal `forward_auth`.
- Yanqing does not run its own public Caddy or Nginx.
- `/cnstock/yanqing.html` remains a 404 and is not a redirect.

## Independent Runtime Boundary

- Yanqing does not use cnstock APIs, login, databases, cookies, local state, shared data directories, or report assets.
- Runtime data and evidence stay under `/root/apps/yanqing/data` and `/root/apps/yanqing/data/evidence`.
- Do not modify or include `data/`, `backups/`, `logs/`, or `.env` files during documentation work.

## Verification

- `https://brianhub.net/yanqing/` returns 200 for an authenticated session.
- `https://brianhub.net/yanqing/api/health` returns the Yanqing health response.
- An unauthenticated page or business API request follows the portal SSO check.
- The portal documentation center renders `docs/README.md` and the standard `specs/` and `plans/` entries.
