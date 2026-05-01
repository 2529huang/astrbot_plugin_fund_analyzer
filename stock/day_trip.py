"""
股票一日游：快照硬筛 → 日线综合分前 20% → 分时条件（VWAP/尾盘急拉/触板回落）。
不构成投资建议。
"""

from __future__ import annotations

import asyncio
import math
import random
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from astrbot.api import logger

from ..quant_screening import (
    DEFAULT_SCREENING_CONCURRENCY,
    ScreeningRow,
    rank_screening_rows,
    screen_lof_batch,
)

DAY_TRIP_MINUTE_CONCURRENCY = 3
DAY_TRIP_JITTER_SEC = (0.05, 0.15)

MIN_BARS_FOR_INTRADAY = 32  # 至少需覆盖尾盘判定的连续竞价分钟 bar
LOTSIZE = 100.0  # A 股成交量多为「手」，1 手=100 股


def _normalize_screening_code(raw: str) -> str:
    c = str(raw).strip()
    digits = "".join(ch for ch in c if ch.isdigit())
    if len(digits) >= 6:
        return digits[-6:].zfill(6)
    if c:
        return c.zfill(6)
    return ""


def _is_b_share(code: str) -> bool:
    c = (code or "").zfill(6)
    return c.startswith("200") or c.startswith("900")


def _limit_ratio_pct(code: str, name: str) -> float:
    n = name or ""
    if re.search(r"ST", n, re.I):
        return 5.0
    c = (code or "").zfill(6)
    if c.startswith("688"):
        return 20.0
    if c.startswith("30") or c.startswith("301"):
        return 20.0
    return 10.0


def _find_col(df: Any, candidates: tuple[str, ...]) -> Optional[str]:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def spot_has_volume_ratio_column(df: Any) -> bool:
    """快照是否含交易所/数据源提供的「量比」列（非自建）。"""
    return _find_col(df, ("量比", "volume_ratio")) is not None


def _approx_volume_ratio_series(df: Any, vol_col: str) -> Optional[Any]:
    """
    无量比列时：近似量比 = 该股成交量 / 全表「有成交」样本成交量中位数。
    与行情软件量比口径不同，仅作横向活跃度参考。
    """
    import pandas as pd

    vol = pd.to_numeric(df[vol_col], errors="coerce").fillna(0.0)
    med = vol[vol > 0].median()
    if med is None or pd.isna(med) or float(med) <= 0:
        return None
    med_f = float(med)
    return (vol / med_f).where(vol > 0, 0.0)


