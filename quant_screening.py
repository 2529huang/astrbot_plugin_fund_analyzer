"""
批量量化精选：场内 LOF 列表 / A 股行情候选，拉取日线后打分排序输出。
不构成投资建议。
"""

from __future__ import annotations

import asyncio
import math
import random
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from astrbot.api import logger

from .ai_analyzer.quant import QuantAnalyzer

MIN_HISTORY_BARS = 20
HISTORY_DAYS = 60
# 批量精选：每只标的只尝试 1 次 K 线 HTTP（下层 _request 默认会连打 3 次，体感像「失败还一直请求」）
KLINE_MAX_RETRIES_SCREENING = 1
# 批量拉 K 线默认并发（原 8 易触发东财断连/限速，略降以换稳定）
DEFAULT_SCREENING_CONCURRENCY = 1
# 取得并发槽后、发请求前随机等待（秒），打散 burst；False 则关闭
SCREENING_JITTER_ENABLED = True
SCREENING_JITTER_SEC = (0.05, 0.2)

DISCLAIMER = (
    "\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "⚠️ 以上内容仅为量化指标回溯与排序演示，不构成任何投资建议。\n"
    "投资有风险；批量请求可能触发数据源限速。\n"
)


@dataclass
class ScreeningRow:
    code: str
    name: str
    trend_score: int
    signal: str
    sharpe_ratio: float


def _row_from_history(
    quant: QuantAnalyzer,
    code: str,
    name: str,
    history: list[dict],
) -> Optional[ScreeningRow]:
    if not history or len(history) < MIN_HISTORY_BARS:
        return None
    indicators = quant.calculate_all_indicators(history)
    perf = quant.calculate_performance(history)
    sharpe = perf.sharpe_ratio if perf else float("-inf")
    if sharpe != sharpe or math.isinf(sharpe):
        sharpe = float("-inf")
    return ScreeningRow(
        code=code,
        name=name,
        trend_score=int(indicators.trend_score),
        signal=str(indicators.signal),
        sharpe_ratio=float(sharpe),
    )


async def screen_lof_batch(
    fund_analyzer: Any,
    rows: list[tuple[str, str]],
    *,
    max_concurrent: int = DEFAULT_SCREENING_CONCURRENCY,
) -> list[ScreeningRow]:
    quant = QuantAnalyzer()
    sem = asyncio.Semaphore(max_concurrent)
    lo, hi = SCREENING_JITTER_SEC

    async def one(code: str, name: str) -> Optional[ScreeningRow]:
        async with sem:
            if SCREENING_JITTER_ENABLED and hi > 0:
                await asyncio.sleep(random.uniform(lo, hi))
            try:
                hist = await fund_analyzer.get_lof_history(
                    code,
                    days=HISTORY_DAYS,
                    adjust="qfq",
                    prefer_otc=False,
                    kline_max_retries=KLINE_MAX_RETRIES_SCREENING,
                )
            except Exception as e:
                logger.debug(f"量化精选拉取行情失败 {code}: {e}")
                return None
            if not hist:
                return None
            return _row_from_history(quant, code, name, hist)

    results = await asyncio.gather(*[one(c, n) for c, n in rows])
    return [r for r in results if r is not None]


def _normalize_screening_code(raw: str) -> str:
    c = str(raw).strip()
    digits = "".join(ch for ch in c if ch.isdigit())
    if len(digits) >= 6:
        return digits[-6:].zfill(6)
    if c:
        return c.zfill(6)
    return ""


def pairs_from_board_like_df(df: Any, max_scan: int) -> list[tuple[str, str]]:
    """
    从板块成份或 ETF 现货表取 (代码, 名称) 列表。
    有涨跌幅类列时按 |涨跌幅| 降序取前 max_scan；否则按表顺序截取。
    """
    import pandas as pd

    if df is None or len(df) == 0 or max_scan <= 0:
        return []
    code_col = "代码"
    name_col = "名称"
    if code_col not in df.columns:
        logger.warning("pairs_from_board_like_df: 无「代码」列，预览: %s", list(df.columns)[:20])
        return []

    rate_col: Optional[str] = None
    for col in ("涨跌幅", "changepercent", "振幅"):
        if col in df.columns:
            rate_col = col
            break

    dd = df.copy()
    if rate_col:
        dd["_abs"] = pd.to_numeric(dd[rate_col], errors="coerce").fillna(0).abs()
        dd = dd.sort_values("_abs", ascending=False)
    else:
        logger.debug("pairs_from_board_like_df: 无涨跌幅列，按原始顺序取前 %s 条", max_scan)

    pairs: list[tuple[str, str]] = []
    for _, row in dd.head(max_scan).iterrows():
        c = _normalize_screening_code(row.get(code_col, ""))
        if not c:
            continue
        nm = str(row[name_col]) if name_col in dd.columns else ""
        pairs.append((c, nm))
    return pairs


async def screen_board_like_pairs(
    fund_analyzer: Any,
    pairs: list[tuple[str, str]],
    *,
    max_concurrent: int = DEFAULT_SCREENING_CONCURRENCY,
) -> list[ScreeningRow]:
    if not pairs:
        return []
    return await screen_lof_batch(
        fund_analyzer, pairs, max_concurrent=max_concurrent
    )


