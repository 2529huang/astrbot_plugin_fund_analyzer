"""
AstrBot 基金数据分析插件
使用 AKShare 开源库获取基金数据，进行分析和展示
默认分析：国投瑞银白银期货(LOF)A (代码: 161226)
"""

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register

# 导入股票分析模块
from .stock import StockAnalyzer, StockInfo

# 默认超时时间（秒）- AKShare获取LOF数据需要较长时间
DEFAULT_TIMEOUT = 120  # 2分钟
# 数据缓存有效期（秒）
CACHE_TTL = 300  # 5分钟


@dataclass
class FundInfo:
    """基金基本信息"""

    code: str  # 基金代码
    name: str  # 基金名称
    latest_price: float  # 最新价
    change_amount: float  # 涨跌额
    change_rate: float  # 涨跌幅
    open_price: float  # 开盘价
    high_price: float  # 最高价
    low_price: float  # 最低价
    prev_close: float  # 昨收
    volume: float  # 成交量
    amount: float  # 成交额
    turnover_rate: float  # 换手率

    @property
    def change_symbol(self) -> str:
        """涨跌符号"""
        if self.change_rate > 0:
            return "📈"
        elif self.change_rate < 0:
            return "📉"
        return "➡️"

    @property
    def trend_emoji(self) -> str:
        """趋势表情"""
        if self.change_rate >= 3:
            return "🚀"
        elif self.change_rate >= 1:
            return "↗️"
        elif self.change_rate > 0:
            return "↑"
        elif self.change_rate <= -3:
            return "💥"
        elif self.change_rate <= -1:
            return "↘️"
        elif self.change_rate < 0:
            return "↓"
        return "➡️"


