# Collapsible Sidebar And PDF Export Implementation Plan

> **For agentic workers:** implement inline in this project. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Yanqing research workspace easier to use during long reports by collapsing the left panel and exporting the visible report as PDF.

**Architecture:** The collapsible left panel remains a frontend-only control in `frontend/index.html`. PDF export is now server-rendered: the frontend stores the current report id and downloads `GET /api/research/{id}/pdf`; the backend reloads the persisted report JSON, renders an A4 HTML report, and uses headless Chromium to produce a PDF. No SSO, gateway, AI configuration, external cnstock dependency, or research data-source boundary changes.

**Tech Stack:** Plain HTML, CSS, JavaScript, existing FastAPI static frontend.

## Global Constraints

- Do not use cnstock APIs, login, database, data directories, cookies, local state, or report assets.
- Do not add project-local login or AI key configuration.
- Do not expose secrets in code, docs, logs, pages, or API output.
- Do not output direct trading instructions.
- Missing data remains `数据不足`.
- Docker service remains behind BrianHub gateway and SSO.

---

### Task 1: Add Frontend Controls

**Files:**
- Modify: `frontend/index.html`

**Interfaces:**
- Produces: `toggleSidebar()` and `exportPdf()` browser functions.
- Produces: `body.sidebar-collapsed` CSS state.

- [x] Add a compact toolbar in the header with `折叠左侧` and `导出 PDF` buttons.
- [x] Keep `导出 PDF` disabled until a real report is rendered.
- [x] Implement `toggleSidebar()` to collapse the left panel on desktop and hide form content on mobile.
- [x] Implement `exportPdf()` as a download trigger for `/api/research/{id}/pdf`; do not call `window.print()`.

### Task 2: Add Server PDF Rendering

**Files:**
- Modify: `backend/app/main.py`
- Modify: `Dockerfile`

**Interfaces:**
- Produces: `GET /api/research/{research_id}/pdf`.
- Consumes: persisted report JSON under `data/research`.
- Uses: headless Chromium and `fonts-noto-cjk` inside the app container.

- [x] Add a persisted-report loader shared by JSON read and PDF export.
- [x] Render a standalone report HTML document using the same report sections and visual language as the browser report.
- [x] Add A4 pagination CSS: section/card `break-inside: avoid-page`, readable margins, and natural long evidence-card pagination.
- [x] Add Chromium and CJK fonts to the production image.

### Task 3: Verify And Deploy

**Files:**
- Modify: `docs/CHANGELOG.md`
- Modify: `docs/PRD.md`
- Modify: `docs/DEPLOYMENT.md`

- [x] Run local syntax/static checks.
- [ ] Sync code and docs to `/root/apps/yanqing`.
- [ ] Rebuild the VPS container so Chromium is installed.
- [ ] Run health check and manually download a PDF from a generated or historical report.
- [ ] Commit locally and push to VPS bare remote `vps/main`.
