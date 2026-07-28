# Yanqing PRD

## Product Goal

Yanqing is an independent equity research workspace. A user supplies a stock name or code; the system collects source data, builds a snapshot, and asks AI to analyze fundamentals, key tensions, evidence, risks, research questions, and follow-up triggers.

## Independent Boundary

- Yanqing is standalone and is not part of cnstock.
- It must not call cnstock APIs or read cnstock pools, holdings, market caches, reports, databases, tables, or data directories.
- It must not reuse cnstock login, passwords, sessions, cookies, or local state.
- The UI must not add navigation links to cnstock or the portal.
- The only shared AI capability is portal `/internal/ai-config`, accessed with `PORTAL_INTERNAL_TOKEN` without exposing its value.

## V2.0 Current Scope

- Automatically collect public announcements, annual reports, semiannual reports, and quarterly reports as source evidence.
- Store evidence metadata, downloaded documents, extracted text, snippets, source status, and data gaps under Yanqing's independent evidence directory.
- Inject traceable source evidence into auto-research snapshots. Missing or failed source text is reported as `data insufficient`; AI must not invent facts.
- Build an `evidence_digest` from already collected CNINFO snippets and financial metrics so AI and users can reuse available evidence instead of only seeing raw source rows.
- Show digest topics, financial facts, and follow-up questions in the frontend before the raw source-document list.
- Show a `contradiction_matrix` so researchers can compare claims, supporting evidence, opposing evidence, data gaps, and tracking triggers in one place.
- Show a `tracking_dashboard` so researchers can track next checks, current evidence, invalidation conditions, and data gaps.
- Sanitize direct trade instructions at report-validation time and downgrade those fields to `data insufficient` research language, while preserving factual disclosures that are evidence rather than user trading commands.
- Provide a collapsible research-control panel and browser PDF export for long-report reading, archiving, and offline review.
- Show `financial_traceability` cards for key financial fields so researchers can verify period, value, source, interpretation, risk, and explicit data gaps.
- Show `research_judgement` near the top of the report with a bolder conditional conclusion, confidence, scenarios, strengthen conditions, and weaken conditions.
- Use CNINFO as the primary public source, with SSE and SZSE represented as future adapter boundaries.
- Provide evidence source status, refresh, list, and detail capabilities and show source evidence in the frontend.

## SSO Requirement

The `/yanqing` page and business APIs must be protected by the BrianHub gateway. The gateway must use `forward_auth` to call portal `/auth/check?redirect=1`. Yanqing does not implement a separate login flow.

## Later Scope

- V1.8: financial-field traceability from displayed metrics to period, field, source, and interpretation.
- V1.9: policy-source and tender/order-source adapters, source detail navigation, and tracking loop.
- Later V2.x: evidence grading and source-detail navigation for financial fields, policies, tenders, and orders.
