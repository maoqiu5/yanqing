# V2.2 Financial Traceability Implementation Plan

**Goal:** Add field-level financial traceability cards to Yanqing snapshots and report UI.

**Architecture:** Build traceability from existing `snapshot.financials` rows, inject into `input_snapshot.financial_traceability`, and render it in the existing single-page frontend. No new backend endpoints, databases, secrets, or external project dependencies.

## Tasks

- [x] Add failing unit test for `build_financial_traceability`.
- [x] Implement traceability card generation for key financial fields.
- [x] Inject `financial_traceability` into automatic company snapshots.
- [x] Render “财报字段追溯” in the report UI with historical-report fallback.
- [x] Add static frontend regression assertions.
- [x] Run local syntax checks and VPS container tests.
- [x] Rebuild production container and perform health/SSO checks.
- [x] Commit and push to VPS bare remote.