def filter_spot_for_day_trip(
    df: Any,
    *,
    pct_low: float = 3.0,
    pct_high: float = 9.0,
    min_volume_ratio: float = 1.5,
) -> tuple[list[tuple[str, str]], dict[str, dict[str, float]], bool]:
    """
    从 A 股快照表筛选：涨跌幅 [pct_low, pct_high]、量比 > min_volume_ratio；
    剔除停牌（无量）、B 股。

    若无「量比」列但有「成交量」，则用全样本成交量中位数自建近似量比（第三项返回 True）。

    Returns:
        pairs: (代码, 名称) 列表
        meta:  code -> prev_close, change_rate, volume_ratio
        volume_ratio_is_approx: 量比是否为自建近似
    """
    import pandas as pd

    if df is None or len(df) == 0:
        return [], {}, False

    code_col = _find_col(df, ("代码",))
    name_col = _find_col(df, ("名称",))
    rate_col = _find_col(df, ("涨跌幅", "changepercent"))
    volr_col = _find_col(df, ("量比", "volume_ratio"))
    vol_col = _find_col(df, ("成交量", "volume"))
    prev_col = _find_col(df, ("昨收", "settlement"))

    if not code_col or not name_col or not rate_col:
        logger.warning(
            "一日游硬筛: 缺少必要列（代码/名称/涨跌幅）。列预览: %s",
            list(df.columns)[:25],
        )
        return [], {}, False

    volume_ratio_is_approx = False
    d = df.copy()
    rate = pd.to_numeric(d[rate_col], errors="coerce")
    vol = pd.to_numeric(d[vol_col], errors="coerce") if vol_col else pd.Series(0.0, index=d.index)
    prev = pd.to_numeric(d[prev_col], errors="coerce") if prev_col else pd.Series(0.0, index=d.index)

    if volr_col:
        volr = pd.to_numeric(d[volr_col], errors="coerce")
    elif vol_col:
        approx = _approx_volume_ratio_series(d, vol_col)
        if approx is None:
            logger.warning(
                "一日游硬筛: 无「量比」且无法由成交量计算中位数近似（缺少有效成交）。"
            )
            return [], {}, False
        volr = approx
        volume_ratio_is_approx = True
        logger.info(
            "一日游硬筛: 快照无量比列，已用「成交量/全表有成交样本成交量中位数」自建近似量比。"
        )
    else:
        logger.warning(
            "一日游硬筛: 缺少「量比」与「成交量」，列预览: %s",
            list(df.columns)[:25],
        )
        return [], {}, False

    mask = (
        rate.ge(pct_low)
        & rate.le(pct_high)
        & volr.gt(min_volume_ratio)
        & vol.gt(0)
    )
    dd = d.loc[mask]

    pairs: list[tuple[str, str]] = []
    meta: dict[str, dict[str, float]] = {}
    for _, row in dd.iterrows():
        c = _normalize_screening_code(str(row.get(code_col, "")))
        if not c or _is_b_share(c):
            continue
        nm = str(row[name_col]) if name_col in dd.columns else ""
        pairs.append((c, nm))
        vr = float(volr.loc[row.name])
        if math.isnan(vr):
            vr = 0.0
        meta[c] = {
            "prev_close": float(prev.loc[row.name]) if prev_col else 0.0,
            "change_rate": float(rate.loc[row.name]) if not math.isnan(rate.loc[row.name]) else 0.0,
            "volume_ratio": vr,
        }
    seen: set[str] = set()
    deduped: list[tuple[str, str]] = []
    dedup_meta: dict[str, dict[str, float]] = {}
    for c, nm in pairs:
        if c in seen:
            continue
        seen.add(c)
        deduped.append((c, nm))
        if c in meta:
            dedup_meta[c] = meta[c]
    return deduped, dedup_meta, volume_ratio_is_approx


def pick_top_fraction(
    rows: list[ScreeningRow], *, fraction: float = 0.2
) -> list[ScreeningRow]:
    if not rows:
        return []
    ranked = rank_screening_rows(rows)
    n = max(1, math.ceil(len(ranked) * fraction))
    return ranked[:n]


def _minute_df_to_arrays(df: Any) -> Optional[dict[str, Any]]:
    """将 akshare 分钟线 DataFrame 转为 numpy-friendly 数组（列序容错）。"""
    import numpy as np

    if df is None or len(df) < MIN_BARS_FOR_INTRADAY:
        return None
    if len(df.columns) < 7:
        return None
    # 时间, 开, 收, 高, 低, 量, 额, [均价]
    tcol = df.iloc[:, 0].astype(str)
    opens = np.asarray(df.iloc[:, 1], dtype=float)
    closes = np.asarray(df.iloc[:, 2], dtype=float)
    highs = np.asarray(df.iloc[:, 3], dtype=float)
    lows = np.asarray(df.iloc[:, 4], dtype=float)
    vols = np.asarray(df.iloc[:, 5], dtype=float)
    amts = np.asarray(df.iloc[:, 6], dtype=float)
    return {
        "time": tcol,
        "open": opens,
        "close": closes,
        "high": highs,
        "low": lows,
        "volume": vols,
        "amount": amts,
    }


