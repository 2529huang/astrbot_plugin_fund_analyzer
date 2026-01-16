"""
AI 分析提示词模板模块
集中管理所有 LLM 提示词，便于调整和优化
"""

from typing import Any

# ============================================================
# 系统角色提示词
# ============================================================

SYSTEM_PROMPT = """你是一位专业的量化基金分析师，拥有丰富的金融市场分析和量化投资经验。
你擅长：
1. 分析各类基金的投资标的和风险收益特征
2. 解读技术指标（MACD、RSI、KDJ、布林带等）和市场趋势
3. 解读绩效指标（夏普比率、索提诺比率、最大回撤、VaR等）
4. 评估策略回测结果和量化交易信号
5. 追踪影响基金表现的各类因素
6. 给出专业、客观、谨慎的投资建议

请始终保持专业、客观的分析态度，基于量化数据进行分析，注意风险提示。"""


# ============================================================
# 新闻摘要提示词模板
# ============================================================

NEWS_SUMMARY_PROMPT = """请简要总结当前"{fund_name}"（追踪{underlying}）相关的市场动态和新闻要点，包括：
1. 相关商品/资产的价格走势
2. 影响该基金的重要政策或事件
3. 市场情绪和资金流向

请用3-5条要点简要概括，每条不超过50字。如果你不确定最新信息，请基于该类型资产的一般影响因素进行分析。"""


# ============================================================
# 主分析提示词模板
# ============================================================

ANALYSIS_PROMPT_TEMPLATE = """你是一位专业的量化基金分析师。请基于以下量化数据和技术指标对基金进行深度分析，并给出投资建议。

## 基金基本信息
- 基金名称: {fund_name}
- 基金代码: {fund_code}
- 最新价格: {latest_price:.4f}
- 今日涨跌: {change_rate:+.2f}%
- 成交额: {amount:,.0f}

## 绩效量化分析
{performance_summary}

## 技术指标详情
{tech_indicators}

## 策略回测结果
{backtest_summary}

## 影响因素分析
{factors_text}

## 近期行情走势
{history_summary}

## 相关新闻资讯
{news_summary}

## 请按以下格式输出分析报告:

### 1. 基金概况
简要介绍该基金的投资标的和特点

### 2. 量化绩效评估
基于夏普比率、索提诺比率、最大回撤等指标评估基金的风险调整后收益表现

### 3. 技术面分析
基于MACD、RSI、KDJ、布林带等技术指标分析当前走势和买卖信号

### 4. 策略回测解读
解读回测策略的有效性，分析策略信号的参考价值

### 5. 影响因素分析
分析各个影响因素的当前状态和对基金的影响

### 6. 趋势预测
- 短期趋势(1周内): 结合技术信号和量化指标给出判断
- 中期趋势(1个月): 结合基本面和技术面综合判断
- 上涨概率评估: (给出一个百分比，需要说明依据)

### 7. 投资建议
给出明确的操作建议(买入/持有/卖出)及理由，包括建议的仓位比例

### 8. 风险提示
列出主要的投资风险，包括VaR风险值的解读

请用专业但易懂的语言进行分析，注意量化数据的解读和风险提示。"""


# ============================================================
# 简化版分析提示词（用于快速分析）
# ============================================================

QUICK_ANALYSIS_PROMPT = """请对基金【{fund_name}】({fund_code})进行快速分析。

当前价格: {latest_price:.4f}
今日涨跌: {change_rate:+.2f}%
技术趋势: {trend}

请简要给出：
1. 短期走势判断
2. 上涨概率（百分比）
3. 操作建议（一句话）"""


# ============================================================
# 风险评估提示词
# ============================================================

RISK_ASSESSMENT_PROMPT = """请对基金【{fund_name}】进行风险评估。

基金类型: {fund_type}
追踪标的: {underlying}
近20日波动率: {volatility}
近20日最高价: {high_20d}
近20日最低价: {low_20d}

请列出该基金的主要风险点（3-5条），并给出风险等级评估（低/中/高）。"""


# ============================================================
# 提示词构建器
# ============================================================