class FundAnalyzer:
    """基金分析核心类"""

    # 默认基金代码：国投瑞银白银期货(LOF)A
    DEFAULT_FUND_CODE = "161226"
    DEFAULT_FUND_NAME = "国投瑞银白银期货(LOF)A"

    def __init__(self):
        self._ak = None
        self._pd = None
        self._initialized = False
        # 缓存 LOF 基金列表数据
        self._lof_cache = None
        self._lof_cache_time = None

    async def _ensure_init(self):
        """确保akshare已初始化"""
        if not self._initialized:
            try:
                import akshare as ak
                import pandas as pd

                self._ak = ak
                self._pd = pd
                self._initialized = True
                logger.info("AKShare 库初始化成功")
            except ImportError as e:
                logger.error(f"AKShare 库导入失败: {e}")
                raise ImportError("请先安装 akshare 库: pip install akshare")

    def _safe_float(self, value, default: float = 0.0) -> float:
        """安全地将值转换为float，处理NaN和None"""
        if value is None:
            return default
        try:
            import math

            if isinstance(value, float) and math.isnan(value):
                return default
            result = float(value)
            if math.isnan(result):
                return default
            return result
        except (ValueError, TypeError):
            return default

    async def _get_lof_data(self):
        """获取LOF基金数据（带缓存）"""
        now = datetime.now()

        # 检查缓存是否有效
        if (
            self._lof_cache is not None
            and self._lof_cache_time is not None
            and (now - self._lof_cache_time).total_seconds() < CACHE_TTL
        ):
            logger.debug("使用缓存的LOF基金数据")
            return self._lof_cache

        # 缓存过期或不存在，重新获取
        logger.info("正在从东方财富获取LOF基金数据，请稍候...")
        try:
            df = await asyncio.wait_for(
                asyncio.to_thread(self._ak.fund_lof_spot_em),
                timeout=DEFAULT_TIMEOUT,
            )
            # 更新缓存
            self._lof_cache = df
            self._lof_cache_time = now
            logger.info(f"LOF基金数据获取成功，共 {len(df)} 只基金")
            return df
        except asyncio.TimeoutError:
            logger.error(f"获取LOF基金数据超时 (>{DEFAULT_TIMEOUT}秒)")
            # 如果有旧缓存，返回旧缓存
            if self._lof_cache is not None:
                logger.warning("使用过期的缓存数据")
                return self._lof_cache
            raise TimeoutError("数据获取超时，请稍后重试")

    async def get_lof_realtime(self, fund_code: str = None) -> FundInfo | None:
        """
        获取LOF基金实时行情

        Args:
            fund_code: 基金代码，默认为国投瑞银白银期货LOF

        Returns:
            FundInfo 对象或 None
        """
        await self._ensure_init()

        if fund_code is None:
            fund_code = self.DEFAULT_FUND_CODE

        try:
            # 获取LOF基金实时行情（使用缓存）
            df = await self._get_lof_data()

            # 确保基金代码是字符串格式
            fund_code = str(fund_code).strip()
            logger.debug(f"查询基金代码: '{fund_code}', 类型: {type(fund_code)}")

            # 查找指定基金
            fund_data = df[df["代码"] == fund_code]

            if fund_data.empty:
                logger.warning(f"未找到基金代码: {fund_code}")
                return None

            row = fund_data.iloc[0]

            return FundInfo(
                code=str(row["代码"]) if "代码" in row.index else fund_code,
                name=str(row["名称"]) if "名称" in row.index else "",
                latest_price=self._safe_float(
                    row["最新价"] if "最新价" in row.index else 0
                ),
                change_amount=self._safe_float(
                    row["涨跌额"] if "涨跌额" in row.index else 0
                ),
                change_rate=self._safe_float(
                    row["涨跌幅"] if "涨跌幅" in row.index else 0
                ),
                open_price=self._safe_float(
                    row["开盘价"] if "开盘价" in row.index else 0
                ),
                high_price=self._safe_float(
                    row["最高价"] if "最高价" in row.index else 0
                ),
                low_price=self._safe_float(
                    row["最低价"] if "最低价" in row.index else 0
                ),
                prev_close=self._safe_float(row["昨收"] if "昨收" in row.index else 0),
                volume=self._safe_float(row["成交量"] if "成交量" in row.index else 0),
                amount=self._safe_float(row["成交额"] if "成交额" in row.index else 0),
                turnover_rate=self._safe_float(
                    row["换手率"] if "换手率" in row.index else 0
                ),
            )

        except Exception as e:
            logger.error(f"获取LOF基金实时行情失败: {e}")
            return None

    async def get_lof_history(
        self, fund_code: str = None, days: int = 30, adjust: str = "qfq"
    ) -> list[dict] | None:
        """
        获取LOF基金历史行情

        Args:
            fund_code: 基金代码
            days: 获取天数
            adjust: 复权类型 qfq-前复权, hfq-后复权, ""-不复权

        Returns:
            历史数据列表或 None
        """
        await self._ensure_init()

        if fund_code is None:
            fund_code = self.DEFAULT_FUND_CODE

        # 确保基金代码是字符串格式
        fund_code = str(fund_code).strip()

        try:
            end_date = datetime.now()
            # 使用 days * 3 以覆盖长假期（如春节、国庆），确保有足够交易日
            # 额外加 60 天作为技术指标计算的预热数据
            start_date = end_date - timedelta(days=days * 3 + 60)

            df = await asyncio.wait_for(
                asyncio.to_thread(
                    self._ak.fund_lof_hist_em,
                    symbol=fund_code,
                    period="daily",
                    start_date=start_date.strftime("%Y%m%d"),
                    end_date=end_date.strftime("%Y%m%d"),
                    adjust=adjust,
                ),
                timeout=DEFAULT_TIMEOUT,
            )

            if df is None or df.empty:
                return None

            # 只取最近N天
            df = df.tail(days)

            result = []
            for _, row in df.iterrows():
                result.append(
                    {
                        "date": str(row["日期"]) if "日期" in row.index else "",
                        "open": self._safe_float(
                            row["开盘"] if "开盘" in row.index else 0
                        ),
                        "close": self._safe_float(
                            row["收盘"] if "收盘" in row.index else 0
                        ),
                        "high": self._safe_float(
                            row["最高"] if "最高" in row.index else 0
                        ),
                        "low": self._safe_float(
                            row["最低"] if "最低" in row.index else 0
                        ),
                        "volume": self._safe_float(
                            row["成交量"] if "成交量" in row.index else 0
                        ),
                        "amount": self._safe_float(
                            row["成交额"] if "成交额" in row.index else 0
                        ),
                        "change_rate": self._safe_float(
                            row["涨跌幅"] if "涨跌幅" in row.index else 0
                        ),
                    }
                )

            return result

        except asyncio.TimeoutError:
            logger.error(f"获取LOF基金历史行情超时: {fund_code}")
            return None
        except Exception as e:
            logger.error(f"获取LOF基金历史行情失败: {e}")
            return None

    async def search_fund(self, keyword: str) -> list[dict]:
        """
        搜索LOF基金

        Args:
            keyword: 搜索关键词（基金名称或代码）

        Returns:
            匹配的基金列表
        """
        await self._ensure_init()

        try:
            df = await self._get_lof_data()

            # 搜索代码或名称包含关键词的基金
            mask = df["代码"].str.contains(keyword, na=False) | df["名称"].str.contains(
                keyword, na=False
            )

            results = df[mask].head(10)  # 最多返回10条

            fund_list = []
            for _, row in results.iterrows():
                fund_list.append(
                    {
                        "code": str(row["代码"]) if "代码" in row.index else "",
                        "name": str(row["名称"]) if "名称" in row.index else "",
                        "latest_price": self._safe_float(
                            row["最新价"] if "最新价" in row.index else 0
                        ),
                        "change_rate": self._safe_float(
                            row["涨跌幅"] if "涨跌幅" in row.index else 0
                        ),
                    }
                )

            return fund_list

        except Exception as e:
            logger.error(f"搜索基金失败: {e}")
            return []

    def calculate_technical_indicators(
        self, history_data: list[dict]
    ) -> dict[str, Any]:
        """
        计算技术指标（委托给 quant.py 中的完整实现）

        Args:
            history_data: 历史数据列表

        Returns:
            技术指标字典
        """
        if not history_data or len(history_data) < 5:
            return {}

        # 使用 quant.py 中的量化分析器
        from .ai_analyzer.quant import QuantAnalyzer

        quant = QuantAnalyzer()
        indicators = quant.calculate_all_indicators(history_data)

        closes = [d["close"] for d in history_data]
        current_price = closes[-1] if closes else 0

        # 转换为兼容格式
        return {
            "ma5": round(indicators.ma5, 4) if indicators.ma5 else None,
            "ma10": round(indicators.ma10, 4) if indicators.ma10 else None,
            "ma20": round(indicators.ma20, 4) if indicators.ma20 else None,
            "return_5d": None,  # 由 quant.py 的绩效分析提供
            "return_10d": None,
            "return_20d": None,
            "volatility": None,
            "high_20d": max(closes[-20:]) if len(closes) >= 20 else max(closes),
            "low_20d": min(closes[-20:]) if len(closes) >= 20 else min(closes),
            "trend": indicators.signal,
            "current_price": current_price,
        }


# 贵金属价格缓存TTL（15分钟）
METAL_CACHE_TTL = 900


