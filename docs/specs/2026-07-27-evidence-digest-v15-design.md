# Yanqing V1.5 Evidence Digest Design

## Goal

Make already collected TuShare financial data and CNINFO announcement/PDF text more useful before adding new sources. The system should turn raw `evidence_library.items`, snippets, and derived financial metrics into a compact `evidence_digest` that AI and the frontend can use directly.

## Scope

- Build `evidence_digest` during automatic snapshot creation.
- Tag existing CNINFO evidence snippets with research topics such as revenue, profit, cash flow, receivables, contract assets, impairment, orders, policy, risk, and legal opinion.
- Add financial digest facts from existing derived metrics and financial tables.
- Add unresolved questions when current evidence lacks order/policy/customer support.
- Render the digest on the frontend before raw source documents.

## Out Of Scope

- No new external source.
- No cnstock dependency.
- No new login, AI key configuration, database, or runtime directory.
- No direct trading instructions.

## Data Shape

`snapshot.evidence_digest`:

```json
{
  "status": "ready | limited | insufficient",
  "items": [
    {
      "topic": "cashflow",
      "label": "经营现金流",
      "source": "震安科技股份有限公司2025年度审计报告",
      "quote": "应收账款余额与经营现金流情况需关注",
      "evidence_id": "...",
      "date": "2026-01-01",
      "category": "annual_report"
    }
  ],
  "financial_facts": [
    {"topic": "valuation", "label": "估值", "observation": "pe_ttm: 12.3；pb: 1.5"}
  ],
  "open_questions": ["订单数据不足：当前公告原文未提供可追溯订单证据"],
  "data_gaps": ["政策数据不足：当前证据库未提供可追溯政策证据"]
}
```

## Guardrails

- Missing evidence produces `数据不足`; no fabricated announcements, orders, policy facts, customers, or financial fields.
- Exact `evidence[].quote` validation remains server-side.
- Untraceable AI narrative and quote output is downgraded, not allowed as a fact.

## Verification

- Unit tests cover digest topic extraction, financial facts, insufficient evidence gaps, and snapshot injection.
- VPS container tests must pass before deployment.
- Health and SSO checks remain unchanged.
