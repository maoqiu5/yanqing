# Yanqing V1.5 Evidence Digest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a compact evidence digest so already collected CNINFO and financial data is reused by AI and visible in the frontend.

**Architecture:** Keep the existing single-file backend pattern. Add pure helper functions in `backend/app/main.py`, inject the digest into snapshots, then render it from `frontend/index.html`.

**Tech Stack:** FastAPI backend, Python unittest, vanilla HTML/CSS/JS frontend, Docker Compose deployment.

## Global Constraints

- Yanqing must not call cnstock APIs or read cnstock data.
- AI configuration remains portal `/internal/ai-config` only.
- No real secrets in code, docs, logs, or responses.
- Missing source support must say `数据不足`.
- No direct trading instructions.

---

### Task 1: Backend Evidence Digest

**Files:**
- Modify: `backend/app/main.py`
- Test: `backend/test_main.py`

**Interfaces:**
- Produces: `build_evidence_digest(snapshot: dict[str, Any]) -> dict[str, Any]`
- Consumes: `snapshot["evidence_library"]`, `snapshot["derived"]`, `snapshot["financials"]`

- [ ] Write tests for topic tagging, financial facts, and missing order/policy gaps.
- [ ] Implement topic keyword mapping and digest item extraction.
- [ ] Inject `evidence_digest` into `build_company_snapshot`.
- [ ] Run backend tests.

### Task 2: Frontend Digest Display

**Files:**
- Modify: `frontend/index.html`

**Interfaces:**
- Consumes: `payload.input_snapshot.evidence_digest`

- [ ] Render digest facts and open questions between financial metrics and AI evidence.
- [ ] Keep raw source-document section intact.
- [ ] Verify HTML escaping and fallback text.

### Task 3: Documentation And Deployment

**Files:**
- Modify: `docs/PRD.md`
- Modify: `docs/CHANGELOG.md`

- [ ] Document V1.5 current scope.
- [ ] Run local syntax checks.
- [ ] Run VPS container tests.
- [ ] Commit, push to `vps/main`, sync files to `/root/apps/yanqing`, rebuild container, and verify health/SSO.
