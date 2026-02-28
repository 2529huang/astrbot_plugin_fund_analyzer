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
2. 深度解读技术指标（MACD金叉/死叉/背离、RSI多周期超买超卖/背离、KDJ、布林带等）和市场趋势
3. 解读绩效指标（夏普比率、索提诺比率、最大回撤、VaR等）
4. 评估策略回测结果和量化交易信号
5. 追踪影响基金表现的各类因素
6. 给出专业、客观、谨慎的投资建议

**核心原则：你必须保持分析视角的平衡性。无论整体看多还是看空，都必须同时输出看涨理由和看跌理由/风险提示，帮助投资者全面了解可能的风险。**

请始终保持专业、客观的分析态度，基于量化数据进行分析，注意风险提示。"""


# ============================================================
# 新闻摘要提示词模板
# ============================================================

NEWS_SUMMARY_PROMPT = """请简要总结当前"{fund_name}"（追踪{underlying}）相关的市场动态和新闻要点。

当前日期：{current_date}
当前季节性背景：{seasonal_context}
建议搜索关键词：{search_keywords}

**国际形势分析要点：**
{global_situation_text}

请从以下维度分析：
1. **商品/资产价格动态**：相关商品或资产的最新国际/国内价格走势
2. **国际形势与地缘政治**：当前国际局势对该资产的影响（如地缘冲突、大国博弈等）
3. **央行与货币政策**：美联储、中国央行等政策动向及其影响
4. **政策与事件影响**：近期影响该基金的重要政策或突发事件
5. **市场情绪与资金**：市场情绪变化和资金流向趋势
6. **季节性因素**：当前时期的季节性消费/需求特点

请用5-8条要点简要概括，每条不超过60字。注意标注利多🔺或利空🔻信号。"""


# ============================================================
# 主分析提示词模板
# ============================================================

ANALYSIS_PROMPT_TEMPLATE = """你是一位专业的量化基金分析师，精通中国市场和国际形势。请基于以下量化数据和技术指标对基金进行深度分析，并给出**明确具体**的投资建议。

**⚠️ 重要要求：你必须同时给出看涨理由和看跌理由，保持分析的客观平衡。即使整体看多，也必须详细说明潜在的下跌风险和看跌因素。**

## 基金基本信息
- 基金名称: {fund_name}
- 基金代码: {fund_code}
- 最新价格: {latest_price:.4f}
- 今日涨跌: {change_rate:+.2f}%
- 成交额: {amount:,.0f}
- 分析日期: {current_date}

## 绩效量化分析
{performance_summary}

## 技术指标详情
{tech_indicators}

## 策略回测结果
{backtest_summary}

## 影响因素分析（含季节性）
{factors_text}

## 国际形势与地缘政治
{global_situation_text}

## 资金流向数据（主力净流入）
{fund_flow_text}

## 近期行情走势
{history_summary}

## 相关新闻资讯（含国际形势）
{news_summary}

## 请按以下格式输出分析报告:

### 1. 基金概况
简要介绍该基金的投资标的和特点

### 2. 量化绩效评估
基于夏普比率、索提诺比率、最大回撤等指标评估基金的风险调整后收益表现

### 3. 技术面分析
#### 3.1 MACD指标深度解读
- DIF/DEA当前位置及趋势方向
- MACD柱状图变化趋势（红柱放大/缩小 or 绿柱放大/缩小）
- 金叉/死叉信号及其可靠性分析
- MACD背离检测结果（顶背离=看跌信号，底背离=看涨信号）

#### 3.2 RSI指标多周期分析
- 各周期RSI(6/12/14/24)的当前状态和所处区域
- RSI超买超卖判断及其对走势的指引
- RSI背离检测结果及其含义
- 多周期RSI一致性分析（共振判断）

#### 3.3 其他技术指标
- KDJ、布林带等辅助指标的确认/矛盾信号
- 均线系统排列和支撑/阻力位

### 4. 国际形势与地缘政治分析
**重点分析**：
- 当前国际局势对该资产的影响（地缘冲突、大国关系等）
- 美联储/各国央行政策走向
- 全球资金流向和避险情绪
- 对该基金的利多/利空判断

### 5. 影响因素综合分析
分析各个影响因素的当前状态和对基金的影响，包括：
- 宏观经济因素
- 行业/商品供需
- 政策面影响
- **季节性因素**（重点分析当前时期的特殊影响）