async def screen_lof_funds(
    fund_analyzer: Any,
    *,
    cap: Optional[int] = None,
    max_concurrent: int = DEFAULT_SCREENING_CONCURRENCY,
) -> tuple[list[ScreeningRow], int]:
    lst = await fund_analyzer._api.get_lof_list()
    if not lst:
        return [], 0
    pairs: list[tuple[str, str]] = []
    for item in lst:
        code = str(item.get("code", "")).strip()
        name = str(item.get("name", ""))
        if not code:
            continue
        digits = "".join(ch for ch in code if ch.isdigit())
        if len(digits) >= 6:
            code = digits[-6:].zfill(6)
        else:
            code = code.zfill(6)
        pairs.append((code, name))
    if cap is not None and cap > 0:
        pairs = pairs[:cap]
    attempted = len(pairs)
    rows = await screen_lof_batch(fund_analyzer, pairs, max_concurrent=max_concurrent)
    return rows, attempted


def _pandas_abs_change_pairs(df: Any, max_scan: int) -> list[tuple[str, str]]:
    import pandas as pd

    rate_col = "涨跌幅"
    if rate_col not in df.columns:
        for alt in ("changepercent", "振幅"):
            if alt in df.columns:
                rate_col = alt
                break
        else:
            logger.warning(
                "行情中无可用涨跌幅类列（需 涨跌幅 等）。列预览: %s",
                list(df.columns)[:20],
            )
            return []

    code_col = "代码"
    name_col = "名称"
    if code_col not in df.columns:
        logger.warning("行情中无代码列「代码」")
        return []

    dd = df.copy()
    dd["_abs"] = pd.to_numeric(dd[rate_col], errors="coerce").fillna(0).abs()
    dd = dd.sort_values("_abs", ascending=False)

    pairs: list[tuple[str, str]] = []
    for _, row in dd.head(max_scan).iterrows():
        c = _normalize_screening_code(row.get(code_col, ""))
        if not c:
            continue
        nm = str(row[name_col]) if name_col in dd.columns else ""
        pairs.append((c, nm))
    return pairs


async def screen_stocks_by_abs_pct(
    stock_analyzer: Any,
    fund_analyzer: Any,
    *,
    max_scan: int = 150,
    max_concurrent: int = DEFAULT_SCREENING_CONCURRENCY,
) -> tuple[list[ScreeningRow], int]:
    df = await stock_analyzer._get_stock_data()
    if df is None or len(df) == 0:
        return [], 0
    pairs = _pandas_abs_change_pairs(df, max_scan)
    attempted = len(pairs)
    if not pairs:
        return [], 0
    rows = await screen_lof_batch(fund_analyzer, pairs, max_concurrent=max_concurrent)
    return rows, attempted


def rank_screening_rows(rows: list[ScreeningRow]) -> list[ScreeningRow]:
    # 主键综合分 trend_score 降序；次键夏普比率降序（无有效夏普时已在 _row_from_history 记为 -inf）
    return sorted(rows, key=lambda r: (-r.trend_score, -r.sharpe_ratio))


def signal_badge_class(signal: str) -> str:
    """映射技术信号到报告模板徽章样式类（与国内涨跌色惯例一致）。"""
    s = (signal or "").strip()
    if s in ("强烈买入", "买入", "强买"):
        return "bg-red"
    if s in ("强烈卖出", "卖出", "强卖"):
        return "bg-green"
    if s == "观望":
        return "bg-gray"
    return "bg-orange"


def screening_report_template_data(
    *,
    title: str,
    screened: list[ScreeningRow],
    candidate_count: int,
    valid_count: int,
) -> dict[str, Any]:
    rows_out: list[dict[str, Any]] = []
    for i, row in enumerate(screened, 1):
        sr = row.sharpe_ratio
        sharpe_s = f"{sr:.3f}" if sr > -999 else "---"
        nm = row.name
        display = nm if len(nm) <= 20 else nm[:18] + "…"
        rows_out.append(
            {
                "rank": i,
                "code": row.code,
                "name": display,
                "name_full": nm,
                "trend_score": row.trend_score,
                "signal": row.signal,
                "sharpe": sharpe_s,
                "badge_class": signal_badge_class(row.signal),
            }
        )
    disclaimer_lines = [
        ln.strip()
        for ln in DISCLAIMER.strip().split("\n")
        if ln.strip() and set(ln.strip()) != {"━"}
    ]
    return {
        "report_title": title,
        "meta_line": f"计划分析: {candidate_count} 只 · K线有效的样本数: {valid_count}",
        "generated_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "rows": rows_out,
        "disclaimer_lines": disclaimer_lines or ["不构成投资建议。", "批量请求可能触发数据源限速。"],
    }


def format_screening_plain(
    *,
    title: str,
    screened: list[ScreeningRow],
    candidate_count: int,
    valid_count: int,
) -> str:
    lines = [
        title,
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        f"计划分析: {candidate_count} 只 · K线有效的样本数: {valid_count}",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        f"{'排名':<5}{'代码':<10}{'名称':<14}{'综合分':<8}{'信号':<10}{'夏普':<10}",
    ]
    for i, row in enumerate(screened, 1):
        nm = row.name if len(row.name) <= 14 else row.name[:12] + ".."
        sr = row.sharpe_ratio
        sr_s = f"{sr:.3f}" if sr > -999 else "---"
        lines.append(
            f"{i:<5}{row.code:<10}{nm:<14}{row.trend_score:<8}"
            f"{row.signal:<10}{sr_s:<10}"
        )
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def parse_optional_positive_int(default: Optional[int], s: str) -> Optional[int]:
    s = (s or "").strip()
    if not s:
        return default
    try:
        v = int(s)
        return v if v > 0 else default
    except ValueError:
        return default