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
        # 延迟初始化 AI 分析器
        self._ai_analyzer = None
        # 获取插件数据目录
        self._data_dir = Path(StarTools.get_data_dir("fund_analyzer"))
        self._data_dir.mkdir(parents=True, exist_ok=True)
        # 加载用户设置
        self.user_fund_settings: dict[str, str] = self._load_user_settings()
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

    @filter.command("基金")
    async def fund_query(self, event: AstrMessageEvent, code: str = None):
        """
        查询基金实时行情
        用法: 基金 [基金代码]
        示例: 基金 161226
        """
        try:
            user_id = event.get_sender_id()
            fund_code = code or self._get_user_fund(user_id)

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
            fund_code = code or self._get_user_fund(user_id)

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
            fund_code = code or self._get_user_fund(user_id)

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
            fund_code = code or self._get_user_fund(user_id)

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
            fund_code = code or self._get_user_fund(user_id)

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
📊 基金分析插件帮助
━━━━━━━━━━━━━━━━━
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
  • 基金 161226
  • 基金分析
  • 量化分析 161226
  • 智能分析 161226
  • 基金历史 161226 20
  • 搜索基金 白银
━━━━━━━━━━━━━━━━━
📊 量化分析功能说明:
  无需AI，纯数据量化分析:
  - 绩效指标: 夏普/索提诺/卡玛比率
  - 风险指标: 最大回撤/VaR/波动率
  - 技术指标: MACD/RSI/KDJ/布林带
  - 策略回测: MA交叉/RSI策略
━━━━━━━━━━━━━━━━━
🤖 智能分析功能说明:
  调用AI大模型+量化数据，综合分析:
  - 量化绩效评估和风险分析
  - 技术指标深度解读
  - 策略回测结果解读
  - 相关市场动态和新闻
  - 上涨趋势和概率预测
━━━━━━━━━━━━━━━━━
⚠️ 数据来源: AKShare (东方财富)
💡 投资有风险，入市需谨慎！
""".strip()
        yield event.plain_result(help_text)

    async def terminate(self):
        """插件停止时的清理工作"""
        logger.info("基金分析插件已停止")
