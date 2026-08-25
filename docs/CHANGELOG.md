# Yanqing CHANGELOG


## 2026-08-25 v2.3 Phase 1

- Added evidence grading and confidence metadata for Yanqing evidence records and snippets:
  - `EvidenceGrade` (A/B/C/D), `EvidenceRef`, `source_type`, `grade`, `confidence`, `file_name`, `retrieved_at`.
  - `ContradictionMatrixRow.supporting_evidence_refs / opposing_evidence_refs`.
  - `TrackingDashboardItem.evidence_refs`.
  - `EvidenceLibrary.summary.grade_summary`.
- Added conservative rule-based `grade_evidence_record` / `confidence_for_evidence`, with idempotent backfill for existing evidence indexes.
- Enriched `evidence_digest` items with source type, grade, confidence, and page metadata.
- Impact: evidence credibility and traceability groundwork only; no SSO, AI config, data-source boundary, or cnstock boundary changes.
- Verification: isolated container run of `backend.test_main` with 53 tests passed.

## 2026-08-25 v2.3 Phase 2

- Added original announcement browsing and source traceability APIs:
  - `GET /api/evidence/{ticker}/{evidence_id}/pdf`
  - `GET /api/evidence/{ticker}/{evidence_id}/text`
  - `GET /api/evidence/{ticker}/{evidence_id}/source`
- Added page-preserving PDF text extraction (`extract_pdf_text_pages`) and page-aware evidence snippets.
- Added `local_pages_path` to evidence records and `text/{evidence_id}.pages.json` storage.
- Enhanced evidence detail/source responses with grade, source type, page count, and snippet page metadata.
- Updated frontend with grade badges, original PDF/text buttons, and source links in evidence digest, evidence chain, contradiction matrix, and tracking dashboard.
- Security: original file APIs validate evidence id and keep file access inside the ticker evidence directory.
- Impact: evidence browsing and traceability only; no SSO, AI config, data-source boundary, or cnstock boundary changes.
- Verification: isolated container run of `backend.test_main` with 61 tests passed.

## 2026-08-25 v2.3 Phase 3

- Added structured evidence references to tracking dashboard items.
- Implemented `_validate_evidence_refs`: verifies `evidence_id` exists and quote matches snapshot evidence, drops invalid refs, and downgrades items without valid refs to `data_insufficient`.
- Added fallback generation from evidence snippets by trigger keywords.
- Added status mapping from evidence grade: A/B direct evidence -> `confirmed`, C/indirect -> `watch`, no valid ref -> `data_insufficient`.
- Added `evidence_refs` to the AI schema hint so new reports can emit precise evidence references.
- Frontend already renders `evidence_refs` as clickable source links in tracking dashboard cards.
- Impact: tracking precision only; no SSO, AI config, data-source boundary, or cnstock boundary changes.
- Verification: isolated container run of `backend.test_main` with 65 tests passed.

## 2026-08-25 v2.3 Phase 4

- Improved server-rendered PDF pagination and reading experience:
  - Cover page now forces a page break.
  - Major report sections (当前研判、矛盾矩阵、跟踪仪表盘、财报追溯、证据摘要、来源追溯、公告原文摘要) start on new pages.
  - Panels/cards use `break-inside: avoid-page` / `page-break-inside: avoid` so cards do not split across pages.
  - Added PDF footer/page number CSS via `@page` margin boxes (ignored if the renderer does not support them).
- Added a "证据来源追溯" PDF section that aggregates `evidence_refs` from tracking dashboard, contradiction matrix, and evidence chain.
- Impact: PDF export readability only; no SSO, AI config, data-source boundary, or cnstock boundary changes.
- Verification: isolated container run of `backend.test_main` with 68 tests passed.




## 2026-08-06 v2.2.8

- Fixed PDF export subprocess lifecycle management by running Chromium in a dedicated process session and cleaning the renderer process group on timeout.
- Enabled Docker Compose `init: true` for the app service so orphaned Chromium/crashpad descendants are reaped by Docker init instead of accumulating under uvicorn PID 1.
- Impact: PDF export runtime stability only; no research logic, data-source boundary, SSO, or AI configuration changes.
- Verification: local subprocess lifecycle regression checks, production compose init check, VPS rebuild/recreate, health check, and post-export zombie-count observation.

