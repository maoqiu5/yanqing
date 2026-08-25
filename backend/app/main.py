from __future__ import annotations

import json
from enum import Enum
import hashlib
import signal
import subprocess
import tempfile
from datetime import timedelta
from html import escape, unescape
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field, ValidationError

ROOT_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = ROOT_DIR / "frontend"
DATA_DIR = Path(os.getenv("YANQING_DATA_DIR", "/app/data"))
RESEARCH_DIR = DATA_DIR / "research"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
CACHE_DIR = DATA_DIR / "cache"
EVIDENCE_DIR = DATA_DIR / "evidence"
PDF_RUNTIME_DIR = DATA_DIR / "runtime" / "pdf"
TUSHARE_API_URL = os.getenv("TUSHARE_API_URL", "http://api.tushare.pro")
CHROMIUM_PATH = os.getenv("CHROMIUM_PATH", "").strip()
PDF_RENDER_TIMEOUT_SECONDS = int(os.getenv("PDF_RENDER_TIMEOUT_SECONDS", "180"))
TRADE_ACTION_WORDS = ("买入", "卖出", "加仓", "减仓", "增持", "减持", "清仓", "建仓", "满仓", "梭哈", "抄底", "止盈", "止损")
TRADE_DIRECTIVE_NOTE = "数据不足：该表述包含直接交易指令，已移除，需改为研究跟踪条件。"
TRADE_DIRECTIVE_PREFIXES = ("建议", "可以", "可", "应", "应当", "应该", "考虑", "适合", "立即", "直接", "现在", "操作", "策略", "信号", "时机")
TRADE_DIRECTIVE_SUFFIXES = ("信号", "机会", "时点", "建议", "策略", "操作", "仓位")


def _data_gap(message: str) -> str:
    return message if "数据不足" in message else f"{message}：数据不足"


class ResearchRequest(BaseModel):
    stock_name: str = Field(min_length=1, max_length=80)
    ticker: str = Field(default="", max_length=32)
    industry: str = Field(default="", max_length=120)
    business: str = Field(default="", max_length=1000)
    materials: str = Field(default="", max_length=60000)
    question: str = Field(default="", max_length=1200)
    depth: str = Field(default="full")


class AutoResearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=80)
    ticker: str = Field(default="", max_length=32)
    depth: str = Field(default="full")
    supplemental_materials: str = Field(default="", max_length=20000)
    question: str = Field(default="", max_length=1200)



class EvidenceGrade(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"


class EvidenceConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EvidenceRef(BaseModel):
    evidence_id: str = ""
    source_label: str = ""
    quote: str = ""
    page: int | None = None
    source_url: str = ""
    source_date: str = ""
    grade: str = EvidenceGrade.D.value
    confidence: str = "low"
    field: str = ""
    logic: str = ""


class EvidenceItem(BaseModel):
    source: str
    quote: str = ""
    note: str = ""
    evidence_id: str = ""
    page: int | None = None
    source_url: str = ""
    source_date: str = ""
    grade: str = EvidenceGrade.D.value
    confidence: str = "low"


class EvidenceDisplay(BaseModel):
    items: list[EvidenceItem] = Field(default_factory=list)
    downgraded_count: int = 0


class ContradictionMatrixRow(BaseModel):
    claim: str = "数据不足"
    supporting_evidence: list[str] = Field(default_factory=list)
    supporting_evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    opposing_evidence: list[str] = Field(default_factory=list)
    opposing_evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    tracking_triggers: list[str] = Field(default_factory=list)


class TrackingDashboardItem(BaseModel):
    trigger: str = "数据不足"
    status: str = "watch"
    why: str = "数据不足"
    evidence: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    next_check: str = "数据不足"
    invalidate_if: str = "数据不足"


class EvidenceRefreshRequest(BaseModel):
    limit: int = Field(default=20, ge=1, le=50)
    days: int = Field(default=720, ge=1, le=3650)
    download: bool = True
    extract_text: bool = True


class EvidenceSnippet(BaseModel):
    quote: str = ""
    note: str = ""
    page: int | None = None
    page_label: str = ""
    source_url: str = ""
    source_date: str = ""
    grade: str = EvidenceGrade.D.value
    confidence: str = "low"


class EvidenceRecord(BaseModel):
    evidence_id: str
    ticker: str
    source: str = "cninfo"
    source_label: str = "CNINFO 公告原文"
    source_type: str = "official_announcement"
    grade: str = EvidenceGrade.D.value
    confidence: str = "low"
    file_name: str = ""
    retrieved_at: str = ""
    title: str
    announcement_date: str = ""
    category: str = "other"
    url: str = ""
    local_pdf_path: str = ""
    local_text_path: str = ""
    local_pages_path: str = ""
    download_status: str = "skipped"
    text_extract_status: str = "skipped"
    snippet_count: int = 0
    text_length: int = 0
    snippets: list[EvidenceSnippet] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)

def source_type_for_category(category: str) -> str:
    if str(category or "") in {"annual_report", "semiannual_report", "quarterly_report"}:
        return "official_financial_report"
    return "official_announcement"


def _downgrade_evidence_grade(grade: str) -> str:
    order = (EvidenceGrade.A.value, EvidenceGrade.B.value, EvidenceGrade.C.value, EvidenceGrade.D.value)
    try:
        index = order.index(str(grade or EvidenceGrade.D.value))
    except ValueError:
        return EvidenceGrade.D.value
    return order[min(index + 1, len(order) - 1)]


def grade_evidence_record(item: dict[str, Any]) -> tuple[str, str]:
    source_type = str(item.get("source_type") or source_type_for_category(item.get("category") or ""))
    category = str(item.get("category") or "other")

    if source_type == "official_financial_report":
        grade = EvidenceGrade.A.value
        confidence = "high"
    elif source_type == "official_announcement":
        grade = EvidenceGrade.B.value
        confidence = "high" if category in {"forecast", "contract"} else "medium"
    elif source_type in {"exchange_reply", "policy", "tender_order"}:
        grade = EvidenceGrade.B.value if source_type in {"policy", "tender_order"} else EvidenceGrade.C.value
        confidence = "medium"
    else:
        grade = EvidenceGrade.C.value
        confidence = "medium"

    if not item.get("evidence_id") or not item.get("url"):
        return EvidenceGrade.D.value, "low"

    download_status = str(item.get("download_status") or "")
    text_status = str(item.get("text_extract_status") or "")
    if download_status != "downloaded" or text_status != "ready":
        grade = _downgrade_evidence_grade(grade)
        if grade == EvidenceGrade.D.value:
            confidence = "low"
        elif confidence == "high":
            confidence = "medium"

    gaps = [str(gap) for gap in item.get("data_gaps") or [] if str(gap).strip()]
    if any(("下载失败" in gap or "提取失败" in gap or "数据不足" in gap) for gap in gaps):
        grade = _downgrade_evidence_grade(grade)
        confidence = "low"

    return grade, confidence


def confidence_for_evidence(item: dict[str, Any], snippet: dict[str, Any] | None = None) -> str:
    _, confidence = grade_evidence_record(item)
    if snippet is None:
        return confidence
    if not str(snippet.get("quote") or "").strip():
        return "low"
    if confidence == "high" and snippet.get("page") is None:
        return "medium"
    if confidence == "medium" and snippet.get("page") is not None:
        return "high"
    return confidence



class EvidenceLibrary(BaseModel):
    status: str
    items: list[dict[str, Any]] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


class ResearchReport(BaseModel):
    title: str
    data_quality: str
    core_view: str
    research_judgement: dict[str, Any] = Field(default_factory=dict)
    business_basics: list[str] = Field(default_factory=list)
    investment_contradiction: dict[str, Any]
    financial_diagnosis: list[str] = Field(default_factory=list)
    policy_order_chain: list[str] = Field(default_factory=list)
    risks_and_disconfirming_evidence: list[str] = Field(default_factory=list)
    research_questions: list[str] = Field(default_factory=list)
    tracking_triggers: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    evidence_display: EvidenceDisplay = Field(default_factory=EvidenceDisplay)
    contradiction_matrix: list[ContradictionMatrixRow] = Field(default_factory=list)
    tracking_dashboard: list[TrackingDashboardItem] = Field(default_factory=list)


class PortalAiConfig(BaseModel):
    enabled: bool = False
    baseUrl: str = ""
    apiKey: str = ""
    model: str = ""
    timeoutSeconds: int = 30
    analysisLimit: int = 12