class AnalysisPromptBuilder:
    """分析提示词构建器"""

    @staticmethod
    def build_news_prompt(fund_name: str, underlying: str) -> str:
        """
        构建新闻摘要提示词

        Args:
            fund_name: 基金名称
            underlying: 追踪标的

        Returns:
            提示词字符串
        """
        return NEWS_SUMMARY_PROMPT.format(
            fund_name=fund_name,
            underlying=underlying,
        )

    @staticmethod
    def build_analysis_prompt(
        fund_name: str,
        fund_code: str,
        latest_price: float,
        change_rate: float,
        amount: float,
        factors_text: str,
        tech_summary: str,
        history_summary: str,
        news_summary: str = "",
    ) -> str:
        """
        构建主分析提示词

        Args:
            fund_name: 基金名称
            fund_code: 基金代码
            latest_price: 最新价格
            change_rate: 涨跌幅
            amount: 成交额
            factors_text: 影响因素文本
            tech_summary: 技术指标摘要
            history_summary: 历史行情摘要
            news_summary: 新闻摘要

        Returns:
            提示词字符串
        """
        return ANALYSIS_PROMPT_TEMPLATE.format(
            fund_name=fund_name,
            fund_code=fund_code,
            latest_price=latest_price,
            change_rate=change_rate,
            amount=amount,
            factors_text=factors_text,
            tech_summary=tech_summary if tech_summary else "暂无数据",
            history_summary=history_summary if history_summary else "暂无数据",
            news_summary=news_summary if news_summary else "暂无相关新闻",
        )

    @staticmethod
    def build_quick_prompt(
        fund_name: str,
        fund_code: str,
        latest_price: float,
        change_rate: float,
        trend: str,
    ) -> str:
        """
        构建快速分析提示词

        Args:
            fund_name: 基金名称
            fund_code: 基金代码
            latest_price: 最新价格
            change_rate: 涨跌幅
            trend: 技术趋势

        Returns:
            提示词字符串
        """
        return QUICK_ANALYSIS_PROMPT.format(
            fund_name=fund_name,
            fund_code=fund_code,
            latest_price=latest_price,
            change_rate=change_rate,
            trend=trend,
        )

    @staticmethod
    def build_risk_prompt(
        fund_name: str,
        fund_type: str,
        underlying: str,
        volatility: float,
        high_20d: float,
        low_20d: float,
    ) -> str:
        """
        构建风险评估提示词

        Args:
            fund_name: 基金名称
            fund_type: 基金类型
            underlying: 追踪标的
            volatility: 波动率
            high_20d: 20日最高价
            low_20d: 20日最低价

        Returns:
            提示词字符串
        """
        return RISK_ASSESSMENT_PROMPT.format(
            fund_name=fund_name,
            fund_type=fund_type,
            underlying=underlying,
            volatility=volatility,
            high_20d=high_20d,
            low_20d=low_20d,
        )

    @staticmethod
    def format_history_summary(history_data: list[dict], max_days: int = 10) -> str:
        """
        格式化历史数据摘要

        Args:
            history_data: 历史数据列表
            max_days: 最多显示天数

        Returns:
            格式化的历史数据文本
        """
        if not history_data:
            return ""

        recent_data = history_data[-max_days:]
        lines = []

        for d in recent_data:
            change = d.get("change_rate", 0)
            change_emoji = "📈" if change > 0 else "📉" if change < 0 else "➡️"
            lines.append(
                f"  {d['date']}: 收盘 {d['close']:.4f}, "
                f"涨跌 {change_emoji}{change:+.2f}%"
            )

        return "\n".join(lines)

    @staticmethod
    def format_tech_summary(indicators: dict[str, Any]) -> str:
        """
        格式化技术指标摘要

        Args:
            indicators: 技术指标字典

        Returns:
            格式化的技术指标文本
        """
        if not indicators:
            return ""

        lines = [
            f"  - 当前价格: {indicators.get('current_price', 0):.4f}",
            f"  - 5日均线(MA5): {indicators.get('ma5', 'N/A')}",
            f"  - 10日均线(MA10): {indicators.get('ma10', 'N/A')}",
            f"  - 20日均线(MA20): {indicators.get('ma20', 'N/A')}",
            f"  - 5日收益率: {indicators.get('return_5d', 'N/A')}%",
            f"  - 10日收益率: {indicators.get('return_10d', 'N/A')}%",
            f"  - 20日波动率: {indicators.get('volatility', 'N/A')}",
            f"  - 趋势判断: {indicators.get('trend', '未知')}",
        ]

        return "\n".join(lines)
