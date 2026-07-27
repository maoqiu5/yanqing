import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

os.environ["TUSHARE_TOKEN"] = ""
os.environ["YANQING_DATA_DIR"] = "/tmp/yanqing-test-data"

from backend.app.main import app  # noqa: E402


client = TestClient(app)


class StockSearchTests(unittest.TestCase):
    def test_returns_direct_code_candidate_without_tushare_token(self):
        response = client.get("/api/stocks/search", params={"q": "300767"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["results"][0]["ts_code"], "300767.SZ")
        self.assertEqual(payload["results"][0]["source"], "code")


class SnapshotEvidenceTests(unittest.TestCase):
    def test_build_evidence_library_returns_limited_library_when_refresh_fails(self):
        from backend.app import main

        with patch("backend.app.main.refresh_evidence_for_ticker", side_effect=RuntimeError("CNINFO unavailable")) as refresh:
            library = main.build_evidence_library("000001.SZ", refresh=True, limit=7, days=30)

        refresh.assert_called_once()
        self.assertEqual(refresh.call_args.args[0], "000001.SZ")
        self.assertEqual(refresh.call_args.args[1].limit, 7)
        self.assertEqual(refresh.call_args.args[1].days, 30)
        self.assertTrue(refresh.call_args.args[1].download)
        self.assertTrue(refresh.call_args.args[1].extract_text)
        self.assertIn(library["status"], ("limited", "insufficient"))
        self.assertEqual(library["items"], [])
        self.assertTrue(library["data_gaps"])
        json.dumps(library, ensure_ascii=False)

    def test_snapshot_includes_evidence_library_when_refresh_fails(self):
        import backend.app.main as main

        original_build = main.build_evidence_library
        original_stock_basic = main.stock_basic_cache
        original_collect = main.collect_tushare
        original_sina = main.sina_quote
        try:
            main.build_evidence_library = lambda ticker, refresh=True, limit=20, days=720: {
                "status": "insufficient",
                "items": [],
                "data_gaps": ["公告原文数据不足"],
            }
            main.stock_basic_cache = lambda: []
            main.collect_tushare = lambda api_name, params, fields, failures, limit=10: []
            main.sina_quote = lambda ticker: {"source": "Sina", "status": "empty"}

            snapshot = main.build_company_snapshot("300767.SZ")

            self.assertIn("evidence_library", snapshot)
            self.assertEqual(snapshot["evidence_library"]["status"], "insufficient")
            self.assertIn("公告原文数据不足", snapshot["evidence_library"]["data_gaps"])
        finally:
            main.build_evidence_library = original_build
            main.stock_basic_cache = original_stock_basic
            main.collect_tushare = original_collect
            main.sina_quote = original_sina


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

    def test_evidence_index_round_trips_and_invalid_cache_is_empty(self):
        from backend.app import main

        original_evidence_dir = main.EVIDENCE_DIR
        try:
            main.EVIDENCE_DIR = main.DATA_DIR / "evidence-test"
            records = [{"evidence_id": "a", "title": "公告", "announcement_date": "2026-01-01"}]
            main.save_evidence_index("000001.SZ", records)
            self.assertEqual(main.load_evidence_index("000001.SZ"), records)

            path = main.evidence_ticker_dir("000001.SZ") / "index.json"
            path.write_text("not json", encoding="utf-8")
            self.assertEqual(main.load_evidence_index("000001.SZ"), [])
        finally:
            main.EVIDENCE_DIR = original_evidence_dir

    def test_build_evidence_library_reports_insufficient_without_cache(self):
        from backend.app import main

        original_evidence_dir = main.EVIDENCE_DIR
        try:
            main.EVIDENCE_DIR = main.DATA_DIR / "empty-evidence-test"
            self.assertEqual(main.build_evidence_library("000001.SZ", refresh=False), {
                "status": "insufficient",
                "items": [],
                "data_gaps": ["公告原文数据不足"],
            })
        finally:
            main.EVIDENCE_DIR = original_evidence_dir

    def test_evidence_ticker_dir_rejects_traversal_and_absolute_like_tickers(self):
        from backend.app import main

        original_evidence_dir = main.EVIDENCE_DIR
        try:
            main.EVIDENCE_DIR = main.DATA_DIR / "evidence-containment-test"
            for ticker in ("..\\outside", "../outside", "C:\\outside", "/tmp/outside"):
                with self.assertRaisesRegex(Exception, "invalid evidence ticker"):
                    main.evidence_ticker_dir(ticker)
        finally:
            main.EVIDENCE_DIR = original_evidence_dir

    def test_evidence_library_model_matches_serializable_library(self):
        from backend.app.main import EvidenceLibrary, build_evidence_library

        library = EvidenceLibrary.model_validate(build_evidence_library("000001.SZ", refresh=False))
        self.assertEqual(library.model_dump(mode="json")["status"], "insufficient")

    def test_build_evidence_library_marks_limited_when_refresh_returns_gap_with_cached_items(self):
        from backend.app import main

        original_evidence_dir = main.EVIDENCE_DIR
        try:
            main.EVIDENCE_DIR = main.DATA_DIR / "limited-refresh-gap-test"
            main.save_evidence_index("000001.SZ", [{
                "evidence_id": "cached",
                "announcement_date": "2026-01-01",
                "title": "\u5df2\u7f13\u5b58\u516c\u544a",
            }])
            with patch("backend.app.main.refresh_evidence_for_ticker", return_value={
                "ticker": "000001.SZ",
                "items": main.load_evidence_index("000001.SZ"),
                "data_gaps": ["CNINFO\u516c\u544a\u641c\u7d22\u5931\u8d25\uff1a\u6570\u636e\u4e0d\u8db3"],
            }):
                library = main.build_evidence_library("000001.SZ", refresh=True)

            self.assertEqual(library["status"], "limited")
            self.assertIn("CNINFO\u516c\u544a\u641c\u7d22\u5931\u8d25\uff1a\u6570\u636e\u4e0d\u8db3", library["data_gaps"])
        finally:
            main.EVIDENCE_DIR = original_evidence_dir


class AutoResearchEvidenceValidationTests(unittest.TestCase):
    def test_trade_instruction_blocks_increase_and_reduce_holdings(self):
        from backend.app.main import _contains_trade_instruction

        self.assertTrue(_contains_trade_instruction({"core_view": "建议增持"}))
        self.assertTrue(_contains_trade_instruction({"core_view": "建议减持"}))

    def test_snapshot_evidence_rejects_fabricated_cninfo_quote_without_library_items(self):
        from backend.app.main import _validate_snapshot_evidence

        with self.assertRaises(HTTPException) as raised:
            _validate_snapshot_evidence(
                {"evidence": [{"source": "CNINFO公告/evidence_library", "quote": "公司已签订重大订单"}]},
                {"evidence_library": {"items": []}},
            )
        self.assertEqual(raised.exception.status_code, 422)
        self.assertIn("traceable", str(raised.exception.detail))

    def test_snapshot_evidence_rejects_unmatched_cninfo_quote(self):
        from backend.app.main import _validate_snapshot_evidence

        with self.assertRaises(HTTPException) as raised:
            _validate_snapshot_evidence(
                {"evidence": [{"source": "CNINFO公告", "quote": "虚构的重大订单"}]},
                {"evidence_library": {"items": [{"title": "关于日常经营的公告", "snippets": [{"quote": "公司经营情况正常"}]}]}},
            )
        self.assertEqual(raised.exception.status_code, 422)
        self.assertIn("traceable", str(raised.exception.detail))

    def test_snapshot_evidence_rejects_fabricated_source_backed_narrative_claim(self):
        from backend.app.main import _validate_snapshot_evidence

        with self.assertRaises(HTTPException) as raised:
            _validate_snapshot_evidence(
                {
                    "core_view": "\u516c\u53f8\u5df2\u62ff\u5230\u91cd\u5927\u8ba2\u5355\uff0c\u653f\u7b56\u63a8\u52a8\u6536\u5165\u9ad8\u589e",
                    "business_basics": ["\u5ba2\u6237\u4e3b\u8981\u662f\u5730\u65b9\u653f\u5e9c"],
                    "policy_order_chain": ["\u516c\u544a\u539f\u6587\u663e\u793a\u8ba2\u5355\u5df2\u8f6c\u5316\u4e3a\u6536\u5165"],
                    "evidence": [],
                },
                {"evidence_library": {"items": [{"title": "\u65e5\u5e38\u7ecf\u8425\u516c\u544a", "snippets": [{"quote": "\u516c\u53f8\u65e5\u5e38\u7ecf\u8425\u60c5\u51b5\u6b63\u5e38"}]}]}},
            )
        self.assertEqual(raised.exception.status_code, 422)
        self.assertIn("narrative", str(raised.exception.detail))

    def test_snapshot_evidence_allows_source_backed_narrative_when_marked_insufficient(self):
        from backend.app.main import _validate_snapshot_evidence

        _validate_snapshot_evidence(
            {"core_view": "\u516c\u544a\u539f\u6587\u6570\u636e\u4e0d\u8db3\uff0c\u91cd\u5927\u8ba2\u5355\u4ecd\u9700\u6838\u5b9e", "evidence": []},
            {"evidence_library": {"items": []}},
        )


class EvidenceSnippetTests(unittest.TestCase):
    def test_build_evidence_snippets_prefers_research_keywords(self):
        from backend.app.main import build_evidence_snippets

        text = "公司实现营业收入12亿元。重大合同金额5亿元。经营现金流为正。"
        snippets = build_evidence_snippets(text, "重大合同公告", limit=2)

        self.assertEqual(len(snippets), 2)
        self.assertTrue(all(item["page"] is None for item in snippets))
        self.assertTrue(any("重大合同" in item["quote"] for item in snippets))


class EvidenceApiTests(unittest.TestCase):
    def test_evidence_status_endpoint(self):
        response = client.get("/api/evidence/300767.SZ/sources/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["ticker"], "300767.SZ")
        self.assertEqual(payload["sources"][0]["name"], "cninfo")
        self.assertTrue(payload["sources"][0]["configured"])
        self.assertEqual(payload["sources"][0]["status"], "ready")

    def test_evidence_list_uses_cache_without_refresh(self):
        from backend.app import main

        original_evidence_dir = main.EVIDENCE_DIR
        main.EVIDENCE_DIR = main.DATA_DIR / "list-api-test"
        try:
            ticker_dir = main.evidence_ticker_dir("300767.SZ")
            ticker_dir.mkdir(parents=True, exist_ok=True)
            (ticker_dir / "index.json").write_text(json.dumps({"items": [
                {"evidence_id": "old", "announcement_date": "2026-01-01"},
                {"evidence_id": "new", "announcement_date": "2026-02-01"},
            ]}), encoding="utf-8")

            with patch("backend.app.main.search_cninfo_announcements", side_effect=AssertionError("network refresh attempted")):
                response = client.get("/api/evidence/300767.SZ")

            self.assertEqual(response.status_code, 200)
            self.assertEqual([item["evidence_id"] for item in response.json()["items"]], ["new", "old"])
        finally:
            main.EVIDENCE_DIR = original_evidence_dir

    def test_evidence_detail_returns_404_for_missing_evidence(self):
        from backend.app import main

        original_evidence_dir = main.EVIDENCE_DIR
        main.EVIDENCE_DIR = main.DATA_DIR / "detail-404-api-test"
        try:
            with patch("backend.app.main.search_cninfo_announcements", side_effect=AssertionError("network call")):
                response = client.get("/api/evidence/300767.SZ/missing")
            self.assertEqual(response.status_code, 404)
        finally:
            main.EVIDENCE_DIR = original_evidence_dir

    def test_evidence_detail_caps_text_preview_at_5000_chars(self):
        from backend.app import main

        original_evidence_dir = main.EVIDENCE_DIR
        main.EVIDENCE_DIR = main.DATA_DIR / "detail-preview-api-test"
        try:
            ticker_dir = main.evidence_ticker_dir("300767.SZ")
            ticker_dir.mkdir(parents=True, exist_ok=True)
            text_path = ticker_dir / "record.txt"
            text_path.write_text("x" * 6000, encoding="utf-8")
            main.save_evidence_index("300767.SZ", [{"evidence_id": "record", "local_text_path": str(text_path)}])

            with patch("backend.app.main.search_cninfo_announcements", side_effect=AssertionError("network call")):
                response = client.get("/api/evidence/300767.SZ/record")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json()["text_preview"]), 5000)
        finally:
            main.EVIDENCE_DIR = original_evidence_dir

    def test_evidence_detail_ignores_text_outside_ticker_directory(self):
        from backend.app import main

        original_evidence_dir = main.EVIDENCE_DIR
        main.EVIDENCE_DIR = main.DATA_DIR / "detail-containment-api-test"
        try:
            ticker_dir = main.evidence_ticker_dir("300767.SZ")
            ticker_dir.mkdir(parents=True, exist_ok=True)
            outside_path = main.EVIDENCE_DIR / "outside.txt"
            outside_path.write_text("should not be exposed", encoding="utf-8")
            main.save_evidence_index("300767.SZ", [{"evidence_id": "record", "local_text_path": str(outside_path)}])

            with patch("backend.app.main.search_cninfo_announcements", side_effect=AssertionError("network call")):
                response = client.get("/api/evidence/300767.SZ/record")
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("text_preview", response.json())
        finally:
            main.EVIDENCE_DIR = original_evidence_dir

    def test_evidence_refresh_saves_and_returns_mocked_records(self):
        from backend.app import main

        original_evidence_dir = main.EVIDENCE_DIR
        main.EVIDENCE_DIR = main.DATA_DIR / "refresh-api-test"
        record = {
            "evidence_id": "a" * 64,
            "ticker": "300767.SZ",
            "source": "cninfo",
            "title": "annual report",
            "announcement_date": "2026-01-01",
            "category": "annual_report",
            "url": "https://static.cninfo.com.cn/finalpage/report.PDF",
            "download_status": "skipped",
            "text_extract_status": "skipped",
            "snippets": [],
            "data_gaps": [],
        }
        try:
            with patch("backend.app.main.search_cninfo_announcements", return_value=[record]) as search, patch(
                "backend.app.main.download_cninfo_pdf", side_effect=lambda item: {**item, "download_status": "downloaded"}
            ) as download:
                response = client.post("/api/evidence/300767/refresh", json={"download": True, "extract_text": False})

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["ticker"], "300767.SZ")
            self.assertEqual(payload["items"][0]["evidence_id"], record["evidence_id"])
            self.assertEqual(payload["items"][0]["download_status"], "downloaded")
            self.assertEqual(payload["data_gaps"], [])
            search.assert_called_once_with("300767.SZ", limit=20, days=720)
            download.assert_called_once_with(record)
            self.assertEqual(main.load_evidence_index("300767.SZ")[0]["evidence_id"], record["evidence_id"])
        finally:
            main.EVIDENCE_DIR = original_evidence_dir


    def test_evidence_refresh_writes_extracted_text_under_text_directory(self):
        from backend.app import main

        original_evidence_dir = main.EVIDENCE_DIR
        record = {
            "evidence_id": "b" * 64,
            "ticker": "300767.SZ",
            "source": "cninfo",
            "title": "annual report",
            "announcement_date": "2026-01-01",
            "category": "annual_report",
            "url": "https://static.cninfo.com.cn/finalpage/report.PDF",
            "download_status": "skipped",
            "text_extract_status": "skipped",
            "snippets": [],
            "data_gaps": [],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            main.EVIDENCE_DIR = main.DATA_DIR / "refresh-text-path-test"
            pdf_path = Path(temp_dir) / "source.pdf"
            pdf_path.write_bytes(b"pdf")
            try:
                with patch("backend.app.main.search_cninfo_announcements", return_value=[record]), patch(
                    "backend.app.main.download_cninfo_pdf",
                    return_value={**record, "download_status": "downloaded", "local_pdf_path": str(pdf_path)},
                ), patch("backend.app.main.extract_pdf_text", return_value=("合同文本", "ready")):
                    response = client.post("/api/evidence/300767/refresh", json={"download": True})

                self.assertEqual(response.status_code, 200)
                item = response.json()["items"][0]
                self.assertEqual(Path(item["local_text_path"]).parent.name, "text")
                self.assertTrue(Path(item["local_text_path"]).is_file())
                self.assertEqual(Path(item["local_text_path"]).read_text(encoding="utf-8"), "合同文本")
            finally:
                main.EVIDENCE_DIR = original_evidence_dir


    def test_evidence_refresh_rejects_unsafe_text_evidence_id(self):
        from backend.app import main

        original_evidence_dir = main.EVIDENCE_DIR
        record = {
            "evidence_id": "..\\outside",
            "ticker": "300767.SZ",
            "source": "cninfo",
            "title": "annual report",
            "announcement_date": "2026-01-01",
            "category": "annual_report",
            "url": "https://static.cninfo.com.cn/finalpage/report.PDF",
            "download_status": "skipped",
            "text_extract_status": "skipped",
            "snippets": [],
            "data_gaps": [],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            main.EVIDENCE_DIR = Path(temp_dir) / "evidence"
            pdf_path = Path(temp_dir) / "source.pdf"
            pdf_path.write_bytes(b"pdf")
            try:
                with patch("backend.app.main.search_cninfo_announcements", return_value=[record]), patch(
                    "backend.app.main.download_cninfo_pdf",
                    return_value={**record, "download_status": "downloaded", "local_pdf_path": str(pdf_path)},
                ), patch("backend.app.main.extract_pdf_text", return_value=("合同文本", "ready")):
                    response = client.post("/api/evidence/300767/refresh", json={"download": True})

                self.assertEqual(response.status_code, 200)
                item = response.json()["items"][0]
                self.assertEqual(item["text_extract_status"], "failed")
                self.assertIn("公告PDF文本提取失败：数据不足", item["data_gaps"])
                self.assertFalse((main.evidence_ticker_dir("300767.SZ") / "outside.txt").exists())
            finally:
                main.EVIDENCE_DIR = original_evidence_dir

    def test_evidence_refresh_rejects_text_directory_symlink(self):
        from backend.app import main

        original_evidence_dir = main.EVIDENCE_DIR
        record = {
            "evidence_id": "c" * 64,
            "ticker": "300767.SZ",
            "source": "cninfo",
            "title": "annual report",
            "announcement_date": "2026-01-01",
            "category": "annual_report",
            "url": "https://static.cninfo.com.cn/finalpage/report.PDF",
            "download_status": "skipped",
            "text_extract_status": "skipped",
            "snippets": [],
            "data_gaps": [],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            main.EVIDENCE_DIR = temp_root / "evidence"
            ticker_root = main.evidence_ticker_dir("300767.SZ")
            ticker_root.mkdir(parents=True, exist_ok=True)
            outside_dir = temp_root / "outside"
            outside_dir.mkdir()
            try:
                (ticker_root / "text").symlink_to(outside_dir, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"symlink creation unavailable: {exc}")

            pdf_path = temp_root / "source.pdf"
            pdf_path.write_bytes(b"pdf")
            try:
                with patch("backend.app.main.search_cninfo_announcements", return_value=[record]), patch(
                    "backend.app.main.download_cninfo_pdf",
                    return_value={**record, "download_status": "downloaded", "local_pdf_path": str(pdf_path)},
                ), patch("backend.app.main.extract_pdf_text", return_value=("contract text", "ready")):
                    response = client.post("/api/evidence/300767/refresh", json={"download": True})

                self.assertEqual(response.status_code, 200)
                item = response.json()["items"][0]
                self.assertEqual(item["text_extract_status"], "failed")
                self.assertIn("公告PDF文本提取失败：数据不足", item["data_gaps"])
                self.assertFalse((outside_dir / f'{record["evidence_id"]}.txt').exists())
            finally:
                main.EVIDENCE_DIR = original_evidence_dir


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

    def test_search_maps_exchange_and_uses_cninfo_org_id_when_available(self):
        from backend.app import main

        announcement_payload = {
            "announcements": [
                {"announcementTitle": f"公告 {index}", "adjunctUrl": f"finalpage/{index}.PDF"}
                for index in range(60)
            ]
        }
        stock_payload = {
            "stockList": [
                {"code": "600000", "orgId": "gssh0600000"},
                {"code": "300767", "orgId": "9900031933"},
                {"code": "430047", "orgId": "gfbj0830047"},
            ]
        }

        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self.payload

        class FakeClient:
            post_data: list[dict[str, object]] = []

            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def get(self, url, headers):
                return FakeResponse(stock_payload)

            def post(self, url, data, headers):
                FakeClient.post_data.append(data)
                return FakeResponse(announcement_payload)

        original_client = main.httpx.Client
        original_cache_dir = main.CACHE_DIR
        try:
            main.CACHE_DIR = main.DATA_DIR / "cninfo-stock-list-test"
            main.httpx.Client = FakeClient
            for ticker in ("600000.SH", "300767.SZ", "430047.BJ"):
                rows = main.search_cninfo_announcements(ticker, limit=100, days=30)
                self.assertEqual(len(rows), 50)

            self.assertEqual([data["column"] for data in FakeClient.post_data], ["sse", "szse", "bse"])
            self.assertTrue(all(data["pageSize"] == 50 for data in FakeClient.post_data))
            self.assertEqual([data["stock"] for data in FakeClient.post_data], ["600000,gssh0600000", "300767,9900031933", "430047,gfbj0830047"])
        finally:
            main.httpx.Client = original_client
            main.CACHE_DIR = original_cache_dir

    def test_refresh_reports_gap_when_no_announcements_or_cache_exist(self):
        from backend.app import main

        original_evidence_dir = main.EVIDENCE_DIR
        try:
            main.EVIDENCE_DIR = main.DATA_DIR / "empty-refresh-gap-test"
            with patch("backend.app.main.search_cninfo_announcements", return_value=[]):
                payload = main.refresh_evidence_for_ticker("300767.SZ", main.EvidenceRefreshRequest(limit=2, days=30, download=True, extract_text=True))

            self.assertEqual(payload["items"], [])
            self.assertIn("公告原文数据不足", payload["data_gaps"])
        finally:
            main.EVIDENCE_DIR = original_evidence_dir

    def test_download_rejects_malicious_evidence_id_without_network(self):
        from backend.app import main

        original_client = main.httpx.Client
        try:
            def fail_if_called(**kwargs):
                raise AssertionError("download attempted a network request")

            main.httpx.Client = fail_if_called
            result = main.download_cninfo_pdf({
                "ticker": "300767.SZ",
                "evidence_id": "..\\outside",
                "url": "https://static.cninfo.com.cn/finalpage/report.PDF",
            })
            self.assertEqual(result["download_status"], "failed")
            self.assertIn("公告PDF下载失败：数据不足", result["data_gaps"])
        finally:
            main.httpx.Client = original_client

    def test_download_rejects_non_cninfo_host_without_network(self):
        from backend.app import main

        original_client = main.httpx.Client
        try:
            def fail_if_called(**kwargs):
                raise AssertionError("download attempted a network request")

            main.httpx.Client = fail_if_called
            result = main.download_cninfo_pdf({
                "ticker": "300767.SZ",
                "evidence_id": "a" * 64,
                "url": "https://example.com/report.PDF",
            })
            self.assertEqual(result["download_status"], "failed")
            self.assertIn("公告PDF下载失败：数据不足", result["data_gaps"])
        finally:
            main.httpx.Client = original_client

    def test_download_rejects_documents_directory_symlink(self):
        from backend.app import main

        class FakeResponse:
            url = "https://static.cninfo.com.cn/finalpage/report.PDF"
            content = b"not written outside"

            def raise_for_status(self):
                return None

        class FakeClient:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def get(self, url):
                return FakeResponse()

        original_client = main.httpx.Client
        original_evidence_dir = main.EVIDENCE_DIR
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            main.EVIDENCE_DIR = temp_root / "evidence"
            ticker_root = main.evidence_ticker_dir("300767.SZ")
            ticker_root.mkdir(parents=True, exist_ok=True)
            outside_dir = temp_root / "outside"
            outside_dir.mkdir()
            try:
                (ticker_root / "documents").symlink_to(outside_dir, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"symlink creation unavailable: {exc}")
            try:
                main.httpx.Client = FakeClient
                result = main.download_cninfo_pdf({
                    "ticker": "300767.SZ",
                    "evidence_id": "a" * 64,
                    "url": "https://static.cninfo.com.cn/finalpage/report.PDF",
                })

                self.assertEqual(result["download_status"], "failed")
                self.assertTrue(any("\u6570\u636e\u4e0d\u8db3" in gap or "PDF" in gap for gap in result["data_gaps"]))
                self.assertFalse((outside_dir / f'{"a" * 64}.pdf').exists())
            finally:
                main.httpx.Client = original_client
                main.EVIDENCE_DIR = original_evidence_dir

    def test_download_rejects_redirect_to_non_cninfo_host(self):
        from backend.app import main

        class FakeResponse:
            url = "https://evil.example/a.pdf"
            content = b"not written"

            def raise_for_status(self):
                return None

        class FakeClient:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def get(self, url):
                return FakeResponse()

        original_client = main.httpx.Client
        try:
            main.httpx.Client = FakeClient
            result = main.download_cninfo_pdf({
                "ticker": "300767.SZ",
                "evidence_id": "a" * 64,
                "url": "https://static.cninfo.com.cn/finalpage/report.PDF",
            })
            self.assertEqual(result["download_status"], "failed")
            self.assertIn("公告PDF下载失败：数据不足", result["data_gaps"])
        finally:
            main.httpx.Client = original_client


if __name__ == "__main__":
    unittest.main()
