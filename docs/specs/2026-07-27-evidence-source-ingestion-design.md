# Yanqing V1.4 Evidence Source Ingestion Design

## Goal

Yanqing V1.4 will automatically collect announcement and financial-report source material for a stock, persist it in Yanqing's independent data directory, and inject traceable evidence into auto research snapshots. The feature must improve report trustworthiness without depending on cnstock data, sessions, APIs, directories, cookies, or database state.

The first implementation targets a reliable minimum loop:

- Search public announcement sources by `ts_code`.
- Save announcement metadata and downloaded PDF files.
- Extract text when possible.
- Generate short, source-linked snippets for the research snapshot.
- Mark missing or failed evidence as `数据不足`.

## Scope

Included:

- CNINFO announcement search as the primary public source.
- Source adapter boundaries for future SSE/SZSE fallback sources.
- Evidence cache under `YANQING_DATA_DIR/evidence`.
- New API endpoints for refresh, list, read, and source status.
- Auto research integration through `input_snapshot.evidence_library`.
- Frontend evidence-source visibility.
- Tests for source parsing, cache behavior, data-gap handling, and snapshot injection.

Excluded from V1.4 minimum loop:

- User-uploaded evidence management.
- Full semantic PDF section parsing.
- OCR for scanned PDFs.
- Cross-source deduplication beyond title/date/url hash.
- Live trading recommendations or rating language.

## Data Sources

### Primary Source: CNINFO

CNINFO is the first source because it provides broad A-share announcement coverage and PDF links through a searchable public disclosure surface.

The implementation should isolate source details in a small adapter:

- `search_announcements(ts_code, limit, start_date, end_date) -> list[AnnouncementMeta]`
- `download_announcement(meta) -> DownloadResult`
- `source_status() -> SourceStatus`

The adapter must use conservative request headers and short timeouts. If CNINFO changes behavior, the adapter should fail closed and record a data gap instead of fabricating evidence.

### Future Fallback Sources

SSE and SZSE source adapters should be represented by an interface but not fully implemented in the first pass unless CNINFO is unavailable during verification. The source status API should return future adapters as `configured=false` or `not_implemented` rather than hiding them.

## Storage

All evidence lives under Yanqing's independent data root:

```text
data/evidence/{safe_ticker}/
  index.json
  documents/
    {evidence_id}.pdf
  text/
    {evidence_id}.txt
```

`index.json` contains one record per announcement:

```json
{
  "evidence_id": "sha256-prefix",
  "ticker": "300767.SZ",
  "source": "cninfo",
  "title": "announcement title",
  "announcement_date": "2026-07-27",
  "category": "annual_report",
  "url": "https://...",
  "local_pdf_path": "/app/data/evidence/300767_SZ/documents/...",
  "local_text_path": "/app/data/evidence/300767_SZ/text/...",
  "download_status": "ready",
  "text_extract_status": "ready",
  "snippets": [
    {
      "quote": "short source excerpt",
      "note": "matched research topic or field",
      "page": null
    }
  ],
  "data_gaps": []
}
```

Paths returned by APIs should be useful for diagnostics but never expose tokens, cookies, or request headers.

## Categorization

Announcement categories should be deterministic and conservative:

- `annual_report`: annual report title keywords.
- `semiannual_report`: semiannual report title keywords.
- `quarterly_report`: quarterly report title keywords.
- `forecast`: earnings forecast and preliminary earnings title keywords.
- `contract`: major contract, bid-winning, and order title keywords.
- `pledge`: share pledge title keywords.
- `risk`: risk warning, litigation, arbitration, regulatory, and inquiry title keywords.
- `other`: no confident match

If a title could match a noisy category, use `other`. Research prompts can still inspect the title, but they must not turn ambiguous titles into unsupported conclusions.

## API

### `GET /api/evidence/{ticker}/sources/status`

Returns source readiness:

```json
{
  "ticker": "300767.SZ",
  "sources": [
    {
      "name": "cninfo",
      "configured": true,
      "status": "ready",
      "purpose": "announcement and financial-report source documents"
    }
  ]
}
```