def _compute_vwap(m: dict[str, Any]) -> float:
    import numpy as np

    vol = m["volume"]
    amt = m["amount"]
    total_vol_shares = float(np.sum(vol) * LOTSIZE)
    total_amt = float(np.sum(amt))
    if total_vol_shares <= 0:
        return 0.0
    return total_amt / total_vol_shares


def _touch_limit_fallback(
    high: float, close: float, prev_close: float, limit_pct: float
) -> bool:
    if prev_close <= 0:
        return False
    lim = prev_close * (1.0 + limit_pct / 100.0)
    eps, delta = 0.005, 0.01
    touched = high >= lim * (1.0 - eps)
    fell = close < lim * (1.0 - delta)
    return bool(touched and fell)


def evaluate_intraday_minutes(
    df: Any,
    *,
    code: str,
    name: str,
    prev_close: float,
    vwap_tol: float = 0.001,
) -> dict[str, Any]:
    """
    分时规则：
    - 后 30 根 bar 最低价均 >= VWAP * (1 - vwap_tol)
    - 回避：最后 15 分钟涨幅 (last_close vs iloc[-15] close) > 3%
    - 因子：VWAP 偏离%、尾盘量比（末30分成交额/前半程按分钟归一）、触板回落
    """
    import numpy as np

    out: dict[str, Any] = {
        "code": code,
        "name": name,
        "passed": False,
        "fail_reason": "",
        "vwap": 0.0,
        "vwap_deviation_pct": 0.0,
        "tail_vol_ratio": 0.0,
        "touch_limit_fell": False,
    }
    m = _minute_df_to_arrays(df)
    if m is None:
        out["fail_reason"] = "分时数据不足或非交易时段"
        return out

    vwap = _compute_vwap(m)
    if vwap <= 0:
        out["fail_reason"] = "无法计算日内均价(VWAP)"
        return out

    last_close = float(m["close"][-1])
    out["vwap"] = vwap
    out["vwap_deviation_pct"] = (last_close - vwap) / vwap * 100.0 if vwap > 0 else 0.0

    lows_last30 = m["low"][-30:]
    if np.any(lows_last30 < vwap * (1.0 - vwap_tol)):
        out["fail_reason"] = "最后30分钟曾跌破日内均价"
        return out

    if len(m["close"]) >= 15:
        ref_close = float(m["close"][-15])
        if ref_close > 0 and (last_close - ref_close) / ref_close > 0.03:
            out["fail_reason"] = "尾盘15分钟急拉超3%"
            return out

    vol = m["volume"]
    amt = m["amount"]
    n = len(vol)
    tail_amt = float(np.sum(amt[-30:]))
    prior_amt = float(np.sum(amt[:-30])) if n > 30 else 0.0
    prior_minutes = max(1, n - 30)
    # 尾盘「量比」：末30分每分钟均额 / 此前每分钟均额
    tail_rate = tail_amt / 30.0 if tail_amt > 0 else 0.0
    prior_rate = prior_amt / float(prior_minutes) if prior_amt > 0 else 0.0
    out["tail_vol_ratio"] = (tail_rate / prior_rate) if prior_rate > 0 else 0.0

    out["touch_limit_fell"] = _touch_limit_fallback(
        float(np.max(m["high"])),
        last_close,
        prev_close,
        _limit_ratio_pct(code, name),
    )

    out["passed"] = True
    return out


def _trade_date_bounds(now: Optional[datetime] = None) -> tuple[str, str]:
    """当日分钟拉取时间窗（覆盖两市连续竞价）。"""
    dt = now or datetime.now()
    d = dt.strftime("%Y-%m-%d")
    start = f"{d} 09:00:00"
    end = f"{d} 15:30:00"
    return start, end


def fetch_minute_bars_sync(symbol: str, start_date: str, end_date: str) -> Any:
    import akshare as ak

    return ak.stock_zh_a_hist_min_em(
        symbol=symbol,
        period="1",
        adjust="",
        start_date=start_date,
        end_date=end_date,
    )