## 2026-07-28 v2.2.7

- Added GitHub as a backup remote for the Yanqing repository while keeping `vps/main` as the local main branch upstream.
- Synchronized tracked source and documentation files between local project and `/root/apps/yanqing`, leaving VPS-only runtime data, env files, and Engramory untouched.
- Impact: version management and documentation only; no runtime behavior, data-source boundary, SSO, or AI configuration changes.
- Verification: tracked-file SHA-256 comparison between local and VPS production directory, VPS bare remote commit check, GitHub remote commit check, and sensitive/runtime path scan of the committed tree.

## 2026-07-28 v2.2.6

- Fixed Chromium discovery for server PDF export by using `shutil.which` plus common absolute binary paths instead of a runtime `--version` probe.
- Impact: PDF export renderer detection only; no research logic, data-source boundary, SSO, or AI configuration changes.
- Verification: local Python syntax check, VPS container rebuild, health check, Chromium path check, and non-secret portal-token presence check.

## 2026-07-28 v2.2.5

- Increased the server PDF render timeout and added Chromium launch flags to make long report exports more reliable.
- Impact: PDF export only; no research logic, data-source boundary, SSO, or AI configuration changes.
- Verification: local Python syntax check.

## 2026-07-28 v2.2.4

- Replaced browser print-based PDF export with a server-side `/api/research/{id}/pdf` download endpoint.
- Added report-to-HTML PDF rendering with A4 pagination rules so major sections and cards avoid awkward page breaks.
- Added Chromium and CJK fonts to the production image for consistent Chinese PDF output.
- Impact: report archiving/export only; no research data-source, SSO, AI configuration, or cnstock boundary changes.
- Verification: local Python syntax check and frontend JavaScript syntax check. Full business testing intentionally left for manual user testing.

## 2026-07-28 v2.2.3

- Added an evidence-library summary layer for CNINFO announcements, including download/extraction counts, snippet counts, latest announcement date, category/source breakdowns, and aggregated gaps.
- Added per-announcement `source_label`, `snippet_count`, and `text_length` fields to make the raw announcement chain easier to scan and reuse.
- Upgraded the frontend to show announcement evidence summary before the raw announcement cards.
- Impact: announcement evidence ingestion, evidence-library display, and research report readability.
- Verification: local Python/JavaScript syntax checks and VPS container backend unit tests.

## 2026-07-28 v2.2.2

- Fixed the research form inputs to disable browser autocomplete/history suggestions and use Yanqing-specific field names.
- Impact: frontend research form only; no backend business logic, data boundary, SSO, gateway, or AI configuration changes.
- Verification: frontend static regression test, local Python/JavaScript syntax checks, VPS container backend unit tests, and health checks.

## 2026-07-28 v2.2.1

- Improved financial readability by replacing raw machine field names in digest observations with Chinese labels.
- Added `source_label` for financial traceability cards so the UI can show human-readable source names while retaining raw field provenance in data.
- Added `research_judgement` with conclusion, confidence, base/upside/downside cases, and strengthen/weaken conditions.
- Strengthened AI prompts to require bolder conditional fundamental judgement without allowing direct trading instructions.
- Impact: backend report validation, AI schema/prompt, frontend report rendering, and project documentation.
- Verification: local Python/JavaScript syntax checks and VPS container backend unit tests.

## 2026-07-28 v2.2

- Added `financial_traceability` to auto-research snapshots for field-level financial source tracking.
- Added traceability cards for revenue, net profit, operating cash flow, receivables, contract assets, inventory, margins, ROE, ROIC, and impairment data gaps.
- Added frontend display for `财报字段追溯` before evidence digest so researchers can verify field, period, value, source, interpretation, and risk.
- Impact: backend snapshot payloads, frontend report rendering, and project documentation.
- Verification: local Python/JavaScript syntax checks and VPS container backend unit tests.

## 2026-07-28 v2.1

- Added a collapsible left research-control panel so long reports can use more horizontal space.
- Added a browser print-based `导出 PDF` button that prints only the research report body for archiving.
- Added a frontend static regression test for the sidebar and PDF export controls.
- Impact: frontend workspace usability, print/PDF output, and project documentation.
- Verification: local Python syntax check, VPS container frontend-control regression test, VPS container backend unit tests, health check, SSO redirect checks, and browser workflow review.

