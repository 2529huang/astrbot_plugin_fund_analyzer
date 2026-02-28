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
from typing import Any, Optional

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.core.utils.t2i.renderer import HtmlRenderer

# 导入股票分析模块
from .stock import StockAnalyzer, StockInfo

# 导入本地图片生成器
from .image_generator import render_fund_image, PLAYWRIGHT_AVAILABLE

# 导入东方财富 API 模块（直接 HTTP 请求，不依赖 akshare）
from .eastmoney_api import get_api as get_eastmoney_api

# 默认超时时间（秒）- AKShare获取LOF数据需要较长时间
DEFAULT_TIMEOUT = 120  # 2分钟
# 数据缓存有效期（秒）
CACHE_TTL = 1800  # 30分钟


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
        # 使用东方财富 API 模块（不再依赖 akshare）
        self._api = get_eastmoney_api()
        self._initialized = True

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

    async def get_lof_realtime(
        self, fund_code: Optional[str] = None
    ) -> FundInfo | None:
        """
        获取LOF基金实时行情

        Args:
            fund_code: 基金代码，默认为国投瑞银白银期货LOF

        Returns:
            FundInfo 对象或 None
        """
        if fund_code is None:
            fund_code = self.DEFAULT_FUND_CODE

        fund_code = str(fund_code).strip()

        try:
            data = await self._api.get_fund_realtime(fund_code)
            if not data:
                logger.warning(f"未找到基金数据: {fund_code}")
                return None

            return FundInfo(
                code=data.get("code", fund_code),
                name=data.get("name", ""),
                latest_price=data.get("latest_price", 0.0),
                change_amount=data.get("change_amount", 0.0),
                change_rate=data.get("change_rate", 0.0),
                open_price=data.get("open_price", 0.0),
                high_price=data.get("high_price", 0.0),
                low_price=data.get("low_price", 0.0),
                prev_close=data.get("prev_close", 0.0),
                volume=data.get("volume", 0.0),
                amount=data.get("amount", 0.0),
                turnover_rate=data.get("turnover_rate", 0.0),
            )
        except Exception as e:
            logger.error(f"获取LOF基金实时行情失败: {e}")
            return None

    async def get_lof_history(
        self, fund_code: Optional[str] = None, days: int = 30, adjust: str = "qfq"
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
        if fund_code is None:
            fund_code = self.DEFAULT_FUND_CODE

        fund_code = str(fund_code).strip()

        try:
            history = await self._api.get_fund_history(fund_code, days, adjust)
            return history
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
        try:
            results = await self._api.search_fund(keyword)
            return results
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
        perf = quant.calculate_performance(history_data)

        closes = [d["close"] for d in history_data]
        current_price = closes[-1] if closes else 0

        # 计算区间收益率
        def calc_return(days):
            if len(closes) > days:
                prev = closes[-(days + 1)]
                if prev != 0:
                    return (current_price - prev) / prev * 100
            return None

        # 转换为兼容格式
        return {
            "ma5": round(indicators.ma5, 4) if indicators.ma5 else None,
            "ma10": round(indicators.ma10, 4) if indicators.ma10 else None,
            "ma20": round(indicators.ma20, 4) if indicators.ma20 else None,
            "return_5d": calc_return(5),
            "return_10d": calc_return(10),
            "return_20d": calc_return(20),
            "volatility": perf.volatility if perf else None,
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
        # 初始化图片渲染器
        self.image_renderer = HtmlRenderer()
        # 是否使用本地图片生成器（优先使用）
        self.use_local_renderer = PLAYWRIGHT_AVAILABLE
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

        def format_item(
            data: dict, unit: str = "美元/盎司", divisor: float = 1.0
        ) -> str:
            """格式化单个金属品种的价格信息

            Args:
                data: 价格数据字典
                unit: 显示单位
                divisor: 除数，用于单位转换（如白银可能需要除以100）
            """
            if not data:
                return "  暂无数据"

            change_rate = parse_change_rate(data.get("change_rate", "0%"))
            change_emoji = (
                "🔴" if change_rate < 0 else "🟢" if change_rate > 0 else "⚪"
            )
            trend_emoji = "📈" if change_rate > 0 else "📉" if change_rate < 0 else "➡️"

            # 应用单位转换
            price = data["price"] / divisor
            change = data.get("change", 0) / divisor
            open_p = data.get("open", 0) / divisor
            high_p = data.get("high", 0) / divisor
            low_p = data.get("low", 0) / divisor
            buy_p = data.get("buy_price", 0) / divisor
            sell_p = data.get("sell_price", 0) / divisor

            return f"""  {trend_emoji} 最新价: {price:.2f} {unit}
  {change_emoji} 涨跌: {change:+.2f} ({data.get("change_rate", "0%")})
  📊 今开: {open_p:.2f} | 最高: {high_p:.2f} | 最低: {low_p:.2f}
  💹 买入: {buy_p:.2f} | 卖出: {sell_p:.2f}"""

        lines = [
            "💰 今日贵金属行情（国际现货）",
            "━━━━━━━━━━━━━━━━━",
        ]

        # 黄金 - 国际金价，单位是美元/盎司
        if "au_td" in prices:
            lines.append("🥇 黄金")
            lines.append(format_item(prices["au_td"], "美元/盎司", 1.0))
            if prices["au_td"].get("update_time"):
                lines.append(f"  🕐 更新: {prices['au_td']['update_time']}")
            lines.append("")

        # 白银 - 国际银价，API返回的是美分/盎司，需要除以100转为美元/盎司
        if "ag_td" in prices:
            lines.append("🥈 白银")
            # 白银价格如果大于1000，说明是美分/盎司，需要除以100
            silver_price = prices["ag_td"].get("price", 0)
            divisor = 100.0 if silver_price > 1000 else 1.0
            lines.append(format_item(prices["ag_td"], "美元/盎司", divisor))
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
    async def stock_query(self, event: AstrMessageEvent, code: str = ""):
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

            stock_code = str(code).strip().zfill(6)
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
    async def search_stock(self, event: AstrMessageEvent, keyword: str = ""):
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
    async def fund_query(self, event: AstrMessageEvent, code: str = ""):
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
                # 区分是基金代码错误还是数据源问题
                if not normalized_code:
                    yield event.plain_result(f"❌ 基金代码不能为空")
                    return

                # 如果代码是6位数字，通常是有效的基金代码格式，但未找到数据
                if len(normalized_code) == 6 and normalized_code.isdigit():
                    # 尝试再次搜索确认是否存在
                    try:
                        search_res = await self.analyzer.search_fund(normalized_code)
                        if not search_res:
                            yield event.plain_result(
                                f"❌ 未找到基金代码 {fund_code}\n"
                                "💡 请检查代码是否正确，或使用「搜索基金 关键词」查找"
                            )
                            return
                    except Exception:
                        pass  # 搜索出错忽略，继续下面的判断

                yield event.plain_result(
                    f"⚠️ 暂时无法获取基金 {fund_code} 的数据\n"
                    "💡 可能是数据源暂时不可用，或该基金为非LOF基金\n"
                    "💡 请稍后重试"
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
    async def fund_analysis(self, event: AstrMessageEvent, code: str = ""):
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

            yield event.plain_result(f"📊 正在生成基金 {fund_code} 分析报告...")

            # 获取实时行情
            info = await self.analyzer.get_lof_realtime(fund_code)
            if not info:
                # 区分是基金代码错误还是数据源问题
                if not normalized_code:
                    yield event.plain_result(f"❌ 基金代码不能为空")
                    return

                # 如果代码是6位数字，通常是有效的基金代码格式，但未找到数据
                if len(normalized_code) == 6 and normalized_code.isdigit():
                    # 尝试再次搜索确认是否存在
                    try:
                        search_res = await self.analyzer.search_fund(normalized_code)
                        if not search_res:
                            yield event.plain_result(
                                f"❌ 未找到基金代码 {fund_code}\n"
                                "💡 请检查代码是否正确，或使用「搜索基金 关键词」查找"
                            )
                            return
                    except Exception:
                        pass  # 搜索出错忽略，继续下面的判断

                yield event.plain_result(
                    f"⚠️ 暂时无法获取基金 {fund_code} 的数据\n"
                    "💡 可能是数据源暂时不可用，或该基金为非LOF基金\n"
                    "💡 请稍后重试"
                )
                return

            # 获取历史数据进行分析
            history = await self.analyzer.get_lof_history(fund_code, days=30)

            # 计算技术指标
            indicators = {}
            if history:
                indicators = self.analyzer.calculate_technical_indicators(history)
                # 绘制小图用于报告
                plot_img = await asyncio.to_thread(
                    self._plot_history_chart, history, info.name
                )
            else:
                plot_img = None

            # 准备模板数据
            ma_data = []
            if indicators:
                for ma in ["ma5", "ma10", "ma20"]:
                    if indicators.get(ma):
                        ma_data.append({"name": ma.upper(), "value": indicators[ma]})

            data = {
                "fund_name": info.name,
                "fund_code": info.code,
                "latest_price": info.latest_price,
                "change_amount": info.change_amount,
                "change_rate": info.change_rate,
                "plot_img": plot_img,
                "trend": indicators.get("trend", "数据不足"),
                "volatility": indicators.get("volatility"),
                "return_5d": indicators.get("return_5d"),
                "return_10d": indicators.get("return_10d"),
                "return_20d": indicators.get("return_20d"),
                "ma_data": ma_data,
                "generated_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            # 读取模板
            template_path = self._data_dir / "templates" / "analysis_report.html"
            # 如果不在数据目录，尝试检查插件目录
            if not template_path.exists():
                template_path = (
                    Path(__file__).parent / "templates" / "analysis_report.html"
                )

            if not template_path.exists():
                # 降级到文本模式
                yield event.plain_result(self._format_analysis(info, indicators))
                return

            with open(template_path, "r", encoding="utf-8") as f:
                template_str = f.read()

            # 渲染图片
            img_url = await self.image_renderer.render_custom_template(
                tmpl_str=template_str, tmpl_data=data, return_url=True
            )

            # 发送图片
            yield event.image_result(img_url)

        except ImportError:
            yield event.plain_result(
                "❌ AKShare 库未安装\n请管理员执行: pip install akshare"
            )
        except TimeoutError as e:
            yield event.plain_result(f"⏰ {str(e)}\n💡 数据源响应较慢，请稍后再试")
        except Exception as e:
            logger.error(f"基金分析出错: {e}")
            yield event.plain_result(f"❌ 分析失败: {str(e)}")

    def _plot_history_chart(self, history: list[dict], fund_name: str) -> str | None:
        """
        绘制历史行情走势图 (价格+均线+成交量) 并返回 Base64 字符串
        """
        try:
            import base64
            import io
            import matplotlib.pyplot as plt
            import matplotlib.gridspec as gridspec
            import matplotlib.dates as mdates
            import pandas as pd

            # 设置中文字体，防止乱码
            plt.rcParams["font.sans-serif"] = [
                "SimHei",
                "Arial Unicode MS",
                "Microsoft YaHei",
                "WenQuanYi Micro Hei",
                "sans-serif",
            ]
            plt.rcParams["axes.unicode_minus"] = False

            # 准备数据
            df = pd.DataFrame(history)
            if df.empty:
                return None

            df["date"] = pd.to_datetime(df["date"])
            dates = df["date"]
            closes = df["close"]
            volumes = df["volume"]

            # 计算均线
            df["ma5"] = df["close"].rolling(window=5).mean()
            df["ma10"] = df["close"].rolling(window=10).mean()
            df["ma20"] = df["close"].rolling(window=20).mean()

            # 创建画布
            fig = plt.figure(figsize=(10, 6), dpi=100)
            gs = gridspec.GridSpec(2, 1, height_ratios=[3, 1], hspace=0.15)

            # 主图：价格 + 均线
            ax1 = plt.subplot(gs[0])
            ax1.plot(dates, closes, label="收盘价", color="#333333", linewidth=1.5)
            ax1.plot(
                dates, df["ma5"], label="MA5", color="#f5222d", linewidth=1.0, alpha=0.8
            )
            ax1.plot(
                dates,
                df["ma10"],
                label="MA10",
                color="#faad14",
                linewidth=1.0,
                alpha=0.8,
            )

            # 只有数据足够时才画MA20
            if len(df) >= 20:
                ax1.plot(
                    dates,
                    df["ma20"],
                    label="MA20",
                    color="#52c41a",
                    linewidth=1.0,
                    alpha=0.8,
                )

            ax1.set_title(f"{fund_name} - 价格走势", fontsize=14, pad=10)
            ax1.grid(True, linestyle="--", alpha=0.3)
            ax1.legend(loc="upper left", frameon=True, fontsize=9)

            # 副图：成交量
            ax2 = plt.subplot(gs[1], sharex=ax1)

            # 根据涨跌设置颜色 (红涨绿跌)
            colors = []
            for i in range(len(df)):
                if i == 0:
                    c = "#f5222d" if df.iloc[i].get("change_rate", 0) > 0 else "#52c41a"
                else:
                    change = df.iloc[i]["close"] - df.iloc[i - 1]["close"]
                    c = "#f5222d" if change >= 0 else "#52c41a"
                colors.append(c)

            ax2.bar(dates, volumes, color=colors, alpha=0.8)
            ax2.set_ylabel("成交量", fontsize=10)
            ax2.grid(True, linestyle="--", alpha=0.3)

            # 日期格式化
            ax1.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
            plt.setp(ax1.get_xticklabels(), visible=False)  # 隐藏主图X轴标签
            plt.gcf().autofmt_xdate()  # 自动旋转日期

            plt.tight_layout()

            # 保存到内存
            buffer = io.BytesIO()
            plt.savefig(buffer, format="png", bbox_inches="tight")
            buffer.seek(0)

            # 转 Base64
            image_base64 = base64.b64encode(buffer.read()).decode("utf-8")
            plt.close()

            return image_base64
        except Exception as e:
            logger.error(f"绘图失败: {e}")
            return None

    @filter.command("基金历史")
    async def fund_history(
        self, event: AstrMessageEvent, code: str = "", days: str = "10"
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
                f"📜 正在生成基金 {fund_code} 近 {num_days} 日行情报告..."
            )

            # 获取基金名称
            info = await self.analyzer.get_lof_realtime(fund_code)
            fund_name = info.name if info else fund_code

            history = await self.analyzer.get_lof_history(fund_code, days=num_days)

            if history:
                # 绘制走势图
                plot_img = await asyncio.to_thread(
                    self._plot_history_chart, history, fund_name
                )

                # 计算区间统计
                closes = [d["close"] for d in history]
                total_return = (
                    ((closes[-1] - closes[0]) / closes[0]) * 100 if closes[0] else 0
                )

                # 准备模板数据
                data = {
                    "fund_name": fund_name,
                    "fund_code": fund_code,
                    "days": num_days,
                    "history_list": list(reversed(history)),  # 倒序显示，最近的在前面
                    "plot_img": plot_img,
                    "total_return": total_return,
                    "max_price": max(closes),
                    "min_price": min(closes),
                    "generated_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }

                # 读取模板
                template_path = (
                    Path(__file__).parent / "templates" / "history_report.html"
                )
                if not template_path.exists():
                    yield event.plain_result(f"❌ 模板文件不存在: {template_path}")
                    return

                # 渲染图片 - 优先使用本地渲染器
                if self.use_local_renderer:
                    try:
                        img_path = await render_fund_image(
                            template_path=template_path, template_data=data, width=420
                        )
                        yield event.image_result(img_path)
                    except Exception as e:
                        logger.warning(f"本地渲染失败，回退到网络渲染: {e}")
                        # 回退到网络渲染
                        with open(template_path, "r", encoding="utf-8") as f:
                            template_str = f.read()
                        img_url = await self.image_renderer.render_custom_template(
                            tmpl_str=template_str,
                            tmpl_data=data,
                            return_url=True,
                        )
                        yield event.image_result(img_url)
                else:
                    # 使用网络渲染
                    with open(template_path, "r", encoding="utf-8") as f:
                        template_str = f.read()
                    img_url = await self.image_renderer.render_custom_template(
                        tmpl_str=template_str,
                        tmpl_data=data,
                        return_url=True,
                    )
                    yield event.image_result(img_url)

            else:
                yield event.plain_result(f"❌ 未找到基金 {fund_code} 的历史数据")

        except ImportError:
            yield event.plain_result(
                "❌ AKShare 库未安装\n请管理员执行: pip install akshare matplotlib"
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
    async def ai_fund_analysis(self, event: AstrMessageEvent, code: str = ""):
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
                # 区分是基金代码错误还是数据源问题
                if not normalized_code:
                    yield event.plain_result(f"❌ 基金代码不能为空")
                    return

                # 如果代码是6位数字，通常是有效的基金代码格式，但未找到数据
                if len(normalized_code) == 6 and normalized_code.isdigit():
                    # 尝试再次搜索确认是否存在
                    try:
                        search_res = await self.analyzer.search_fund(normalized_code)
                        if not search_res:
                            yield event.plain_result(
                                f"❌ 未找到基金代码 {fund_code}\n"
                                "💡 请检查代码是否正确，或使用「搜索基金 关键词」查找"
                            )
                            return
                    except Exception:
                        pass  # 搜索出错忽略，继续下面的判断

                yield event.plain_result(
                    f"⚠️ 暂时无法获取基金 {fund_code} 的数据\n"
                    "💡 可能是数据源暂时不可用，或该基金为非LOF基金\n"
                    "💡 请稍后重试"
                )
                return
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

            # 5. 获取资金流向数据（场内基金）
            fund_flow_text = ""
            try:
                fund_flow = await self.analyzer._api.get_fund_flow(fund_code, days=10)
                fund_flow_text = self.analyzer._api.format_fund_flow_text(fund_flow)
            except Exception as e:
                logger.debug(f"获取资金流向失败: {e}")
                fund_flow_text = "暂无资金流向数据"

            # 6. 使用 AI 分析器执行分析（含量化数据和资金流向）
            try:
                analysis_result = await self.ai_analyzer.analyze(
                    fund_info=info,
                    history_data=history or [],
                    technical_indicators=indicators,
                    user_id=user_id,
                    fund_flow_text=fund_flow_text,
                )

                # 获取技术信号
                signal, score = self.ai_analyzer.get_technical_signal(history or [])

                # 使用 markdown 库将 Markdown 转换为 HTML
                try:
                    import markdown

                    formatted_content = markdown.markdown(
                        analysis_result, extensions=["nl2br", "tables", "fenced_code"]
                    )
                except ImportError:
                    # 如果 markdown 库不可用，回退到简单的正则替换
                    import re

                    formatted_content = re.sub(
                        r"\*\*(.*?)\*\*", r"<strong>\1</strong>", analysis_result
                    )
                    # 处理换行
                    formatted_content = formatted_content.replace("\n", "<br>")

                # 准备模板数据
                data = {
                    "fund_name": info.name,
                    "fund_code": info.code,
                    "latest_price": info.latest_price,
                    "change_amount": info.change_amount,
                    "change_rate": info.change_rate,
                    "signal": signal,
                    "score": score,
                    "analysis_content": formatted_content,
                    "generated_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }

                # 读取模板
                template_path = self._data_dir / "templates" / "ai_analysis_report.html"
                if not template_path.exists():
                    template_path = (
                        Path(__file__).parent / "templates" / "ai_analysis_report.html"
                    )

                if not template_path.exists():
                    # 降级到文本模式
                    header = f"""
🤖 【{info.name}】智能量化分析报告
━━━━━━━━━━━━━━━━━
📅 分析时间: {datetime.now().strftime("%Y-%m-%d %H:%M")}
💰 当前价格: {info.latest_price:.4f} ({info.change_rate:+.2f}%)
📊 技术信号: {signal} (评分: {score})
━━━━━━━━━━━━━━━━━
""".strip()
                    yield event.plain_result(f"{header}\n\n{analysis_result}")
                else:
                    # 渲染图片 - 优先使用本地渲染器
                    if self.use_local_renderer:
                        try:
                            img_path = await render_fund_image(
                                template_path=template_path,
                                template_data=data,
                                width=480,
                            )
                            yield event.image_result(img_path)
                        except Exception as e:
                            logger.warning(f"本地渲染失败，回退到网络渲染: {e}")
                            with open(template_path, "r", encoding="utf-8") as f:
                                template_str = f.read()
                            img_url = await self.image_renderer.render_custom_template(
                                tmpl_str=template_str, tmpl_data=data, return_url=True
                            )
                            yield event.image_result(img_url)
                    else:
                        with open(template_path, "r", encoding="utf-8") as f:
                            template_str = f.read()
                        img_url = await self.image_renderer.render_custom_template(
                            tmpl_str=template_str, tmpl_data=data, return_url=True
                        )
                        yield event.image_result(img_url)

                # 添加免责声明 (如果是图片模式，免责声明已包含在图片底部，这里可以省略，或者发一条简短的)
                # yield event.plain_result("⚠️ 投资有风险，决策需谨慎。")

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
    async def quant_analysis(self, event: AstrMessageEvent, code: str = ""):
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
                # 区分是基金代码错误还是数据源问题
                if not normalized_code:
                    yield event.plain_result(f"❌ 基金代码不能为空")
                    return

                # 如果代码是6位数字，通常是有效的基金代码格式，但未找到数据
                if len(normalized_code) == 6 and normalized_code.isdigit():
                    # 尝试再次搜索确认是否存在
                    try:
                        search_res = await self.analyzer.search_fund(normalized_code)
                        if not search_res:
                            yield event.plain_result(
                                f"❌ 未找到基金代码 {fund_code}\n"
                                "💡 请检查代码是否正确，或使用「搜索基金 关键词」查找"
                            )
                            return
                    except Exception:
                        pass  # 搜索出错忽略，继续下面的判断

                yield event.plain_result(
                    f"⚠️ 暂时无法获取基金 {fund_code} 的数据\n"
                    "💡 可能是数据源暂时不可用，或该基金为非LOF基金\n"
                    "💡 请稍后重试"
                )
                return
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

    def _plot_comparison_chart(
        self,
        history_a: list[dict],
        name_a: str,
        history_b: list[dict],
        name_b: str,
    ) -> str | None:
        """
        绘制双基金对比走势图 (归一化收益率)
        """
        try:
            import base64
            import io
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates
            import pandas as pd

            # 设置中文字体
            plt.rcParams["font.sans-serif"] = [
                "SimHei",
                "Arial Unicode MS",
                "Microsoft YaHei",
                "WenQuanYi Micro Hei",
                "sans-serif",
            ]
            plt.rcParams["axes.unicode_minus"] = False

            # 转换为DataFrame
            df_a = pd.DataFrame(history_a)
            df_b = pd.DataFrame(history_b)

            if df_a.empty or df_b.empty:
                return None

            df_a["date"] = pd.to_datetime(df_a["date"])
            df_b["date"] = pd.to_datetime(df_b["date"])

            # 确保按日期排序
            df_a = df_a.sort_values("date")
            df_b = df_b.sort_values("date")

            # 找到公共日期范围
            common_dates = pd.merge(
                df_a[["date"]], df_b[["date"]], on="date", how="inner"
            )["date"]

            if common_dates.empty:
                return None

            # 过滤只保留公共日期的数据
            df_a = df_a[df_a["date"].isin(common_dates)]
            df_b = df_b[df_b["date"].isin(common_dates)]

            # 计算累计收益率 (归一化)
            base_a = df_a.iloc[0]["close"]
            base_b = df_b.iloc[0]["close"]

            if base_a == 0 or base_b == 0:
                return None

            df_a["norm_close"] = (df_a["close"] - base_a) / base_a * 100
            df_b["norm_close"] = (df_b["close"] - base_b) / base_b * 100

            # 绘图
            fig, ax = plt.subplots(figsize=(10, 5), dpi=100)

            ax.plot(
                df_a["date"],
                df_a["norm_close"],
                label=f"{name_a}",
                color="#1890ff",
                linewidth=2,
            )
            ax.plot(
                df_b["date"],
                df_b["norm_close"],
                label=f"{name_b}",
                color="#eb2f96",
                linewidth=2,
            )

            # 填充差异区域
            ax.fill_between(
                df_a["date"],
                df_a["norm_close"],
                df_b["norm_close"],
                where=(df_a["norm_close"] > df_b["norm_close"]),
                interpolate=True,
                color="#1890ff",
                alpha=0.1,
            )
            ax.fill_between(
                df_a["date"],
                df_a["norm_close"],
                df_b["norm_close"],
                where=(df_a["norm_close"] < df_b["norm_close"]),
                interpolate=True,
                color="#eb2f96",
                alpha=0.1,
            )

            ax.set_title("累计收益率对比 (%)", fontsize=14, pad=10)
            ax.grid(True, linestyle="--", alpha=0.3)
            ax.legend(loc="upper left", frameon=True)

            # 格式化Y轴百分比
            import matplotlib.ticker as mtick

            ax.yaxis.set_major_formatter(mtick.PercentFormatter())

            # 日期格式化
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
            plt.gcf().autofmt_xdate()

            plt.tight_layout()

            # 保存
            buffer = io.BytesIO()
            plt.savefig(buffer, format="png", bbox_inches="tight")
            buffer.seek(0)

            image_base64 = base64.b64encode(buffer.read()).decode("utf-8")
            plt.close()

            return image_base64

        except Exception as e:
            logger.error(f"对比绘图失败: {e}")
            return None

    # ============================================================
    # 多智能体博弈分析指令
    # ============================================================
    @filter.command("股票智能分析")
    async def multi_agent_debate(self, event: AstrMessageEvent, code: str = ""):
        """
        多智能体博弈分析（6 Agent + 多空辩论 + 博弈论裁定）
        用法: 股票智能分析 [基金/股票代码]
        示例: 股票智能分析 161226
        """
        try:
            user_id = event.get_sender_id()
            normalized_code = self._normalize_fund_code(code)
            fund_code = normalized_code or self._get_user_fund(user_id)

            yield event.plain_result(
                f"⚖️ 即将对 {fund_code} 启动多智能体博弈分析\n"
                "🧠 6 位 AI 分析师 + 多空辩论 + 博弈论裁定\n"
                "📡 正在采集数据，预计需要 3-5 分钟..."
            )

            # 1. 获取基金基本信息
            info = await self.analyzer.get_lof_realtime(fund_code)
            if not info:
                if (
                    normalized_code
                    and len(normalized_code) == 6
                    and normalized_code.isdigit()
                ):
                    try:
                        search_res = await self.analyzer.search_fund(normalized_code)
                        if not search_res:
                            yield event.plain_result(
                                f"❌ 未找到基金代码 {fund_code}\n"
                                "💡 请检查代码是否正确，或使用「搜索基金 关键词」查找"
                            )
                            return
                    except Exception:
                        pass
                yield event.plain_result(
                    f"⚠️ 暂时无法获取基金 {fund_code} 的数据\n"
                    "💡 可能是数据源暂时不可用，请稍后重试"
                )
                return

            # 2. 检查大模型是否可用
            provider = self.context.get_using_provider()
            if not provider:
                yield event.plain_result(
                    "❌ 未配置大模型提供商\n"
                    "💡 请在 AstrBot 管理面板配置 LLM 提供商后再试"
                )
                return

            # 3. 获取历史数据和资金流向
            history_task = self.analyzer.get_lof_history(fund_code, days=60)
            flow_task = self.analyzer._api.get_fund_flow(fund_code, days=10)

            history_data = await history_task
            fund_flow_data = []
            try:
                fund_flow_data = await flow_task
            except Exception as e:
                logger.debug(f"获取资金流向失败: {e}")

            if not history_data or len(history_data) < 10:
                yield event.plain_result(
                    f"⚠️ 基金 {fund_code} 历史数据不足，无法进行深度分析"
                )
                return

            # 4. 获取新闻摘要和影响因素
            # yield event.plain_result("📰 正在获取市场资讯和影响因素...")

            news_summary = await self.ai_analyzer.get_news_summary(info.name, info.code)
            factors_text = self.ai_analyzer.factors.format_factors_text(info.name)
            global_situation_text = (
                self.ai_analyzer.factors.format_global_situation_text(info.name)
            )

            # 5. 创建辩论引擎并执行
            from .stock.debate_engine import DebateEngine

            engine = DebateEngine(self.context)

            # 进度回调：通过 yield 发送进度消息
            progress_messages = []

            async def on_progress(msg: str):
                progress_messages.append(msg)

            debate_result = await engine.run_debate(
                fund_info=info,
                history_data=history_data,
                fund_flow_data=fund_flow_data,
                news_summary=news_summary,
                factors_text=factors_text,
                global_situation_text=global_situation_text,
                quant_analyzer=self.ai_analyzer.quant,
                eastmoney_api=self.analyzer._api,
                progress_callback=on_progress,
            )

            # 6. 发送进度汇总
            if progress_messages:
                yield event.plain_result("\n".join(progress_messages))

            # 7. 尝试渲染图片报告
            def _md_to_html(text: str) -> str:
                """将 Markdown 文本转换为 HTML（内置实现，无外部依赖）"""
                import re as _re

                if not text:
                    return ""

                lines = text.split("\n")
                html_parts: list[str] = []
                i = 0

                while i < len(lines):
                    line = lines[i]
                    stripped = line.strip()

                    # 空行 → 段落间距
                    if not stripped:
                        html_parts.append("")
                        i += 1
                        continue

                    # 标题 h1-h6
                    h_match = _re.match(r"^(#{1,6})\s+(.+)$", stripped)
                    if h_match:
                        level = len(h_match.group(1))
                        content = _inline_md(h_match.group(2))
                        fs = max(18 - level * 2, 12)
                        html_parts.append(
                            f"<h{level} style='margin:8px 0 4px;"
                            f"font-size:{fs}px'>"
                            f"{content}</h{level}>"
                        )
                        i += 1
                        continue

                    # 水平线
                    if _re.match(r"^[-*_]{3,}\s*$", stripped):
                        html_parts.append(
                            "<hr style='border:none;"
                            "border-top:1px solid #e0e0e0;"
                            "margin:8px 0'>"
                        )
                        i += 1
                        continue

                    # 表格（以 | 开头的连续行）
                    if stripped.startswith("|") and "|" in stripped[1:]:
                        table_lines = []
                        while i < len(lines) and lines[i].strip().startswith("|"):
                            table_lines.append(lines[i].strip())
                            i += 1
                        html_parts.append(_table_to_html(table_lines))
                        continue

                    # 无序列表（- / * / + 开头）
                    if _re.match(r"^[-*+]\s+", stripped):
                        items = []
                        while i < len(lines):
                            li_match = _re.match(
                                r"^\s*[-*+]\s+(.+)$", lines[i].strip()
                            )
                            if li_match:
                                items.append(_inline_md(li_match.group(1)))
                                i += 1
                            elif lines[i].strip() == "":
                                i += 1
                                break
                            else:
                                break
                        li_html = "".join(f"<li>{it}</li>" for it in items)
                        html_parts.append(
                            f"<ul style='margin:4px 0;padding-left:20px'>{li_html}</ul>"
                        )
                        continue

                    # 有序列表（1. 开头）
                    if _re.match(r"^\d+[.)]\s+", stripped):
                        items = []
                        while i < len(lines):
                            ol_match = _re.match(
                                r"^\s*\d+[.)]\s+(.+)$", lines[i].strip()
                            )
                            if ol_match:
                                items.append(_inline_md(ol_match.group(1)))
                                i += 1
                            elif lines[i].strip() == "":
                                i += 1
                                break
                            else:
                                break
                        li_html = "".join(f"<li>{it}</li>" for it in items)
                        html_parts.append(
                            f"<ol style='margin:4px 0;padding-left:20px'>{li_html}</ol>"
                        )
                        continue

                    # 普通文本行
                    content = _inline_md(stripped)
                    html_parts.append(
                        f"<p style='margin:4px 0'>{content}</p>"
                    )
                    i += 1

                return "\n".join(html_parts)

            def _inline_md(text: str) -> str:
                """处理行内 Markdown 格式"""
                import re as _re

                # 加粗+斜体 ***text***
                text = _re.sub(
                    r"\*{3}(.+?)\*{3}",
                    r"<strong><em>\1</em></strong>",
                    text,
                )
                # 加粗 **text**
                text = _re.sub(
                    r"\*{2}(.+?)\*{2}",
                    r"<strong>\1</strong>",
                    text,
                )
                # 斜体 *text*
                text = _re.sub(
                    r"\*(.+?)\*",
                    r"<em>\1</em>",
                    text,
                )
                # 行内代码 `code`
                code_style = (
                    "background:#f5f5f5;padding:1px 4px;"
                    "border-radius:3px;font-size:12px"
                )
                text = _re.sub(
                    r"`([^`]+)`",
                    rf"<code style='{code_style}'>\1</code>",
                    text,
                )
                # 链接 [text](url)
                text = _re.sub(
                    r"\[([^\]]+)\]\(([^\)]+)\)",
                    r'<a href="\2">\1</a>',
                    text,
                )
                # emoji 标记保留（🔺🔻等已是 unicode）
                return text

            def _table_to_html(table_lines: list[str]) -> str:
                """将 Markdown 表格行转换为 HTML 表格"""
                import re as _re

                if len(table_lines) < 2:
                    return "<br>".join(table_lines)

                def _parse_row(row: str) -> list[str]:
                    cells = row.strip().strip("|").split("|")
                    return [_inline_md(c.strip()) for c in cells]

                rows = []
                for tl in table_lines:
                    # 跳过分隔行 |---|---|
                    if _re.match(r"^\|[\s\-:|]+\|$", tl):
                        continue
                    rows.append(_parse_row(tl))

                if not rows:
                    return ""

                style = (
                    "width:100%;border-collapse:collapse;font-size:12px;margin:6px 0"
                )
                td_style = "border:1px solid #e0e0e0;padding:4px 6px"
                th_style = f"{td_style};background:#f5f5f5;font-weight:600"

                # 第一行当表头
                header = rows[0]
                th_html = "".join(f"<th style='{th_style}'>{c}</th>" for c in header)
                body_html = ""
                for row in rows[1:]:
                    td_html = "".join(f"<td style='{td_style}'>{c}</td>" for c in row)
                    body_html += f"<tr>{td_html}</tr>"

                return (
                    f"<table style='{style}'>"
                    f"<thead><tr>{th_html}</tr></thead>"
                    f"<tbody>{body_html}</tbody>"
                    f"</table>"
                )

            direction_class_map = {
                "看涨": "bullish",
                "看跌": "bearish",
                "中性": "neutral",
            }
            direction_emoji_map = {"看涨": "📈", "看跌": "📉", "中性": "↔️"}

            agents_data = []
            for r in debate_result.agent_reports:
                agents_data.append(
                    {
                        "emoji": r.agent_emoji,
                        "name": r.agent_name,
                        "direction": r.direction,
                        "direction_class": direction_class_map.get(
                            r.direction, "neutral"
                        ),
                        "confidence": f"{r.confidence:.0f}",
                    }
                )

            tmpl_data = {
                "fund_name": info.name,
                "fund_code": info.code,
                "final_direction": debate_result.final_direction,
                "direction_class": direction_class_map.get(
                    debate_result.final_direction, "neutral"
                ),
                "direction_emoji": direction_emoji_map.get(
                    debate_result.final_direction, "❓"
                ),
                "confidence": f"{debate_result.confidence:.0f}",
                "bull_win_rate": f"{debate_result.bull_win_rate:.0f}",
                "bear_win_rate": f"{debate_result.bear_win_rate:.0f}",
                "agents": agents_data,
                "bull_argument_html": _md_to_html(debate_result.bull_argument),
                "bear_argument_html": _md_to_html(debate_result.bear_argument),
                "judge_verdict_html": _md_to_html(debate_result.judge_verdict),
                "total_llm_calls": debate_result.total_llm_calls,
                "total_time": f"{debate_result.total_time_seconds:.0f}",
                "generated_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            template_path = self._data_dir / "templates" / "debate_report.html"
            if not template_path.exists():
                template_path = (
                    Path(__file__).parent / "templates" / "debate_report.html"
                )

            if template_path.exists():
                # 渲染图片报告
                if self.use_local_renderer:
                    try:
                        img_path = await render_fund_image(
                            template_path=template_path,
                            template_data=tmpl_data,
                            width=520,
                        )
                        yield event.image_result(img_path)
                    except Exception as e:
                        logger.warning(f"本地渲染失败，回退到网络渲染: {e}")
                        with open(template_path, encoding="utf-8") as f:
                            template_str = f.read()
                        img_url = await self.image_renderer.render_custom_template(
                            tmpl_str=template_str, tmpl_data=tmpl_data, return_url=True
                        )
                        yield event.image_result(img_url)
                else:
                    with open(template_path, encoding="utf-8") as f:
                        template_str = f.read()
                    img_url = await self.image_renderer.render_custom_template(
                        tmpl_str=template_str, tmpl_data=tmpl_data, return_url=True
                    )
                    yield event.image_result(img_url)
            else:
                # 降级到纯文本摘要
                summary = engine.format_debate_summary(debate_result)
                yield event.plain_result(summary)

            # 8. 发送简洁文字结论（纯文本，不含 markdown）
            summary = engine.format_debate_summary(debate_result)
            yield event.plain_result(summary)

        except ImportError:
            yield event.plain_result(
                "❌ AKShare 库未安装\n请管理员执行: pip install akshare"
            )
        except TimeoutError as e:
            yield event.plain_result(f"⏰ {str(e)}\n💡 数据源响应较慢，请稍后再试")
        except Exception as e:
            logger.error(f"多智能体博弈分析出错: {e}")
            yield event.plain_result(f"❌ 博弈分析失败: {str(e)}")

    @filter.command("基金对比")
    async def fund_compare(
        self, event: AstrMessageEvent, code1: str = "", code2: str = ""
    ):
        """
        对比两只基金的表现
        用法: 基金对比 [代码1] [代码2]
        示例: 基金对比 161226 160220
        """
        if not code1 or not code2:
            yield event.plain_result(
                "❌ 请提供两个基金代码\n用法: 基金对比 代码1 代码2\n示例: 基金对比 161226 160220"
            )
            return

        try:
            # 标准化代码
            code1 = self._normalize_fund_code(code1) or code1
            code2 = self._normalize_fund_code(code2) or code2

            yield event.plain_result(f"⚖️ 正在对比基金 {code1} vs {code2}...")

            # 并发获取两个基金的信息和历史数据
            # 使用 gather 提高效率
            task1 = self.analyzer.get_lof_realtime(code1)
            task2 = self.analyzer.get_lof_realtime(code2)
            task3 = self.analyzer.get_lof_history(code1, days=60)
            task4 = self.analyzer.get_lof_history(code2, days=60)

            info1, info2, hist1, hist2 = await asyncio.gather(
                task1, task2, task3, task4
            )

            if not info1:
                # 尝试区分错误原因 (基金1)
                if len(code1) == 6 and code1.isdigit():
                    try:
                        search_res = await self.analyzer.search_fund(code1)
                        if not search_res:
                            yield event.plain_result(
                                f"❌ 未找到基金代码 {code1}\n"
                                "💡 请检查代码是否正确，或使用「搜索基金 关键词」查找"
                            )
                            return
                    except Exception:
                        pass

                yield event.plain_result(
                    f"⚠️ 暂时无法获取基金 {code1} 的数据\n"
                    "💡 可能是数据源暂时不可用，或该基金为非LOF基金\n"
                    "💡 请稍后重试"
                )
                return

            if not info2:
                # 尝试区分错误原因 (基金2)
                if len(code2) == 6 and code2.isdigit():
                    try:
                        search_res = await self.analyzer.search_fund(code2)
                        if not search_res:
                            yield event.plain_result(
                                f"❌ 未找到基金代码 {code2}\n"
                                "💡 请检查代码是否正确，或使用「搜索基金 关键词」查找"
                            )
                            return
                    except Exception:
                        pass

                yield event.plain_result(
                    f"⚠️ 暂时无法获取基金 {code2} 的数据\n"
                    "💡 可能是数据源暂时不可用，或该基金为非LOF基金\n"
                    "💡 请稍后重试"
                )
                return
            if not hist1 or len(hist1) < 10:
                yield event.plain_result(f"⚠️ 基金 {code1} 历史数据不足")
                return
            if not hist2 or len(hist2) < 10:
                yield event.plain_result(f"⚠️ 基金 {code2} 历史数据不足")
                return

            # 计算量化指标
            from .ai_analyzer.quant import QuantAnalyzer

            quant = QuantAnalyzer()

            perf1 = quant.calculate_performance(hist1)
            perf2 = quant.calculate_performance(hist2)

            if not perf1 or not perf2:
                yield event.plain_result("❌ 计算绩效指标失败")
                return

            # 绘制对比图
            plot_img = await asyncio.to_thread(
                self._plot_comparison_chart, hist1, info1.name, hist2, info2.name
            )

            # 准备模板数据
            data = {
                "fund_a_name": info1.name,
                "fund_b_name": info2.name,
                "fund_a_code": info1.code,
                "fund_b_code": info2.code,
                "days": 60,
                "metrics_a": perf1,
                "metrics_b": perf2,
                "plot_img": plot_img,
                "generated_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            # 渲染模板
            template_path = self._data_dir / "templates" / "comparison_report.html"
            if not template_path.exists():
                template_path = (
                    Path(__file__).parent / "templates" / "comparison_report.html"
                )

            if not template_path.exists():
                yield event.plain_result("❌ 模板文件缺失")
                return

            with open(template_path, "r", encoding="utf-8") as f:
                template_str = f.read()

            img_url = await self.image_renderer.render_custom_template(
                tmpl_str=template_str, tmpl_data=data, return_url=True
            )

            yield event.image_result(img_url)

        except Exception as e:
            logger.error(f"基金对比出错: {e}")
            yield event.plain_result(f"❌ 对比失败: {str(e)}")

    @filter.command("基金帮助")
    async def fund_help(self, event: AstrMessageEvent):
        """显示基金分析插件帮助信息"""
        help_text = """
📊 基金/股票分析插件帮助
━━━━━━━━━━━━━━━━━
💰 贵金属行情:
🔹 今日行情 - 查询金价银价实时行情
━━━━━━━━━━━━━━━━━
📈 A股实时行情 (缓存10分钟):
🔹 股票 <代码> - 查询A股实时行情
🔹 搜索股票 关键词 - 搜索A股股票
━━━━━━━━━━━━━━━━━
📊 LOF基金功能:
🔹 基金 [代码] - 查询基金实时行情
🔹 基金分析 [代码] - 技术分析(均线/趋势)
🔹 基金对比 [代码1] [代码2] - ⚖️对比两只基金
🔹 量化分析 [代码] - 📈专业量化指标分析
🔹 智能分析 [代码] - 🤖AI量化深度分析
🔹 股票智能分析 [代码] - ⚖️多智能体博弈分析
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
  • 基金对比 161226 513100
  • 量化分析 161226
  • 智能分析 161226
  • 股票智能分析 161226
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
⚖️ 多智能体博弈分析说明:
  6 位 AI 分析师独立研判 + 多空辩论 + 博弈论裁定:
  - 📰 舆情Agent: 情绪因子与市场舆论
  - 🦈 游资Agent: 龙虎榜与游资行为
  - 🛡️ 风控Agent: 政策风险与红线监控
  - 📊 技术Agent: 技术指标与趋势信号
  - 🧩 筹码Agent: 主力行为与筹码分布
  - ⚡ 大单Agent: 实时资金流向与异动
━━━━━━━━━━━━━━━━━
⚠️ 数据来源: AKShare/国际金价网
💡 A股数据缓存10分钟，仅供参考
💡 投资有风险，入市需谨慎！
""".strip()
        yield event.plain_result(help_text)
        yield event.plain_result(help_text)

    async def terminate(self):
        """插件停止时的清理工作"""
        logger.info("基金分析插件已停止")