app = FastAPI(title="Yanqing Research API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("CORS_ALLOW_ORIGINS", "*").split(",") if origin.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "yanqing"}


@app.get("/api/data-source/status")
def data_source_status() -> dict[str, Any]:
    return {
        "tushare": {"configured": bool(_tushare_token()), "purpose": "股票基础信息、行情估值、三大报表、财务指标"},
        "sina_quote": {"configured": True, "purpose": "公开实时/延迟行情兜底"},
        "local_storage": {"configured": True, "root": str(DATA_DIR), "snapshots": str(SNAPSHOT_DIR), "research": str(RESEARCH_DIR)},
    }


@app.get("/api/evidence/{ticker}/sources/status")
def evidence_source_status(ticker: str) -> dict[str, Any]:
    normalized = normalize_ts_code(ticker)
    return {
        "ticker": normalized,
        "sources": [{
            "name": "cninfo",
            "configured": True,
            "status": "ready",
            "purpose": "public announcements and financial reports",
        }],
    }


@app.post("/api/evidence/{ticker}/refresh")
def refresh_evidence(ticker: str, request: EvidenceRefreshRequest) -> dict[str, Any]:
    normalized = normalize_ts_code(ticker)
    return refresh_evidence_for_ticker(normalized, request)


@app.get("/api/evidence/{ticker}")
def evidence_list(ticker: str) -> dict[str, Any]:
    normalized = normalize_ts_code(ticker)
    items = sort_evidence_records(load_evidence_index(normalized))
    return {
        "ticker": normalized,
        "items": items,
        "data_gaps": [] if items else ["公告原文数据不足"],
    }


def _find_evidence_item(ticker: str, evidence_id: str) -> dict[str, Any] | None:
    normalized = normalize_ts_code(ticker)
    for row in load_evidence_index(normalized):
        if str(row.get("evidence_id")) == evidence_id:
            return _normalize_evidence_record(row)
    return None


def _load_evidence_pages(item: dict[str, Any]) -> list[str]:
    pages_path = str(item.get("local_pages_path") or "")
    if pages_path:
        try:
            payload = json.loads(Path(pages_path).read_text(encoding="utf-8"))
            pages = payload.get("pages") if isinstance(payload, dict) else None
            if isinstance(pages, list):
                return [str(page) for page in pages]
        except Exception:
            pass
    text_path = str(item.get("local_text_path") or "")
    if text_path:
        try:
            candidate = Path(text_path).resolve()
            candidate.relative_to(evidence_ticker_dir(str(item.get("ticker") or "")).resolve())
            if candidate.is_file():
                return [candidate.read_text(encoding="utf-8")]
        except Exception:
            pass
    return []


def _resolve_evidence_file(ticker: str, evidence_id: str, kind: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{64}", evidence_id):
        raise HTTPException(status_code=400, detail="invalid evidence id")
    ticker_root = evidence_ticker_dir(ticker).resolve()
    if kind == "pdf":
        relative = Path("documents") / f"{evidence_id}.pdf"
    elif kind == "text":
        relative = Path("text") / f"{evidence_id}.txt"
    elif kind == "pages":
        relative = Path("text") / f"{evidence_id}.pages.json"
    else:
        raise HTTPException(status_code=400, detail="invalid evidence kind")
    candidate = (ticker_root / relative).resolve()
    try:
        candidate.relative_to(ticker_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid evidence path") from exc
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="evidence file not found")
    return candidate


@app.get("/api/evidence/{ticker}/{evidence_id}")
def evidence_detail(ticker: str, evidence_id: str) -> dict[str, Any]:
    item = _find_evidence_item(ticker, evidence_id)
    if item is None:
        raise HTTPException(status_code=404, detail="evidence not found")

    result = dict(item)
    text_path = str(result.get("local_text_path") or "")
    if text_path:
        try:
            candidate = Path(text_path).resolve()
            candidate.relative_to(evidence_ticker_dir(ticker).resolve())
            if candidate.is_file():
                result["text_preview"] = candidate.read_text(encoding="utf-8")[:5000]
        except (OSError, UnicodeError, ValueError, HTTPException):
            pass
    result["snippet_pages"] = [
        {"page": snippet.get("page"), "quote": snippet.get("quote")}
        for snippet in (result.get("snippets") or [])
        if isinstance(snippet, dict)
    ]
    return result


@app.get("/api/evidence/{ticker}/{evidence_id}/pdf")
def evidence_pdf(ticker: str, evidence_id: str) -> FileResponse:
    path = _resolve_evidence_file(ticker, evidence_id, "pdf")
    return FileResponse(path, media_type="application/pdf", filename=path.name, content_disposition_type="inline")


@app.get("/api/evidence/{ticker}/{evidence_id}/text")
def evidence_text(ticker: str, evidence_id: str, page: int | None = Query(default=None, ge=1)) -> dict[str, Any]:
    item = _find_evidence_item(ticker, evidence_id)
    if item is None:
        raise HTTPException(status_code=404, detail="evidence not found")
    pages = _load_evidence_pages(item)
    if not pages:
        raise HTTPException(status_code=404, detail="evidence text not found")
    page_count = len(pages)
    if page is not None and page > page_count:
        raise HTTPException(status_code=404, detail="page not found")
    if page is not None:
        text_preview = pages[page - 1][:5000]
    else:
        text_preview = "\n".join(pages)[:5000]
    return {
        "evidence_id": item.get("evidence_id"),
        "ticker": item.get("ticker"),
        "title": item.get("title"),
        "source_url": item.get("url"),
        "source_label": item.get("source_label"),
        "grade": item.get("grade"),
        "page": page,
        "page_count": page_count,
        "text_preview": text_preview,
    }


@app.get("/api/evidence/{ticker}/{evidence_id}/source")
def evidence_source(ticker: str, evidence_id: str) -> dict[str, Any]:
    item = _find_evidence_item(ticker, evidence_id)
    if item is None:
        raise HTTPException(status_code=404, detail="evidence not found")
    pages = _load_evidence_pages(item)
    result = dict(item)
    result["page_count"] = len(pages)
    result["snippet_pages"] = [
        {"page": snippet.get("page"), "quote": snippet.get("quote")}
        for snippet in (result.get("snippets") or [])
        if isinstance(snippet, dict)
    ]
    return result


@app.get("/api/stocks/search")
def stock_search(q: str = Query(min_length=1), limit: int = Query(default=10, ge=1, le=30)) -> dict[str, Any]:
    return {"query": q, "results": search_stocks(q, limit=limit)}


@app.get("/api/snapshots/{ticker}/latest")
def latest_snapshot(ticker: str) -> dict[str, Any]:
    normalized = normalize_ts_code(ticker)
    root = SNAPSHOT_DIR / safe_key(normalized)
    for path in sorted(root.glob("*.json"), reverse=True):
        return json.loads(path.read_text(encoding="utf-8"))
    raise HTTPException(status_code=404, detail="snapshot not found")


@app.post("/api/research/auto")
def create_auto_research(request: AutoResearchRequest) -> dict[str, Any]:
    stock = resolve_stock(request.query, request.ticker)
    snapshot = build_company_snapshot(stock["ts_code"])
    if request.supplemental_materials.strip():
        snapshot["supplemental_materials"] = request.supplemental_materials.strip()
    if request.question.strip():
        snapshot["research_question"] = request.question.strip()
    snapshot_path = save_snapshot(snapshot)
    if not snapshot_has_required_financial_data(snapshot):
        raise HTTPException(
            status_code=503,
            detail={
                "message": "自动深研需要财务和行情数据。请先配置 TUSHARE_TOKEN，或等待后续接入更多公开财报源。",
                "snapshot_path": str(snapshot_path),
                "data_gaps": snapshot.get("data_gaps", []),
            },
        )
    config = _fetch_portal_ai_config()
    payload = _call_ai_with_snapshot(config, request, snapshot)
    report_dict = _validate_report(payload)
    _validate_snapshot_evidence(report_dict, snapshot)
    saved = _save_report_from_snapshot(request, snapshot, report_dict, config.model)
    saved["snapshot_path"] = str(snapshot_path)
    return saved


@app.post("/api/research")
def create_research(request: ResearchRequest) -> dict[str, Any]:
    config = _fetch_portal_ai_config()
    payload = _call_ai(config, request)
    report_dict = _validate_report(payload)
    return _save_report(request, report_dict, config.model)


@app.get("/api/research/history")
def research_history(limit: int = 20) -> dict[str, Any]:
    rows = []
    for path in sorted(RESEARCH_DIR.glob("*/*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        rows.append(_summary(payload))
        if len(rows) >= limit:
            break
    return {"items": rows}


@app.get("/api/research/{research_id}")
def read_research(research_id: str) -> dict[str, Any]:
    return load_research_payload(research_id)


@app.get("/api/research/{research_id}/pdf")
def download_research_pdf(research_id: str) -> Response:
    payload = load_research_payload(research_id)
    pdf = render_research_pdf_bytes(payload)
    filename = safe_pdf_filename(payload)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def search_stocks(query: str, limit: int = 10) -> list[dict[str, Any]]:
    text = query.strip().upper()
    candidates: list[dict[str, Any]] = []
    direct = direct_code_stock(text)
    if direct:
        candidates.append(direct)
    try:
        basics = stock_basic_cache()
    except Exception:
        basics = []
    for row in basics:
        haystack = " ".join(str(row.get(key) or "") for key in ("ts_code", "symbol", "name", "industry", "market", "area")).upper()
        if text in haystack:
            candidates.append({**row, "source": "TuShare stock_basic"})
    dedup: dict[str, dict[str, Any]] = {}
    for item in candidates:
        dedup[item["ts_code"]] = item
    return sorted(dedup.values(), key=lambda item: match_score(text, item), reverse=True)[:limit]


def resolve_stock(query: str, ticker: str = "") -> dict[str, Any]:
    if ticker.strip():
        code = normalize_ts_code(ticker)
        try:
            basics = [row for row in stock_basic_cache() if row.get("ts_code") == code]
        except Exception:
            basics = []
        return basics[0] if basics else {"ts_code": code, "symbol": code[:6], "name": query or code, "industry": "数据不足", "source": "ticker"}
    results = search_stocks(query, limit=5)
    if not results:
        raise HTTPException(status_code=404, detail="未找到股票，请输入更完整的名称或代码")
    return results[0]


def build_company_snapshot(ts_code: str) -> dict[str, Any]:
    failures: list[str] = []
    try:
        stock = first_or_empty([row for row in stock_basic_cache() if row.get("ts_code") == ts_code])
    except Exception:
        stock = {}
    daily = collect_tushare("daily", {"ts_code": ts_code}, "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount", failures, limit=80)
    daily_basic = collect_tushare("daily_basic", {"ts_code": ts_code}, "ts_code,trade_date,close,turnover_rate,volume_ratio,pe,pe_ttm,pb,ps,ps_ttm,total_share,float_share,free_share,total_mv,circ_mv", failures, limit=80)
    income = collect_tushare("income", {"ts_code": ts_code}, "ts_code,ann_date,f_ann_date,end_date,report_type,total_revenue,revenue,operate_profit,total_profit,n_income,n_income_attr_p,ebit,ebitda,basic_eps,diluted_eps", failures, limit=16)
    balance = collect_tushare("balancesheet", {"ts_code": ts_code}, "ts_code,ann_date,f_ann_date,end_date,total_assets,total_liab,total_hldr_eqy_inc_min_int,accounts_receiv,oth_receiv,prepayment,inventories,contract_assets,total_cur_assets,total_cur_liab", failures, limit=16)
    cashflow = collect_tushare("cashflow", {"ts_code": ts_code}, "ts_code,ann_date,f_ann_date,end_date,n_cashflow_act,n_cashflow_inv_act,n_cash_flows_fnc_act,c_fr_sale_sg,st_cash_out_act,free_cashflow", failures, limit=16)
    indicators = collect_tushare("fina_indicator", {"ts_code": ts_code}, "ts_code,ann_date,end_date,eps,dt_eps,total_revenue_ps,revenue_ps,capital_rese_ps,surplus_rese_ps,undist_profit_ps,grossprofit_margin,netprofit_margin,roe,roe_waa,roa,roic,debt_to_assets,current_ratio,quick_ratio,ar_turn,ca_turn,assets_turn,ocfps,or_yoy,netprofit_yoy,q_sales_yoy,q_profit_yoy", failures, limit=16)
    forecast = collect_tushare("forecast", {"ts_code": ts_code}, "ts_code,ann_date,end_date,type,p_change_min,p_change_max,net_profit_min,net_profit_max,last_parent_net,summary,change_reason", failures, limit=8)
    dividend = collect_tushare("dividend", {"ts_code": ts_code}, "ts_code,end_date,ann_date,div_proc,stk_div,stk_bo_rate,stk_co_rate,cash_div,cash_div_tax,record_date,ex_date,pay_date", failures, limit=8)
    pledge = collect_tushare("pledge_stat", {"ts_code": ts_code}, "ts_code,end_date,pledge_count,unrest_pledge,rest_pledge,total_share,pledge_ratio", failures, limit=8)
    quote = sina_quote(ts_code)
    derived = derive_research_metrics(income, balance, cashflow, indicators, daily_basic)
    evidence_library = build_evidence_library(ts_code, refresh=True, limit=20, days=720)
    snapshot = {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ticker": ts_code,
        "stock": stock or {"ts_code": ts_code, "name": ts_code, "industry": "数据不足"},
        "sources": data_source_status(),
        "quote": quote,
        "market": {"daily": daily[:10], "daily_basic": daily_basic[:10]},
        "financials": {"income": income[:8], "balance": balance[:8], "cashflow": cashflow[:8], "indicators": indicators[:8], "forecast": forecast[:5], "dividend": dividend[:5], "pledge": pledge[:5]},
        "derived": derived,
        "evidence_library": evidence_library,
        "data_gaps": failures,
        "research_frame": {
            "basic_questions": ["公司靠什么赚钱", "收入来自哪里", "客户是谁", "壁垒是什么", "最大约束是什么"],
            "contradiction_questions": ["政策需求是否转订单", "订单是否转收入", "收入是否转利润", "利润是否转现金流", "减值是出清还是长期问题"],
            "tracking_triggers": ["新订单连续恢复", "经营现金流持续为正", "应收账款/合同资产下降", "毛利率修复", "减值减少", "政策进入地方预算"],
        },
    }
    snapshot["financial_traceability"] = build_financial_traceability(snapshot)
    snapshot["evidence_digest"] = build_evidence_digest(snapshot)
    return snapshot


def derive_research_metrics(income: list[dict[str, Any]], balance: list[dict[str, Any]], cashflow: list[dict[str, Any]], indicators: list[dict[str, Any]], daily_basic: list[dict[str, Any]]) -> dict[str, Any]:
    latest_income = first_or_empty(income)
    latest_balance = first_or_empty(balance)
    latest_cashflow = first_or_empty(cashflow)
    latest_indicator = first_or_empty(indicators)
    latest_daily_basic = first_or_empty(daily_basic)
    revenue = num(latest_income.get("revenue") or latest_income.get("total_revenue"))
    profit = num(latest_income.get("n_income_attr_p") or latest_income.get("n_income"))
    ocf = num(latest_cashflow.get("n_cashflow_act"))
    ar = num(latest_balance.get("accounts_receiv"))
    contract_assets = num(latest_balance.get("contract_assets"))
    inventory = num(latest_balance.get("inventories"))
    anomalies: list[dict[str, Any]] = []
    if revenue and profit is not None:
        anomalies.append({"item": "利润/收入", "observation": f"收入 {fmt_yi(revenue)}，归母净利润 {fmt_yi(profit)}", "implication": "判断收入是否真正转化为利润"})
    if profit and ocf is not None:
        diff = ocf - profit
        anomalies.append({"item": "经营现金流/利润", "observation": f"经营现金流 {fmt_yi(ocf)}，与利润差额 {fmt_yi(diff)}", "implication": "现金流显著弱于利润时需核实回款和应收"})
    if revenue and (ar or contract_assets):
        ratio = ((ar or 0) + (contract_assets or 0)) / revenue * 100
        anomalies.append({"item": "应收和合同资产/收入", "observation": f"占收入 {ratio:.1f}%", "implication": "比例偏高时，订单质量和回款是核心矛盾"})
    if revenue and inventory:
        anomalies.append({"item": "存货/收入", "observation": f"存货约 {fmt_yi(inventory)}", "implication": "存货变化用于观察项目交付和需求节奏"})
    yoy = {key: latest_indicator.get(key) for key in ("or_yoy", "netprofit_yoy", "q_sales_yoy", "q_profit_yoy") if latest_indicator.get(key) not in (None, "")}
    return {
        "latest_period": latest_income.get("end_date") or latest_indicator.get("end_date") or "数据不足",
        "valuation": {"pe_ttm": latest_daily_basic.get("pe_ttm"), "pb": latest_daily_basic.get("pb"), "total_mv": latest_daily_basic.get("total_mv"), "circ_mv": latest_daily_basic.get("circ_mv")},
        "profitability": {"grossprofit_margin": latest_indicator.get("grossprofit_margin"), "netprofit_margin": latest_indicator.get("netprofit_margin"), "roe": latest_indicator.get("roe") or latest_indicator.get("roe_waa"), "roic": latest_indicator.get("roic")},
        "growth": yoy,
        "balance_quality": {"accounts_receiv": ar, "contract_assets": contract_assets, "inventories": inventory, "debt_to_assets": latest_indicator.get("debt_to_assets")},
        "cashflow": {"n_cashflow_act": ocf, "ocfps": latest_indicator.get("ocfps")},
        "anomalies": anomalies,
    }


def snapshot_has_required_financial_data(snapshot: dict[str, Any]) -> bool:
    financials = snapshot.get("financials") or {}
    market = snapshot.get("market") or {}
    required_groups = ("income", "balance", "cashflow", "indicators")
    has_financials = any(financials.get(group) for group in required_groups)
    has_market = bool(market.get("daily") or market.get("daily_basic") or snapshot.get("quote", {}).get("price"))
    return has_financials and has_market


def save_snapshot(snapshot: dict[str, Any]) -> Path:
    ticker = snapshot["ticker"]
    day = datetime.now(timezone.utc).date().isoformat()
    root = SNAPSHOT_DIR / safe_key(ticker)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{day}.json"
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def classify_announcement(title: str) -> str:
    text = str(title or "").lower()
    categories = (
        ("semiannual_report", ("半年度报告", "中报", "半年报")),
        ("annual_report", ("年度报告", "年报")),
        ("quarterly_report", ("季度报告", "一季度", "二季度", "三季度", "四季度", "季度")),
        ("forecast", ("业绩预告", "业绩快报", "盈利预测", "业绩预增", "预亏")),
        ("contract", ("合同", "签订协议", "中标", "重大项目")),
        ("pledge", ("质押", "解押", "解除质押")),
        ("risk", ("风险", "问询函", "监管函", "立案", "诉讼")),
    )
    for category, keywords in categories:
        if any(keyword in text for keyword in keywords):
            return category
    return "other"


CNINFO_SEARCH_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
CNINFO_STATIC_URL = "https://static.cninfo.com.cn/"
CNINFO_STOCK_LIST_URL = "https://www.cninfo.com.cn/new/data/szse_stock.json"


def _cninfo_title(value: Any) -> str:
    text = unescape(str(value or ""))
    return re.sub(r"<[^>]*>", "", text).strip()


def _cninfo_date(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 100000000000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat()
    text = str(value).strip()
    match = re.search(r"(\d{4})[-/]?(\d{2})[-/]?(\d{2})", text)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return text


def parse_cninfo_announcements(payload: dict[str, Any], ticker: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in payload.get("announcements") or []:
        if not isinstance(item, dict):
            continue
        title = _cninfo_title(item.get("announcementTitle") or item.get("title"))
        announcement_date = _cninfo_date(item.get("announcementTime") or item.get("announcementDate"))
        adjunct_url = str(item.get("adjunctUrl") or item.get("url") or "").strip()
        url = adjunct_url if adjunct_url.startswith("http") else f"{CNINFO_STATIC_URL}{adjunct_url.lstrip('/')}"
        meta = {"source": "cninfo", "ticker": ticker, "title": title, "date": announcement_date, "url": url}
        rows.append(
            EvidenceRecord(
                evidence_id=evidence_id_for(meta),
                ticker=ticker,
                title=title,
                announcement_date=announcement_date,
                category=classify_announcement(title),
                url=url,
                source_label="CNINFO 公告原文",
            ).model_dump(mode="json")
        )
    return rows


def cninfo_column_for_ticker(ticker: str) -> str:
    _, exchange = normalize_ts_code(ticker).split(".")
    columns = {"SH": "sse", "SZ": "szse", "BJ": "bse"}
    return columns[exchange]


def cninfo_stock_list_cache() -> list[dict[str, Any]]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / "cninfo_stock_list.json"
    if path.exists() and path.stat().st_size > 0:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            items = payload.get("items")
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
        except Exception:
            pass
    headers = {"Referer": "https://www.cninfo.com.cn/", "User-Agent": "Yanqing/1.0 (public CNINFO adapter)"}
    with httpx.Client(timeout=12) as client:
        response = client.get(CNINFO_STOCK_LIST_URL, headers=headers)
        response.raise_for_status()
        payload = response.json()
    rows = [item for item in payload.get("stockList") or [] if isinstance(item, dict)]
    path.write_text(json.dumps({"updated_at": datetime.now(timezone.utc).isoformat(), "items": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    return rows


def cninfo_org_id_for_ticker(ticker: str) -> str:
    code, _ = normalize_ts_code(ticker).split(".")
    try:
        for row in cninfo_stock_list_cache():
            if str(row.get("code") or "") == code and row.get("orgId"):
                return str(row["orgId"])
    except Exception:
        return ""
    return ""


def cninfo_stock_parameter(ticker: str) -> str:
    code, _ = normalize_ts_code(ticker).split(".")
    org_id = cninfo_org_id_for_ticker(ticker)
    return f"{code},{org_id}" if org_id else code


def search_cninfo_announcements(ticker: str, limit: int, days: int) -> list[dict[str, Any]]:
    bounded_limit = min(50, max(1, int(limit)))
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=max(1, int(days)))
    params = {
        "pageNum": 1,
        "pageSize": bounded_limit,
        "column": cninfo_column_for_ticker(ticker),
        "tabName": "fulltext",
        "plate": "",
        "stock": cninfo_stock_parameter(ticker),
        "searchkey": "",
        "secid": "",
        "category": "",
        "trade": "",
        "seDate": f"{start.isoformat()}~{today.isoformat()}",
    }
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "User-Agent": "Yanqing/1.0 (public CNINFO adapter)",
    }
    with httpx.Client(timeout=12) as client:
        response = client.post(CNINFO_SEARCH_URL, data=params, headers=headers)
        response.raise_for_status()
        payload = response.json()
    return parse_cninfo_announcements(payload, ticker)[:bounded_limit]


def download_cninfo_pdf(record: dict[str, Any]) -> dict[str, Any]:
    updated = dict(record)
    try:
        ticker = str(updated["ticker"])
        evidence_id = str(updated["evidence_id"])
        url = str(updated["url"])
        if not re.fullmatch(r"[0-9a-f]{64}", evidence_id):
            raise ValueError("invalid evidence id")
        parsed_url = urlparse(url)
        if parsed_url.scheme.lower() != "https" or parsed_url.hostname != "static.cninfo.com.cn":
            raise ValueError("unsupported evidence URL")
        ticker_dir = evidence_ticker_dir(ticker).resolve()
        documents_dir = ticker_dir / "documents"
        documents_dir.mkdir(parents=True, exist_ok=True)
        documents_dir = documents_dir.resolve()
        try:
            documents_dir.relative_to(ticker_dir)
        except ValueError as exc:
            raise ValueError("invalid evidence documents directory") from exc
        destination = (documents_dir / f"{evidence_id}.pdf").resolve()
        try:
            destination.relative_to(documents_dir)
        except ValueError as exc:
            raise ValueError("invalid evidence destination") from exc
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            final_url = urlparse(str(response.url))
            if final_url.scheme.lower() != "https" or final_url.hostname != "static.cninfo.com.cn":
                raise ValueError("unsupported redirected evidence URL")
            destination.write_bytes(response.content)
        updated["local_pdf_path"] = str(destination)
        updated["download_status"] = "downloaded"
    except Exception:
        updated["download_status"] = "failed"
        gaps = list(updated.get("data_gaps") or [])
        gap = _data_gap("公告PDF下载失败")
        if gap not in gaps:
            gaps.append(gap)
        updated["data_gaps"] = gaps
    return updated


def extract_pdf_text_pages(pdf_path: Path) -> tuple[list[str], str]:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        pages = [page.extract_text() or "" for page in reader.pages]
        return pages, "ready"
    except Exception:
        return [], "failed"


def extract_pdf_text(pdf_path: Path) -> tuple[str, str]:
    pages, status = extract_pdf_text_pages(pdf_path)
    if status != "ready":
        return "", status
    return "\n".join(pages)[:120000], "ready"


def build_evidence_snippets(text: str, title: str, limit: int = 3, pages: list[str] | None = None) -> list[dict[str, Any]]:
    bounded_limit = max(0, int(limit))
    if not bounded_limit:
        return []
    keywords = (
        "营业收入",
        "净利润",
        "经营现金流",
        "合同",
        "订单",
        "中标",
        "质押",
        "风险",
        "诉讼",
        "监管",
    )
    if pages:
        candidates: list[tuple[int, str]] = []
        for page_index, page_text in enumerate(pages, start=1):
            for part in re.split(r"[。！？!?；;\n\r]+", str(page_text or "")):
                sentence = part.strip()
                if sentence:
                    candidates.append((page_index, sentence))
        ranked = sorted(
            enumerate(candidates),
            key=lambda item: (sum(keyword in item[1][1] for keyword in keywords), -item[0]),
            reverse=True,
        )
    else:
        sentences = [part.strip() for part in re.split(r"[。！？!?；;\n\r]+", str(text or "")) if part.strip()]
        ranked = sorted(
            enumerate(sentences),
            key=lambda item: (sum(keyword in item[1] for keyword in keywords), -item[0]),
            reverse=True,
        )
    snippets: list[dict[str, Any]] = []
    for rank_item in ranked[:bounded_limit]:
        if pages:
            page_number, sentence = rank_item[1]
        else:
            page_number, sentence = None, rank_item[1]
        quote = sentence[:239]
        snippets.append({
            "quote": quote,
            "note": f"{title.strip() or '公告'}中的研究关键词句",
            "page": page_number,
        })
    return snippets


def summarize_evidence_library(items: list[dict[str, Any]]) -> dict[str, Any]:
    summary_items = [item for item in items if isinstance(item, dict)]
    snippet_count = 0
    downloaded_count = 0
    extracted_count = 0
    text_length = 0
    latest_announcement_date = ""
    category_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    grade_counts: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0}
    data_gaps: list[str] = []

    for item in summary_items:
        snippets = item.get("snippets") if isinstance(item.get("snippets"), list) else []
        snippet_count += len([snippet for snippet in snippets if isinstance(snippet, dict)])
        if item.get("download_status") == "downloaded":
            downloaded_count += 1
        if item.get("text_extract_status") == "ready":
            extracted_count += 1
        text_length += _evidence_item_text_length(item)

        announcement_date = str(item.get("announcement_date") or "")
        if announcement_date and announcement_date > latest_announcement_date:
            latest_announcement_date = announcement_date

        category = str(item.get("category") or "other")
        category_counts[category] = category_counts.get(category, 0) + 1
        source_label = str(item.get("source_label") or item.get("source") or "cninfo")
        source_counts[source_label] = source_counts.get(source_label, 0) + 1

        grade = str(item.get("grade") or "").strip()
        if not grade or grade == EvidenceGrade.D.value:
            grade, _ = grade_evidence_record(item)
        grade_counts[grade] = grade_counts.get(grade, 0) + 1

        for gap in item.get("data_gaps") or []:
            gap_text = str(gap).strip()
            if gap_text and gap_text not in data_gaps:
                data_gaps.append(gap_text)

    return {
        "total_items": len(summary_items),
        "downloaded_count": downloaded_count,
        "extracted_count": extracted_count,
        "snippet_count": snippet_count,
        "text_length": text_length,
        "latest_announcement_date": latest_announcement_date,
        "grade_summary": grade_counts,
        "category_counts": category_counts,
        "source_counts": source_counts,
        "data_gaps": data_gaps,
    }


def _evidence_item_text_length(item: dict[str, Any]) -> int:
    text_length = item.get("text_length")
    if isinstance(text_length, int) and text_length >= 0:
        return text_length
    try:
        path = Path(str(item.get("local_text_path") or ""))
        if path.is_file():
            return len(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    snippets = item.get("snippets")
    if isinstance(snippets, list):
        return sum(len(str(snippet.get("quote") or "")) for snippet in snippets if isinstance(snippet, dict))
    return 0


def _normalize_evidence_record(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    normalized["source_label"] = str(normalized.get("source_label") or normalized.get("source") or "CNINFO 公告原文")
    category = str(normalized.get("category") or "other")
    if not str(normalized.get("source_type") or "").strip():
        normalized["source_type"] = source_type_for_category(category)
    current_grade = str(normalized.get("grade") or "").strip()
    if not current_grade or current_grade == EvidenceGrade.D.value:
        normalized["grade"], normalized["confidence"] = grade_evidence_record(normalized)
    elif not str(normalized.get("confidence") or "").strip():
        _, normalized["confidence"] = grade_evidence_record(normalized)
    if not str(normalized.get("file_name") or "").strip():
        local_pdf_path = str(normalized.get("local_pdf_path") or "")
        normalized["file_name"] = Path(local_pdf_path).name if local_pdf_path else ""
    normalized.setdefault("retrieved_at", "")
    normalized.setdefault("local_pages_path", "")
    snippets = normalized.get("snippets")
    if isinstance(snippets, list):
        normalized["snippet_count"] = sum(1 for snippet in snippets if isinstance(snippet, dict))
        enriched_snippets = []
        for snippet in snippets:
            if not isinstance(snippet, dict):
                enriched_snippets.append(snippet)
                continue
            item_snippet = dict(snippet)
            item_snippet["source_url"] = str(item_snippet.get("source_url") or normalized.get("url") or "")
            item_snippet["source_date"] = str(item_snippet.get("source_date") or normalized.get("announcement_date") or "")
            if not str(item_snippet.get("grade") or "").strip():
                item_snippet["grade"] = normalized.get("grade") or EvidenceGrade.D.value
            if not str(item_snippet.get("confidence") or "").strip():
                item_snippet["confidence"] = confidence_for_evidence(normalized, item_snippet)
            item_snippet["page_label"] = str(item_snippet.get("page_label") or ("第{}页".format(item_snippet["page"]) if item_snippet.get("page") is not None else ""))
            enriched_snippets.append(item_snippet)
        normalized["snippets"] = enriched_snippets
    elif not isinstance(normalized.get("snippet_count"), int):
        normalized["snippet_count"] = 0
    if not isinstance(normalized.get("text_length"), int):
        normalized["text_length"] = _evidence_item_text_length(normalized)
    return normalized


def evidence_id_for(meta: dict[str, Any]) -> str:
    payload = json.dumps(meta, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def evidence_ticker_dir(ticker: str) -> Path:
    raw_ticker = str(ticker or "")
    normalized = safe_key(raw_ticker)
    normalized = normalized.replace("\\", "_").replace("/", "_").replace(":", "_")
    normalized = re.sub(r"\.{2,}", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("._")
    suspicious = any(separator in raw_ticker for separator in ("/", "\\", ":")) or any(
        component == ".." for component in re.split(r"[\\/]", raw_ticker)
    )
    if suspicious or not normalized:
        raise HTTPException(status_code=422, detail="invalid evidence ticker")

    evidence_root = EVIDENCE_DIR.resolve()
    candidate = (evidence_root / normalized).resolve()
    try:
        candidate.relative_to(evidence_root)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="invalid evidence ticker") from exc
    return candidate


def load_evidence_index(ticker: str) -> list[dict[str, Any]]:
    path = evidence_ticker_dir(ticker) / "index.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = payload.get("items")
        return sort_evidence_records(items) if isinstance(items, list) and all(isinstance(item, dict) for item in items) else []
    except (OSError, TypeError, ValueError, AttributeError):
        return []


def save_evidence_index(ticker: str, records: list[dict[str, Any]]) -> None:
    root = evidence_ticker_dir(ticker)
    root.mkdir(parents=True, exist_ok=True)
    payload = {"updated_at": datetime.now(timezone.utc).isoformat(), "items": sort_evidence_records(records)}
    (root / "index.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def sort_evidence_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(records, key=lambda item: str(item.get("announcement_date") or ""), reverse=True)


def merge_evidence_records(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = {str(item.get("evidence_id")): item for item in existing if item.get("evidence_id")}
    merged.update({str(item.get("evidence_id")): item for item in incoming if item.get("evidence_id")})
    return sort_evidence_records(list(merged.values()))


def refresh_evidence_for_ticker(ticker: str, request: EvidenceRefreshRequest) -> dict[str, Any]:
    normalized = normalize_ts_code(ticker)
    existing = load_evidence_index(normalized)
    data_gaps: list[str] = []
    incoming: list[dict[str, Any]] = []
    try:
        incoming = search_cninfo_announcements(normalized, limit=request.limit, days=request.days)
    except Exception:
        data_gaps.append(_data_gap("CNINFO公告搜索失败"))

    refreshed_items: list[dict[str, Any]] = []
    for item in incoming:
        current = dict(item)
        if request.download:
            try:
                downloaded = download_cninfo_pdf(current)
                if isinstance(downloaded, dict):
                    current = downloaded
            except Exception:
                current["download_status"] = "failed"
                gaps = list(current.get("data_gaps") or [])
                gap = _data_gap("公告PDF下载失败")
                if gap not in gaps:
                    gaps.append(gap)
                current["data_gaps"] = gaps
        if request.extract_text and current.get("download_status") == "downloaded":
            try:
                pdf_path = Path(str(current.get("local_pdf_path") or ""))
                pages, status = extract_pdf_text_pages(pdf_path) if pdf_path.is_file() else ([], "failed")
                if status == "ready":
                    evidence_id = str(current.get("evidence_id") or "")
                    if not re.fullmatch(r"[0-9a-f]{64}", evidence_id):
                        raise ValueError("invalid evidence id")
                    ticker_root = evidence_ticker_dir(normalized).resolve()
                    text_dir = ticker_root / "text"
                    text_dir.mkdir(parents=True, exist_ok=True)
                    resolved_text_dir = text_dir.resolve()
                    resolved_text_dir.relative_to(ticker_root)
                    text_path = (resolved_text_dir / f"{evidence_id}.txt").resolve()
                    text_path.relative_to(resolved_text_dir)
                    pages_path = (resolved_text_dir / f"{evidence_id}.pages.json").resolve()
                    pages_path.relative_to(resolved_text_dir)
                    text = "\n".join(pages)[:120000]
                    text_path.write_text(text, encoding="utf-8")
                    pages_path.write_text(json.dumps({"pages": pages}, ensure_ascii=False), encoding="utf-8")
                    current["local_text_path"] = str(text_path)
                    current["local_pages_path"] = str(pages_path)
                    current["snippets"] = build_evidence_snippets(text, str(current.get("title") or ""), pages=pages)
                    current["snippet_count"] = len(current.get("snippets") or [])
                    current["text_length"] = len(text)
                    current["text_extract_status"] = "ready"
                else:
                    current["text_extract_status"] = "failed"
                    raise ValueError("PDF text extraction failed")
            except Exception:
                current["text_extract_status"] = "failed"
                gaps = list(current.get("data_gaps") or [])
                gap = _data_gap("公告PDF文本提取失败")
                if gap not in gaps:
                    gaps.append(gap)
                current["data_gaps"] = gaps
        refreshed_items.append(_normalize_evidence_record(current))

    merged = merge_evidence_records(existing, refreshed_items)
    save_evidence_index(normalized, merged)
    for item in refreshed_items:
        data_gaps.extend(str(gap) for gap in item.get("data_gaps") or [] if str(gap) not in data_gaps)
    gap = _data_gap("公告原文数据不足")
    if not merged and gap not in data_gaps:
        data_gaps.append(gap)
    return {
        "ticker": normalized,
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
        "items": merged,
        "data_gaps": data_gaps,
    }


def build_evidence_library(ticker: str, refresh: bool = True, limit: int = 20, days: int = 720) -> dict[str, Any]:
    refresh_gaps: list[str] = []
    if refresh:
        try:
            refresh_result = refresh_evidence_for_ticker(
                ticker,
                EvidenceRefreshRequest(limit=limit, days=days, download=True, extract_text=True),
            )
            refresh_gaps.extend(str(gap) for gap in refresh_result.get("data_gaps") or [])
        except Exception:
            refresh_gaps.append(_data_gap("公告原文刷新失败"))
    items = [_normalize_evidence_record(item) for item in sort_evidence_records(load_evidence_index(ticker))]
    refresh_gaps = list(dict.fromkeys(_data_gap(str(gap)) for gap in refresh_gaps if str(gap).strip()))
    library = EvidenceLibrary(
        status="ready" if items and not refresh_gaps else ("limited" if items else "insufficient"),
        items=items[:limit],
        data_gaps=refresh_gaps if items else list(dict.fromkeys(refresh_gaps + [_data_gap("公告原文数据不足")])),
        summary=summarize_evidence_library(items[:limit]),
    )
    return library.model_dump(mode="json")


EVIDENCE_DIGEST_TOPICS = (
    ("revenue", "收入", ("营业收入", "收入", "营收")),
    ("profit", "利润", ("净利润", "利润", "毛利率", "净利率")),
    ("cashflow", "经营现金流", ("经营现金流", "现金流", "回款")),
    ("receivables", "应收与合同资产", ("应收账款", "合同资产", "回款")),
    ("impairment", "减值", ("减值", "坏账", "信用损失")),
    ("inventory", "存货", ("存货", "库存")),
    ("orders", "订单/合同", ("订单", "合同", "中标", "重大项目")),
    ("policy", "政策传导", ("政策", "预算", "专项债", "住建", "发改")),
    ("risk", "风险/监管", ("风险", "诉讼", "监管", "问询", "处罚")),
    ("legal", "法律意见", ("法律意见书", "律师", "合规", "发行股票")),
)


def build_evidence_digest(snapshot: dict[str, Any]) -> dict[str, Any]:
    library = snapshot.get("evidence_library") or {}
    items = library.get("items") if isinstance(library, dict) else []
    items = items if isinstance(items, list) else []
    digest_items: list[dict[str, Any]] = []

    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "")
        snippets = [s for s in (item.get("snippets") or []) if isinstance(s, dict)]
        text_chunks = [(title, None)] + [(str(s.get("quote") or ""), s) for s in snippets]
        for chunk, source_snippet in text_chunks:
            if not chunk:
                continue
            topics = evidence_topics_for_text(chunk)
            if not topics:
                continue
            for topic, label in topics:
                digest_items.append({
                    "topic": topic,
                    "label": label,
                    "source": title or "公告原文",
                    "quote": chunk[:240],
                    "evidence_id": str(item.get("evidence_id") or ""),
                    "date": str(item.get("announcement_date") or ""),
                    "category": str(item.get("category") or "other"),
                    "source_type": str(item.get("source_type") or source_type_for_category(item.get("category") or "")),
                    "grade": str(item.get("grade") or EvidenceGrade.D.value),
                    "confidence": str(item.get("confidence") or "low"),
                    "page": source_snippet.get("page") if source_snippet and source_snippet.get("page") is not None else None,
                })

    financial_facts = build_financial_digest_facts(snapshot)
    digest_topics = {str(item.get("topic")) for item in digest_items}
    open_questions = build_digest_open_questions(digest_topics, financial_facts)
    data_gaps = list(library.get("data_gaps") or []) if isinstance(library, dict) else []
    data_gaps.extend(question for question in open_questions if "数据不足" in question)
    deduped_items = dedupe_digest_items(digest_items)
    status = "ready" if deduped_items or financial_facts else ("limited" if items else "insufficient")
    return {
        "status": status,
        "items": deduped_items[:30],
        "financial_facts": financial_facts,
        "open_questions": open_questions,
        "data_gaps": list(dict.fromkeys(str(gap) for gap in data_gaps if str(gap).strip())),
    }


def evidence_topics_for_text(text: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for topic, label, keywords in EVIDENCE_DIGEST_TOPICS:
        if any(keyword in text for keyword in keywords):
            found.append((topic, label))
    return found


def dedupe_digest_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in items:
        key = (str(item.get("topic") or ""), str(item.get("source") or ""), str(item.get("quote") or ""))
        if key[0] and key[2]:
            deduped[key] = item
    return list(deduped.values())


def build_financial_digest_facts(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    derived = snapshot.get("derived") if isinstance(snapshot.get("derived"), dict) else {}
    facts: list[dict[str, str]] = []
    latest_period = str(derived.get("latest_period") or "数据不足")
    cashflow = derived.get("cashflow") if isinstance(derived.get("cashflow"), dict) else {}
    balance_quality = derived.get("balance_quality") if isinstance(derived.get("balance_quality"), dict) else {}
    valuation = derived.get("valuation") if isinstance(derived.get("valuation"), dict) else {}
    profitability = derived.get("profitability") if isinstance(derived.get("profitability"), dict) else {}

    cash_obs = compact_kv(cashflow, ("n_cashflow_act", "ocfps"))
    if cash_obs:
        facts.append({"topic": "cashflow", "label": "经营现金流", "period": latest_period, "observation": cash_obs})
    balance_obs = compact_kv(balance_quality, ("accounts_receiv", "contract_assets", "inventories", "debt_to_assets"))
    if balance_obs:
        facts.append({"topic": "receivables", "label": "资产质量", "period": latest_period, "observation": balance_obs})
    valuation_obs = compact_kv(valuation, ("pe_ttm", "pb", "total_mv", "circ_mv"))
    if valuation_obs:
        facts.append({"topic": "valuation", "label": "估值", "period": latest_period, "observation": valuation_obs})
    profit_obs = compact_kv(profitability, ("grossprofit_margin", "netprofit_margin", "roe", "roic"))
    if profit_obs:
        facts.append({"topic": "profit", "label": "盈利质量", "period": latest_period, "observation": profit_obs})
    return facts


FINANCIAL_SOURCE_LABELS = {"income": "利润表", "balance": "资产负债表", "cashflow": "现金流量表", "indicators": "财务指标", "valuation": "行情估值"}
FINANCIAL_FIELD_LABELS = {
    "revenue": "营业收入",
    "total_revenue": "营业总收入",
    "n_income": "净利润",
    "n_income_attr_p": "归母净利润",
    "n_cashflow_act": "经营现金流净额",
    "ocfps": "每股经营现金流",
    "accounts_receiv": "应收账款",
    "contract_assets": "合同资产",
    "inventories": "存货",
    "debt_to_assets": "资产负债率",
    "grossprofit_margin": "毛利率",
    "netprofit_margin": "净利率",
    "roe": "ROE",
    "roic": "ROIC",
    "pe_ttm": "PE TTM",
    "pb": "PB",
    "total_mv": "总市值",
    "circ_mv": "流通市值",
    "or_yoy": "营业收入同比",
    "netprofit_yoy": "净利润同比",
    "q_sales_yoy": "单季收入同比",
    "q_profit_yoy": "单季利润同比",
}


FINANCIAL_TRACE_FIELDS = (
    ("revenue", "营业收入", "income", "revenue", "收入修复是判断基本盘是否改善的第一层证据。", "收入需要继续与利润、回款和订单证据交叉验证。"),
    ("net_profit", "归母净利润", "income", "n_income_attr_p", "利润能否修复决定收入增长是否有质量。", "若收入恢复但利润仍弱，需追踪毛利率、费用率和减值。"),
    ("operating_cash_flow", "经营现金流净额", "cashflow", "n_cashflow_act", "经营现金流验证利润是否转化为真实回款。", "若现金流弱于利润，需重点核实应收、合同资产和回款节奏。"),
    ("accounts_receiv", "应收账款", "balance", "accounts_receiv", "应收账款反映收入确认后的回款压力。", "应收相对收入偏高时，需关注坏账、客户质量和账龄结构。"),
    ("contract_assets", "合同资产", "balance", "contract_assets", "合同资产用于观察项目确认、验收和回款链条。", "合同资产增长需要结合订单、验收和收款条款核实。"),
    ("inventory", "存货", "balance", "inventories", "存货变化反映备货、项目交付和需求节奏。", "存货高企或周转变慢时，需关注跌价和需求兑现。"),
    ("gross_margin", "毛利率", "indicators", "grossprofit_margin", "毛利率是收入质量和竞争格局变化的直观指标。", "毛利率修复若缺少订单结构支撑，仍需谨慎验证。"),
    ("net_margin", "净利率", "indicators", "netprofit_margin", "净利率体现费用、减值和经营效率后的利润质量。", "净利率偏弱时，需要拆费用率和减值。"),
    ("roe", "ROE", "indicators", "roe", "ROE衡量股东资本回报质量。", "ROE下行时，需判断是利润弱、资产周转慢还是杠杆变化。"),
    ("roic", "ROIC", "indicators", "roic", "ROIC观察经营资产投入后的回报能力。", "ROIC不足时，需结合产能、项目周期和资本开支核实。"),
    ("impairment", "减值损失", "income", "asset_impair_loss", "减值决定利润下滑是一次性出清还是结构性风险。", "数据不足：当前快照未采集该字段，需接入财报原文字段或补充 TuShare 减值字段。"),
)


def _first_financial_row(snapshot: dict[str, Any], group: str) -> dict[str, Any]:
    financials = snapshot.get("financials") if isinstance(snapshot.get("financials"), dict) else {}
    rows = financials.get(group) if isinstance(financials.get(group), list) else []
    return first_or_empty(rows)


def _financial_trace_item(snapshot: dict[str, Any], field: tuple[str, str, str, str, str, str]) -> dict[str, Any]:
    field_key, label, group, source_field, interpretation, risk = field
    row = _first_financial_row(snapshot, group)
    value = row.get(source_field)
    period = str(row.get("end_date") or row.get("ann_date") or "数据不足")
    has_value = value not in (None, "")
    return {
        "field_key": field_key,
        "label": label,
        "period": period if has_value else "数据不足",
        "value": value if has_value else "数据不足",
        "unit": "%" if field_key in {"gross_margin", "net_margin", "roe", "roic"} else "元",
        "source": f"tushare.{group}.{source_field}",
        "source_label": f"TuShare {FINANCIAL_SOURCE_LABELS.get(group, group)} / {label}",
        "data_status": "ready" if has_value else "insufficient",
        "interpretation": interpretation if has_value else f"{label}数据不足：当前快照未提供可追溯字段值。",
        "risk": risk,
    }


def build_financial_traceability(snapshot: dict[str, Any]) -> dict[str, Any]:
    items = [_financial_trace_item(snapshot, field) for field in FINANCIAL_TRACE_FIELDS]
    ready_count = sum(1 for item in items if item["data_status"] == "ready")
    data_gaps = [f"{item['label']}数据不足" for item in items if item["data_status"] != "ready"]
    return {
        "status": "ready" if ready_count >= 4 else ("limited" if ready_count else "insufficient"),
        "items": items,
        "data_gaps": data_gaps,
    }


def compact_kv(payload: dict[str, Any], keys: tuple[str, ...]) -> str:
    parts = []
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            parts.append(f"{FINANCIAL_FIELD_LABELS.get(key, key)}: {value}")
    return "；".join(parts)


def build_digest_open_questions(topics: set[str], financial_facts: list[dict[str, str]]) -> list[str]:
    questions = []
    if "orders" not in topics:
        questions.append("订单数据不足：当前公告原文未提供可追溯订单/合同/中标证据。")
    if "policy" not in topics:
        questions.append("政策数据不足：当前证据库未提供可追溯政策落地证据。")
    if "receivables" in topics or any(fact.get("topic") == "receivables" for fact in financial_facts):
        questions.append("继续核实应收账款、合同资产与回款节奏是否匹配收入确认。")
    if "cashflow" in topics or any(fact.get("topic") == "cashflow" for fact in financial_facts):
        questions.append("继续核实经营现金流是否持续修复。")
    return questions


def _fetch_portal_ai_config() -> PortalAiConfig:
    url = os.getenv("PORTAL_AI_CONFIG_URL", "http://portal_frontend:3000/internal/ai-config")
    token = os.getenv("PORTAL_INTERNAL_TOKEN", "").strip()
    if not token:
        raise HTTPException(status_code=503, detail="PORTAL_INTERNAL_TOKEN is required")
    try:
        with httpx.Client(timeout=10) as client:
            response = client.get(url, headers={"X-Internal-Token": token})
            response.raise_for_status()
            config = PortalAiConfig.model_validate(response.json())
    except Exception as exc:
        raise HTTPException(status_code=503, detail="portal AI config unavailable") from exc
    if not config.enabled:
        raise HTTPException(status_code=503, detail="portal AI config is disabled")
    if not config.baseUrl or not config.apiKey or not config.model:
        raise HTTPException(status_code=503, detail="portal AI config is incomplete")
    return config


def _call_ai(config: PortalAiConfig, request: ResearchRequest) -> dict[str, Any]:
    return _call_ai_messages(config, _manual_messages(request))


def _call_ai_with_snapshot(config: PortalAiConfig, request: AutoResearchRequest, snapshot: dict[str, Any]) -> dict[str, Any]:
    return _call_ai_messages(config, _snapshot_messages(request, snapshot))


def _call_ai_messages(config: PortalAiConfig, messages: list[dict[str, str]]) -> dict[str, Any]:
    base = config.baseUrl.rstrip("/")
    try:
        with httpx.Client(timeout=max(5, config.timeoutSeconds)) as client:
            response = client.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {config.apiKey}", "Content-Type": "application/json"},
                json={"model": config.model, "messages": messages, "temperature": 0.2, "max_tokens": 3000},
            )
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            return json.loads(_strip_json_fence(content))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="AI response is not valid JSON") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="AI research request failed") from exc


def _validate_report(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        report = ResearchReport.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="AI output schema validation failed") from exc
    report_dict = report.model_dump(mode="json")
    _sanitize_trade_instructions(report_dict)
    report_dict["contradiction_matrix"] = build_contradiction_matrix(report_dict)
    report_dict["tracking_dashboard"] = build_tracking_dashboard(report_dict)
    report_dict["research_judgement"] = build_research_judgement(report_dict)
    _sanitize_trade_instructions(report_dict)
    if _contains_trade_instruction(report_dict):
        raise HTTPException(status_code=422, detail="AI output contains direct trade instruction")
    return report_dict


def _clean_text_items(items: Any, limit: int = 5) -> list[str]:
    if not isinstance(items, list):
        return []
    cleaned: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in cleaned:
            cleaned.append(text)
        if len(cleaned) >= limit:
            break
    return cleaned


def build_contradiction_matrix(report: dict[str, Any]) -> list[dict[str, Any]]:
    existing = report.get("contradiction_matrix")
    if isinstance(existing, list) and existing:
        rows: list[dict[str, Any]] = []
        for row in existing[:5]:
            if not isinstance(row, dict):
                continue
            rows.append({
                "claim": str(row.get("claim") or "数据不足").strip() or "数据不足",
                "supporting_evidence": _clean_text_items(row.get("supporting_evidence")),
                "opposing_evidence": _clean_text_items(row.get("opposing_evidence")),
                "data_gaps": _clean_text_items(row.get("data_gaps")),
                "tracking_triggers": _clean_text_items(row.get("tracking_triggers")),
            })
        if rows:
            return rows

    contradiction = report.get("investment_contradiction")
    contradiction = contradiction if isinstance(contradiction, dict) else {}
    claim = str(contradiction.get("summary") or report.get("core_view") or "数据不足").strip() or "数据不足"
    supporting = _clean_text_items(contradiction.get("positive"), limit=4)
    supporting.extend(item for item in _clean_text_items(report.get("financial_diagnosis"), limit=2) if item not in supporting)
    opposing = _clean_text_items(contradiction.get("negative"), limit=4)
    opposing.extend(item for item in _clean_text_items(report.get("risks_and_disconfirming_evidence"), limit=2) if item not in opposing)
    gaps = _clean_text_items(report.get("policy_order_chain"), limit=3)
    key_question = str(contradiction.get("key_question") or "").strip()
    if key_question and key_question not in gaps:
        gaps.insert(0, key_question)
    if not gaps:
        gaps = ["数据不足：核心矛盾仍需补充可追溯来源"]
    triggers = _clean_text_items(report.get("tracking_triggers"), limit=5)
    if not triggers:
        triggers = ["数据不足：缺少明确跟踪触发器"]

    return [{
        "claim": claim,
        "supporting_evidence": supporting or ["数据不足：缺少支持证据"],
        "opposing_evidence": opposing or ["数据不足：缺少反向证据"],
        "data_gaps": gaps,
        "tracking_triggers": triggers,
    }]


def _all_evidence_keywords() -> tuple[str, ...]:
    return tuple(keyword for _, _, keywords in EVIDENCE_DIGEST_TOPICS for keyword in keywords)


def _build_evidence_refs_for_trigger(trigger: str, items: list[Any], limit: int = 3) -> list[dict[str, Any]]:
    bounded_limit = max(0, int(limit))
    if not bounded_limit:
        return []
    keywords = tuple(keyword for keyword in _all_evidence_keywords() if keyword in str(trigger or ""))
    refs: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        for snippet in item.get("snippets") or []:
            if not isinstance(snippet, dict):
                continue
            quote = str(snippet.get("quote") or "").strip()
            title = str(item.get("title") or "")
            if keywords and not any(keyword in quote or keyword in title for keyword in keywords):
                continue
            refs.append({
                "evidence_id": str(item.get("evidence_id") or ""),
                "source_label": str(item.get("source_label") or item.get("source") or "CNINFO 公告原文"),
                "quote": quote or title,
                "page": snippet.get("page"),
                "source_url": str(item.get("url") or ""),
                "source_date": str(item.get("announcement_date") or ""),
                "grade": str(item.get("grade") or EvidenceGrade.D.value),
                "confidence": str(snippet.get("confidence") or item.get("confidence") or "low"),
                "field": "",
                "logic": f"匹配触发器关键词：{trigger}",
            })
            if len(refs) >= bounded_limit:
                return refs
    return refs


def _validate_evidence_refs(report: dict[str, Any], snapshot: dict[str, Any]) -> None:
    library = snapshot.get("evidence_library") if isinstance(snapshot.get("evidence_library"), dict) else {}
    items = library.get("items") if isinstance(library.get("items"), list) else []
    items_by_id = {str(item.get("evidence_id")): item for item in items if isinstance(item, dict)}
    dashboard = report.get("tracking_dashboard")
    if not isinstance(dashboard, list):
        return
    for row in dashboard:
        if not isinstance(row, dict):
            continue
        trigger = str(row.get("trigger") or "").strip()
        raw_refs = row.get("evidence_refs") if isinstance(row.get("evidence_refs"), list) else []
        valid_refs: list[dict[str, Any]] = []
        for ref in raw_refs:
            if not isinstance(ref, dict):
                continue
            ref = dict(ref)
            evidence_id = str(ref.get("evidence_id") or "")
            item = items_by_id.get(evidence_id)
            if item is None:
                continue
            quote = str(ref.get("quote") or "").strip()
            snippet_texts = [str(snippet.get("quote") or "") for snippet in item.get("snippets") or [] if isinstance(snippet, dict)]
            if quote and not any(quote in text for text in snippet_texts) and quote not in str(item.get("title") or ""):
                continue
            snippet = next((s for s in item.get("snippets") or [] if isinstance(s, dict) and quote and str(s.get("quote") or "") == quote), None)
            if not isinstance(snippet, dict) and snippet_texts:
                snippet = next((s for s in item.get("snippets") or [] if isinstance(s, dict)), None)
            ref.setdefault("source_label", str(item.get("source_label") or item.get("source") or "CNINFO 公告原文"))
            ref.setdefault("source_url", str(item.get("url") or ""))
            ref.setdefault("source_date", str(item.get("announcement_date") or ""))
            ref.setdefault("grade", str(item.get("grade") or EvidenceGrade.D.value))
            ref.setdefault("confidence", str(snippet.get("confidence") if isinstance(snippet, dict) else item.get("confidence") or "low"))
            if ref.get("page") is None and isinstance(snippet, dict):
                ref["page"] = snippet.get("page")
            valid_refs.append(ref)
        if not valid_refs:
            valid_refs = _build_evidence_refs_for_trigger(trigger, items, limit=3)
        row["evidence_refs"] = valid_refs
        if not valid_refs:
            row["status"] = "data_insufficient"
            if not row.get("evidence"):
                row["evidence"] = ["数据不足：缺少当前证据"]
        elif str(row.get("status")) != "invalidated":
            has_strong = any(str(ref.get("grade")) in {"A", "B"} for ref in valid_refs)
            row["status"] = "confirmed" if has_strong else "watch"
            if not row.get("evidence"):
                row["evidence"] = [str(ref.get("quote") or ref.get("source_label") or "证据") for ref in valid_refs[:4]]


def build_tracking_dashboard(report: dict[str, Any]) -> list[dict[str, Any]]:
    existing = report.get("tracking_dashboard")
    if isinstance(existing, list) and existing:
        rows: list[dict[str, Any]] = []
        for row in existing[:8]:
            if not isinstance(row, dict):
                continue
            trigger = str(row.get("trigger") or "").strip()
            if not trigger:
                continue
            status = str(row.get("status") or "watch").strip()
            if status not in {"watch", "data_insufficient", "confirmed", "invalidated"}:
                status = "watch"
            rows.append({
                "trigger": trigger,
                "status": status,
                "why": str(row.get("why") or "数据不足").strip() or "数据不足",
                "evidence": _clean_text_items(row.get("evidence"), limit=4) or ["数据不足：缺少当前证据"],
                "evidence_refs": [dict(ref) for ref in row.get("evidence_refs") or [] if isinstance(ref, dict)],
                "next_check": str(row.get("next_check") or "下一期财报、公告或订单披露继续核实").strip(),
                "invalidate_if": str(row.get("invalidate_if") or "触发器未出现或反向证据增强").strip(),
            })
        if rows:
            return rows

    matrix = report.get("contradiction_matrix") if isinstance(report.get("contradiction_matrix"), list) else []
    triggers: list[str] = []
    by_trigger: dict[str, dict[str, Any]] = {}
    for row in matrix:
        if not isinstance(row, dict):
            continue
        for trigger in _clean_text_items(row.get("tracking_triggers"), limit=5):
            if trigger not in triggers:
                triggers.append(trigger)
                by_trigger[trigger] = row
    for trigger in _clean_text_items(report.get("tracking_triggers"), limit=8):
        if trigger not in triggers:
            triggers.append(trigger)

    evidence_display = report.get("evidence_display") if isinstance(report.get("evidence_display"), dict) else {}
    display_items = evidence_display.get("items") if isinstance(evidence_display.get("items"), list) else []
    display_evidence = []
    for item in display_items[:4]:
        if isinstance(item, dict):
            quote = str(item.get("quote") or "").strip()
            note = str(item.get("note") or "").strip()
            if quote:
                display_evidence.append(f"{quote}；{note}" if note else quote)

    dashboard: list[dict[str, Any]] = []
    for trigger in triggers[:8]:
        row = by_trigger.get(trigger) or {}
        claim = str(row.get("claim") or report.get("core_view") or "核心矛盾").strip()
        row_evidence = _clean_text_items(row.get("supporting_evidence"), limit=2)
        row_evidence.extend(item for item in _clean_text_items(row.get("opposing_evidence"), limit=2) if item not in row_evidence)
        evidence = list(row_evidence)
        evidence.extend(item for item in display_evidence[:2] if item not in evidence)
        status = "watch" if evidence else "data_insufficient"
        dashboard.append({
            "trigger": trigger,
            "status": status,
            "why": f"用于验证：{claim}",
            "evidence": evidence or ["数据不足：缺少当前证据"],
            "next_check": f"下一期财报、公告或订单披露继续核实：{trigger}",
            "invalidate_if": f"{trigger}未出现，或相关反向证据继续增强",
        })

    if dashboard:
        return dashboard
    return [{
        "trigger": "数据不足",
        "status": "data_insufficient",
        "why": "当前报告缺少可执行跟踪触发器",
        "evidence": ["数据不足：缺少当前证据"],
        "next_check": "下一期财报、公告或订单披露继续核实",
        "invalidate_if": "后续仍无可追溯数据支撑当前研究命题",
    }]


def build_research_judgement(report: dict[str, Any]) -> dict[str, Any]:
    existing = report.get("research_judgement") if isinstance(report.get("research_judgement"), dict) else {}
    core = str(existing.get("conclusion") or report.get("core_view") or "数据不足：缺少核心研判").strip()
    if core and not core.startswith("当前研判"):
        core = f"当前研判：{core}"

    matrix = report.get("contradiction_matrix") if isinstance(report.get("contradiction_matrix"), list) else []
    first_claim = str((matrix[0] or {}).get("claim") if matrix else report.get("core_view") or "核心矛盾").strip()
    dashboard = report.get("tracking_dashboard") if isinstance(report.get("tracking_dashboard"), list) else []
    triggers = _clean_text_items(report.get("tracking_triggers"), limit=5)
    strengthen = _clean_text_items(existing.get("strengthen_conditions"), limit=5)
    weaken = _clean_text_items(existing.get("weaken_conditions"), limit=5)

    if not strengthen:
        strengthen = [f"{trigger}，则当前修复逻辑增强" for trigger in triggers[:3]]
    if not strengthen and dashboard:
        strengthen = [str(item.get("next_check") or "").strip() for item in dashboard[:3] if isinstance(item, dict) and item.get("next_check")]
    if not strengthen:
        strengthen = ["数据不足：缺少可增强当前研判的明确条件"]

    if not weaken:
        weaken = [str(item.get("invalidate_if") or "").strip() for item in dashboard[:3] if isinstance(item, dict) and item.get("invalidate_if")]
    if not weaken:
        weaken = _clean_text_items(report.get("risks_and_disconfirming_evidence"), limit=3)
    if not weaken:
        weaken = ["数据不足：缺少可推翻当前研判的明确反证"]

    data_quality = str(report.get("data_quality") or "limited")
    if isinstance(existing.get("confidence"), dict) and existing["confidence"].get("level"):
        confidence = existing["confidence"]
    else:
        level = "高" if data_quality == "ready" and len(dashboard) >= 4 else ("中" if data_quality in {"ready", "limited"} else "低")
        confidence = {
            "level": level,
            "reason": "基于当前财务字段、证据链、反证和触发器形成的基本面研判；缺失来源仍以数据不足处理。",
        }

    base_case = existing.get("base_case") if isinstance(existing.get("base_case"), dict) else {}
    upside_case = existing.get("upside_case") if isinstance(existing.get("upside_case"), dict) else {}
    downside_case = existing.get("downside_case") if isinstance(existing.get("downside_case"), dict) else {}
    return {
        "conclusion": core,
        "confidence": confidence,
        "base_case": {
            "title": str(base_case.get("title") or "最可能情景"),
            "description": str(base_case.get("description") or f"{first_claim}仍是主线，当前证据支持形成有条件研判，而非停留在泛泛跟踪。"),
        },
        "upside_case": {
            "title": str(upside_case.get("title") or "增强情景"),
            "description": str(upside_case.get("description") or "若增强条件连续兑现，说明基本面修复质量提高。"),
        },
        "downside_case": {
            "title": str(downside_case.get("title") or "削弱情景"),
            "description": str(downside_case.get("description") or "若削弱条件出现，当前研判需要下修或推翻。"),
        },
        "strengthen_conditions": strengthen,
        "weaken_conditions": weaken,
    }


SOURCE_BACKED_EVIDENCE_TERMS = ("cninfo", "公告", "原文", "evidence_library", "订单", "政策", "客户", "财报", "年报", "季报")
UNCERTAIN_RESEARCH_TERMS = ("数据不足", "核实", "待确认", "需确认", "跟踪", "是否", "?", "？")
SIGNIFICANT_EVIDENCE_TERMS = (
    "审计报告",
    "年度报告",
    "半年度报告",
    "季度报告",
    "法律意见书",
    "财报",
    "财务报表",
    "营业收入",
    "净利润",
    "经营现金流",
    "应收账款",
    "合同资产",
    "存货",
    "减值",
    "毛利率",
    "净利率",
    "订单",
    "合同",
    "中标",
    "客户",
    "政策",
    "回款",
    "收入",
    "利润",
    "现金流",
)
SOURCE_BACKED_NARRATIVE_FIELDS = (
    "core_view",
    "business_basics",
    "investment_contradiction",
    "financial_diagnosis",
    "policy_order_chain",
    "risks_and_disconfirming_evidence",
)


def _collect_evidence_texts(items: list[Any]) -> list[str]:
    texts: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, str) and value.strip():
            texts.append(value.strip())
        elif isinstance(value, dict):
            for nested in value.values():
                collect(nested)
        elif isinstance(value, list):
            for nested in value:
                collect(nested)

    collect(items)
    return texts


def _is_exact_numeric_structured_evidence(source: str, quote: str) -> bool:
    if any(term in source.lower() for term in SOURCE_BACKED_EVIDENCE_TERMS):
        return False
    return bool(re.fullmatch(r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:%|亿元?|万股?|倍|元|万元)?", quote.strip()))


def _collect_report_narratives(report: dict[str, Any]) -> list[str]:
    texts: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, str) and value.strip():
            texts.append(value.strip())
        elif isinstance(value, dict):
            for nested in value.values():
                collect(nested)
        elif isinstance(value, list):
            for nested in value:
                collect(nested)

    for field in SOURCE_BACKED_NARRATIVE_FIELDS:
        collect(report.get(field))
    return texts


def _untraceable_narrative_gap() -> str:
    return "数据不足：该叙述未能追溯到公告/财报原文证据，需补充来源后再判断。"


def _untraceable_evidence_note() -> str:
    return "数据不足：该证据摘录未能追溯到快照证据库，已移除原摘录。"


def _sanitize_report_narratives(report: dict[str, Any], allowed_texts: list[str], has_items: bool) -> None:
    def sanitize(value: Any) -> Any:
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return value
            if not _source_backed_text(text):
                return value
            if _is_uncertain_or_gap_statement(text):
                return value
            if has_items and _high_risk_claim_is_grounded(text, allowed_texts):
                return value
            return _untraceable_narrative_gap()
        if isinstance(value, list):
            return [sanitize(item) for item in value]
        if isinstance(value, dict):
            return {key: sanitize(nested) for key, nested in value.items()}
        return value

    for field in SOURCE_BACKED_NARRATIVE_FIELDS:
        if field in report:
            report[field] = sanitize(report.get(field))


def _sanitize_report_evidence(report: dict[str, Any], allowed_texts: list[str], has_items: bool) -> None:
    sanitized: list[dict[str, Any]] = []
    for evidence in report.get("evidence") or []:
        if not isinstance(evidence, dict):
            continue
        item = dict(evidence)
        source = str(item.get("source") or "")
        quote = str(item.get("quote") or "").strip()
        source_backed = _source_backed_text(f"{source} {quote}")
        traceable = bool(quote and any(quote in text for text in allowed_texts))
        structured = bool(quote and _is_exact_numeric_structured_evidence(source, quote))

        if quote and not traceable and not structured:
            item["quote"] = ""
            item["note"] = _untraceable_evidence_note()
        elif source_backed and not has_items:
            item["quote"] = ""
            item["note"] = _untraceable_evidence_note()
        sanitized.append(item)
    report["evidence"] = sanitized


def _build_evidence_display(report: dict[str, Any]) -> None:
    items: list[dict[str, Any]] = []
    downgraded_count = 0
    downgrade_note = _untraceable_evidence_note()

    for evidence in report.get("evidence") or []:
        if not isinstance(evidence, dict):
            continue
        quote = str(evidence.get("quote") or "").strip()
        note = str(evidence.get("note") or "").strip()
        if quote:
            items.append(evidence)
        elif note == downgrade_note:
            downgraded_count += 1

    report["evidence_display"] = {"items": items, "downgraded_count": downgraded_count}


def _source_backed_text(value: str) -> bool:
    haystack = value.lower()
    return any(term in haystack for term in SOURCE_BACKED_EVIDENCE_TERMS)


def _is_uncertain_or_gap_statement(value: str) -> bool:
    return any(term in value for term in UNCERTAIN_RESEARCH_TERMS)


def _high_risk_claim_is_grounded(value: str, allowed_texts: list[str]) -> bool:
    normalized = value.strip()
    if not normalized:
        return True
    narrative_terms = {term for term in SIGNIFICANT_EVIDENCE_TERMS if term in normalized}
    for evidence_text in allowed_texts:
        evidence = str(evidence_text or "").strip()
        if not evidence:
            continue
        if normalized in evidence:
            return True
        if len(evidence) >= 8 and evidence in normalized:
            return True
        shared_terms = {term for term in narrative_terms if term in evidence}
        if len(shared_terms) >= 2:
            return True
        if shared_terms & {"审计报告", "年度报告", "半年度报告", "季度报告", "法律意见书"}:
            return True
    return False


def _validate_snapshot_evidence(report: dict[str, Any], snapshot: dict[str, Any]) -> None:
    library = snapshot.get("evidence_library") or {}
    items = library.get("items") if isinstance(library, dict) else []
    items = items if isinstance(items, list) else []
    allowed_texts = _collect_evidence_texts(items)

    _sanitize_report_narratives(report, allowed_texts, bool(items))

    _sanitize_report_evidence(report, allowed_texts, bool(items))
    _build_evidence_display(report)
    _validate_evidence_refs(report, snapshot)


def _schema_hint() -> dict[str, Any]:
    return {
        "title": "研究标题",
        "data_quality": "ready | limited | insufficient",
        "core_view": "明确核心研究判断：要敢于判断基本面强弱、修复阶段和第一矛盾；不得包含买入/卖出/加仓/减仓等交易指令",
        "research_judgement": {
            "conclusion": "当前研判：用一句话给出有条件的基本面判断，不说交易动作",
            "confidence": {"level": "高 | 中 | 低", "reason": "置信度原因，说明证据强弱和数据缺口"},
            "base_case": {"title": "最可能情景", "description": "当前最可能的基本面路径"},
            "upside_case": {"title": "增强情景", "description": "哪些证据兑现会增强研判"},
            "downside_case": {"title": "削弱情景", "description": "哪些反证出现会削弱或推翻研判"},
            "strengthen_conditions": ["增强当前研判的条件"],
            "weaken_conditions": ["削弱当前研判的条件"],
        },
        "business_basics": ["公司靠什么赚钱、收入结构、客户/上下游、壁垒、约束；没有证据写数据不足"],
        "investment_contradiction": {"summary": "核心矛盾", "positive": ["正面证据"], "negative": ["反面证据"], "key_question": "最该验证的问题"},
        "financial_diagnosis": ["营收vs利润、净利润vs经营现金流、应收/合同资产vs收入、毛利率/净利率、减值线索、费用率、存货、ROE/ROIC"],
        "policy_order_chain": ["政策-订单-收入-回款链条；没有数据写数据不足"],
        "risks_and_disconfirming_evidence": ["风险与反证"],
        "research_questions": ["人工继续核实的问题"],
        "tracking_triggers": ["未来1-3个季度触发器"],
        "evidence": [{"source": "evidence_library.items中的来源或数据源/字段", "quote": "仅填写快照中存在的短摘录或数值", "note": "如何支持结论；缺少原文或来源时写数据不足，不得编造公告、订单、政策、客户或财务事实"}],
        "contradiction_matrix": [{
            "claim": "研究命题，例如收入修复能否转化为利润和现金流",
            "supporting_evidence": ["支持命题的可追溯证据或结构化财务事实"],
            "opposing_evidence": ["反向证据、风险或反证"],
            "data_gaps": ["缺少的公告、订单、政策、客户、财报原文字段或仍需核实的问题"],
            "tracking_triggers": ["未来1-3个季度应观察的触发器"],
        }],
        "tracking_dashboard": [{
            "trigger": "具体跟踪触发器",
            "status": "watch | data_insufficient | confirmed | invalidated",
            "why": "为什么该触发器能验证或推翻核心矛盾",
            "evidence": ["当前已有证据或结构化事实；没有则写数据不足"],
            "evidence_refs": [{"evidence_id": "证据库中的64位ID", "quote": "快照中存在的引用句", "page": 3}],
            "next_check": "下一步检查的财报、公告、订单、政策或字段",
            "invalidate_if": "什么情况会推翻当前判断",
        }],
    }


def _manual_messages(request: ResearchRequest) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "你是A股资深调研员助手。只基于用户输入材料做研究框架、证据链和风险反证，不提供直接交易指令。缺失信息必须写数据不足，不得编造。你要敢于给出有条件的基本面研判、置信度、增强条件和削弱条件，不能只写继续跟踪。只返回严格JSON。"},
        {"role": "user", "content": json.dumps({"required_schema": _schema_hint(), "input": request.model_dump(mode="json")}, ensure_ascii=False)},
    ]


def _snapshot_messages(request: AutoResearchRequest, snapshot: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "你是A股资深研究员。你要像调研员一样先看基本盘，再找核心矛盾，再追证据链。只能依据系统采集的数据快照和用户补充材料；公告、订单、政策、客户、财务原文只能引用 evidence_library.items 中存在的公告、订单、政策、客户、财务原文文字片段；缺少原文或抽取失败必须写数据不足；不得编造公告、订单、政策或交易结论；不得给买入卖出加仓减仓指令。你必须给出有条件的基本面研判、置信度、最可能情景、增强条件和削弱条件，不能只写继续跟踪；允许判断强弱和修复阶段，不允许给交易动作。只返回严格JSON。"},
        {"role": "user", "content": json.dumps({"task": "生成V1.1+V1.2深研驾驶舱报告", "depth": request.depth, "required_schema": _schema_hint(), "snapshot": snapshot}, ensure_ascii=False)},
    ]


def _save_report(request: ResearchRequest, report: dict[str, Any], model: str) -> dict[str, Any]:
    return persist_report(stock_name=request.stock_name, ticker=request.ticker, report=report, model=model, input_snapshot=request.model_dump(mode="json"))


def _save_report_from_snapshot(request: AutoResearchRequest, snapshot: dict[str, Any], report: dict[str, Any], model: str) -> dict[str, Any]:
    stock = snapshot.get("stock") or {}
    return persist_report(stock_name=str(stock.get("name") or request.query), ticker=snapshot.get("ticker", request.ticker), report=report, model=model, input_snapshot=snapshot)


def persist_report(stock_name: str, ticker: str, report: dict[str, Any], model: str, input_snapshot: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    research_id = f"{now.strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"
    day = now.date().isoformat()
    root = RESEARCH_DIR / day
    root.mkdir(parents=True, exist_ok=True)
    payload = {"id": research_id, "status": "ready", "created_at": now.isoformat(), "stock_name": stock_name, "ticker": ticker, "model": model, "report": report, "input_snapshot": input_snapshot}
    path = root / f"{research_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    payload["storage_path"] = str(path)
    return payload


def load_research_payload(research_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"\d{14}-[a-f0-9]{8}", research_id):
        raise HTTPException(status_code=404, detail="research report not found")
    for path in RESEARCH_DIR.glob(f"*/{research_id}.json"):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise HTTPException(status_code=500, detail="failed to read research report") from exc
    raise HTTPException(status_code=404, detail="research report not found")


def safe_pdf_filename(payload: dict[str, Any]) -> str:
    ticker = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(payload.get("ticker") or "").strip()).strip("-")
    research_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(payload.get("id") or "report").strip()).strip("-")
    parts = [part for part in ("yanqing", ticker, research_id) if part]
    return "-".join(parts)[:150] + ".pdf"


def render_research_pdf_bytes(payload: dict[str, Any]) -> bytes:
    html = build_research_pdf_html(payload)
    PDF_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=PDF_RUNTIME_DIR) as temp_dir:
        root = Path(temp_dir)
        html_path = root / "report.html"
        pdf_path = root / "report.pdf"
        user_data_dir = root / "chromium-profile"
        html_path.write_text(html, encoding="utf-8")
        chromium = resolve_chromium_path()
        command = [
            chromium,
            "--headless=new",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--no-first-run",
            "--disable-background-networking",
            "--disable-default-apps",
            "--disable-sync",
            "--disable-crash-reporter",
            "--disable-breakpad",
            "--metrics-recording-only",
            "--force-color-profile=srgb",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=10000",
            f"--user-data-dir={user_data_dir}",
            "--print-to-pdf-no-header",
            f"--print-to-pdf={pdf_path}",
            html_path.as_uri(),
        ]
        _run_pdf_renderer(command, timeout_seconds=PDF_RENDER_TIMEOUT_SECONDS, pdf_path=pdf_path)
        if not pdf_path.is_file() or pdf_path.stat().st_size <= 0:
            raise HTTPException(status_code=500, detail="PDF generation produced no file")
        return pdf_path.read_bytes()


def _run_pdf_renderer(command: list[str], *, timeout_seconds: int, pdf_path: Path) -> None:
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="PDF renderer is not available") from exc
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        _terminate_process_group(process, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _terminate_process_group(process, signal.SIGKILL)
            process.wait(timeout=5)
        raise HTTPException(status_code=504, detail="PDF generation timed out") from exc
    if process.returncode != 0:
        raise HTTPException(status_code=500, detail="PDF generation failed")
    if not pdf_path.is_file() or pdf_path.stat().st_size <= 0:
        raise HTTPException(status_code=500, detail="PDF generation produced no file")


def _terminate_process_group(process: subprocess.Popen[bytes], sig: int) -> None:
    try:
        os.killpg(os.getpgid(process.pid), sig)
    except ProcessLookupError:
        return
    except Exception:
        process.kill()


def resolve_chromium_path() -> str:
    candidates = [CHROMIUM_PATH] if CHROMIUM_PATH else []
    candidates.extend((
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("google-chrome"),
        shutil.which("google-chrome-stable"),
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
    ))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise HTTPException(status_code=503, detail="PDF renderer is not available")


def build_research_pdf_html(payload: dict[str, Any]) -> str:
    report = payload.get("report") if isinstance(payload.get("report"), dict) else {}
    snapshot = payload.get("input_snapshot") if isinstance(payload.get("input_snapshot"), dict) else {}
    derived = snapshot.get("derived") if isinstance(snapshot.get("derived"), dict) else {}
    digest = snapshot.get("evidence_digest") if isinstance(snapshot.get("evidence_digest"), dict) else {}
    trace = snapshot.get("financial_traceability") if isinstance(snapshot.get("financial_traceability"), dict) else {}
    library = snapshot.get("evidence_library") if isinstance(snapshot.get("evidence_library"), dict) else {}
    evidence_display = report.get("evidence_display") if isinstance(report.get("evidence_display"), dict) else {}
    evidence_items = evidence_display.get("items") if isinstance(evidence_display.get("items"), list) else []
    tracking_dashboard = report.get("tracking_dashboard") if isinstance(report.get("tracking_dashboard"), list) else []
    contradiction_matrix = report.get("contradiction_matrix") if isinstance(report.get("contradiction_matrix"), list) else []
    judgement = report.get("research_judgement") if isinstance(report.get("research_judgement"), dict) else {}

    body = [
        '<main class="report">',
        '<section class="cover">',
        f"<p>研擎深研报告</p><h1>{_h(payload.get('stock_name') or payload.get('ticker') or '未命名标的')}</h1>",
        f"<div>{_h(payload.get('ticker') or '-')} · {_h(str(payload.get('created_at') or '')[:19].replace('T', ' '))} · 模型 {_h(payload.get('model') or '-')}</div>",
        "</section>",
        _metrics([
            ("数据质量", report.get("data_quality") or "数据不足", derived.get("latest_period") or "-"),
            ("PE TTM", _dig(derived, "valuation", "pe_ttm") or "不足", f"PB {_dig(derived, 'valuation', 'pb') or '-'}"),
            ("ROE", _dig(derived, "profitability", "roe") or "不足", f"毛利率 {_dig(derived, 'profitability', 'grossprofit_margin') or '-'}"),
            ("证据状态", library.get("status") or "insufficient", f"公告 {len(library.get('items') or [])} 条"),
        ]),
        _section(report.get("title") or "核心观点", f"<p class=\"core\">{_h(report.get('core_view') or '数据不足')}</p>"),
        _judgement_pdf(judgement, report),
        _cards("基本研究框架", [
            ("基本盘", _list_html(report.get("business_basics"))),
            ("核心矛盾", f"<p>{_h(_dig(report, 'investment_contradiction', 'summary') or '数据不足')}</p>{_list_html([*_as_list(_dig(report, 'investment_contradiction', 'positive')), *_as_list(_dig(report, 'investment_contradiction', 'negative')), _dig(report, 'investment_contradiction', 'key_question')])}"),
            ("财务体检", _list_html(report.get("financial_diagnosis"))),
            ("政策订单链", _list_html(report.get("policy_order_chain"))),
            ("风险与反证", _list_html(report.get("risks_and_disconfirming_evidence"))),
            ("跟踪触发器", _list_html(report.get("tracking_triggers"))),
        ]),
        _matrix_pdf(contradiction_matrix),
        _dashboard_pdf(tracking_dashboard),
        _cards("系统识别的异常", [("异常线索", _list_html([f"{item.get('item')}：{item.get('observation')}；{item.get('implication')}" for item in derived.get("anomalies") or [] if isinstance(item, dict)]))]),
        _financial_trace_pdf(trace),
        _evidence_digest_pdf(digest),
        _cards("调研问题", [("待核实", _list_html(report.get("research_questions")))]),
        _cards("证据链", [(str(item.get("source") or "来源不足"), f"<p>{_h(item.get('quote') or '数据不足')}</p><span>{_h(item.get('note') or '')}</span>") for item in evidence_items] or [("数据不足", "<span>当前没有可直接展示的可追溯证据。</span>")]),
        _source_traceability_pdf(report, snapshot),
        _evidence_library_pdf(library),
        "</main>",
    ]
    return "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">" + _pdf_css() + "</head><body>" + "".join(body) + "</body></html>"


def _h(value: Any) -> str:
    return escape(str(value if value is not None else ""), quote=True)


def _dig(payload: Any, *keys: str) -> Any:
    current = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return [value] if value not in (None, "") else []


def _list_html(items: Any) -> str:
    values = [str(item).strip() for item in _as_list(items) if str(item or "").strip()]
    if not values:
        values = ["数据不足"]
    return "<ul>" + "".join(f"<li>{_h(item)}</li>" for item in values) + "</ul>"


def _section(title: str, inner_html: str, extra_class: str = "") -> str:
    css_class = "panel"
    if extra_class:
        css_class += f" {extra_class}"
    return f'<section class="{css_class}"><h2>{_h(title)}</h2>{inner_html}</section>'


def _metrics(items: list[tuple[str, Any, Any]]) -> str:
    return '<section class="metrics">' + "".join(f'<article class="metric"><span>{_h(label)}</span><strong>{_h(value)}</strong><small>{_h(note)}</small></article>' for label, value, note in items) + "</section>"


def _cards(title: str, cards: list[tuple[str, str]], extra_class: str = "") -> str:
    return _section(title, '<div class="grid">' + "".join(f'<article class="card"><strong>{_h(card_title)}</strong>{inner}</article>' for card_title, inner in cards) + "</div>", extra_class=extra_class)


def _judgement_pdf(judgement: dict[str, Any], report: dict[str, Any]) -> str:
    conclusion = judgement.get("conclusion") or f"当前研判：{report.get('core_view') or '数据不足'}"
    confidence = judgement.get("confidence") if isinstance(judgement.get("confidence"), dict) else {}
    cards = [
        (_dig(judgement, "base_case", "title") or "最可能情景", f"<p>{_h(_dig(judgement, 'base_case', 'description') or '数据不足')}</p>"),
        (_dig(judgement, "upside_case", "title") or "增强情景", f"<p>{_h(_dig(judgement, 'upside_case', 'description') or '数据不足')}</p><span>增强条件</span>{_list_html(judgement.get('strengthen_conditions'))}"),
        (_dig(judgement, "downside_case", "title") or "削弱情景", f"<p>{_h(_dig(judgement, 'downside_case', 'description') or '数据不足')}</p><span>削弱条件</span>{_list_html(judgement.get('weaken_conditions'))}"),
    ]
    return _section("当前研判", f'<p class="core">{_h(conclusion)}</p><p class="snapshot">置信度：{_h(confidence.get("level") or "数据不足")} · {_h(confidence.get("reason") or "")}</p><div class="grid">' + "".join(f'<article class="card"><strong>{_h(title)}</strong>{inner}</article>' for title, inner in cards) + "</div>", extra_class="page-break")


def _matrix_pdf(rows: list[Any]) -> str:
    cards = []
    for row in rows[:6]:
        if not isinstance(row, dict):
            continue
        cards.append((row.get("claim") or "数据不足", f"<span>支持证据</span>{_list_html(row.get('supporting_evidence'))}<span>反向证据</span>{_list_html(row.get('opposing_evidence'))}<span>数据缺口</span>{_list_html(row.get('data_gaps'))}<span>跟踪触发器</span>{_list_html(row.get('tracking_triggers'))}"))
    return _cards("核心矛盾证据矩阵", cards or [("数据不足", _list_html([]))], extra_class="page-break")


def _dashboard_pdf(items: list[Any]) -> str:
    status_text = {"watch": "观察中", "data_insufficient": "数据不足", "confirmed": "已验证", "invalidated": "已推翻"}
    cards = []
    for item in items[:8]:
        if not isinstance(item, dict):
            continue
        cards.append((item.get("trigger") or "数据不足", f"<span>状态：{_h(status_text.get(str(item.get('status')), item.get('status') or '观察中'))}</span><p>{_h(item.get('why') or '数据不足')}</p><span>当前证据</span>{_list_html(item.get('evidence'))}<span>下一步检查</span><p>{_h(item.get('next_check') or '数据不足')}</p><span>推翻条件</span><p>{_h(item.get('invalidate_if') or '数据不足')}</p>"))
    return _cards("跟踪触发器仪表盘", cards or [("数据不足", _list_html([]))], extra_class="page-break")


def _financial_trace_pdf(trace: dict[str, Any]) -> str:
    items = trace.get("items") if isinstance(trace.get("items"), list) else []
    cards = []
    for item in items:
        if not isinstance(item, dict):
            continue
        cards.append((item.get("label") or item.get("field_key") or "字段", f"<span>{_h(item.get('period') or '数据不足')} · {_h(item.get('source_label') or item.get('source') or '')}</span><p>{_h(item.get('value') or '数据不足')} {_h(item.get('unit') or '')}</p><span>解释</span><p>{_h(item.get('interpretation') or '数据不足')}</p><span>风险</span><p>{_h(item.get('risk') or '数据不足')}</p>"))
    gap = "；".join(str(gap) for gap in trace.get("data_gaps") or []) or "无"
    return _section("财报字段追溯", f'<p class="snapshot">状态：{_h(trace.get("status") or "insufficient")} · 数据缺口：{_h(gap)}</p><div class="grid">' + "".join(f'<article class="card"><strong>{_h(title)}</strong>{inner}</article>' for title, inner in (cards or [("数据不足", "<span>当前快照没有可追溯的财报字段。</span>")])) + "</div>", extra_class="page-break")


def _evidence_digest_pdf(digest: dict[str, Any]) -> str:
    cards = []
    for fact in digest.get("financial_facts") or []:
        if isinstance(fact, dict):
            cards.append((fact.get("label") or fact.get("topic") or "财务事实", f"<span>{_h(fact.get('period') or '-')}</span><p>{_h(fact.get('observation') or '数据不足')}</p>"))
    for item in (digest.get("items") or [])[:8]:
        if isinstance(item, dict):
            cards.append((item.get("label") or item.get("topic") or "证据", f"<span>{_h(item.get('source') or '-')} · {_h(item.get('date') or '-')}</span><p>{_h(item.get('quote') or '数据不足')}</p>"))
    gaps = "；".join(str(gap) for gap in digest.get("data_gaps") or []) or "无"
    return _section("可用证据摘要", f'<p class="snapshot">状态：{_h(digest.get("status") or "insufficient")} · 数据缺口：{_h(gaps)}</p><div class="grid">' + "".join(f'<article class="card"><strong>{_h(title)}</strong>{inner}</article>' for title, inner in (cards or [("数据不足", "<span>当前没有可摘要的公告/财报证据。</span>")])) + f'</div><h2>待核实问题</h2>{_list_html(digest.get("open_questions"))}', extra_class="page-break")


def _evidence_library_pdf(library: dict[str, Any]) -> str:
    summary = library.get("summary") if isinstance(library.get("summary"), dict) else {}
    items = library.get("items") if isinstance(library.get("items"), list) else []
    cards = []
    for item in items:
        if not isinstance(item, dict):
            continue
        snippets = "".join(f"<p>{_h(snippet.get('quote') if isinstance(snippet, dict) else snippet)}</p>" for snippet in item.get("snippets") or [])
        gaps = f'<span class="warn">{"；".join(_h(gap) for gap in item.get("data_gaps") or [])}</span>' if item.get("data_gaps") else ""
        cards.append((item.get("title") or "未命名文档", f"<span>日期：{_h(item.get('announcement_date') or '-')} · 分类：{_h(item.get('category') or 'other')}</span><span>来源：{_h(item.get('source_label') or item.get('source') or '-')} · 文本抽取：{_h(item.get('text_extract_status') or 'skipped')} · 摘录：{_h(item.get('snippet_count') or 0)} · 正文长度：{_h(item.get('text_length') or 0)}</span>{snippets or '<p class=\"snapshot\">暂无摘录</p>'}{gaps}"))
    metrics = _metrics([
        ("原文公告", summary.get("total_items") or 0, ""),
        ("已下载", summary.get("downloaded_count") or 0, ""),
        ("已抽取", summary.get("extracted_count") or 0, ""),
        ("摘录", summary.get("snippet_count") or 0, ""),
    ])
    gaps = "；".join(str(gap) for gap in summary.get("data_gaps") or []) or "无"
    return _section("公告原文摘要", metrics + f'<p class="snapshot">最近公告：{_h(summary.get("latest_announcement_date") or "数据不足")} · 正文总长度：{_h(summary.get("text_length") or 0)} · 缺口：{_h(gaps)}</p><div class="grid">' + "".join(f'<article class="card evidence-card"><strong>{_h(title)}</strong>{inner}</article>' for title, inner in (cards or [("暂无公告原文", "<span>当前快照没有可展示的源文件证据。</span>")])) + "</div>", extra_class="page-break")


def _source_traceability_pdf(report: dict[str, Any], snapshot: dict[str, Any]) -> str:
    refs: list[dict[str, Any]] = []

    def add_ref(ref: Any) -> None:
        if not isinstance(ref, dict) or not ref.get("evidence_id"):
            return
        if not any(existing.get("evidence_id") == ref.get("evidence_id") and existing.get("quote") == ref.get("quote") for existing in refs):
            refs.append(ref)

    for row in report.get("tracking_dashboard") or []:
        if isinstance(row, dict):
            for ref in row.get("evidence_refs") or []:
                add_ref(ref)
    for row in report.get("contradiction_matrix") or []:
        if isinstance(row, dict):
            for ref in row.get("supporting_evidence_refs") or []:
                add_ref(ref)
            for ref in row.get("opposing_evidence_refs") or []:
                add_ref(ref)
    evidence_display = report.get("evidence_display") if isinstance(report.get("evidence_display"), dict) else {}
    for item in evidence_display.get("items") or []:
        if isinstance(item, dict):
            add_ref(item)

    if not refs:
        return _section("证据来源追溯", '<p class="snapshot">当前报告没有可追溯的结构化证据引用。</p>', extra_class="page-break")
    rows = []
    for ref in refs[:50]:
        page_text = f" · 第{_h(str(ref.get('page')))}页" if ref.get("page") is not None else ""
        rows.append((
            f"{_h(ref.get('grade') or 'D')} · {_h(ref.get('source_label') or '来源')}",
            f"<span>{_h(ref.get('source_date') or '')}{page_text}</span><p>{_h(ref.get('quote') or '')}</p><span>证据ID：{_h(str(ref.get('evidence_id') or '')[:12])}</span>",
        ))
    return _section("证据来源追溯", '<div class="grid">' + "".join(f'<article class="card"><strong>{_h(title)}</strong>{inner}</article>' for title, inner in rows) + "</div>", extra_class="page-break")


def _pdf_css() -> str:
    return """<style>
@page{size:A4;margin:14mm 12mm 16mm}
@page{@bottom-center{content:counter(page) " / " counter(pages);font-size:9px;color:#647284}@bottom-right{content:"研擎深研报告";font-size:9px;color:#647284}}
*{box-sizing:border-box}
body{margin:0;background:#fff;color:#17212b;font-family:Arial,"Microsoft YaHei",sans-serif;font-size:12px;line-height:1.65}
.report{width:100%}
.cover{break-after:page;page-break-after:always;margin-bottom:12px;padding-bottom:10px;border-bottom:2px solid #195cff}
.cover p{margin:0;color:#647284;font-size:12px}
.cover h1{margin:2px 0 4px;font-size:26px;line-height:1.25}
.cover div{color:#647284}
h2{margin:0 0 8px;font-size:16px;line-height:1.35}
p{margin:0 0 6px}
ul{margin:0;padding-left:16px;color:#4e5f73}
li{margin:0 0 3px}
.panel{break-inside:avoid-page;page-break-inside:avoid;margin:0 0 10px;padding:12px;border:1px solid #dbe4ef;border-radius:8px;background:#fff}
.panel.page-break{break-before:page;page-break-before:always}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:10px}
.metric,.card{break-inside:avoid-page;page-break-inside:avoid;padding:10px;border:1px solid #dbe4ef;border-radius:8px;background:#f8fbff}
.metric span,.card span,.snapshot{display:block;color:#647284;font-size:10.5px;line-height:1.55}
.metric strong{display:block;font-size:17px;line-height:1.25;word-break:break-word}
.card strong{display:block;margin-bottom:5px;color:#0f8f6f;font-size:13px}
.core{padding:10px;border-left:4px solid #0f8f6f;border-radius:6px;background:#eaf8f3;line-height:1.8}
.warn{color:#ad7414}
.evidence-card{break-inside:avoid-page;page-break-inside:avoid}
</style>"""


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    report = payload.get("report") or {}
    return {"id": payload.get("id"), "created_at": payload.get("created_at"), "stock_name": payload.get("stock_name"), "ticker": payload.get("ticker"), "title": report.get("title"), "data_quality": report.get("data_quality")}


def stock_basic_cache() -> list[dict[str, Any]]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / "stock_basic.json"
    if path.exists() and path.stat().st_size > 0:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("items"):
                return payload["items"]
        except Exception:
            pass
    rows = tushare_query("stock_basic", {"exchange": "", "list_status": "L"}, "ts_code,symbol,name,area,industry,market,list_date")
    path.write_text(json.dumps({"updated_at": datetime.now(timezone.utc).isoformat(), "items": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    return rows


def collect_tushare(api_name: str, params: dict[str, Any], fields: str, failures: list[str], limit: int = 10) -> list[dict[str, Any]]:
    try:
        rows = tushare_query(api_name, params, fields)
        return sorted(rows, key=lambda row: str(row.get("end_date") or row.get("trade_date") or row.get("ann_date") or ""), reverse=True)[:limit]
    except Exception as exc:
        failures.append(f"{api_name}: {type(exc).__name__}")
        return []


def tushare_query(api_name: str, params: dict[str, Any], fields: str = "") -> list[dict[str, Any]]:
    token = _tushare_token()
    if not token:
        raise RuntimeError("TUSHARE_TOKEN is not configured")
    with httpx.Client(timeout=30) as client:
        response = client.post(TUSHARE_API_URL, json={"api_name": api_name, "token": token, "params": params, "fields": fields})
        response.raise_for_status()
        payload = response.json()
    if payload.get("code") not in (0, None):
        raise RuntimeError(str(payload.get("msg") or f"TuShare {api_name} failed"))
    data = payload.get("data") or {}
    columns = data.get("fields") or []
    return [dict(zip(columns, item)) for item in data.get("items") or []]


def sina_quote(ts_code: str) -> dict[str, Any]:
    code, exchange = ts_code.split(".")
    symbol = ("sh" if exchange == "SH" else "sz") + code
    try:
        response = httpx.get(f"https://hq.sinajs.cn/list={symbol}", headers={"Referer": "https://finance.sina.com.cn/", "User-Agent": "Mozilla/5.0"}, timeout=8)
        response.raise_for_status()
        text = response.content.decode("gbk", errors="ignore")
        raw = text.split('="', 1)[1].rsplit('"', 1)[0]
        values = raw.split(",")
        if len(values) < 32 or not values[0]:
            return {"source": "Sina", "status": "empty"}
        previous = num(values[2]) or 0
        price = num(values[3]) or 0
        pct = ((price - previous) / previous * 100) if previous else 0
        return {"source": "Sina hq", "name": values[0], "price": price, "previous_close": previous, "pct_change": round(pct, 2), "amount": num(values[9]), "quote_time": f"{values[30]} {values[31]}"}
    except Exception:
        return {"source": "Sina", "status": "failed"}


def _tushare_token() -> str:
    return os.getenv("TUSHARE_TOKEN", "").strip()


def direct_code_stock(text: str) -> dict[str, Any] | None:
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) != 6:
        return None
    code = normalize_ts_code(digits)
    return {"ts_code": code, "symbol": code[:6], "name": code, "industry": "数据不足", "source": "code"}


def normalize_ts_code(raw: str) -> str:
    text = raw.strip().upper().replace(" ", "")
    match = re.fullmatch(r"(SH|SZ|BJ)?(\d{6})(?:\.(SH|SZ|BJ))?", text)
    if not match:
        raise HTTPException(status_code=422, detail="请输入6位A股代码或TuShare ts_code")
    prefix, code, suffix = match.groups()
    exchange = suffix or prefix or infer_exchange(code)
    return f"{code}.{exchange}"


def infer_exchange(code: str) -> str:
    if code.startswith(("600", "601", "603", "605", "688")):
        return "SH"
    if code.startswith(("000", "001", "002", "003", "300")):
        return "SZ"
    if code.startswith(("43", "83", "87", "88", "92")):
        return "BJ"
    raise HTTPException(status_code=422, detail="无法推断交易所，请输入 .SH/.SZ/.BJ")


def match_score(text: str, item: dict[str, Any]) -> int:
    code = str(item.get("symbol") or "").upper()
    ts_code = str(item.get("ts_code") or "").upper()
    name = str(item.get("name") or "").upper()
    if text == ts_code or text == code:
        return 100
    if code.startswith(text):
        return 90
    if text in name:
        return 80 + min(len(text), 10)
    return 30


def first_or_empty(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return rows[0] if rows else {}


def num(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


def fmt_yi(value: float | None) -> str:
    if value is None:
        return "数据不足"
    return f"{value / 100000000:.2f}亿"


def safe_key(value: str) -> str:
    return value.upper().replace(".", "_").replace("/", "_")


def _strip_json_fence(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    return text.strip()


def _is_direct_trade_instruction_text(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return False
    for word in TRADE_ACTION_WORDS:
        if word not in compact:
            continue
        if compact == word:
            return True
        if re.search(rf"({'|'.join(map(re.escape, TRADE_DIRECTIVE_PREFIXES))})[^。；;，,、]{{0,8}}{re.escape(word)}", compact):
            return True
        if re.search(rf"{re.escape(word)}[^。；;，,、]{{0,6}}({'|'.join(map(re.escape, TRADE_DIRECTIVE_SUFFIXES))})", compact):
            return True
    return False


def _sanitize_trade_instructions(value: Any) -> Any:
    if isinstance(value, str):
        return TRADE_DIRECTIVE_NOTE if _is_direct_trade_instruction_text(value) else value
    if isinstance(value, list):
        for index, item in enumerate(value):
            value[index] = _sanitize_trade_instructions(item)
        return value
    if isinstance(value, dict):
        for key, item in list(value.items()):
            value[key] = _sanitize_trade_instructions(item)
        return value
    return value


def _contains_trade_instruction(value: Any) -> bool:
    if isinstance(value, str):
        return _is_direct_trade_instruction_text(value)
    if isinstance(value, list):
        return any(_contains_trade_instruction(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_trade_instruction(item) for item in value.values())
    return False