@dataclass
class DayTripLine:
    code: str
    name: str
    trend_score: int
    signal: str
    spot_change_pct: float
    spot_volume_ratio: float
    vwap_deviation_pct: float
    tail_vol_ratio: float
    touch_limit_fell: str


def _format_minute_fail_summary(
    counts: dict[str, int],
    top_pool: int,
    minute_pass: int,
) -> str:
    if not counts:
        return ""
    total = sum(counts.values())
    if total <= 0:
        return ""
    lines_out = [
        f"📌 分时未通过统计（本池 {top_pool} 只，通过 {minute_pass} 只，未通过 {total} 只）:",
    ]
    for reason, cnt in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
        lines_out.append(f"   • {reason}: {cnt}")
    return "\n".join(lines_out) + "\n"


def format_day_trip_report(
    lines: list[DayTripLine],
    *,
    hard_n: int,
    k_valid: int,
    top_pool: int,
    minute_pass: int,
    trade_date: str,
    truncation_note: str = "",
    volume_ratio_is_approx: bool = False,
    minute_fail_counts: Optional[dict[str, int]] = None,
) -> str:
    from ..quant_screening import DISCLAIMER

    vr_line = ""
    if volume_ratio_is_approx:
        vr_line = (
            "⚠️ 快照无量比列：表中「量比」为自建近似＝该股成交量÷全表有成交样本的成交量中位数，"
            "与常见行情软件「量比」口径不同，仅作筛选用。\n"
        )
    header = (
        "📋 股票一日游（硬筛→综合分前20%→分时）\n"
        + vr_line
        + f"交易日: {trade_date} | 硬筛: {hard_n} | 日线有效: {k_valid} | 前20%池: {top_pool} | 分时通过: {minute_pass}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    fail_summary = _format_minute_fail_summary(
        minute_fail_counts or {},
        top_pool,
        minute_pass,
    )

    if not lines:
        body = "无同时满足分时条件的标的。\n" + fail_summary + (truncation_note or "")
        return header + body + DISCLAIMER

    col = (
        f"{'代码':<8}{'名称':<10}{'综合':<5}{'涨跌%':<7}{'量比':<6}"
        f"{'偏离VWAP':<9}{'尾盘量比':<8}{'触板回':<6}\n"
    )
    rows = [col]
    for r in lines:
        nm = r.name if len(r.name) <= 10 else r.name[:8] + "…"
        rows.append(
            f"{r.code:<8}{nm:<10}{r.trend_score:<5}"
            f"{r.spot_change_pct:+.2f}{'':>3}{r.spot_volume_ratio:<6.2f}"
            f"{r.vwap_deviation_pct:+.2f}%{'':>2}"
            f"{r.tail_vol_ratio:<8.2f}{r.touch_limit_fell:<6}\n"
        )
    body = "".join(rows)
    if fail_summary:
        body += fail_summary
    if truncation_note:
        body += truncation_note
    return header + body + DISCLAIMER


