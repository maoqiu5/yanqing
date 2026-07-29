# Yanqing Deployment

## BrianHub Deployment Baseline

- Project slug: `yanqing`
- Page path: `https://brianhub.net/yanqing/`
- API path: `https://brianhub.net/yanqing/api/*`
- VPS directory: `/root/apps/yanqing`
- Data directory: `/root/apps/yanqing/data`
- Evidence directory: `/root/apps/yanqing/data/evidence`
- PDF runtime directory: `/root/apps/yanqing/data/runtime/pdf`
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
- `PDF_RENDER_TIMEOUT_SECONDS`: optional PDF export timeout in seconds, default `180`.
- `CHROMIUM_PATH`: optional Chromium binary path override when the container binary is not discoverable on `PATH`.

## Gateway

- The `/yanqing*` route strips `/yanqing` and proxies to `yanqing_app:8000` after portal `forward_auth`.
- Yanqing does not run its own public Caddy or Nginx.
- `/cnstock/yanqing.html` remains a 404 and is not a redirect.

## Independent Runtime Boundary

- Yanqing does not use cnstock APIs, login, databases, cookies, local state, shared data directories, or report assets.
- Runtime data and evidence stay under `/root/apps/yanqing/data` and `/root/apps/yanqing/data/evidence`.
- Server-rendered PDF export writes only temporary Chromium artifacts under `/root/apps/yanqing/data/runtime/pdf`.
- Do not modify or include `data/`, `backups/`, `logs/`, or `.env` files during documentation work.

## PDF Export

- The frontend `导出 PDF` button downloads `GET /yanqing/api/research/{id}/pdf`; it does not call browser print.
- The backend renders the saved report JSON into an A4 HTML document and uses headless Chromium in the application container.
- The production image installs `chromium` and `fonts-noto-cjk`; set `CHROMIUM_PATH` only if the binary path differs.
- If PDF export fails, first check that the container image was rebuilt after the Dockerfile change and that `/root/apps/yanqing/data/runtime/pdf` is writable.

## Verification

- `https://brianhub.net/yanqing/` returns 200 for an authenticated session.
- `https://brianhub.net/yanqing/api/health` returns the Yanqing health response.
- A generated or historical report downloads a PDF from `/yanqing/api/research/{id}/pdf`.
- An unauthenticated page or business API request follows the portal SSO check.
- The portal documentation center renders `docs/README.md` and the standard `specs/` and `plans/` entries.
