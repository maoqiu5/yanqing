# Collapsible Sidebar And PDF Export Implementation Plan

> **For agentic workers:** implement inline in this project. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Yanqing research workspace easier to use during long reports by collapsing the left panel and exporting the visible report as PDF.

**Architecture:** This is a frontend-only change in `frontend/index.html`. The report remains server-rendered data fetched through existing APIs; PDF export uses browser print/save-as-PDF with print-specific CSS. No backend, data, SSO, gateway, AI configuration, or runtime directory changes.

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

- [ ] Add a compact toolbar in the header with `折叠左侧` and `导出 PDF` buttons.
- [ ] Keep `导出 PDF` disabled until a real report is rendered.
- [ ] Implement `toggleSidebar()` to collapse the left panel on desktop and hide form content on mobile.
- [ ] Implement `exportPdf()` with `window.print()`.

### Task 2: Add Print Styles

**Files:**
- Modify: `frontend/index.html`

**Interfaces:**
- Consumes: existing `#output` report DOM.

- [ ] Add `@media print` CSS that hides header, sidebar, notices, buttons, search/history/source panels.
- [ ] Force the report to full width and remove shadows/backgrounds for clean PDF output.
- [ ] Prevent card content from splitting awkwardly with `break-inside: avoid`.

### Task 3: Verify And Deploy

**Files:**
- Modify: `docs/CHANGELOG.md`
- Modify: `docs/PRD.md`

- [ ] Run local syntax/static checks.
- [ ] Sync frontend and docs to `/root/apps/yanqing`.
- [ ] Rebuild the VPS container.
- [ ] Run VPS backend tests and health check.
- [ ] Use the browser with an authenticated session to run one stock research flow and assess whether the cockpit meets senior A-share analyst needs.
- [ ] Commit locally and push to VPS bare remote `vps/main`.
