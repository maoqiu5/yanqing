# Yanqing V1.4 Evidence And SSO Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build automatic CNINFO announcement evidence ingestion for Yanqing V1.4 and align the live `/yanqing` route with BrianHub SSO and documentation standards.

**Architecture:** Keep Yanqing standalone. Add focused evidence helpers to the FastAPI backend, persist source metadata/PDF/text under `YANQING_DATA_DIR/evidence`, inject bounded evidence into auto research snapshots, and expose compact evidence APIs and UI. Update gateway routing on VPS so `/yanqing` is protected by portal `forward_auth`, while health verification remains documented and operable.

**Tech Stack:** FastAPI, Pydantic v2, httpx, standard-library JSON/file storage, optional `pypdf` for PDF text extraction, native HTML/CSS/JS frontend, Docker Compose, Caddy gateway on `brianhub_edge`.

## Global Constraints

- Do not use cnstock APIs, login, database, cookies, local state, data directories, or report assets.
- Only shared AI capability is portal `/internal/ai-config` using `PORTAL_INTERNAL_TOKEN`; never print, save, or return token values.
- Data gaps must be marked `数据不足`; AI must not invent announcements, orders, policies, customers, revenue structure, or financial-report fields.
- Do not output direct buy/sell/add/reduce trading instructions.
- Persist Yanqing data only under `YANQING_DATA_DIR`, with evidence under `YANQING_DATA_DIR/evidence`.
- Docker service must stay on `brianhub_edge`; Yanqing must not run its own Caddy/Nginx on public ports.
- Update `docs/README.md`, `docs/PRD.md`, `docs/DEPLOYMENT.md`, and `docs/CHANGELOG.md`; ensure docs are visible through BrianHub portal document center after deployment.
- Current local folder has no `.git`; replace commit steps with file/hash verification unless a Git repository is added before execution.

---

## File Structure

- Modify `backend/requirements.txt`: add `pypdf` for PDF text extraction.
- Modify `backend/app/main.py`: add evidence models, storage helpers, CNINFO adapter, evidence API endpoints, snapshot injection, and prompt constraints.
- Modify `backend/test_main.py`: add unit/integration tests with mocked public-source calls.
- Modify `frontend/index.html`: add evidence status and source-document evidence display.
- Modify `docs/README.md`: align with BrianHub documentation-entry requirements.
- Modify `docs/PRD.md`: document V1.4 scope, SSO rule, data sources, storage, and limitations.
- Modify `docs/DEPLOYMENT.md`: document SSO gateway route, env vars, data/backup/log boundaries, deploy, rollback, health checks.
- Modify `docs/CHANGELOG.md`: add V1.4 and SSO entry.
- Create `docs/specs/2026-07-27-evidence-source-ingestion-design.md`: copy the approved spec into BrianHub-standard docs location.
- Create `docs/plans/2026-07-27-yanqing-v14-evidence-sso.md`: copy this plan into BrianHub-standard docs location after review.
- On VPS, modify `/root/apps/brianhub-gateway/Caddyfile`: add `forward_auth portal_frontend:3000 { uri /auth/check?redirect=1 }` inside `route /yanqing*`.

---

### Task 1: Documentation And SSO Baseline

**Files:**
- Modify: `docs/README.md`
- Modify: `docs/PRD.md`
- Modify: `docs/DEPLOYMENT.md`
- Modify: `docs/CHANGELOG.md`
- Create: `docs/specs/2026-07-27-evidence-source-ingestion-design.md`
- Create: `docs/plans/2026-07-27-yanqing-v14-evidence-sso.md`

**Interfaces:**
- Consumes: BrianHub portal standards read from `/root/apps/portal/docs`.
- Produces: Documentation that later deployment steps can verify through portal docs center.

- [ ] **Step 1: Copy approved spec into BrianHub-standard docs directory**

Create `docs/specs/2026-07-27-evidence-source-ingestion-design.md` with the same content as `docs/superpowers/specs/2026-07-27-evidence-source-ingestion-design.md`.

Run:

```powershell
Copy-Item -LiteralPath 'docs\superpowers\specs\2026-07-27-evidence-source-ingestion-design.md' -Destination 'docs\specs\2026-07-27-evidence-source-ingestion-design.md' -Force
```

