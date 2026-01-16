"""
AI 基金分析器核心模块
提供基于大模型的智能分析功能，整合量化分析数据
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from astrbot.api import logger

from .factors import FundInfluenceFactors
from .prompts import AnalysisPromptBuilder
from .quant import QuantAnalyzer

if TYPE_CHECKING:
    from astrbot.api.provider import Provider
    from astrbot.api.star import Context


class AIFundAnalyzer:
    """AI 智能基金分析器（含量化分析）"""

    def __init__(self, context: "Context"):
        """
        初始化 AI 分析器

        Args:
            context: AstrBot 上下文
        """
        self.context = context
        self.factors = FundInfluenceFactors()
        self.prompt_builder = AnalysisPromptBuilder()
        self.quant = QuantAnalyzer()  # 量化分析器

    def _get_provider(self) -> "Provider | None":
        """获取 LLM 提供商"""
        return self.context.get_using_provider()

    async def get_news_summary(
        self,
        fund_name: str,
        fund_code: str,
    ) -> str:
        """
        获取基金相关新闻摘要

        Args:
            fund_name: 基金名称
            fund_code: 基金代码

        Returns:
            新闻摘要文本
        """
        provider = self._get_provider()
        if not provider:
            return "暂无法获取新闻资讯（未配置大模型）"

        # 获取影响因素
        factors = self.factors.get_factors(fund_name)

        # 构建提示词
        prompt = self.prompt_builder.build_news_prompt(
            fund_name=fund_name,
            underlying=factors["underlying"],
        )

        try:
            response = await provider.text_chat(
                prompt=prompt,
                session_id=f"fund_news_{fund_code}_{datetime.now().strftime('%Y%m%d')}",
                persist=False,
            )
            return response.completion_text
        except Exception as e:
            logger.warning(f"获取新闻摘要失败: {e}")
            return "暂无法获取最新新闻资讯"

    async def analyze(
        self,
        fund_info: Any,  # FundInfo 类型
        history_data: list[dict],
        technical_indicators: dict[str, Any],
        user_id: str,
    ) -> str:
        """
        执行 AI 智能分析（含量化数据）

        Args:
            fund_info: 基金信息对象
            history_data: 历史数据列表
            technical_indicators: 技术指标（旧版，保留兼容性）
            user_id: 用户 ID

        Returns:
            分析结果文本
        """
        provider = self._get_provider()
        if not provider:
            raise ValueError("未配置大模型提供商")

        # 1. 计算量化绩效指标
        performance = self.quant.calculate_performance(history_data)
        performance_summary = (
            self.quant.format_performance_text(performance)
            if performance
            else "历史数据不足，无法计算绩效指标"
        )

        # 2. 计算全部技术指标
        tech_indicators = self.quant.calculate_all_indicators(history_data)
        tech_indicators_text = self.quant.format_indicators_text(tech_indicators)

        # 3. 运行策略回测
        backtest_results = self.quant.run_all_backtests(history_data)
        backtest_summary = self.quant.format_backtest_text(backtest_results)

        # 4. 获取影响因素文本
        factors_text = self.factors.format_factors_text(fund_info.name)

        # 5. 格式化历史数据
        history_summary = self.prompt_builder.format_history_summary(history_data)

        # 6. 获取新闻摘要
        news_summary = await self.get_news_summary(fund_info.name, fund_info.code)

        # 7. 构建分析提示词（使用新模板）
        analysis_prompt = self._build_quant_analysis_prompt(
            fund_info=fund_info,
            performance_summary=performance_summary,
            tech_indicators_text=tech_indicators_text,
            backtest_summary=backtest_summary,
            factors_text=factors_text,
            history_summary=history_summary,
            news_summary=news_summary,
        )

        # 8. 调用大模型分析
        response = await provider.text_chat(
            prompt=analysis_prompt,
            session_id=f"fund_analysis_{fund_info.code}_{user_id}",
            persist=False,
        )

        return response.completion_text

    def _build_quant_analysis_prompt(
        self,
        fund_info: Any,
        performance_summary: str,
        tech_indicators_text: str,
        backtest_summary: str,
        factors_text: str,
        history_summary: str,
        news_summary: str,
    ) -> str:
        """构建包含量化数据的分析提示词"""
        from .prompts import ANALYSIS_PROMPT_TEMPLATE

        return ANALYSIS_PROMPT_TEMPLATE.format(
            fund_name=fund_info.name,
            fund_code=fund_info.code,
            latest_price=fund_info.latest_price,
            change_rate=fund_info.change_rate,
            amount=fund_info.amount,
            performance_summary=performance_summary
            if performance_summary
            else "暂无数据",
            tech_indicators=tech_indicators_text
            if tech_indicators_text
            else "暂无数据",
            backtest_summary=backtest_summary
            if backtest_summary
            else "历史数据不足，无法回测",
            factors_text=factors_text,
            history_summary=history_summary if history_summary else "暂无数据",
            news_summary=news_summary if news_summary else "暂无相关新闻",
        )

    async def quick_analyze(
        self,
        fund_info: Any,  # FundInfo 类型
        trend: str,
    ) -> str:
        """
        快速分析（简化版）

        Args:
            fund_info: 基金信息对象
            trend: 技术趋势判断

        Returns:
            快速分析结果
        """
        provider = self._get_provider()
        if not provider:
            raise ValueError("未配置大模型提供商")

        prompt = self.prompt_builder.build_quick_prompt(
            fund_name=fund_info.name,
            fund_code=fund_info.code,
            latest_price=fund_info.latest_price,
            change_rate=fund_info.change_rate,
            trend=trend,
        )

        response = await provider.text_chat(
            prompt=prompt,
            session_id=f"fund_quick_{fund_info.code}",
            persist=False,
        )

        return response.completion_text

    async def assess_risk(
        self,
        fund_info: Any,  # FundInfo 类型
        technical_indicators: dict[str, Any],
    ) -> str:
        """
        风险评估

        Args:
            fund_info: 基金信息对象
            technical_indicators: 技术指标

        Returns:
            风险评估结果
        """
        provider = self._get_provider()
        if not provider:
            raise ValueError("未配置大模型提供商")

        factors = self.factors.get_factors(fund_info.name)

        prompt = self.prompt_builder.build_risk_prompt(
            fund_name=fund_info.name,
            fund_type=factors["type"],
            underlying=factors["underlying"],
            volatility=technical_indicators.get("volatility", 0),
            high_20d=technical_indicators.get("high_20d", 0),
            low_20d=technical_indicators.get("low_20d", 0),
        )

        response = await provider.text_chat(
            prompt=prompt,
            session_id=f"fund_risk_{fund_info.code}",
            persist=False,
        )

        return response.completion_text

    def get_influence_factors(self, fund_name: str) -> dict:
        """
        获取基金影响因素

        Args:
            fund_name: 基金名称

        Returns:
            影响因素字典
        """
        return self.factors.get_factors(fund_name)

    # ============================================================
    # 量化分析方法（无需 LLM）
    # ============================================================

    def get_quant_summary(self, history_data: list[dict]) -> str:
        """
        获取量化分析摘要（无需 LLM）

        Args:
            history_data: 历史数据列表

        Returns:
            量化分析文本摘要
        """
        lines = ["📊 **量化分析报告**\n"]

        # 1. 绩效指标
        performance = self.quant.calculate_performance(history_data)
        if performance:
            lines.append("**【绩效分析】**")
            lines.append(f"累计收益: {performance.total_return:+.2f}%")
            lines.append(f"年化收益: {performance.annual_return:+.2f}%")
            lines.append(f"年化波动率: {performance.volatility:.2f}%")
            lines.append(f"最大回撤: {performance.max_drawdown:.2f}%")
            lines.append(f"夏普比率: {performance.sharpe_ratio:.2f}")
            lines.append(f"索提诺比率: {performance.sortino_ratio:.2f}")
            lines.append(f"95% VaR: {performance.var_95:.2f}%")
            lines.append("")

        # 2. 技术指标
        indicators = self.quant.calculate_all_indicators(history_data)
        lines.append("**【技术指标】**")
        if indicators.ma5:
            lines.append(f"MA5: {indicators.ma5:.4f}")
        if indicators.ma20:
            lines.append(f"MA20: {indicators.ma20:.4f}")
        if indicators.rsi_14:
            rsi_status = (
                "超买"
                if indicators.rsi_14 > 70
                else "超卖"
                if indicators.rsi_14 < 30
                else "中性"
            )
            lines.append(f"RSI(14): {indicators.rsi_14:.2f} ({rsi_status})")
        if indicators.macd_hist is not None:
            macd_status = "红柱" if indicators.macd_hist > 0 else "绿柱"
            lines.append(f"MACD: {macd_status}")
        lines.append(f"综合评分: {indicators.trend_score} 分")
        lines.append(f"**技术信号: {indicators.signal}**")
        lines.append("")

        # 3. 回测结果
        backtests = self.quant.run_all_backtests(history_data)
        if backtests:
            lines.append("**【策略回测】**")
            for bt in backtests:
                lines.append(
                    f"• {bt.strategy_name}: 收益 {bt.total_return:+.2f}%, 胜率 {bt.win_rate:.1f}%"
                )
            lines.append("")

        return "\n".join(lines)

    def get_technical_signal(self, history_data: list[dict]) -> tuple[str, int]:
        """
        获取技术信号

        Args:
            history_data: 历史数据列表

        Returns:
            (信号文本, 评分) 元组
        """
        indicators = self.quant.calculate_all_indicators(history_data)
        return indicators.signal, indicators.trend_score

    def get_performance_metrics(self, history_data: list[dict]):
        """
        获取绩效指标

        Args:
            history_data: 历史数据列表

        Returns:
            PerformanceMetrics 对象或 None
        """
        return self.quant.calculate_performance(history_data)

    def get_backtest_results(self, history_data: list[dict]):
        """
        获取回测结果

        Args:
            history_data: 历史数据列表

        Returns:
            BacktestResult 列表
        """
        return self.quant.run_all_backtests(history_data)