### 6. 资金流向解读
基于主力资金流向数据，分析：
- **主力资金动向**：近期主力累计净流入/净流出趋势
- **超大单与大单分析**：超大单（机构）和大单的流向是否一致，是否有分歧
- **主力与散户博弈**：主力净流入 vs 小单净流入的对比，判断是否存在主力吸筹/洗盘/出货迹象
- **资金势能判断**：结合价格和资金流向，判断当前资金势能（量价齐升、缩量上涨、放量下跌等）
- 对当前趋势的支撑/分歧信号

### 7. 新闻面解读
结合最新资讯分析市场情绪和潜在影响，标注利多🔺或利空🔻

### 7. 趋势预测
- 短期趋势(1周内): 结合技术信号、资金流向、国际形势和量化指标给出判断
- 中期趋势(1个月): 结合基本面、技术面、资金面、季节性和国际形势综合判断
- 上涨概率评估: (给出一个具体百分比，需要说明依据)

### 8. 🎯 核心投资建议（重点）

**请给出一个明确、具体、可操作的投资建议，格式如下：**

📊 **操作建议**: [强烈买入/买入/持有观望/减仓/卖出/强烈卖出]

⏰ **时间窗口**: [具体说明操作时间，如"未来1周内"、"春节前"、"本月底前"等]

💰 **仓位建议**: [具体仓位比例，如"建议配置20%-30%仓位"]

📝 **具体理由**（一句话总结）:
[例如："当前白银处于技术性超卖区间，叠加春节首饰消费旺季预期，1周内大概率反弹，建议逢低分批买入"]
[或："黄金连续3周下跌已破重要支撑位，美联储加息预期升温，短期仍有下行空间，建议先减仓观望"]

🎯 **目标价位**: [如有，给出参考目标价/止盈位]
🛑 **止损价位**: [给出参考止损位]

### 9. ⚠️ 风险提示与看跌理由（必须输出）

**此模块为强制输出项，无论整体判断方向如何，都必须详细列出以下内容：**

#### 9.1 技术面看跌信号
- 列出所有技术指标中呈现的看跌/风险信号（MACD死叉、顶背离、RSI超买、均线空头排列等）
- 即使当前看涨，也要说明哪些技术指标接近风险区域
- 关键支撑位跌破后的下行空间评估

#### 9.2 基本面/宏观风险
- 可能导致基金下跌的宏观经济风险因素
- 政策变化风险（加息、监管收紧等）
- 行业/标的特有的下行风险

#### 9.3 量化风险指标
- VaR风险值解读（95%概率下的最大日亏损）
- 最大回撤风险评估
- 波动率异常情况

#### 9.4 国际形势风险
- 地缘政治不确定性对该资产的潜在冲击
- 外汇汇率变动风险
- 全球流动性收紧风险

#### 9.5 季节性风险
- 当前时期是否存在季节性下跌规律
- 历史同期的回撤情况

#### 9.6 最坏情景分析
- 如果上述风险同时发生，预计最大可能跌幅
- 建议的风险应对策略（止损位、对冲方式等）

请用专业但易懂的语言进行分析，**核心建议必须明确具体，让投资者能直接执行**。**风险提示/看跌理由模块必须充分、详尽，确保投资者了解所有潜在风险。**"""


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
    def build_news_prompt(
        fund_name: str,
        underlying: str,
        seasonal_context: str = "",
        search_keywords: list[str] | None = None,
        global_situation_text: str = "",
    ) -> str:
        """
        构建新闻摘要提示词

        Args:
            fund_name: 基金名称
            underlying: 追踪标的
            seasonal_context: 当前季节性背景
            search_keywords: 建议的搜索关键词列表
            global_situation_text: 国际形势分析文本

        Returns:
            提示词字符串
        """
        from datetime import datetime

        keywords_str = "、".join(search_keywords[:8]) if search_keywords else underlying

        return NEWS_SUMMARY_PROMPT.format(
            fund_name=fund_name,
            underlying=underlying,
            current_date=datetime.now().strftime("%Y年%m月%d日"),
            seasonal_context=seasonal_context if seasonal_context else "无特殊季节性因素",
            search_keywords=keywords_str,
            global_situation_text=global_situation_text if global_situation_text else "无特定国际形势关注点",
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