Expected: file exists and contains the V1.4 evidence design.

- [ ] **Step 2: Copy this implementation plan into BrianHub-standard docs directory**

Run:

```powershell
Copy-Item -LiteralPath 'docs\superpowers\plans\2026-07-27-yanqing-v14-evidence-sso.md' -Destination 'docs\plans\2026-07-27-yanqing-v14-evidence-sso.md' -Force
```

Expected: file exists and contains this plan.

- [ ] **Step 3: Update core docs**

Update `docs/README.md` so it lists PRD, deployment, changelog, specs, plans, reports, runbooks, archive, and portal standards. Update `docs/PRD.md` with V1.4 current scope and explicit SSO requirement. Update `docs/DEPLOYMENT.md` with:

```text
项目 slug：yanqing
页面路径：https://brianhub.net/yanqing/
API 路径：https://brianhub.net/yanqing/api/*
VPS 目录：/root/apps/yanqing
数据目录：/root/apps/yanqing/data
证据目录：/root/apps/yanqing/data/evidence
Docker 网络：brianhub_edge
SSO：页面和业务接口通过 gateway forward_auth 调用 portal /auth/check?redirect=1
健康检查：https://brianhub.net/yanqing/api/health
```

Update `docs/CHANGELOG.md` with a dated entry:

```markdown
## 2026-07-27 v1.4 planned

类型：新增、规范对齐、文档
摘要：
- 规划公告/财报原文自动证据采集。
- 规划 `/yanqing` 接入 BrianHub 门户统一登录保护。
- 增加 BrianHub 标准 specs/plans 文档入口。

影响范围：
- 后端证据采集接口、自动深研快照、前端证据展示、网关 SSO、项目文档。

验证：
- 本地测试、VPS 容器测试、线上健康检查、门户文档中心检查。
```

- [ ] **Step 4: Verify docs contain no obvious secrets**

Run:

```powershell
Select-String -Path 'docs\*.md','docs\specs\*.md','docs\plans\*.md' -Pattern 'sk-|api[_-]?key\s*[:=]\s*[^`<变量名]|cookie\s*[:=]|token\s*[:=]|password\s*[:=]' -CaseSensitive:$false
```

Expected: no matches containing real secret values. Variable names such as `PORTAL_INTERNAL_TOKEN` are acceptable.

---

### Task 2: Evidence Models, Category Classifier, And Storage

**Files:**
- Modify: `backend/app/main.py`
- Test: `backend/test_main.py`

**Interfaces:**
- Produces: `EvidenceRefreshRequest`, `EvidenceSnippet`, `EvidenceRecord`, `EvidenceLibrary`, `classify_announcement(title: str) -> str`, `evidence_id_for(meta: dict[str, Any]) -> str`, `load_evidence_index(ticker: str) -> list[dict[str, Any]]`, `save_evidence_index(ticker: str, records: list[dict[str, Any]]) -> None`, `merge_evidence_records(existing, incoming) -> list[dict[str, Any]]`, `build_evidence_library(ticker: str, refresh: bool = True, limit: int = 20, days: int = 720) -> dict[str, Any]`.

- [ ] **Step 1: Write failing tests**

Add tests to `backend/test_main.py`:

```python
class EvidenceStorageTests(unittest.TestCase):
    def test_classifies_announcement_titles_conservatively(self):
        from backend.app.main import classify_announcement

        self.assertEqual(classify_announcement("2025年年度报告"), "annual_report")
        self.assertEqual(classify_announcement("2026年第一季度报告"), "quarterly_report")
        self.assertEqual(classify_announcement("关于控股股东部分股份解除质押的公告"), "pledge")
        self.assertEqual(classify_announcement("关于收到深圳证券交易所问询函的公告"), "risk")
        self.assertEqual(classify_announcement("关于召开股东大会的通知"), "other")

    def test_merge_evidence_records_deduplicates_by_id(self):
        from backend.app.main import merge_evidence_records

        old = [{"evidence_id": "a", "announcement_date": "2026-01-01", "title": "old"}]
        new = [{"evidence_id": "a", "announcement_date": "2026-01-02", "title": "new"}, {"evidence_id": "b", "announcement_date": "2026-01-03", "title": "b"}]
        merged = merge_evidence_records(old, new)

        self.assertEqual([item["evidence_id"] for item in merged], ["b", "a"])
        self.assertEqual(merged[1]["title"], "new")
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m unittest backend.test_main
```

Expected: FAIL because evidence functions do not exist.

- [ ] **Step 3: Implement minimal models/storage helpers**

Add Pydantic models and helper functions to `backend/app/main.py` near existing models and storage helpers. Use `hashlib.sha256`, `timedelta`, and `urllib.parse.urljoin` imports only when needed by later tasks.

Implementation requirements:

```python
class EvidenceRefreshRequest(BaseModel):
    limit: int = Field(default=20, ge=1, le=50)
    days: int = Field(default=720, ge=1, le=3650)
    download: bool = True
    extract_text: bool = True


