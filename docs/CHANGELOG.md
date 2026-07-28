# Yanqing CHANGELOG

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