@register(
    "astrbot_plugin_fund_analyzer",
    "2529huang",
    "基金数据分析插件 - 使用AKShare获取LOF/ETF基金数据",
    "1.0.0",
)
class FundAnalyzerPlugin(Star):
    """基金分析插件主类"""

    # 用户设置文件名
    SETTINGS_FILE = "user_settings.json"

    def __init__(self, context: Context):
        super().__init__(context)
        self.analyzer = FundAnalyzer()
        # 初始化股票分析器
        self.stock_analyzer = StockAnalyzer()
        # 延迟初始化 AI 分析器
        self._ai_analyzer = None
        # 获取插件数据目录
        self._data_dir = Path(StarTools.get_data_dir("fund_analyzer"))
        self._data_dir.mkdir(parents=True, exist_ok=True)
        # 加载用户设置
        self.user_fund_settings: dict[str, str] = self._load_user_settings()
        # 贵金属价格缓存
        self._metal_cache: dict = {}
        self._metal_cache_time: datetime | None = None
        # 检查依赖
        self._check_dependencies()
        logger.info("基金分析插件已加载")

    def _check_dependencies(self):
        """检查必要依赖是否已安装"""
        try:
            import akshare  # noqa: F401
            import pandas  # noqa: F401
        except ImportError as e:
            logger.warning(
                f"基金分析插件依赖未完全安装: {e}\n请执行: pip install akshare pandas"
            )

    def _load_user_settings(self) -> dict[str, str]:
        """从文件加载用户设置"""
        settings_path = self._data_dir / self.SETTINGS_FILE
        if settings_path.exists():
            try:
                with open(settings_path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"加载用户设置失败: {e}")
        return {}

    def _save_user_settings(self):
        """保存用户设置到文件"""
        settings_path = self._data_dir / self.SETTINGS_FILE
        try:
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(self.user_fund_settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存用户设置失败: {e}")

    @property
    def ai_analyzer(self):
        """延迟初始化 AI 分析器"""
        if self._ai_analyzer is None:
            from .ai_analyzer import AIFundAnalyzer

            self._ai_analyzer = AIFundAnalyzer(self.context)
        return self._ai_analyzer

    def _get_user_fund(self, user_id: str) -> str:
        """获取用户设置的默认基金代码"""
        return self.user_fund_settings.get(user_id, FundAnalyzer.DEFAULT_FUND_CODE)

    def _normalize_fund_code(self, code: str | int | None) -> str | None:
        """标准化基金代码，补齐前导0到6位
        
        Args:
            code: 基金代码，可能是字符串、整数或None
            
        Returns:
            标准化后的6位基金代码字符串，如果输入为None则返回None
        """
        if code is None:
            return None
        # 转换为字符串并去除空格
        code_str = str(code).strip()
        if not code_str:
            return None
        # 补齐前导0到6位
        return code_str.zfill(6)

    def _format_fund_info(self, info: FundInfo) -> str:
        """格式化基金信息为文本"""
        # 价格为0通常表示暂无数据（原始数据为NaN）
        if info.latest_price == 0:
            return f"""
📊 【{info.name}】
━━━━━━━━━━━━━━━━━
⚠️ 暂无实时行情数据
━━━━━━━━━━━━━━━━━
🔢 基金代码: {info.code}
💡 可能原因: 停牌/休市/数据源未更新
⏰ 查询时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
""".strip()

        change_color = (
            "🔴" if info.change_rate < 0 else "🟢" if info.change_rate > 0 else "⚪"
        )

        return f"""
📊 【{info.name}】实时行情 {info.trend_emoji}
━━━━━━━━━━━━━━━━━
💰 最新价: {info.latest_price:.4f}
{change_color} 涨跌额: {info.change_amount:+.4f}
{change_color} 涨跌幅: {info.change_rate:+.2f}%
━━━━━━━━━━━━━━━━━
📈 今开: {info.open_price:.4f}
📊 最高: {info.high_price:.4f}
📉 最低: {info.low_price:.4f}
📋 昨收: {info.prev_close:.4f}
━━━━━━━━━━━━━━━━━
📦 成交量: {info.volume:,.0f}
💵 成交额: {info.amount:,.2f}
🔄 换手率: {info.turnover_rate:.2f}%
━━━━━━━━━━━━━━━━━
🔢 基金代码: {info.code}
⏰ 更新时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
""".strip()

    def _format_analysis(self, info: FundInfo, indicators: dict) -> str:
        """格式化技术分析结果"""
        if not indicators:
            return "📊 暂无足够数据进行技术分析"

        trend_emoji = {
            "强势上涨": "🚀",
            "上涨趋势": "📈",
            "强势下跌": "💥",
            "下跌趋势": "📉",
            "震荡": "↔️",
        }.get(indicators.get("trend", "震荡"), "❓")

        ma_status = []
        current = indicators.get("current_price", 0)
        if indicators.get("ma5"):
            status = "上" if current > indicators["ma5"] else "下"
            ma_status.append(f"MA5({indicators['ma5']:.4f}){status}")
        if indicators.get("ma10"):
            status = "上" if current > indicators["ma10"] else "下"
            ma_status.append(f"MA10({indicators['ma10']:.4f}){status}")
        if indicators.get("ma20"):
            status = "上" if current > indicators["ma20"] else "下"
            ma_status.append(f"MA20({indicators['ma20']:.4f}){status}")

        return f"""
📈 【{info.name}】技术分析
━━━━━━━━━━━━━━━━━
{trend_emoji} 趋势判断: {indicators.get("trend", "未知")}
━━━━━━━━━━━━━━━━━
📊 均线分析:
  • {" | ".join(ma_status) if ma_status else "数据不足"}
━━━━━━━━━━━━━━━━━
📈 区间收益率:
  • 5日收益: {indicators.get("return_5d", "--"):+.2f}%
  • 10日收益: {indicators.get("return_10d", "--"):+.2f}%
  • 20日收益: {indicators.get("return_20d", "--"):+.2f}%
━━━━━━━━━━━━━━━━━
📉 波动分析:
  • 20日波动率: {indicators.get("volatility", "--"):.4f}
  • 20日最高: {indicators.get("high_20d", "--"):.4f}
  • 20日最低: {indicators.get("low_20d", "--"):.4f}
━━━━━━━━━━━━━━━━━
💡 投资建议: 请结合自身风险承受能力谨慎投资
""".strip()

    def _format_stock_info(self, info: StockInfo) -> str:
        """格式化A股股票信息为文本"""
        # 价格为0通常表示暂无数据
        if info.latest_price == 0:
            return f"""
📊 【{info.name}】
━━━━━━━━━━━━━━━━━
⚠️ 暂无实时行情数据
━━━━━━━━━━━━━━━━━
🔢 股票代码: {info.code}
💡 可能原因: 停牌/休市/数据源未更新
⏰ 查询时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
""".strip()

        change_color = (
            "🔴" if info.change_rate < 0 else "🟢" if info.change_rate > 0 else "⚪"
        )

        # 格式化市值（转换为亿元）
        def format_market_cap(value):
            if value >= 100000000:  # 亿元
                return f"{value / 100000000:.2f}亿"
            elif value >= 10000:  # 万元
                return f"{value / 10000:.2f}万"
            return f"{value:.2f}"

        return f"""
📊 【{info.name}】实时行情 {info.trend_emoji}
━━━━━━━━━━━━━━━━━
💰 最新价: {info.latest_price:.2f}
{change_color} 涨跌额: {info.change_amount:+.2f}
{change_color} 涨跌幅: {info.change_rate:+.2f}%
📏 振幅: {info.amplitude:.2f}%
━━━━━━━━━━━━━━━━━
📈 今开: {info.open_price:.2f}
📊 最高: {info.high_price:.2f}
📉 最低: {info.low_price:.2f}
📋 昨收: {info.prev_close:.2f}
━━━━━━━━━━━━━━━━━
📦 成交量: {info.volume:,.0f}手
💵 成交额: {format_market_cap(info.amount)}
🔄 换手率: {info.turnover_rate:.2f}%
━━━━━━━━━━━━━━━━━
📈 市盈率(动态): {info.pe_ratio:.2f}
📊 市净率: {info.pb_ratio:.2f}
💰 总市值: {format_market_cap(info.total_market_cap)}
💎 流通市值: {format_market_cap(info.circulating_market_cap)}
━━━━━━━━━━━━━━━━━
🔢 股票代码: {info.code}
⏰ 更新时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
💡 数据缓存10分钟，仅供参考
""".strip()

    async def _fetch_precious_metal_prices(self) -> dict:
        """
        从NowAPI获取上海黄金交易所贵金属价格
        返回包含金价和银价的字典
        API文档: https://www.nowapi.com/api/finance.shgold
        黄金使用1301，白银使用1302，需分开调用
        缓存15分钟
        """
        import aiohttp

        # 检查缓存是否有效（15分钟）
        now = datetime.now()
        if (
            self._metal_cache
            and self._metal_cache_time is not None
            and (now - self._metal_cache_time).total_seconds() < METAL_CACHE_TTL
        ):
            logger.debug("使用贵金属价格缓存")
            return self._metal_cache

        # NowAPI 接口配置
        api_url = "http://api.k780.com/"
        base_params = {
            "app": "finance.gold_price",
            "appkey": "78365",
            "sign": "776f93b557ce6e6afeb860b103a587c7",
            "format": "json",
        }

        prices = {}

        async def fetch_metal(gold_id: str, key: str, name: str) -> dict | None:
            """获取单个金属品种的价格"""
            params = {**base_params, "goldid": gold_id}
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        api_url, params=params, timeout=aiohttp.ClientTimeout(total=30)
                    ) as response:
                        if response.status != 200:
                            logger.error(f"获取{name}价格失败: HTTP {response.status}")
                            return None

                        data = await response.json()

                        if data.get("success") != "1":
                            error_msg = data.get("msg", "未知错误")
                            logger.error(f"NowAPI返回错误({name}): {error_msg}")
                            return None

                        result = data.get("result", {})
                        dt_list = result.get("dtList", {})

                        if gold_id in dt_list:
                            metal_data = dt_list[gold_id]
                            return {
                                "name": metal_data.get("varietynm", name),
                                "variety": metal_data.get("variety", ""),
                                "price": float(metal_data.get("last_price", 0) or 0),
                                "buy_price": float(metal_data.get("buy_price", 0) or 0),
                                "sell_price": float(
                                    metal_data.get("sell_price", 0) or 0
                                ),
                                "high": float(metal_data.get("high_price", 0) or 0),
                                "low": float(metal_data.get("low_price", 0) or 0),
                                "open": float(metal_data.get("open_price", 0) or 0),
                                "prev_close": float(
                                    metal_data.get("yesy_price", 0) or 0
                                ),
                                "change": float(metal_data.get("change_price", 0) or 0),
                                "change_rate": metal_data.get("change_margin", "0%"),
                                "update_time": metal_data.get("uptime", ""),
                            }
                        return None
            except Exception as e:
                logger.error(f"获取{name}价格出错: {e}")
                return None

        try:
            # 分开调用黄金(1301)和白银(1302)
            gold_data = await fetch_metal("1051", "au_td", "黄金")
            if gold_data:
                prices["au_td"] = gold_data

            silver_data = await fetch_metal("1052", "ag_td", "白银")
            if silver_data:
                prices["ag_td"] = silver_data

            # 更新缓存
            if prices:
                self._metal_cache = prices
                self._metal_cache_time = now
                logger.info("贵金属价格已更新并缓存15分钟")

            return prices

        except Exception as e:
            logger.error(f"获取贵金属价格出错: {e}")
            # 如果有旧缓存，返回旧数据
            if self._metal_cache:
                logger.info("使用过期的贵金属缓存数据")
                return self._metal_cache
            return {}

    def _format_precious_metal_prices(self, prices: dict) -> str:
        """格式化贵金属价格信息"""
        if not prices:
            return "❌ 获取贵金属价格失败，请稍后重试"

        def parse_change_rate(rate_str: str) -> float:
            """解析涨跌幅字符串，如 '1.5%' -> 1.5"""
            try:
                return float(rate_str.replace("%", "").replace("+", ""))
            except (ValueError, AttributeError):
                return 0.0

        def format_item(data: dict, unit: str = "元/克") -> str:
            if not data:
                return "  暂无数据"

            change_rate = parse_change_rate(data.get("change_rate", "0%"))
            change_emoji = (
                "🔴" if change_rate < 0 else "🟢" if change_rate > 0 else "⚪"
            )
            trend_emoji = "📈" if change_rate > 0 else "📉" if change_rate < 0 else "➡️"

            return f"""  {trend_emoji} 最新价: {data["price"]:.2f} {unit}
  {change_emoji} 涨跌: {data.get("change", 0):+.2f} ({data.get("change_rate", "0%")})
  📊 今开: {data.get("open", 0):.2f} | 最高: {data.get("high", 0):.2f} | 最低: {data.get("low", 0):.2f}
  💹 买入: {data.get("buy_price", 0):.2f} | 卖出: {data.get("sell_price", 0):.2f}"""

        lines = [
            "💰 今日贵金属行情（国际现货）",
            "━━━━━━━━━━━━━━━━━",
        ]

        # 黄金T+D
        if "au_td" in prices:
            lines.append("🥇 黄金")
            lines.append(format_item(prices["au_td"], "美元/盎司"))
            if prices["au_td"].get("update_time"):
                lines.append(f"  🕐 更新: {prices['au_td']['update_time']}")
            lines.append("")

        # 白银T+D
        if "ag_td" in prices:
            lines.append("🥈 白银")
            lines.append(format_item(prices["ag_td"], "美元/盎司"))
            if prices["ag_td"].get("update_time"):
                lines.append(f"  🕐 更新: {prices['ag_td']['update_time']}")
            lines.append("")

        lines.append("━━━━━━━━━━━━━━━━━")
        lines.append("📌 国际现货24小时交易")
        lines.append("💡 数据来源: NowAPI | 缓存15分钟")

        return "\n".join(lines)

    @filter.command("今日行情")
    async def today_market(self, event: AstrMessageEvent):
        """
        查询今日贵金属行情
        用法: 今日行情
        返回国际金价、银价及涨跌幅
        """
        try:
            yield event.plain_result("🔍 正在获取今日贵金属行情...")

            prices = await self._fetch_precious_metal_prices()

            if prices:
                yield event.plain_result(self._format_precious_metal_prices(prices))
            else:
                yield event.plain_result("❌ 获取贵金属行情失败，请稍后重试")

        except Exception as e:
            logger.error(f"获取今日行情出错: {e}")
            yield event.plain_result(f"❌ 获取行情失败: {str(e)}")

    @filter.command("股票")
    async def stock_query(self, event: AstrMessageEvent, code: str = None):
        """
        查询A股实时行情
        用法: 股票 <股票代码>
        示例: 股票 000001
        示例: 股票 600519
        """
        try:
            if not code:
                yield event.plain_result(
                    "❌ 请输入股票代码\n"
                    "💡 用法: 股票 <股票代码>\n"
                    "💡 示例: 股票 000001 (平安银行)\n"
                    "💡 示例: 股票 600519 (贵州茅台)"
                )
                return

            stock_code = str(code).strip()
            yield event.plain_result(f"🔍 正在查询股票 {stock_code} 的实时行情...")

            info = await self.stock_analyzer.get_stock_realtime(stock_code)

            if info:
                yield event.plain_result(self._format_stock_info(info))
            else:
                yield event.plain_result(
                    f"❌ 未找到股票代码 {stock_code}\n"
                    "💡 请使用「搜索股票 关键词」来搜索正确的股票代码\n"
                    "💡 示例: 搜索股票 茅台"
                )

        except ImportError:
            yield event.plain_result(
                "❌ AKShare 库未安装\n请管理员执行: pip install akshare"
            )
        except TimeoutError as e:
            yield event.plain_result(f"⏰ {str(e)}\n💡 数据源响应较慢，请稍后再试")
        except Exception as e:
            logger.error(f"查询股票行情出错: {e}")
            yield event.plain_result(f"❌ 查询失败: {str(e)}")

    @filter.command("搜索股票")
    async def search_stock(self, event: AstrMessageEvent, keyword: str = None):
        """
        搜索A股股票
        用法: 搜索股票 <关键词>
        示例: 搜索股票 茅台
        """
        try:
            if not keyword:
                yield event.plain_result(
                    "❌ 请输入搜索关键词\n"
                    "💡 用法: 搜索股票 <关键词>\n"
                    "💡 示例: 搜索股票 茅台"
                )
                return

            yield event.plain_result(f"🔍 正在搜索包含 '{keyword}' 的股票...")

            results = await self.stock_analyzer.search_stock(keyword)

            if not results:
                yield event.plain_result(f"❌ 未找到包含 '{keyword}' 的股票")
                return

            # 格式化搜索结果
            lines = [f"🔍 搜索结果: '{keyword}'", "━━━━━━━━━━━━━━━━━"]
            for i, stock in enumerate(results, 1):
                change_emoji = (
                    "🔴"
                    if stock["change_rate"] < 0
                    else "🟢"
                    if stock["change_rate"] > 0
                    else "⚪"
                )
                lines.append(
                    f"{i}. {stock['name']} ({stock['code']})\n"
                    f"   💰 {stock['price']:.2f} {change_emoji} {stock['change_rate']:+.2f}%"
                )
            lines.append("━━━━━━━━━━━━━━━━━")
            lines.append("💡 使用「股票 代码」查看详细行情")

            yield event.plain_result("\n".join(lines))

        except ImportError:
            yield event.plain_result(
                "❌ AKShare 库未安装\n请管理员执行: pip install akshare"
            )
        except TimeoutError as e:
            yield event.plain_result(f"⏰ {str(e)}\n💡 数据源响应较慢，请稍后再试")
        except Exception as e:
            logger.error(f"搜索股票出错: {e}")
            yield event.plain_result(f"❌ 搜索失败: {str(e)}")

    @filter.command("基金")
    async def fund_query(self, event: AstrMessageEvent, code: str = None):
        """
        查询基金实时行情
        用法: 基金 [基金代码]
        示例: 基金 161226
        """
        try:
            user_id = event.get_sender_id()
            # 标准化基金代码，补齐前导0
            normalized_code = self._normalize_fund_code(code)
            fund_code = normalized_code or self._get_user_fund(user_id)

            yield event.plain_result(f"🔍 正在查询基金 {fund_code} 的实时行情...")

            info = await self.analyzer.get_lof_realtime(fund_code)

            if info:
                yield event.plain_result(self._format_fund_info(info))
            else:
                yield event.plain_result(
                    f"❌ 未找到基金代码 {fund_code}\n"
                    "💡 请使用「搜索基金 关键词」来搜索正确的基金代码"
                )

        except ImportError:
            yield event.plain_result(
                "❌ AKShare 库未安装\n请管理员执行: pip install akshare"
            )
        except TimeoutError as e:
            yield event.plain_result(f"⏰ {str(e)}\n💡 数据源响应较慢，请稍后再试")
        except Exception as e:
            logger.error(f"查询基金行情出错: {e}")
            yield event.plain_result(f"❌ 查询失败: {str(e)}")

    @filter.command("基金分析")
    async def fund_analysis(self, event: AstrMessageEvent, code: str = None):
        """
        基金技术分析
        用法: 基金分析 [基金代码]
        示例: 基金分析 161226
        """
        try:
            user_id = event.get_sender_id()
            # 标准化基金代码，补齐前导0
            normalized_code = self._normalize_fund_code(code)
            fund_code = normalized_code or self._get_user_fund(user_id)

            yield event.plain_result(f"📊 正在分析基金 {fund_code}...")

            # 获取实时行情
            info = await self.analyzer.get_lof_realtime(fund_code)
            if not info:
                yield event.plain_result(f"❌ 未找到基金代码 {fund_code}")
                return

            # 获取历史数据进行分析
            history = await self.analyzer.get_lof_history(fund_code, days=30)

            if history:
                indicators = self.analyzer.calculate_technical_indicators(history)
                yield event.plain_result(self._format_analysis(info, indicators))
            else:
                yield event.plain_result(
                    f"📊 【{info.name}】\n"
                    "暂无足够历史数据进行技术分析\n"
                    f"当前价格: {info.latest_price:.4f}"
                )

        except ImportError:
            yield event.plain_result(
                "❌ AKShare 库未安装\n请管理员执行: pip install akshare"
            )
        except TimeoutError as e:
            yield event.plain_result(f"⏰ {str(e)}\n💡 数据源响应较慢，请稍后再试")
        except Exception as e:
            logger.error(f"基金分析出错: {e}")
            yield event.plain_result(f"❌ 分析失败: {str(e)}")

    @filter.command("基金历史")
    async def fund_history(
        self, event: AstrMessageEvent, code: str = None, days: str = "10"
    ):
        """
        查询基金历史行情
        用法: 基金历史 [基金代码] [天数]
        示例: 基金历史 161226 10
        """
        try:
            user_id = event.get_sender_id()
            # 标准化基金代码，补齐前导0
            normalized_code = self._normalize_fund_code(code)
            fund_code = normalized_code or self._get_user_fund(user_id)

            try:
                num_days = int(days)
                if num_days < 1:
                    num_days = 10
                elif num_days > 60:
                    num_days = 60
            except ValueError:
                num_days = 10

            yield event.plain_result(
                f"📜 正在查询基金 {fund_code} 近 {num_days} 日历史..."
            )

            # 获取基金名称
            info = await self.analyzer.get_lof_realtime(fund_code)
            fund_name = info.name if info else fund_code

            history = await self.analyzer.get_lof_history(fund_code, days=num_days)

            if history:
                text_lines = [
                    f"📜 【{fund_name}】近 {len(history)} 日行情",
                    "━━━━━━━━━━━━━━━━━",
                ]

                # 只显示最近的数据
                for item in history[-min(10, len(history)) :]:
                    change = item.get("change_rate", 0)
                    emoji = "🟢" if change > 0 else "🔴" if change < 0 else "⚪"
                    text_lines.append(
                        f"{item['date']} | {item['close']:.4f} | {emoji}{change:+.2f}%"
                    )

                if len(history) > 10:
                    text_lines.append(f"... 共 {len(history)} 条记录")

                text_lines.append("━━━━━━━━━━━━━━━━━")

                # 计算区间统计
                closes = [d["close"] for d in history]
                changes = [d["change_rate"] for d in history]

                total_return = (
                    ((closes[-1] - closes[0]) / closes[0]) * 100 if closes[0] else 0
                )
                up_days = sum(1 for c in changes if c > 0)
                down_days = sum(1 for c in changes if c < 0)

                text_lines.append("📊 区间统计:")
                text_lines.append(f"  • 区间涨跌: {total_return:+.2f}%")
                text_lines.append(f"  • 上涨天数: {up_days} 天")
                text_lines.append(f"  • 下跌天数: {down_days} 天")
                text_lines.append(f"  • 最高价: {max(closes):.4f}")
                text_lines.append(f"  • 最低价: {min(closes):.4f}")

                yield event.plain_result("\n".join(text_lines))
            else:
                yield event.plain_result(f"❌ 未找到基金 {fund_code} 的历史数据")

        except ImportError:
            yield event.plain_result(
                "❌ AKShare 库未安装\n请管理员执行: pip install akshare"
            )
        except TimeoutError as e:
            yield event.plain_result(f"⏰ {str(e)}\n💡 数据源响应较慢，请稍后再试")
        except Exception as e:
            logger.error(f"查询基金历史出错: {e}")
            yield event.plain_result(f"❌ 查询失败: {str(e)}")

    @filter.command("搜索基金")
    async def search_fund(self, event: AstrMessageEvent, keyword: str = ""):
        """
        搜索LOF基金
        用法: 搜索基金 关键词
        示例: 搜索基金 白银
        """
        if not keyword:
            yield event.plain_result(
                "❓ 请输入搜索关键词\n用法: 搜索基金 关键词\n示例: 搜索基金 白银"
            )
            return

        try:
            yield event.plain_result(f"🔍 正在搜索包含「{keyword}」的基金...")

            results = await self.analyzer.search_fund(keyword)

            if results:
                text_lines = [
                    f"📋 搜索结果 (共 {len(results)} 条)",
                    "━━━━━━━━━━━━━━━━━",
                ]

                for fund in results:
                    price = fund.get("latest_price", 0)
                    change = fund.get("change_rate", 0)
                    # 价格为0通常表示暂无数据（原始数据为NaN）
                    if price == 0:
                        price_str = "暂无数据"
                        change_str = ""
                    else:
                        emoji = "🟢" if change > 0 else "🔴" if change < 0 else "⚪"
                        price_str = f"{price:.4f}"
                        change_str = f" {emoji}{change:+.2f}%"
                    text_lines.append(
                        f"{fund['code']} | {fund['name']}\n"
                        f"    💰 {price_str}{change_str}"
                    )

                text_lines.append("━━━━━━━━━━━━━━━━━")
                text_lines.append("💡 使用「基金 代码」查看详情")
                text_lines.append("💡 使用「设置基金 代码」设为默认")

                yield event.plain_result("\n".join(text_lines))
            else:
                yield event.plain_result(
                    f"❌ 未找到包含「{keyword}」的LOF基金\n💡 尝试使用其他关键词搜索"
                )

        except ImportError:
            yield event.plain_result(
                "❌ AKShare 库未安装\n请管理员执行: pip install akshare"
            )
        except TimeoutError as e:
            yield event.plain_result(f"⏰ {str(e)}\n💡 数据源响应较慢，请稍后再试")
        except Exception as e:
            logger.error(f"搜索基金出错: {e}")
            yield event.plain_result(f"❌ 搜索失败: {str(e)}")

    @filter.command("设置基金")
    async def set_default_fund(self, event: AstrMessageEvent, code: str = ""):
        """
        设置默认关注的基金
        用法: 设置基金 基金代码
        示例: 设置基金 161226
        """
        if not code:
            user_id = event.get_sender_id()
            current = self._get_user_fund(user_id)
            yield event.plain_result(
                f"💡 当前默认基金: {current}\n"
                "用法: 设置基金 基金代码\n"
                "示例: 设置基金 161226"
            )
            return

        try:
            # 标准化基金代码，补齐前导0
            code = self._normalize_fund_code(code) or code
            # 验证基金代码是否有效
            info = await self.analyzer.get_lof_realtime(code)

            if info:
                user_id = event.get_sender_id()
                self.user_fund_settings[user_id] = code
                self._save_user_settings()  # 持久化保存
                yield event.plain_result(
                    f"✅ 已设置默认基金\n"
                    f"📊 {info.code} - {info.name}\n"
                    f"💰 当前价格: {info.latest_price:.4f}"
                )
            else:
                yield event.plain_result(
                    f"❌ 无效的基金代码: {code}\n"
                    "💡 请使用「搜索基金 关键词」查找正确代码"
                )

        except ImportError:
            yield event.plain_result(
                "❌ AKShare 库未安装\n请管理员执行: pip install akshare"
            )
        except TimeoutError as e:
            yield event.plain_result(f"⏰ {str(e)}\n💡 数据源响应较慢，请稍后再试")
        except Exception as e:
            logger.error(f"设置默认基金出错: {e}")
            yield event.plain_result(f"❌ 设置失败: {str(e)}")

    @filter.command("智能分析")
    async def ai_fund_analysis(self, event: AstrMessageEvent, code: str = None):
        """
        使用大模型进行智能基金分析（含量化数据）
        用法: 智能分析 [基金代码]
        示例: 智能分析 161226
        """
        try:
            user_id = event.get_sender_id()
            # 标准化基金代码，补齐前导0
            normalized_code = self._normalize_fund_code(code)
            fund_code = normalized_code or self._get_user_fund(user_id)

            yield event.plain_result(
                f"🤖 正在对基金 {fund_code} 进行智能分析...\n"
                "📊 收集数据中，请稍候（约需30秒）..."
            )

            # 1. 获取基金基本信息
            info = await self.analyzer.get_lof_realtime(fund_code)
            if not info:
                yield event.plain_result(
                    f"❌ 未找到基金代码 {fund_code}\n"
                    "💡 请使用「搜索基金 关键词」查找正确代码"
                )
                return

            # 2. 获取历史数据（获取60天以支持更多回测策略）
            history = await self.analyzer.get_lof_history(fund_code, days=60)

            # 3. 计算技术指标（保留旧方法兼容性）
            indicators = {}
            if history:
                indicators = self.analyzer.calculate_technical_indicators(history)

            # 4. 检查大模型是否可用
            provider = self.context.get_using_provider()
            if not provider:
                yield event.plain_result(
                    "❌ 未配置大模型提供商\n"
                    "💡 请在 AstrBot 管理面板配置 LLM 提供商后再试"
                )
                return

            yield event.plain_result(
                "🧠 AI 正在分析数据，生成报告中...\n📈 正在计算量化指标和策略回测..."
            )

            # 5. 使用 AI 分析器执行分析（含量化数据）
            try:
                analysis_result = await self.ai_analyzer.analyze(
                    fund_info=info,
                    history_data=history or [],
                    technical_indicators=indicators,
                    user_id=user_id,
                )

                # 获取技术信号
                signal, score = self.ai_analyzer.get_technical_signal(history or [])

                # 格式化输出
                header = f"""
🤖 【{info.name}】智能量化分析报告
━━━━━━━━━━━━━━━━━
📅 分析时间: {datetime.now().strftime("%Y-%m-%d %H:%M")}
💰 当前价格: {info.latest_price:.4f} ({info.change_rate:+.2f}%)
📊 技术信号: {signal} (评分: {score})
━━━━━━━━━━━━━━━━━
""".strip()

                yield event.plain_result(f"{header}\n\n{analysis_result}")

                # 添加免责声明
                yield event.plain_result(
                    "━━━━━━━━━━━━━━━━━\n"
                    "⚠️ 免责声明: 以上分析仅供参考，不构成投资建议。\n"
                    "量化回测基于历史数据，不代表未来表现。\n"
                    "投资有风险，入市需谨慎！请结合自身情况做出决策。"
                )

            except ValueError as e:
                yield event.plain_result(f"❌ {str(e)}")
            except Exception as e:
                logger.error(f"AI分析失败: {e}")
                yield event.plain_result(
                    f"❌ AI 分析失败: {str(e)}\n"
                    "💡 可能是大模型服务暂时不可用，请稍后再试"
                )

        except ImportError:
            yield event.plain_result(
                "❌ AKShare 库未安装\n请管理员执行: pip install akshare"
            )
        except TimeoutError as e:
            yield event.plain_result(f"⏰ {str(e)}\n💡 数据源响应较慢，请稍后再试")
        except Exception as e:
            logger.error(f"智能分析出错: {e}")
            yield event.plain_result(f"❌ 分析失败: {str(e)}")

    @filter.command("量化分析")
    async def quant_analysis(self, event: AstrMessageEvent, code: str = None):
        """
        纯量化分析（无需大模型）
        包含绩效指标、技术指标、策略回测
        用法: 量化分析 [基金代码]
        示例: 量化分析 161226
        """
        try:
            user_id = event.get_sender_id()
            # 标准化基金代码，补齐前导0
            normalized_code = self._normalize_fund_code(code)
            fund_code = normalized_code or self._get_user_fund(user_id)

            yield event.plain_result(
                f"📊 正在对基金 {fund_code} 进行量化分析...\n"
                "🔢 计算绩效指标、技术指标、策略回测中..."
            )

            # 1. 获取基金基本信息
            info = await self.analyzer.get_lof_realtime(fund_code)
            if not info:
                yield event.plain_result(
                    f"❌ 未找到基金代码 {fund_code}\n"
                    "💡 请使用「搜索基金 关键词」查找正确代码"
                )
                return

            # 2. 获取60天历史数据
            history = await self.analyzer.get_lof_history(fund_code, days=60)

            if not history or len(history) < 20:
                yield event.plain_result(
                    f"📊 【{info.name}】\n"
                    "⚠️ 历史数据不足（需要至少20天），无法进行量化分析"
                )
                return

            # 3. 使用量化分析器生成报告（无需 LLM）
            quant_report = self.ai_analyzer.get_quant_summary(history)

            # 4. 输出报告
            header = f"""
📈 【{info.name}】量化分析报告
━━━━━━━━━━━━━━━━━
🔢 基金代码: {info.code}
💰 当前价格: {info.latest_price:.4f}
📊 今日涨跌: {info.change_rate:+.2f}%
📅 分析时间: {datetime.now().strftime("%Y-%m-%d %H:%M")}
━━━━━━━━━━━━━━━━━
""".strip()

            yield event.plain_result(f"{header}\n\n{quant_report}")

            # 添加说明
            yield event.plain_result(
                "━━━━━━━━━━━━━━━━━\n"
                "📌 指标说明:\n"
                "• 夏普比率 > 1 表示风险调整后收益较好\n"
                "• 最大回撤反映历史最大亏损幅度\n"
                "• VaR 95% 表示95%概率下的最大日亏损\n"
                "• 策略回测基于历史数据模拟\n"
                "━━━━━━━━━━━━━━━━━\n"
                "💡 使用「智能分析」可获取 AI 深度解读"
            )

        except ImportError:
            yield event.plain_result(
                "❌ AKShare 库未安装\n请管理员执行: pip install akshare"
            )
        except TimeoutError as e:
            yield event.plain_result(f"⏰ {str(e)}\n💡 数据源响应较慢，请稍后再试")
        except Exception as e:
            logger.error(f"量化分析出错: {e}")
            yield event.plain_result(f"❌ 分析失败: {str(e)}")

    @filter.command("基金帮助")
    async def fund_help(self, event: AstrMessageEvent):
        """显示基金分析插件帮助信息"""
        help_text = """
📊 基金/股票分析插件帮助
━━━━━━━━━━━━━━━━━
� 贵金属行情:
🔹 今日行情 - 查询金价银价实时行情
━━━━━━━━━━━━━━━━━
📈 A股实时行情 (缓存10分钟):
🔹 股票 <代码> - 查询A股实时行情
🔹 搜索股票 关键词 - 搜索A股股票
━━━━━━━━━━━━━━━━━
📊 LOF基金功能:
🔹 基金 [代码] - 查询基金实时行情
🔹 基金分析 [代码] - 技术分析(均线/趋势)
🔹 量化分析 [代码] - 📈专业量化指标分析
🔹 智能分析 [代码] - 🤖AI量化深度分析
🔹 基金历史 [代码] [天数] - 查看历史行情
🔹 搜索基金 关键词 - 搜索LOF基金
🔹 设置基金 代码 - 设置默认基金
🔹 基金帮助 - 显示本帮助
━━━━━━━━━━━━━━━━━
💡 默认基金: 国投瑞银白银期货(LOF)A
   基金代码: 161226
━━━━━━━━━━━━━━━━━
📈 示例:
  • 今日行情 (金银价格)
  • 股票 000001 (平安银行)
  • 搜索股票 茅台
  • 基金 161226
  • 基金分析
  • 量化分析 161226
  • 智能分析 161226
  • 基金历史 161226 20
  • 搜索基金 白银
━━━━━━━━━━━━━━━━━
🤖 智能分析功能说明:
  调用AI大模型+量化数据，综合分析:
  - 量化绩效评估和风险分析
  - 技术指标深度解读
  - 策略回测结果解读
  - 相关市场动态和新闻
  - 上涨趋势和概率预测
━━━━━━━━━━━━━━━━━
⚠️ 数据来源: AKShare/国际金价网
💡 A股数据缓存10分钟，仅供参考
💡 投资有风险，入市需谨慎！
""".strip()
        yield event.plain_result(help_text)

    async def terminate(self):
        """插件停止时的清理工作"""
        logger.info("基金分析插件已停止")
