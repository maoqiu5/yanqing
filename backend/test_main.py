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

    def test_build_evidence_digest_uses_existing_cninfo_and_financial_data(self):
        from backend.app.main import build_evidence_digest

        snapshot = {
            "evidence_library": {
                "status": "ready",
                "items": [{
                    "evidence_id": "e1",
                    "title": "\u9707\u5b89\u79d1\u62802025\u5e74\u5ea6\u5ba1\u8ba1\u62a5\u544a",
                    "announcement_date": "2026-04-20",
                    "category": "annual_report",
                    "snippets": [
                        {"quote": "\u5e94\u6536\u8d26\u6b3e\u4e0e\u7ecf\u8425\u73b0\u91d1\u6d41\u60c5\u51b5\u9700\u5173\u6ce8"},
                        {"quote": "\u8425\u4e1a\u6536\u5165\u548c\u51c0\u5229\u6da6\u51fa\u73b0\u53d8\u52a8"},
                    ],
                }]
            },
            "derived": {
                "latest_period": "20251231",
                "cashflow": {"n_cashflow_act": -120000000},
                "balance_quality": {"accounts_receiv": 450000000, "contract_assets": 230000000},
                "valuation": {"pe_ttm": 12.3, "pb": 1.5},
            },
        }

        digest = build_evidence_digest(snapshot)

        self.assertEqual(digest["status"], "ready")
        self.assertTrue(any(item["topic"] == "receivables" for item in digest["items"]))
        self.assertTrue(any(item["topic"] == "cashflow" for item in digest["items"]))
        self.assertTrue(any(fact["topic"] == "cashflow" for fact in digest["financial_facts"]))
        facts_text = json.dumps(digest["financial_facts"], ensure_ascii=False)
        self.assertIn("\u7ecf\u8425\u73b0\u91d1\u6d41\u51c0\u989d", facts_text)
        self.assertIn("\u5e94\u6536\u8d26\u6b3e", facts_text)
        self.assertNotIn("n_cashflow_act", facts_text)
        self.assertNotIn("accounts_receiv", facts_text)
        self.assertTrue(any("\u8ba2\u5355\u6570\u636e\u4e0d\u8db3" in question for question in digest["open_questions"]))

    def test_snapshot_includes_evidence_digest(self):
        import backend.app.main as main

        original_build = main.build_evidence_library
        original_stock_basic = main.stock_basic_cache
        original_collect = main.collect_tushare
        original_sina = main.sina_quote
        try:
            main.build_evidence_library = lambda ticker, refresh=True, limit=20, days=720: {
                "status": "ready",
                "items": [{"title": "\u5ba1\u8ba1\u62a5\u544a", "snippets": [{"quote": "\u7ecf\u8425\u73b0\u91d1\u6d41\u9700\u5173\u6ce8"}]}],
                "data_gaps": [],
            }
            main.stock_basic_cache = lambda: []
            main.collect_tushare = lambda api_name, params, fields, failures, limit=10: []
            main.sina_quote = lambda ticker: {"source": "Sina", "status": "empty"}

            snapshot = main.build_company_snapshot("300767.SZ")

            self.assertIn("evidence_digest", snapshot)
            self.assertIn("items", snapshot["evidence_digest"])
            self.assertIn("open_questions", snapshot["evidence_digest"])
        finally:
            main.build_evidence_library = original_build
            main.stock_basic_cache = original_stock_basic
            main.collect_tushare = original_collect
            main.sina_quote = original_sina

    def test_build_financial_traceability_maps_key_fields_to_sources(self):
        from backend.app.main import build_financial_traceability

        trace = build_financial_traceability({
            "financials": {
                "income": [{"end_date": "20260331", "revenue": 52428658.97, "n_income_attr_p": -1901201.47}],
                "balance": [{"end_date": "20260331", "accounts_receiv": 425278061.39, "contract_assets": 9511394.21, "inventories": 86000000}],
                "cashflow": [{"end_date": "20260331", "n_cashflow_act": 99798188.68}],
                "indicators": [{"end_date": "20260331", "grossprofit_margin": 26.36, "netprofit_margin": -3.88, "roe": -0.42, "roic": 1.12}],
            }
        })

        by_key = {item["field_key"]: item for item in trace["items"]}
        self.assertEqual(trace["status"], "ready")
        self.assertEqual(by_key["revenue"]["label"], "\u8425\u4e1a\u6536\u5165")
        self.assertEqual(by_key["revenue"]["period"], "20260331")
        self.assertEqual(by_key["revenue"]["value"], 52428658.97)
        self.assertEqual(by_key["revenue"]["source"], "tushare.income.revenue")
        self.assertEqual(by_key["revenue"]["source_label"], "TuShare 利润表 / 营业收入")
        self.assertIn("\u6536\u5165", by_key["revenue"]["interpretation"])
        self.assertEqual(by_key["operating_cash_flow"]["source"], "tushare.cashflow.n_cashflow_act")
        self.assertEqual(by_key["contract_assets"]["value"], 9511394.21)
        self.assertEqual(by_key["impairment"]["data_status"], "insufficient")
        self.assertIn("\u6570\u636e\u4e0d\u8db3", by_key["impairment"]["risk"])


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
    def test_build_tracking_dashboard_uses_matrix_and_report_triggers(self):
        from backend.app.main import build_tracking_dashboard

        dashboard = build_tracking_dashboard({
            "contradiction_matrix": [{
                "claim": "\u6536\u5165\u4fee\u590d\u80fd\u5426\u8f6c\u5316\u4e3a\u5229\u6da6",
                "supporting_evidence": ["2025\u5e74\u6536\u5165\u6062\u590d"],
                "opposing_evidence": ["2026Q1\u6536\u5165\u4e0b\u6ed1"],
                "data_gaps": ["\u8ba2\u5355\u6570\u636e\u4e0d\u8db3"],
                "tracking_triggers": ["\u6bdb\u5229\u7387\u56de\u5347"],
            }],
            "tracking_triggers": ["\u6bdb\u5229\u7387\u56de\u5347", "\u5e94\u6536\u7ee7\u7eed\u4e0b\u964d"],
            "evidence_display": {"items": [{"quote": "grossprofit_margin: 26.3693", "note": "\u6bdb\u5229\u7387\u7ebf\u7d22"}]},
        })

        self.assertEqual([item["trigger"] for item in dashboard], ["\u6bdb\u5229\u7387\u56de\u5347", "\u5e94\u6536\u7ee7\u7eed\u4e0b\u964d"])
        self.assertEqual(dashboard[0]["status"], "watch")
        self.assertIn("\u6536\u5165\u4fee\u590d", dashboard[0]["why"])
        self.assertTrue(any("grossprofit_margin" in item for item in dashboard[0]["evidence"]))
        self.assertIn("\u4e0b\u4e00\u671f", dashboard[0]["next_check"])
        self.assertIn("\u672a\u51fa\u73b0", dashboard[0]["invalidate_if"])

    def test_validate_report_adds_bolder_research_judgement(self):
        from backend.app.main import _validate_report

        validated = _validate_report({
            "title": "\u9707\u5b89\u79d1\u6280\u6df1\u7814",
            "data_quality": "limited",
            "core_view": "\u6536\u5165\u4fee\u590d\u5c1a\u672a\u5145\u5206\u8f6c\u5316\u4e3a\u5229\u6da6\u548c\u73b0\u91d1\u6d41\uff0c\u56de\u6b3e\u662f\u7b2c\u4e00\u77db\u76fe\u3002",
            "business_basics": ["\u51cf\u9694\u9707\u884c\u4e1a\uff0c\u6570\u636e\u4ecd\u9700\u539f\u6587\u8865\u5f3a\u3002"],
            "investment_contradiction": {
                "summary": "\u6536\u5165\u4fee\u590d\u80fd\u5426\u7a7f\u900f\u5230\u5229\u6da6\u548c\u73b0\u91d1\u6d41",
                "positive": ["\u7ecf\u8425\u73b0\u91d1\u6d41\u4e3a\u6b63"],
                "negative": ["\u5e94\u6536\u8d26\u6b3e\u4ecd\u9ad8"],
                "key_question": "\u56de\u6b3e\u662f\u5426\u6301\u7eed\u6539\u5584",
            },
            "financial_diagnosis": ["\u7ecf\u8425\u73b0\u91d1\u6d41\u4e0e\u51c0\u5229\u6da6\u80cc\u79bb"],
            "policy_order_chain": ["\u8ba2\u5355\u6570\u636e\u4e0d\u8db3"],
            "risks_and_disconfirming_evidence": ["\u5e94\u6536\u548c\u51cf\u503c\u98ce\u9669"],
            "research_questions": ["\u51cf\u503c\u662f\u5426\u51fa\u6e05"],
            "tracking_triggers": ["\u7ecf\u8425\u73b0\u91d1\u6d41\u6301\u7eed\u4e3a\u6b63", "\u5e94\u6536\u8d26\u6b3e\u4e0b\u964d"],
            "evidence": [],
        })

        judgement = validated["research_judgement"]
        self.assertIn("\u5f53\u524d\u7814\u5224", judgement["conclusion"])
        self.assertEqual(judgement["confidence"]["level"], "\u4e2d")
        self.assertIn("\u6700\u53ef\u80fd\u60c5\u666f", judgement["base_case"]["title"])
        self.assertTrue(judgement["strengthen_conditions"])
        self.assertTrue(judgement["weaken_conditions"])
        text = json.dumps(judgement, ensure_ascii=False)
        self.assertNotIn("\u4e70\u5165", text)
        self.assertNotIn("\u5356\u51fa", text)

    def test_build_contradiction_matrix_falls_back_from_report_sections(self):
        from backend.app.main import build_contradiction_matrix

        matrix = build_contradiction_matrix({
            "investment_contradiction": {
                "summary": "\u6536\u5165\u4fee\u590d\u80fd\u5426\u8f6c\u5316\u4e3a\u5229\u6da6\u548c\u73b0\u91d1\u6d41",
                "positive": ["2025\u5e74\u8425\u4e1a\u6536\u5165\u6062\u590d"],
                "negative": ["2026Q1\u6536\u5165\u4e0b\u6ed1"],
                "key_question": "\u5e94\u6536\u8d26\u6b3e\u56de\u6b3e\u662f\u5426\u53ef\u6301\u7eed",
            },
            "financial_diagnosis": ["\u7ecf\u8425\u73b0\u91d1\u6d41\u660e\u663e\u597d\u4e8e\u5229\u6da6"],
            "risks_and_disconfirming_evidence": ["\u4ecd\u5b58\u5728\u51cf\u503c\u98ce\u9669"],
            "tracking_triggers": ["\u6bdb\u5229\u7387\u56de\u5347", "\u5e94\u6536\u7ee7\u7eed\u4e0b\u964d"],
        })

        self.assertEqual(len(matrix), 1)
        self.assertIn("\u6536\u5165\u4fee\u590d", matrix[0]["claim"])
        self.assertIn("2025\u5e74\u8425\u4e1a\u6536\u5165\u6062\u590d", matrix[0]["supporting_evidence"])
        self.assertIn("2026Q1\u6536\u5165\u4e0b\u6ed1", matrix[0]["opposing_evidence"])
        self.assertIn("\u5e94\u6536\u8d26\u6b3e\u56de\u6b3e\u662f\u5426\u53ef\u6301\u7eed", matrix[0]["data_gaps"])
        self.assertIn("\u6bdb\u5229\u7387\u56de\u5347", matrix[0]["tracking_triggers"])

    def test_snapshot_evidence_adds_display_summary_for_downgraded_quotes(self):
        from backend.app.main import _validate_snapshot_evidence

        report = {
            "evidence": [
                {"source": "CNINFO\u516c\u544a", "quote": "\u865a\u6784\u7684\u91cd\u5927\u8ba2\u5355"},
                {"source": "CNINFO\u516c\u544a", "quote": "\u516c\u53f8\u7ecf\u8425\u60c5\u51b5\u6b63\u5e38", "note": "\u53ef\u8ffd\u6eaf"},
                {"source": "financials.cashflow", "quote": "99798188.68", "note": "\u7ed3\u6784\u5316\u6570\u503c"},
            ]
        }
        _validate_snapshot_evidence(
            report,
            {"evidence_library": {"items": [{"title": "\u516c\u544a", "snippets": [{"quote": "\u516c\u53f8\u7ecf\u8425\u60c5\u51b5\u6b63\u5e38"}]}]}},
        )

        self.assertEqual(report["evidence_display"]["downgraded_count"], 1)
        self.assertEqual(len(report["evidence_display"]["items"]), 2)
        self.assertEqual(report["evidence_display"]["items"][0]["quote"], "\u516c\u53f8\u7ecf\u8425\u60c5\u51b5\u6b63\u5e38")
        self.assertEqual(report["evidence_display"]["items"][1]["quote"], "99798188.68")

    def test_trade_instruction_blocks_increase_and_reduce_holdings(self):
        from backend.app.main import _contains_trade_instruction

        self.assertTrue(_contains_trade_instruction({"core_view": "建议增持"}))
        self.assertTrue(_contains_trade_instruction({"core_view": "建议减持"}))

    def test_validate_report_sanitizes_direct_trade_instruction_without_rejecting_factual_disclosure(self):
        from backend.app.main import _validate_report

        report = {
            "title": "\u6df1\u7814\u62a5\u544a",
            "data_quality": "limited",
            "core_view": "\u5efa\u8bae\u4e70\u5165\uff0c\u7b49\u5f85\u653f\u7b56\u50ac\u5316",
            "business_basics": ["\u516c\u53f8\u62ab\u9732\u80a1\u4e1c\u51cf\u6301\u516c\u544a\uff0c\u9700\u8ddf\u8e2a\u80a1\u6743\u7ed3\u6784\u53d8\u5316"],
            "investment_contradiction": {
                "summary": "\u53ef\u4ee5\u52a0\u4ed3\uff0c\u6536\u5165\u4fee\u590d\u5f39\u6027\u5927",
                "positive": ["\u5efa\u8bae\u589e\u6301"],
                "negative": ["\u56de\u8d2d\u589e\u6301\u8ba1\u5212\u5c1a\u9700\u6838\u5b9e"],
                "key_question": "\u662f\u5426\u5e94\u51cf\u6301\uff1f",
            },
            "financial_diagnosis": ["\u7ecf\u8425\u73b0\u91d1\u6d41\u9700\u7ee7\u7eed\u8ddf\u8e2a"],
            "policy_order_chain": ["\u8ba2\u5355\u6570\u636e\u4e0d\u8db3"],
            "risks_and_disconfirming_evidence": ["\u6536\u5165\u6062\u590d\u4e0d\u53ca\u9884\u671f"],
            "research_questions": ["\u662f\u5426\u53ef\u4ee5\u4e70\u5165\uff1f"],
            "tracking_triggers": ["\u5356\u51fa\u4fe1\u53f7\u51fa\u73b0"],
            "evidence": [],
        }

        validated = _validate_report(report)
        text = json.dumps(validated, ensure_ascii=False)

        self.assertNotIn("\u5efa\u8bae\u4e70\u5165", text)
        self.assertNotIn("\u53ef\u4ee5\u52a0\u4ed3", text)
        self.assertNotIn("\u5efa\u8bae\u589e\u6301", text)
        self.assertNotIn("\u662f\u5426\u5e94\u51cf\u6301", text)
        self.assertIn("\u6570\u636e\u4e0d\u8db3", validated["core_view"])
        self.assertIn("\u80a1\u4e1c\u51cf\u6301\u516c\u544a", validated["business_basics"][0])
        self.assertIn("\u56de\u8d2d\u589e\u6301\u8ba1\u5212", validated["investment_contradiction"]["negative"][0])

    def test_snapshot_evidence_sanitizes_fabricated_cninfo_quote_without_library_items(self):
        from backend.app.main import _validate_snapshot_evidence

        report = {"evidence": [{"source": "CNINFO\u516c\u544a/evidence_library", "quote": "\u516c\u53f8\u5df2\u7b7e\u8ba2\u91cd\u5927\u8ba2\u5355"}]}
        _validate_snapshot_evidence(report, {"evidence_library": {"items": []}})

        self.assertEqual(report["evidence"][0]["quote"], "")
        self.assertIn("\u6570\u636e\u4e0d\u8db3", report["evidence"][0]["note"])

    def test_snapshot_evidence_sanitizes_unmatched_cninfo_quote(self):
        from backend.app.main import _validate_snapshot_evidence

        report = {"evidence": [{"source": "CNINFO\u516c\u544a", "quote": "\u865a\u6784\u7684\u91cd\u5927\u8ba2\u5355"}]}
        _validate_snapshot_evidence(
            report,
            {"evidence_library": {"items": [{"title": "\u5173\u4e8e\u65e5\u5e38\u7ecf\u8425\u7684\u516c\u544a", "snippets": [{"quote": "\u516c\u53f8\u7ecf\u8425\u60c5\u51b5\u6b63\u5e38"}]}]}},
        )

        self.assertEqual(report["evidence"][0]["quote"], "")
        self.assertIn("\u6570\u636e\u4e0d\u8db3", report["evidence"][0]["note"])

    def test_snapshot_evidence_keeps_traceable_cninfo_quote(self):
        from backend.app.main import _validate_snapshot_evidence

        report = {"evidence": [{"source": "CNINFO\u516c\u544a", "quote": "\u516c\u53f8\u7ecf\u8425\u60c5\u51b5\u6b63\u5e38", "note": "\u652f\u6301\u65e5\u5e38\u7ecf\u8425\u5224\u65ad"}]}
        _validate_snapshot_evidence(
            report,
            {"evidence_library": {"items": [{"title": "\u5173\u4e8e\u65e5\u5e38\u7ecf\u8425\u7684\u516c\u544a", "snippets": [{"quote": "\u516c\u53f8\u7ecf\u8425\u60c5\u51b5\u6b63\u5e38"}]}]}},
        )

        self.assertEqual(report["evidence"][0]["quote"], "\u516c\u53f8\u7ecf\u8425\u60c5\u51b5\u6b63\u5e38")
        self.assertEqual(report["evidence"][0]["note"], "\u652f\u6301\u65e5\u5e38\u7ecf\u8425\u5224\u65ad")

    def test_snapshot_evidence_sanitizes_fabricated_source_backed_narrative_claim(self):
        from backend.app.main import _validate_snapshot_evidence

        report = {
            "core_view": "\u516c\u53f8\u5df2\u62ff\u5230\u91cd\u5927\u8ba2\u5355\uff0c\u653f\u7b56\u63a8\u52a8\u6536\u5165\u9ad8\u589e",
            "business_basics": ["\u5ba2\u6237\u4e3b\u8981\u662f\u5730\u65b9\u653f\u5e9c"],
            "policy_order_chain": ["\u516c\u544a\u539f\u6587\u663e\u793a\u8ba2\u5355\u5df2\u8f6c\u5316\u4e3a\u6536\u5165"],
            "evidence": [],
        }
        _validate_snapshot_evidence(
            report,
            {"evidence_library": {"items": [{"title": "\u65e5\u5e38\u7ecf\u8425\u516c\u544a", "snippets": [{"quote": "\u516c\u53f8\u65e5\u5e38\u7ecf\u8425\u60c5\u51b5\u6b63\u5e38"}]}]}},
        )

        self.assertIn("\u6570\u636e\u4e0d\u8db3", report["core_view"])
        self.assertIn("\u6570\u636e\u4e0d\u8db3", report["business_basics"][0])
        self.assertIn("\u6570\u636e\u4e0d\u8db3", report["policy_order_chain"][0])
        self.assertNotIn("\u6536\u5165\u9ad8\u589e", report["core_view"])

    def test_snapshot_evidence_allows_synthesized_narrative_with_evidence_overlap(self):
        from backend.app.main import _validate_snapshot_evidence

        _validate_snapshot_evidence(
            {
                "core_view": "\u5ba1\u8ba1\u62a5\u544a\u548c\u8d22\u62a5\u7247\u6bb5\u663e\u793a\uff0c\u516c\u53f8\u5e94\u6536\u8d26\u6b3e\u4e0e\u7ecf\u8425\u73b0\u91d1\u6d41\u662f\u6838\u5fc3\u8ddf\u8e2a\u77db\u76fe\u3002",
                "financial_diagnosis": ["\u8d22\u62a5\u6570\u636e\u6307\u5411\u5e94\u6536\u8d26\u6b3e\u548c\u7ecf\u8425\u73b0\u91d1\u6d41\u9700\u7ee7\u7eed\u9a8c\u8bc1\u3002"],
                "evidence": [],
            },
            {"evidence_library": {"items": [{
                "title": "\u9707\u5b89\u79d1\u6280\u80a1\u4efd\u6709\u9650\u516c\u53f82025\u5e74\u5ea6\u5ba1\u8ba1\u62a5\u544a",
                "category": "annual_report",
                "snippets": [
                    {"quote": "\u5e94\u6536\u8d26\u6b3e\u4f59\u989d\u4e0e\u7ecf\u8425\u73b0\u91d1\u6d41\u60c5\u51b5\u9700\u5173\u6ce8"},
                    {"quote": "\u8d22\u62a5\u62ab\u9732\u8425\u4e1a\u6536\u5165\u53ca\u51c0\u5229\u6da6\u53d8\u52a8"},
                ],
            }]}}
        )

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


class FrontendWorkspaceControlsTests(unittest.TestCase):
    def test_frontend_has_collapsible_sidebar_and_pdf_export_controls(self):
        html = (Path(__file__).resolve().parents[1] / "frontend" / "index.html").read_text(encoding="utf-8")

        self.assertIn('id="sidebarToggle"', html)
        self.assertIn('id="exportBtn"', html)
        self.assertIn("function toggleSidebar()", html)
        self.assertIn("function exportPdf()", html)
        self.assertIn("sidebar-collapsed", html)
        self.assertIn("@media print", html)
        self.assertIn("window.print()", html)
        self.assertIn("function financialTrace", html)
        self.assertIn("财报字段追溯", html)
        self.assertIn("function judgementView", html)
        self.assertIn("当前研判", html)


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
