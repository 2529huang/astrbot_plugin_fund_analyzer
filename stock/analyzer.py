"""
A股股票分析器
提供A股实时行情查询、搜索等功能
支持多数据源和网络重试机制
"""

import asyncio
import math
from datetime import datetime
from typing import Any

from astrbot.api import logger

from .models import StockInfo

# 默认超时时间（秒）
DEFAULT_TIMEOUT = 60
# A股实时行情缓存有效期（秒）
STOCK_CACHE_TTL = 600  # 10分钟
# 网络请求最大重试次数
MAX_RETRIES = 3
# 重试间隔（秒）
RETRY_DELAY = 2


class StockAnalyzer:
    """A股股票分析器"""

    def __init__(self):
        self._ak = None
        self._pd = None
        self._initialized = False
        # 缓存 A 股实时行情数据
        self._stock_cache = None
        self._stock_cache_time = None
        # 当前使用的数据源
        self._current_source = "eastmoney"  # 可选: eastmoney, sina

    async def _ensure_init(self):
        """确保akshare已初始化"""
        if not self._initialized:
            try:
                import akshare as ak
                import pandas as pd

                self._ak = ak
                self._pd = pd
                self._initialized = True
                logger.info("StockAnalyzer: AKShare 库初始化成功")
            except ImportError as e:
                logger.error(f"StockAnalyzer: AKShare 库导入失败: {e}")
                raise ImportError("请先安装 akshare 库: pip install akshare")

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        """安全地将值转换为float，处理NaN和None"""
        if value is None:
            return default
        try:
            if isinstance(value, float) and math.isnan(value):
                return default
            result = float(value)
            if math.isnan(result):
                return default
            return result
        except (ValueError, TypeError):
            return default

    async def _fetch_stock_data_eastmoney(self):
        """从东方财富获取A股实时行情数据"""
        logger.info("尝试从东方财富获取A股实时行情数据...")
        df = await asyncio.wait_for(
            asyncio.to_thread(self._ak.stock_zh_a_spot_em),
            timeout=DEFAULT_TIMEOUT,
        )
        return df

    async def _fetch_stock_data_sina(self):
        """从新浪获取A股实时行情数据（备用数据源）"""
        logger.info("尝试从新浪获取A股实时行情数据...")
        df = await asyncio.wait_for(
            asyncio.to_thread(self._ak.stock_zh_a_spot),
            timeout=DEFAULT_TIMEOUT,
        )
        return df

    async def _get_stock_data_with_retry(self):
        """获取A股实时行情数据，带重试和备用数据源"""
        last_error = None

        # 首先尝试东方财富数据源
        for attempt in range(MAX_RETRIES):
            try:
                df = await self._fetch_stock_data_eastmoney()
                self._current_source = "eastmoney"
                logger.info(f"东方财富数据获取成功 (尝试 {attempt + 1}/{MAX_RETRIES})")
                return df
            except asyncio.TimeoutError:
                last_error = TimeoutError("东方财富数据获取超时")
                logger.warning(
                    f"东方财富数据获取超时 (尝试 {attempt + 1}/{MAX_RETRIES})"
                )
            except Exception as e:
                last_error = e
                logger.warning(
                    f"东方财富数据获取失败 (尝试 {attempt + 1}/{MAX_RETRIES}): {e}"
                )

            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY)

        # 东方财富失败，尝试新浪数据源
        logger.info("东方财富数据源不可用，切换到新浪数据源...")
        for attempt in range(MAX_RETRIES):
            try:
                df = await self._fetch_stock_data_sina()
                self._current_source = "sina"
                logger.info(f"新浪数据获取成功 (尝试 {attempt + 1}/{MAX_RETRIES})")
                return df
            except asyncio.TimeoutError:
                last_error = TimeoutError("新浪数据获取超时")
                logger.warning(f"新浪数据获取超时 (尝试 {attempt + 1}/{MAX_RETRIES})")
            except Exception as e:
                last_error = e
                logger.warning(
                    f"新浪数据获取失败 (尝试 {attempt + 1}/{MAX_RETRIES}): {e}"
                )

            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY)

        # 所有数据源都失败
        raise last_error or Exception("所有数据源均不可用")

    async def _get_stock_data(self):
        """获取A股实时行情数据（带缓存，10分钟有效期）"""
        await self._ensure_init()
        now = datetime.now()

        # 检查缓存是否有效
        if (
            self._stock_cache is not None
            and self._stock_cache_time is not None
            and (now - self._stock_cache_time).total_seconds() < STOCK_CACHE_TTL
        ):
            cache_age = int((now - self._stock_cache_time).total_seconds())
            logger.debug(f"使用缓存的A股行情数据 (缓存时间: {cache_age}秒)")
            return self._stock_cache

        # 缓存过期或不存在，重新获取
        try:
            df = await self._get_stock_data_with_retry()
            # 更新缓存
            self._stock_cache = df
            self._stock_cache_time = now
            logger.info(
                f"A股实时行情数据获取成功，共 {len(df)} 只股票 (数据源: {self._current_source})"
            )
            return df
        except Exception as e:
            logger.error(f"获取A股行情数据失败: {e}")
            # 如果有旧缓存，返回旧缓存
            if self._stock_cache is not None:
                logger.warning("使用过期的缓存数据")
                return self._stock_cache
            raise

    def _parse_stock_row_eastmoney(self, row, stock_code: str) -> StockInfo:
        """解析东方财富数据格式"""
        return StockInfo(
            code=str(row["代码"]) if "代码" in row.index else stock_code,
            name=str(row["名称"]) if "名称" in row.index else "",
            latest_price=self._safe_float(
                row["最新价"] if "最新价" in row.index else 0
            ),
            change_amount=self._safe_float(
                row["涨跌额"] if "涨跌额" in row.index else 0
            ),
            change_rate=self._safe_float(row["涨跌幅"] if "涨跌幅" in row.index else 0),
            open_price=self._safe_float(row["今开"] if "今开" in row.index else 0),
            high_price=self._safe_float(row["最高"] if "最高" in row.index else 0),
            low_price=self._safe_float(row["最低"] if "最低" in row.index else 0),
            prev_close=self._safe_float(row["昨收"] if "昨收" in row.index else 0),
            volume=self._safe_float(row["成交量"] if "成交量" in row.index else 0),
            amount=self._safe_float(row["成交额"] if "成交额" in row.index else 0),
            amplitude=self._safe_float(row["振幅"] if "振幅" in row.index else 0),
            turnover_rate=self._safe_float(
                row["换手率"] if "换手率" in row.index else 0
            ),
            pe_ratio=self._safe_float(
                row["市盈率-动态"] if "市盈率-动态" in row.index else 0
            ),
            pb_ratio=self._safe_float(row["市净率"] if "市净率" in row.index else 0),
            total_market_cap=self._safe_float(
                row["总市值"] if "总市值" in row.index else 0
            ),
            circulating_market_cap=self._safe_float(
                row["流通市值"] if "流通市值" in row.index else 0
            ),
        )

    def _parse_stock_row_sina(self, row, stock_code: str) -> StockInfo:
        """解析新浪数据格式"""
        # 新浪数据字段名称略有不同
        return StockInfo(
            code=str(row["代码"]) if "代码" in row.index else stock_code,
            name=str(row["名称"]) if "名称" in row.index else "",
            latest_price=self._safe_float(row.get("最新价", row.get("trade", 0))),
            change_amount=self._safe_float(
                row.get("涨跌额", row.get("pricechange", 0))
            ),
            change_rate=self._safe_float(
                row.get("涨跌幅", row.get("changepercent", 0))
            ),
            open_price=self._safe_float(row.get("今开", row.get("open", 0))),
            high_price=self._safe_float(row.get("最高", row.get("high", 0))),
            low_price=self._safe_float(row.get("最低", row.get("low", 0))),
            prev_close=self._safe_float(row.get("昨收", row.get("settlement", 0))),
            volume=self._safe_float(row.get("成交量", row.get("volume", 0))),
            amount=self._safe_float(row.get("成交额", row.get("amount", 0))),
            amplitude=self._safe_float(row.get("振幅", 0)),
            turnover_rate=self._safe_float(
                row.get("换手率", row.get("turnoverratio", 0))
            ),
            pe_ratio=self._safe_float(row.get("市盈率-动态", row.get("per", 0))),
            pb_ratio=self._safe_float(row.get("市净率", row.get("pb", 0))),
            total_market_cap=self._safe_float(row.get("总市值", row.get("mktcap", 0))),
            circulating_market_cap=self._safe_float(
                row.get("流通市值", row.get("nmc", 0))
            ),
        )

    async def get_stock_realtime(self, stock_code: str) -> StockInfo | None:
        """
        获取A股实时行情

        Args:
            stock_code: 股票代码（如 000001、600519）

        Returns:
            StockInfo 对象或 None
        """
        # 确保股票代码是字符串格式
        stock_code = str(stock_code).strip()
        logger.debug(f"查询股票代码: '{stock_code}'")

        try:
            # 获取A股实时行情（使用缓存）
            df = await self._get_stock_data()

            # 查找指定股票
            stock_data = df[df["代码"] == stock_code]

            if stock_data.empty:
                logger.warning(f"未找到股票代码: {stock_code}")
                return None

            row = stock_data.iloc[0]

            # 根据数据源使用不同的解析方法
            if self._current_source == "sina":
                return self._parse_stock_row_sina(row, stock_code)
            else:
                return self._parse_stock_row_eastmoney(row, stock_code)

        except Exception as e:
            logger.error(f"获取A股实时行情失败: {e}")
            return None

    async def search_stock(self, keyword: str, max_results: int = 10) -> list[dict]:
        """
        搜索A股股票

        Args:
            keyword: 搜索关键词（股票名称或代码）
            max_results: 最大返回数量

        Returns:
            匹配的股票列表
        """
        try:
            df = await self._get_stock_data()

            # 搜索匹配的股票（代码或名称包含关键词）
            mask = df["代码"].str.contains(keyword, case=False, na=False) | df[
                "名称"
            ].str.contains(keyword, case=False, na=False)
            results = df[mask].head(max_results)

            return [
                {
                    "code": str(row["代码"]),
                    "name": str(row["名称"]),
                    "price": self._safe_float(row.get("最新价", row.get("trade", 0))),
                    "change_rate": self._safe_float(
                        row.get("涨跌幅", row.get("changepercent", 0))
                    ),
                }
                for _, row in results.iterrows()
            ]

        except Exception as e:
            logger.error(f"搜索股票失败: {e}")
            return []

    def get_cache_info(self) -> dict:
        """获取缓存信息"""
        if self._stock_cache is None:
            return {"cached": False}

        cache_age = 0
        if self._stock_cache_time:
            cache_age = int((datetime.now() - self._stock_cache_time).total_seconds())

        return {
            "cached": True,
            "cache_age_seconds": cache_age,
            "cache_ttl_seconds": STOCK_CACHE_TTL,
            "stock_count": len(self._stock_cache)
            if self._stock_cache is not None
            else 0,
            "data_source": self._current_source,
        }

    def clear_cache(self):
        """清除缓存"""
        self._stock_cache = None
        self._stock_cache_time = None
        logger.info("股票数据缓存已清除")