class EvidenceSnippet(BaseModel):
    quote: str = ""
    note: str = ""
    page: int | None = None


class EvidenceRecord(BaseModel):
    evidence_id: str
    ticker: str
    source: str = "cninfo"
    title: str
    announcement_date: str = ""
    category: str = "other"
    url: str = ""
    local_pdf_path: str = ""
    local_text_path: str = ""
    download_status: str = "skipped"
    text_extract_status: str = "skipped"
    snippets: list[EvidenceSnippet] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
```

`classify_announcement` must use title keywords and return only `annual_report`, `semiannual_report`, `quarterly_report`, `forecast`, `contract`, `pledge`, `risk`, or `other`.

`merge_evidence_records` must deduplicate by `evidence_id`, prefer incoming records, and sort by `announcement_date` descending.

- [ ] **Step 4: Run tests to verify pass**

Run:

```powershell
python -m unittest backend.test_main
```

Expected: PASS.

---

### Task 3: CNINFO Adapter With Mockable Parsing

**Files:**
- Modify: `backend/app/main.py`
- Test: `backend/test_main.py`

**Interfaces:**
- Consumes: `EvidenceRecord`, `classify_announcement`, `evidence_id_for`.
- Produces: `parse_cninfo_announcements(payload: dict[str, Any], ticker: str) -> list[dict[str, Any]]`, `search_cninfo_announcements(ticker: str, limit: int, days: int) -> list[dict[str, Any]]`, `download_cninfo_pdf(record: dict[str, Any]) -> dict[str, Any]`.

- [ ] **Step 1: Write failing parser test**

Add:

```python
class CninfoAdapterTests(unittest.TestCase):
    def test_parse_cninfo_announcements_maps_records(self):
        from backend.app.main import parse_cninfo_announcements

        payload = {
            "announcements": [
                {
                    "announcementTitle": "2025年年度报告",
                    "announcementTime": 1767225600000,
                    "adjunctUrl": "finalpage/2026-01-01/123.PDF",
                }
            ]
        }

        rows = parse_cninfo_announcements(payload, "300767.SZ")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ticker"], "300767.SZ")
        self.assertEqual(rows[0]["source"], "cninfo")
        self.assertEqual(rows[0]["category"], "annual_report")
        self.assertIn("cninfo.com.cn", rows[0]["url"])
        self.assertEqual(rows[0]["download_status"], "skipped")
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
python -m unittest backend.test_main.CninfoAdapterTests -v
```

Expected: FAIL because parser does not exist.

- [ ] **Step 3: Implement parser and search**

Implement `parse_cninfo_announcements` to read `payload["announcements"]`, normalize title by removing HTML tags, derive date from millisecond timestamp or string, build full URL with `https://static.cninfo.com.cn/`, and create stable `evidence_id` from source/ticker/title/date/url.

Implement `search_cninfo_announcements` using `httpx.Client(timeout=12)` and POST to CNINFO search endpoint with public headers. It must catch exceptions in callers, not return fabricated rows.

- [ ] **Step 4: Run parser tests**

Run:

```powershell
python -m unittest backend.test_main.CninfoAdapterTests -v
```

Expected: PASS.

---

### Task 4: Evidence Refresh API And Cache Behavior

**Files:**
- Modify: `backend/app/main.py`
- Test: `backend/test_main.py`