### `POST /api/evidence/{ticker}/refresh`

Refreshes evidence for one ticker.

Request:

```json
{
  "limit": 20,
  "days": 720,
  "download": true,
  "extract_text": true
}
```

Response:

```json
{
  "ticker": "300767.SZ",
  "refreshed_at": "2026-07-27T00:00:00Z",
  "items": [],
  "data_gaps": []
}
```

The endpoint should be synchronous in V1.4 to keep deployment simple. If refresh takes too long, it should return partial results with data gaps.

### `GET /api/evidence/{ticker}`

Lists cached evidence records, newest first. It should not force a network refresh.

### `GET /api/evidence/{ticker}/{evidence_id}`

Returns one cached record and a bounded text preview. Full PDFs remain local cache artifacts, not unauthenticated public assets in this version.

## Research Snapshot Integration

`build_company_snapshot` should include:

```json
{
  "evidence_library": {
    "status": "ready | limited | insufficient",
    "items": [],
    "data_gaps": []
  }
}
```

Auto research should call the evidence refresh path before AI generation with a modest default, for example 20 announcements across the last 720 days. If refresh fails, the snapshot still saves with `evidence_library.status=limited` or `insufficient`, and AI generation may proceed only if the existing financial-data requirement is met.

The prompt must tell the AI:

- Only cite announcement, order, policy, and financial-report text that appears in `evidence_library.items`.
- If a needed original document is absent or extraction failed, write `数据不足`.
- Do not invent announcements, orders, policies, customers, revenue structure, or report fields.
- Do not output direct buy/sell/add/reduce instructions.

## Frontend

The first UI update should stay compact:

- Data-source panel adds evidence-source status.
- Search/auto-research result shows evidence refresh status.
- Report output adds a source-document evidence section with title, date, category, source, extraction status, and snippets.
- Existing evidence-chain cards remain, but source-backed entries should display announcement title/date when present.

No portal or cnstock navigation links should be added.

## Error Handling

Expected failures are data, not crashes:

- Network timeout: record `cninfo: timeout` in `data_gaps`.
- Announcement search shape changed: record `cninfo: parse_failed`.
- PDF download failed: keep metadata, set `download_status=failed`.
- Text extraction failed: keep PDF metadata, set `text_extract_status=failed`.
- No announcements found: `status=insufficient`, data gap `公告原文数据不足`.

The system must never ask AI to fill a missing announcement fact.

## Testing

Unit tests:

- Ticker normalization still rejects invalid codes.
- CNINFO response parser maps metadata without network dependency.
- Category classifier uses conservative labels.
- Evidence index merge deduplicates stable records.
- Snapshot includes `evidence_library` and data gaps when refresh fails.
- Trade-instruction filter still blocks prohibited words.

Integration tests:

- Evidence list endpoint returns cached records.
- Refresh endpoint handles mocked CNINFO success and failure.
- Auto research snapshot includes evidence records without requiring cnstock.

Manual verification:

- `/api/health` remains unchanged.
- `/api/data-source/status` still shows TuShare and local storage.
- `/api/evidence/300767.SZ/sources/status` returns CNINFO status.
- `/api/evidence/300767.SZ/refresh` creates local evidence files when public source access succeeds.
- `/api/research/auto` saves snapshots containing `evidence_library`.

## Security And Boundary Rules

- Do not log tokens, API keys, cookies, or Authorization headers.
- Do not use cnstock APIs, storage, login, sessions, cookies, or local state.
- Evidence storage remains under `YANQING_DATA_DIR`.
- Public-source fetches must not require private cookies.
- API errors should reveal data-source status and data gaps, not secrets or raw headers.

## Rollout

1. Add evidence data models, category classifier, storage helpers, and tests.
2. Add CNINFO source adapter behind the source interface.
3. Add evidence API endpoints.
4. Inject evidence library into auto research snapshots and prompts.
5. Add frontend evidence-source status and source-backed evidence display.
6. Update docs and changelog.
