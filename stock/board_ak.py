"""
东方财富板块 / 场内 ETF：异步封装与短 TTL 内存缓存。
行业板块列表与成份走 eastmoney_api（aiohttp + 重试），其余仍用 AKShare。
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional

import pandas as pd

from astrbot.api import logger

from ..eastmoney_api import get_api as get_eastmoney_api

AK_TIMEOUT = 90.0
NAMES_CACHE_TTL_SEC = 600
ETF_CACHE_TTL_SEC = 600

_concept_names_cache: tuple[Optional[pd.DataFrame], float] = (None, 0.0)
_industry_names_cache: tuple[Optional[pd.DataFrame], float] = (None, 0.0)
_etf_spot_cache: tuple[Optional[pd.DataFrame], float] = (None, 0.0)


async def _to_thread(fn, *args, **kwargs):
    return await asyncio.wait_for(
        asyncio.to_thread(fn, *args, **kwargs),
        timeout=AK_TIMEOUT,
    )


async def fetch_concept_names_df() -> Optional[pd.DataFrame]:
    global _concept_names_cache
    now = time.monotonic()
    cached, ts = _concept_names_cache
    if cached is not None and ( now - ts) < NAMES_CACHE_TTL_SEC:
        return cached
    try:
        import akshare as ak

        df = await _to_thread(ak.stock_board_concept_name_em)
    except Exception as e:
        logger.error(f"stock_board_concept_name_em: {e}")
        raise
    if df is None or len(df) == 0:
        return None
    _concept_names_cache = (df, now)
    return df


async def fetch_industry_names_df() -> Optional[pd.DataFrame]:
    global _industry_names_cache
    now = time.monotonic()
    cached, ts = _industry_names_cache
    if cached is not None and (now - ts) < NAMES_CACHE_TTL_SEC:
        return cached
    try:
        api = get_eastmoney_api()
        df = await asyncio.wait_for(
            api.get_stock_board_industry_name_em(),
            timeout=AK_TIMEOUT,
        )
    except Exception as e:
        logger.error(f"get_stock_board_industry_name_em: {e}")
        raise
    if df is None or len(df) == 0:
        return None
    _industry_names_cache = (df, now)
    return df


async def fetch_concept_cons(symbol: str) -> Optional[pd.DataFrame]:
    try:
        import akshare as ak

        df = await _to_thread(ak.stock_board_concept_cons_em, symbol)
    except IndexError:
        logger.warning(f"概念板块未匹配名称: {symbol!r}")
        return None
    except Exception as e:
        logger.error(f"stock_board_concept_cons_em({symbol!r}): {e}")
        raise
    if df is None or len(df) == 0:
        return None
    return df


async def fetch_industry_cons(symbol: str) -> Optional[pd.DataFrame]:
    try:
        api = get_eastmoney_api()
        df = await asyncio.wait_for(
            api.get_stock_board_industry_cons_em(symbol),
            timeout=AK_TIMEOUT,
        )
    except IndexError:
        logger.warning(f"行业板块未匹配名称: {symbol!r}")
        return None
    except Exception as e:
        logger.error(f"get_stock_board_industry_cons_em({symbol!r}): {e}")
        raise
    if df is None or len(df) == 0:
        return None
    return df


async def fetch_etf_spot_df() -> Optional[pd.DataFrame]:
    global _etf_spot_cache
    now = time.monotonic()
    cached, ts = _etf_spot_cache
    if cached is not None and (now - ts) < ETF_CACHE_TTL_SEC:
        return cached
    try:
        import akshare as ak

        df = await _to_thread(ak.fund_etf_spot_em)
    except Exception as e:
        logger.error(f"fund_etf_spot_em: {e}")
        raise
    if df is None or len(df) == 0:
        return None
    _etf_spot_cache = (df, now)
    return df


def filter_board_names_by_keyword(df: pd.DataFrame, keyword: str) -> pd.DataFrame:
    if df is None or len(df) == 0:
        return df
    kw = (keyword or "").strip()
    if not kw:
        return df.iloc[0:0]
    col = "板块名称" if "板块名称" in df.columns else None
    if not col:
        for c in df.columns:
            if df[c].dtype == object:
                col = c
                break
    if not col:
        return df.iloc[0:0]
    mask = df[col].astype(str).str.contains(kw, case=False, na=False)
    return df.loc[mask]


def filter_etf_by_keyword(df: pd.DataFrame, keyword: str) -> pd.DataFrame:
    if df is None or len(df) == 0:
        return df
    kw = (keyword or "").strip()
    if not kw:
        return df.iloc[0:0]
    name_m = (
        df["名称"].astype(str).str.contains(kw, case=False, na=False)
        if "名称" in df.columns
        else pd.Series(False, index=df.index)
    )
    code_m = (
        df["代码"].astype(str).str.contains(kw, case=False, na=False)
        if "代码" in df.columns
        else pd.Series(False, index=df.index)
    )
    return df.loc[name_m | code_m]