**Interfaces:**
- Consumes: Task 2 storage helpers and Task 3 CNINFO adapter.
- Produces: API endpoints `GET /api/evidence/{ticker}/sources/status`, `POST /api/evidence/{ticker}/refresh`, `GET /api/evidence/{ticker}`, `GET /api/evidence/{ticker}/{evidence_id}`.

- [ ] **Step 1: Write failing endpoint tests**

Add:

```python
class EvidenceApiTests(unittest.TestCase):
    def test_evidence_status_endpoint(self):
        response = client.get("/api/evidence/300767.SZ/sources/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["ticker"], "300767.SZ")
        self.assertEqual(payload["sources"][0]["name"], "cninfo")

    def test_evidence_list_uses_cache_without_refresh(self):
        from backend.app.main import save_evidence_index

        save_evidence_index("300767.SZ", [{
            "evidence_id": "cached",
            "ticker": "300767.SZ",
            "source": "cninfo",
            "title": "cached annual report",
            "announcement_date": "2026-01-01",
            "category": "annual_report",
            "url": "https://example.invalid/a.pdf",
            "download_status": "skipped",
            "text_extract_status": "skipped",
            "snippets": [],
            "data_gaps": [],
        }])

        response = client.get("/api/evidence/300767.SZ")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["evidence_id"], "cached")
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m unittest backend.test_main.EvidenceApiTests -v
```

Expected: FAIL because endpoints do not exist.

- [ ] **Step 3: Implement endpoints**

Endpoint behavior:

- Source status returns CNINFO as configured/ready because it is a public source with no token.
- Refresh validates ticker via `normalize_ts_code`, calls `refresh_evidence_for_ticker`, saves merged cache, and returns `ticker`, `refreshed_at`, `items`, `data_gaps`.
- List returns cached records newest first.
- Detail returns record plus `text_preview` limited to 5000 characters if local text exists.

- [ ] **Step 4: Run endpoint tests**

Run:

```powershell
python -m unittest backend.test_main.EvidenceApiTests -v
```

Expected: PASS.

---

### Task 5: PDF Download, Text Extraction, And Snippets

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/app/main.py`
- Test: `backend/test_main.py`

**Interfaces:**
- Consumes: cached `EvidenceRecord` dictionaries.
- Produces: `extract_pdf_text(pdf_path: Path) -> tuple[str, str]`, `build_evidence_snippets(text: str, title: str, limit: int = 3) -> list[dict[str, Any]]`.

- [ ] **Step 1: Add dependency**

Append to `backend/requirements.txt`:

```text
pypdf==5.1.0
```

- [ ] **Step 2: Write failing snippet test**

Add:

```python
class EvidenceSnippetTests(unittest.TestCase):
    def test_build_evidence_snippets_prefers_research_keywords(self):
        from backend.app.main import build_evidence_snippets

        text = "公司实现营业收入12亿元。重大合同金额3亿元。经营现金流为正。"
        snippets = build_evidence_snippets(text, "重大合同公告", limit=2)

        self.assertEqual(len(snippets), 2)
        self.assertTrue(any("重大合同" in item["quote"] for item in snippets))
```

- [ ] **Step 3: Implement extraction and snippets**

Use `pypdf.PdfReader` inside `extract_pdf_text`. On import or extraction failure return `("", "failed")`; on success return `(text[:120000], "ready")`.

`build_evidence_snippets` should split Chinese punctuation and newlines, prefer sentences containing `营业收入`, `净利润`, `经营现金流`, `合同`, `订单`, `中标`, `质押`, `风险`, `诉讼`, `监管`, and return bounded quotes under 240 characters.

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m unittest backend.test_main.EvidenceSnippetTests -v
```

Expected: PASS.

---

### Task 6: Snapshot Injection And AI Guardrails

**Files:**
- Modify: `backend/app/main.py`
- Test: `backend/test_main.py`

**Interfaces:**
- Consumes: `build_evidence_library`.
- Produces: `snapshot["evidence_library"]` and stricter `_snapshot_messages`.

- [ ] **Step 1: Write failing snapshot test with mocked evidence**

Add:

