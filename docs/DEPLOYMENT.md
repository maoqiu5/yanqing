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

## Version Management

- Primary local repository: `C:\Users\12514\Documents\研擎`
- Primary VPS bare remote: `vps = ssh://root@192.236.235.229/root/git/yanqing.git`
- GitHub backup remote: `github = git@github.com:maoqiu5/yanqing.git`
- Local `main` should track `vps/main`; GitHub is a backup push target, not the deployment source of truth.
- `git push` does not auto-deploy. Production files under `/root/apps/yanqing` are still released by the documented sync/rebuild process.

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
- The production Compose service uses `init: true` so Docker's init process reaps orphaned Chromium/crashpad descendants.
- The backend starts Chromium in its own process session, waits for the renderer process, and terminates the process group on PDF timeout.
- If PDF export fails, first check that the container image was rebuilt after the Dockerfile change and that `/root/apps/yanqing/data/runtime/pdf` is writable.

## 公告原文浏览与来源追溯

- `GET /yanqing/api/evidence/{ticker}/{evidence_id}/pdf` 返回原始公告 PDF（`inline` 预览）。
- `GET /yanqing/api/evidence/{ticker}/{evidence_id}/text?page=N` 返回指定页文本预览；不带 `page` 时返回全文预览。
- `GET /yanqing/api/evidence/{ticker}/{evidence_id}/source` 返回结构化来源元数据、等级、页码和摘录信息。
- 抽取文本时保存：
  - `data/evidence/{ticker}/text/{evidence_id}.txt`
  - `data/evidence/{ticker}/text/{evidence_id}.pages.json`
- 文件接口只允许访问当前 ticker 证据目录内的 `documents/{evidence_id}.pdf` 和 `text/{evidence_id}.txt`，`evidence_id` 必须是 64 位十六进制。
- 这些 API 仍由 BrianHub 网关 SSO 保护，不额外实现登录。


## Verification

- `https://brianhub.net/yanqing/` returns 200 for an authenticated session.
- `https://brianhub.net/yanqing/api/health` returns the Yanqing health response.
- A generated or historical report downloads a PDF from `/yanqing/api/research/{id}/pdf`.
- Evidence original PDF/text/source endpoints return 200 for authenticated sessions and are covered by gateway SSO.

- An unauthenticated page or business API request follows the portal SSO check.
- The portal documentation center renders `docs/README.md` and the standard `specs/` and `plans/` entries.