## 2026-07-28 v2.0.1

- Fixed the AI report guardrail so direct trade instructions are sanitized at field level instead of returning a whole-report 422.
- Preserved factual disclosures such as shareholder reduction announcements or repurchase/increase plans when they are research evidence rather than user trading instructions.
- Impact: backend report validation and auto/manual research output safety.
- Verification: VPS container backend unit tests.

## 2026-07-28 v2.0

- Added the planned `tracking_dashboard` report layer for trigger/status/evidence/next-check/invalidation tracking.
- Added documentation for the V2.0 tracking-trigger dashboard iteration.
- Impact: report schema, AI prompt, frontend report rendering, and project documentation.
- Verification: local syntax check, VPS container backend unit tests, internal payload fallback check, health check, SSO redirect checks, and browser UI verification.

## 2026-07-27 v1.7

- Added the planned `contradiction_matrix` report layer for claim/support/opposition/gap/trigger comparison.
- Added documentation for the V1.7 evidence-matrix iteration.
- Impact: report schema, AI prompt, frontend report rendering, and project documentation.
- Verification: local syntax check, VPS container backend unit tests, internal payload fallback check, health check, SSO redirect checks, and browser UI verification.

## 2026-07-27 v1.6

- Added `report.evidence_display` as a UI-oriented evidence-chain view that keeps traceable quotes and counts downgraded untraceable evidence.
- Updated the frontend evidence-chain section to hide empty downgraded cards and show a compact downgraded-evidence notice instead.
- Added historical-report fallback so existing reports can render a cleaner evidence chain without regeneration.
- Impact: backend report payload shape, frontend report rendering, and evidence-chain usability.
- Verification: local syntax check and VPS container backend unit tests.

## 2026-07-27 v1.5

- Added `evidence_digest` to reuse already collected CNINFO snippets and financial snapshot metrics.
- Added topic tagging for revenue, profit, cash flow, receivables, contract assets, impairment, orders, policy, risk, and legal evidence.
- Added digest open questions so missing order/policy support becomes an explicit `数据不足` follow-up rather than wasted data.
- Added frontend display for digest financial facts, source-backed snippets, and follow-up questions.
- Impact: auto-research snapshots, AI context, frontend evidence display, and project documentation.
- Verification: local syntax checks and VPS container tests.

## 2026-07-27 v1.4

- Added automatic CNINFO evidence collection for announcement and financial-report source documents.
- Added independent evidence cache under `data/evidence/{ticker}` with downloaded PDFs, extracted text, snippets, and explicit data gaps.
- Added evidence APIs for source status, refresh, list, and detail preview.
- Injected `evidence_library` into auto-research snapshots and added server-side validation for source-backed AI evidence.
- Added frontend source-document evidence display.
- Added BrianHub SSO protection for `/yanqing` through gateway `forward_auth`.
- Added BrianHub-standard `specs/`, `plans/`, and `reports/` documentation entries.
- Hardened final review issues: source-backed narrative claims now require evidence-library traceability, evidence PDF writes reject escaped `documents/` symlinks, and refresh failures propagate explicit `数据不足` gaps.
- Adjusted auto-research evidence guardrails so untraceable narrative claims are downgraded to `数据不足` instead of failing the whole report, while exact evidence quotes remain strictly traceable.
- Adjusted auto-research evidence quotes so untraceable `evidence[].quote` values are removed and marked `数据不足` instead of failing the whole report.
- Impact: backend evidence ingestion, auto-research snapshots, frontend evidence display, gateway SSO, and project documentation.
- Verification: local syntax/static scans, VPS container tests, internal evidence refresh, online SSO redirects for page and API routes, and internal health/data-source checks.

## 2026-07-25 v1.1-v1.2

- Upgraded the main flow from manually pasted material to automatic data collection and research.
- Added independent snapshot and research storage boundaries.
- Added data-source status, stock search, automatic research, and evidence-chain display.

## 2026-07-25 v1.0

- Created Yanqing as an independent project.
- Added the standalone FastAPI service and native HTML frontend.
- Added the `/yanqing` gateway route and retained a 404 for `/cnstock/yanqing.html`.