```python
class SnapshotEvidenceTests(unittest.TestCase):
    def test_snapshot_includes_evidence_library_when_refresh_fails(self):
        import backend.app.main as main

        original = main.build_evidence_library
        try:
            main.build_evidence_library = lambda ticker, refresh=True, limit=20, days=720: {
                "status": "insufficient",
                "items": [],
                "data_gaps": ["公告原文数据不足"],
            }
            snapshot = main.build_company_snapshot("300767.SZ")
        finally:
            main.build_evidence_library = original

        self.assertIn("evidence_library", snapshot)
        self.assertEqual(snapshot["evidence_library"]["status"], "insufficient")
        self.assertIn("公告原文数据不足", snapshot["evidence_library"]["data_gaps"])
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
python -m unittest backend.test_main.SnapshotEvidenceTests -v
```

Expected: FAIL because snapshot lacks evidence library.

- [ ] **Step 3: Inject evidence library**

In `build_company_snapshot`, call:

```python
evidence_library = build_evidence_library(ts_code, refresh=True, limit=20, days=720)
```

Add it to the returned snapshot. If evidence refresh fails internally, `build_evidence_library` returns `status=limited` or `insufficient` with `data_gaps`; it must not throw into the snapshot builder.

Update `_snapshot_messages` system prompt so it says:

```text
只能引用 evidence_library.items 中存在的公告、订单、政策、客户、财报原文字段；缺少原文或抽取失败必须写数据不足。
```

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m unittest backend.test_main.SnapshotEvidenceTests -v
```

Expected: PASS.

---

### Task 7: Frontend Evidence Display

**Files:**
- Modify: `frontend/index.html`

**Interfaces:**
- Consumes: API responses containing `input_snapshot.evidence_library`.
- Produces: visible source-document evidence section without portal/cnstock links.

- [ ] **Step 1: Update render logic**

In `render(payload)`, read:

```javascript
const evidenceLib = snap.evidence_library || {status:'insufficient',items:[],data_gaps:['公告原文数据不足']};
```

Add a panel titled `公告原文证据` showing status, data gaps, and cards for each item with title, date, category, source, extraction status, and snippets.

- [ ] **Step 2: Update data-source panel after health load**

Add a lightweight call after ticker selection or search result render:

```javascript
async function loadEvidenceStatus(ticker){
  if(!ticker)return;
  try{
    const data=await json(`/evidence/${encodeURIComponent(ticker)}/sources/status`);
    notice(`证据源：${data.sources.map(s=>`${s.name}:${s.status}`).join('，')}`);
  }catch(e){}
}
```

Call it when a search result is selected.

- [ ] **Step 3: Manual browser smoke check**

Start local app if dependencies are installed, then open the page and verify text does not overlap at desktop and mobile widths. If local app cannot start, record the reason in final verification.

---

### Task 8: Local Verification

**Files:**
- Read: all changed files.

**Interfaces:**
- Consumes: completed implementation.
- Produces: test and safety evidence before deployment.

- [ ] **Step 1: Run full backend test suite**

Run:

```powershell
python -m unittest backend.test_main
```

Expected: `OK`.

- [ ] **Step 2: Scan for prohibited cnstock coupling**

Run:

```powershell
Select-String -Path 'backend\app\main.py','frontend\index.html','docs\*.md','docs\specs\*.md','docs\plans\*.md' -Pattern 'cnstock' -CaseSensitive:$false
```

Expected: only boundary statements such as “do not use cnstock” and legacy 404 documentation. No cnstock API calls, cookies, databases, or redirects.

- [ ] **Step 3: Scan for obvious secret leaks**

Run:

```powershell
Select-String -Path 'backend\app\main.py','frontend\index.html','docs\*.md','docs\specs\*.md','docs\plans\*.md','docker-compose.prod.yml' -Pattern 'sk-|Bearer [A-Za-z0-9]|cookie\s*[:=]|password\s*[:=]' -CaseSensitive:$false
```

Expected: no real secrets.

---

### Task 9: VPS Deploy And Gateway SSO

**Files:**
- VPS modify: `/root/apps/yanqing`
- VPS modify: `/root/apps/brianhub-gateway/Caddyfile`

**Interfaces:**
- Consumes: local verified code.
- Produces: live Yanqing V1.4 with SSO-protected `/yanqing`.

- [ ] **Step 1: Sync Yanqing files to VPS without secrets or data**

Use an rsync/scp method that excludes `data`, `backups`, `logs`, `.env`, `.git`, caches, and `__pycache__`.

Expected: `/root/apps/yanqing` code and docs match local changed files.

- [ ] **Step 2: Run VPS tests**

Run:

```bash
cd /root/apps/yanqing
docker compose -f docker-compose.prod.yml exec -T app python -m unittest backend.test_main
```

Expected: `OK`.

- [ ] **Step 3: Update gateway route with backup**

Create a timestamped backup:

```bash
cd /root/apps/brianhub-gateway
cp Caddyfile Caddyfile.backup-yanqing-sso-$(date +%Y%m%d-%H%M%S)
```

Modify `route /yanqing*` to:

```caddyfile
route /yanqing* {
	forward_auth portal_frontend:3000 {
		uri /auth/check?redirect=1
	}
	uri strip_prefix /yanqing
	reverse_proxy yanqing_app:8000
}
```

Keep:

```caddyfile
route /cnstock/yanqing.html {
	respond "not found" 404
}
```

- [ ] **Step 4: Rebuild Yanqing and reload gateway**

Run:

```bash
cd /root/apps/yanqing
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
cd /root/apps/brianhub-gateway
docker compose -f docker-compose.prod.yml exec -T caddy caddy reload --config /etc/caddy/Caddyfile
```

Expected: Yanqing app is `Up`; gateway reload succeeds.

---

### Task 10: Online Verification And Documentation Center

**Files:**
- Read: live endpoints and portal document center.

**Interfaces:**
- Consumes: deployed service and gateway route.
- Produces: verified release with documented rollback.

- [ ] **Step 1: Verify health and data-source endpoints**

Run:

```bash
curl -fsS https://brianhub.net/yanqing/api/health
curl -fsS https://brianhub.net/yanqing/api/data-source/status
```

Expected: health returns `status=ok`; data source shows configured flags without secrets.

- [ ] **Step 2: Verify evidence endpoints**

Run:

```bash
curl -fsS https://brianhub.net/yanqing/api/evidence/300767.SZ/sources/status
curl -fsS -X POST https://brianhub.net/yanqing/api/evidence/300767.SZ/refresh -H 'Content-Type: application/json' -d '{"limit":5,"days":720,"download":true,"extract_text":true}'
```

Expected: source status includes CNINFO; refresh returns items or explicit `data_gaps` with no fabricated facts.

- [ ] **Step 3: Verify SSO behavior**

In a browser without portal session, open `https://brianhub.net/yanqing/`.