async def run_day_trip_pipeline(
    _fund_analyzer: Any,
    *,
    pairs: list[tuple[str, str]],
    meta: dict[str, dict[str, float]],
    screening_row_by_code: dict[str, ScreeningRow],
    max_concurrent_minute: int = DAY_TRIP_MINUTE_CONCURRENCY,
    now: Optional[datetime] = None,
) -> tuple[list[DayTripLine], dict[str, Any]]:
    """
    对已得「前20%」screening 结果逐只拉分时并评估。
    screening_row_by_code 仅含 top 分数池内的代码。
    """
    start_d, end_d = _trade_date_bounds(now)
    trade_date = (now or datetime.now()).strftime("%Y-%m-%d")

    ranked = rank_screening_rows(
        [r for r in screening_row_by_code.values() if r.code in meta]
    )
    ordered = [r.code for r in ranked]

    sem = asyncio.Semaphore(max_concurrent_minute)
    lo, hi = DAY_TRIP_JITTER_SEC

    async def one(code: str) -> tuple[Optional[DayTripLine], Optional[str]]:
        row = screening_row_by_code.get(code)
        if not row:
            return None, "无行情元数据"
        m = meta.get(code, {})
        prev = float(m.get("prev_close", 0.0))
        async with sem:
            if hi > 0:
                await asyncio.sleep(random.uniform(lo, hi))
            try:
                df = await asyncio.to_thread(
                    fetch_minute_bars_sync, code, start_d, end_d
                )
            except Exception as e:
                logger.debug("一日游分时失败 %s: %s", code, e)
                return None, "分钟线请求异常"
        ev = evaluate_intraday_minutes(
            df, code=code, name=row.name, prev_close=prev
        )
        if not ev.get("passed"):
            reason = str(ev.get("fail_reason") or "").strip() or "分时条件未满足(未知)"
            return None, reason
        return DayTripLine(
            code=code,
            name=row.name,
            trend_score=row.trend_score,
            signal=row.signal,
            spot_change_pct=float(m.get("change_rate", 0.0)),
            spot_volume_ratio=float(m.get("volume_ratio", 0.0)),
            vwap_deviation_pct=float(ev.get("vwap_deviation_pct", 0.0)),
            tail_vol_ratio=float(ev.get("tail_vol_ratio", 0.0)),
            touch_limit_fell="是" if ev.get("touch_limit_fell") else "否",
        ), None

    results = await asyncio.gather(*[one(c) for c in ordered])
    fail_counts: defaultdict[str, int] = defaultdict(int)
    passed_lines: list[DayTripLine] = []
    for line, fail_reason in results:
        if line is not None:
            passed_lines.append(line)
        elif fail_reason:
            fail_counts[fail_reason] += 1

    stats: dict[str, Any] = {
        "hard_n": len(pairs),
        "k_valid": len(screening_row_by_code),
        "top_pool": len(ordered),
        "minute_pass": len(passed_lines),
        "trade_date": trade_date,
        "minute_fail_counts": dict(fail_counts),
    }
    return passed_lines, stats


async def run_day_trip_full(
    fund_analyzer: Any,
    pairs: list[tuple[str, str]],
    meta: dict[str, dict[str, float]],
    *,
    fraction: float = 0.2,
    max_concurrent_screen: int = DEFAULT_SCREENING_CONCURRENCY,
    max_concurrent_minute: int = DAY_TRIP_MINUTE_CONCURRENCY,
    now: Optional[datetime] = None,
) -> tuple[list[DayTripLine], dict[str, Any]]:
    """硬筛 pairs → 批量日线打分 → 前 fraction → 分时。"""
    if not pairs:
        td = (now or datetime.now()).strftime("%Y-%m-%d")
        return [], {
            "hard_n": 0,
            "k_valid": 0,
            "top_pool": 0,
            "minute_pass": 0,
            "trade_date": td,
            "minute_fail_counts": {},
        }

    raw = await screen_lof_batch(
        fund_analyzer,
        pairs,
        max_concurrent=max_concurrent_screen,
    )
    if not raw:
        td = (now or datetime.now()).strftime("%Y-%m-%d")
        return [], {
            "hard_n": len(pairs),
            "k_valid": 0,
            "top_pool": 0,
            "minute_pass": 0,
            "trade_date": td,
            "minute_fail_counts": {},
        }

    top = pick_top_fraction(raw, fraction=fraction)
    by_code: dict[str, ScreeningRow] = {r.code: r for r in top}
    lines, stats = await run_day_trip_pipeline(
        fund_analyzer,
        pairs=pairs,
        meta=meta,
        screening_row_by_code=by_code,
        max_concurrent_minute=max_concurrent_minute,
        now=now,
    )
    stats["k_valid"] = len(raw)
    stats["top_pool"] = len(top)
    stats["hard_n"] = len(pairs)
    stats["trade_date"] = (now or datetime.now()).strftime("%Y-%m-%d")
    return lines, stats
