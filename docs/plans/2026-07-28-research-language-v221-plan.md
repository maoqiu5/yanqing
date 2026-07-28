# V2.2.1 Research Language Implementation Plan

**Goal:** Improve report readability and make Yanqing output bolder conditional fundamental judgements.

**Architecture:** Backend validation adds a normalized `research_judgement` structure and readable financial labels. Frontend renders the judgement near the top of the report. No data-source, auth, gateway, AI-key, or storage-boundary changes.

## Tasks

- [x] Add failing tests for readable financial labels and `research_judgement`.
- [x] Add Chinese financial field labels to digest observations.
- [x] Add `source_label` for financial traceability cards.
- [x] Add `research_judgement` schema and service-side fallback.
- [x] Strengthen AI prompt to require conditional fundamental judgement, confidence, and strengthen/weaken conditions.
- [x] Render “当前研判” in the frontend.
- [x] Run local syntax checks and VPS container tests.
- [x] Rebuild production container and run health/SSO checks.
- [x] Commit and push to VPS bare remote.