Expected: gateway redirects to portal login/check flow. In an authenticated session, Yanqing page loads.

- [ ] **Step 4: Verify portal docs center visibility**

Open:

```text
https://brianhub.net/?tab=docs&project=yanqing&doc=docs%2FREADME.md
```

Expected: Yanqing docs README renders through portal document center.

- [ ] **Step 5: Record release report**

Create `docs/reports/2026-07-27-v14-evidence-sso-verification.md` with:

```markdown
# Yanqing V1.4 Evidence And SSO Verification

## Summary

- Evidence ingestion deployed:
- Gateway SSO deployed:
- Health check:
- Evidence refresh:
- Portal docs center:

## Rollback

- Yanqing app rollback: restore previous `/root/apps/yanqing` files or previous backup, then rebuild container.
- Gateway rollback: restore `Caddyfile.backup-yanqing-sso-<timestamp>`, reload Caddy, verify `/yanqing`.

## Notes

- No real tokens, API keys, cookies, or private keys were printed or saved.
```

---

## Self-Review Notes

- Spec coverage: covered source ingestion, storage, API, snapshot integration, frontend, SSO, docs, deployment, rollback, and portal docs center verification.
- Scope: CNINFO only in first implementation; SSE/SZSE remain documented future adapters.
- Type consistency: evidence records use `evidence_id`, `ticker`, `source`, `title`, `announcement_date`, `category`, `url`, `local_pdf_path`, `local_text_path`, `download_status`, `text_extract_status`, `snippets`, `data_gaps`.
- Commit constraint: no Git repository exists in the local Yanqing folder, so execution uses verification instead of local commits.
