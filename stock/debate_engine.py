"""
多智能体辩论引擎
通过对同一 LLM 发起多轮请求（不同 system_prompt）模拟多智能体博弈

架构：
  Phase 1: 六大 Agent 并行分析（6 次 LLM 调用，可并发）
  Phase 2: 多方辩手综合看涨论据（1 次 LLM 调用）
  Phase 3: 空方辩手综合看跌论据 + 反驳多方（1 次 LLM 调用）
  Phase 4: 裁判博弈论综合裁定（1 次 LLM 调用）

共 9 次 LLM 调用（Phase 1 可并发，整体约 3-4 轮延迟）
"""

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from astrbot.api import logger

from .agent_prompts import (
    AGENT_CONFIGS,
    BEAR_DEBATER_PROMPT,
    BULL_DEBATER_PROMPT,
    JUDGE_PROMPT,
)
from .data_collector import DataCollector


@dataclass
class AgentReport:
    """单个 Agent 的分析报告"""

    agent_id: str
    agent_name: str
    agent_emoji: str
    analysis: str
    direction: str = "中性"  # 看涨/看跌/中性
    confidence: float = 50.0
    error: str = ""


@dataclass
class DebateResult:
    """辩论结果"""

    # Phase 1: 六大 Agent 分析报告
    agent_reports: list[AgentReport] = field(default_factory=list)
    # Phase 2 & 3: 多空辩论
    bull_argument: str = ""
    bear_argument: str = ""
    # Phase 4: 裁判裁定
    judge_verdict: str = ""
    # 解析后的结论
    final_direction: str = "中性"  # 看涨/看跌/中性
    confidence: float = 50.0
    bull_win_rate: float = 50.0
    bear_win_rate: float = 50.0
    # 元数据
    stock_name: str = ""
    stock_code: str = ""
    stock_price: float = 0.0
    stock_change_rate: float = 0.0
    total_llm_calls: int = 0
    total_time_seconds: float = 0.0


class DebateEngine:
    """多智能体辩论引擎"""

    def __init__(self, context: Any):
        """
        Args:
            context: AstrBot Context，用于获取 LLM Provider
        """
        self.context = context

    def _get_provider(self):
        """获取 LLM Provider"""
        provider = self.context.get_using_provider()
        if not provider:
            raise ValueError("未配置大模型提供商，请在管理面板配置 LLM 后再试")
        return provider

    async def _call_llm(
        self,
        system_prompt: str,
        user_content: str,
    ) -> str:
        """
        调用 LLM（单次独立请求，不污染用户会话）

        Args:
            system_prompt: 角色系统提示词
            user_content: 用户输入数据

        Returns:
            LLM 回复文本
        """
        provider = self._get_provider()

        try:
            resp = await provider.text_chat(
                prompt=user_content,
                system_prompt=system_prompt,
            )

            if hasattr(resp, "completion_text"):
                return resp.completion_text
            return str(resp)
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            raise

    async def _run_single_agent(
        self,
        agent_id: str,
        agent_data: str,
    ) -> AgentReport:
        """
        运行单个 Agent 分析

        Args:
            agent_id: Agent 标识
            agent_data: 该 Agent 需要的数据文本

        Returns:
            AgentReport
        """
        config = AGENT_CONFIGS[agent_id]

        try:
            analysis = await self._call_llm(
                system_prompt=config["prompt"],
                user_content=(f"请基于以下数据进行你的专业分析：\n\n{agent_data}"),
            )

            # 尝试从分析文本中提取方向和信心度
            direction, confidence = self._parse_agent_direction(analysis)

            return AgentReport(
                agent_id=agent_id,
                agent_name=config["name"],
                agent_emoji=config["emoji"],
                analysis=analysis,
                direction=direction,
                confidence=confidence,
            )

        except Exception as e:
            logger.error(f"Agent [{config['name']}] 分析失败: {e}")
            return AgentReport(
                agent_id=agent_id,
                agent_name=config["name"],
                agent_emoji=config["emoji"],
                analysis="",
                error=str(e),
            )

    async def run_debate(
        self,
        fund_info: Any,
        history_data: list[dict],
        fund_flow_data: list[dict] | None = None,
        news_summary: str = "",
        factors_text: str = "",
        global_situation_text: str = "",
        quant_analyzer: Any = None,
        eastmoney_api: Any = None,
        progress_callback: Callable | None = None,
    ) -> DebateResult:
        """
        执行完整的多智能体辩论流程

        Args:
            fund_info: 基金/股票信息对象
            history_data: 历史K线数据
            fund_flow_data: 资金流向数据
            news_summary: 新闻摘要
            factors_text: 影响因素文本
            global_situation_text: 国际形势文本
            quant_analyzer: QuantAnalyzer 实例
            eastmoney_api: EastMoneyAPI 实例
            progress_callback: 进度回调，async func(str) 用于通知进度

        Returns:
            DebateResult 完整辩论结果
        """
        start_time = datetime.now()
        result = DebateResult(
            stock_name=fund_info.name,
            stock_code=fund_info.code,
            stock_price=getattr(fund_info, "latest_price", 0.0),
            stock_change_rate=getattr(fund_info, "change_rate", 0.0),
        )

        # Step 0: 采集数据
        if progress_callback:
            await progress_callback("📡 正在采集多维度市场数据...")

        collector = DataCollector(
            eastmoney_api=eastmoney_api,
            quant_analyzer=quant_analyzer,
        )
        agent_data = await collector.collect_all(
            fund_code=fund_info.code,
            fund_info=fund_info,
            history_data=history_data,
            fund_flow_data=fund_flow_data,
            news_summary=news_summary,
            factors_text=factors_text,
            global_situation_text=global_situation_text,
        )

        # ============================================================
        # Phase 1: 六大 Agent 并行分析（6次 LLM 调用，并发执行）
        # ============================================================
        if progress_callback:
            await progress_callback(
                "🧠 Phase 1/4: 六大分析师正在并行分析...\n"
                "  📰 舆情 | 🦈 游资 | 🛡️ 风控\n"
                "  📊 技术 | 🧩 筹码 | ⚡ 大单异动"
            )

        agent_ids = list(AGENT_CONFIGS.keys())
        tasks = [
            self._run_single_agent(agent_id, agent_data[agent_id])
            for agent_id in agent_ids
        ]
        reports = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
        for r in reports:
            if isinstance(r, Exception):
                logger.error(f"Agent 执行异常: {r}")
                continue
            result.agent_reports.append(r)

        result.total_llm_calls += len(agent_ids)

        # 汇总六大 Agent 的分析文本
        agents_summary = self._build_agents_summary(result.agent_reports)

        # ============================================================
        # Phase 2: 多方辩手综合看涨论据（1次 LLM 调用）
        # ============================================================
        if progress_callback:
            await progress_callback("🟢 Phase 2/4: 多方辩手正在组织看涨论据...")

        name_code = f"{fund_info.name}({fund_info.code})"
        bull_input = (
            f"以下是六位专业分析师对 {name_code} 的独立分析报告：\n\n"
            f"{agents_summary}\n\n"
            f"请从以上分析中提取、整合所有看涨论据，为多方辩护。"
        )

        try:
            result.bull_argument = await self._call_llm(
                system_prompt=BULL_DEBATER_PROMPT,
                user_content=bull_input,
            )
            result.total_llm_calls += 1
        except Exception as e:
            logger.error(f"多方辩手失败: {e}")
            result.bull_argument = f"[多方辩手分析失败: {e}]"

        # ============================================================
        # Phase 3: 空方辩手综合看跌论据 + 反驳（1次 LLM 调用）
        # ============================================================
        if progress_callback:
            await progress_callback(
                "🔴 Phase 3/4: 空方辩手正在组织看跌论据并反驳多方..."
            )

        bear_input = (
            f"以下是六位专业分析师对 {name_code} 的独立分析报告：\n\n"
            f"{agents_summary}\n\n"
            f"---\n\n"
            f"以下是多方辩手的看涨论证（请逐条质疑和反驳）：\n\n"
            f"{result.bull_argument}"
        )

        try:
            result.bear_argument = await self._call_llm(
                system_prompt=BEAR_DEBATER_PROMPT,
                user_content=bear_input,
            )
            result.total_llm_calls += 1
        except Exception as e:
            logger.error(f"空方辩手失败: {e}")
            result.bear_argument = f"[空方辩手分析失败: {e}]"

        # ============================================================
        # Phase 4: 裁判博弈论综合裁定（1次 LLM 调用）
        # ============================================================
        if progress_callback:
            await progress_callback("⚖️ Phase 4/4: 裁判正在进行博弈论综合裁定...")

        price = fund_info.latest_price
        change = fund_info.change_rate
        judge_input = (
            f"# 分析标的：{name_code}\n"
            f"当前价格：{price:.4f}  涨跌：{change:+.2f}%\n\n"
            f"---\n\n"
            f"## 六位分析师的独立报告\n\n{agents_summary}\n\n"
            f"---\n\n"
            f"## 🟢 多方辩手论证\n\n{result.bull_argument}\n\n"
            f"---\n\n"
            f"## 🔴 空方辩手论证\n\n{result.bear_argument}"
        )

        try:
            result.judge_verdict = await self._call_llm(
                system_prompt=JUDGE_PROMPT,
                user_content=judge_input,
            )
            result.total_llm_calls += 1
        except Exception as e:
            logger.error(f"裁判裁定失败: {e}")
            result.judge_verdict = f"[裁判裁定失败: {e}]"

        # 解析裁判结论
        (
            direction,
            confidence,
            bull_rate,
            bear_rate,
        ) = self._parse_judge_verdict(result.judge_verdict)
        result.final_direction = direction
        result.confidence = confidence
        result.bull_win_rate = bull_rate
        result.bear_win_rate = bear_rate

        # 计算耗时
        elapsed = (datetime.now() - start_time).total_seconds()
        result.total_time_seconds = elapsed

        if progress_callback:
            calls = result.total_llm_calls
            await progress_callback(
                f"✅ 分析完成！共 {calls} 次 AI 对话，耗时 {elapsed:.0f} 秒"
            )

        return result

    def _build_agents_summary(self, reports: list[AgentReport]) -> str:
        """将六大 Agent 的报告汇总为文本"""
        parts = []
        for r in reports:
            if r.error:
                parts.append(
                    f"### {r.agent_emoji} {r.agent_name}\n[分析失败: {r.error}]\n"
                )
            else:
                direction_emoji = {
                    "看涨": "🟢",
                    "看跌": "🔴",
                    "中性": "🟡",
                }.get(r.direction, "⚪")

                header = (
                    f"### {r.agent_emoji} {r.agent_name} "
                    f"{direction_emoji}{r.direction}"
                    f"（信心度{r.confidence:.0f}）"
                )
                parts.append(f"{header}\n\n{r.analysis}\n")
        return "\n---\n\n".join(parts)

    def _parse_agent_direction(self, text: str) -> tuple[str, float]:
        """从 Agent 分析文本中提取方向和信心度"""
        direction = "中性"
        confidence = 50.0

        # 提取方向（兑容 markdown 加粗标记）
        # 匹配: 方向判断：看涨 / **方向判断**：看涨 / **方向判断：**看涨
        dir_match = re.search(
            r"\*{0,2}方向判断\*{0,2}[\uff1a:]+\s*\*{0,2}\s*(看涨|看跌|中性)",
            text,
        )
        if not dir_match:
            # 备用：只匹配 "方向" 关键字
            dir_match = re.search(
                r"\*{0,2}方向\*{0,2}[\uff1a:]+\s*\*{0,2}\s*(看涨|看跌|中性)",
                text,
            )
        if dir_match:
            direction = dir_match.group(1)

        # 提取信心度（兑容 markdown 加粗标记）
        conf_match = re.search(
            r"\*{0,2}信心度\*{0,2}[\uff1a:]+\s*\*{0,2}\s*(\d+)",
            text,
        )
        if conf_match:
            confidence = float(conf_match.group(1))
            confidence = max(0, min(100, confidence))

        return direction, confidence

    def _parse_judge_verdict(self, text: str) -> tuple[str, float, float, float]:
        """
        从裁判裁定中提取关键结论

        Returns:
            (方向, 信心度, 多方胜率, 空方胜率)
        """
        direction = "中性"
        confidence = 50.0
        bull_rate = 50.0
        bear_rate = 50.0

        # 提取方向（兼容 markdown 加粗标记）
        dir_match = re.search(
            r"\*{0,2}方向\*{0,2}[\uff1a:]+\s*\*{0,2}\s*(看涨|看跌|中性|观望)",
            text,
        )
        if dir_match:
            raw = dir_match.group(1)
            direction = "中性" if raw == "观望" else raw

        # 提取信心度（兼容 markdown 加粗标记）
        conf_match = re.search(
            r"\*{0,2}信心度\*{0,2}[\uff1a:]+\s*\*{0,2}\s*(\d+)",
            text,
        )
        if conf_match:
            confidence = float(conf_match.group(1))
            confidence = max(0, min(100, confidence))

        # 提取多方胜率（兼容 markdown 加粗标记）
        bull_match = re.search(
            r"\*{0,2}多方胜率\*{0,2}[\uff1a:]+\s*\*{0,2}\s*(\d+)",
            text,
        )
        if bull_match:
            bull_rate = float(bull_match.group(1))

        # 提取空方胜率（兼容 markdown 加粗标记）
        bear_match = re.search(
            r"\*{0,2}空方胜率\*{0,2}[\uff1a:]+\s*\*{0,2}\s*(\d+)",
            text,
        )
        if bear_match:
            bear_rate = float(bear_match.group(1))

        return direction, confidence, bull_rate, bear_rate

    @staticmethod
    def _strip_markdown(text: str) -> str:
        """去除文本中的 Markdown 格式标记，返回纯文本"""
        # 去除标题标记
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
        # 去除加粗/斜体
        text = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", text)
        text = re.sub(r"_{1,3}(.*?)_{1,3}", r"\1", text)
        # 去除链接 [text](url)
        text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
        # 去除表格分隔行
        text = re.sub(r"^\|[-:| ]+\|$", "", text, flags=re.MULTILINE)
        # 简化表格行（去掉 |）
        text = re.sub(
            r"^\|(.+)\|$",
            lambda m: m.group(1).replace("|", "  ").strip(),
            text,
            flags=re.MULTILINE,
        )
        # 去除分隔线
        text = re.sub(r"^[-*_]{3,}$", "", text, flags=re.MULTILINE)
        # 去除代码块
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        # 去除列表标记 (- item / * item)
        text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
        # 清理多余空行
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _extract_plain_conclusion(self, judge_verdict: str) -> str:
        """从裁判裁定中提取简明结论（纯文本）"""
        if not judge_verdict:
            return ""

        # 1. 尝试提取 "=== 简明结论 ===" 标记后的内容
        match = re.search(
            r"===\s*简明结论\s*===[：:\s]*\n?(.*?)(?:⚠️|$)",
            judge_verdict,
            re.DOTALL,
        )
        if match:
            raw = match.group(1).strip()
            cleaned = self._strip_markdown(raw)
            if cleaned and len(cleaned) > 10:
                return cleaned

        # 2. 尝试提取"简明结论"标题后内容
        match2 = re.search(
            r"简明结论[：:\s]*\n(.*?)(?:⚠️|$)",
            judge_verdict,
            re.DOTALL,
        )
        if match2:
            raw = match2.group(1).strip()
            cleaned = self._strip_markdown(raw)
            if cleaned and len(cleaned) > 10:
                return cleaned

        # 3. 兜底：提取"操作建议"部分
        op_match = re.search(
            r"操作建议[\s\S]*?\n([\s\S]*?)(?=\n#{1,4}\s|\n===|⚠️|$)",
            judge_verdict,
        )
        if op_match:
            raw = op_match.group(1).strip()
            cleaned = self._strip_markdown(raw)
            if cleaned:
                # 限制长度
                if len(cleaned) > 200:
                    cleaned = cleaned[:200] + "..."
                return cleaned

        return ""

    def format_debate_summary(self, result: DebateResult) -> str:
        """
        格式化辩论结果为简洁纯文本摘要（不含任何 markdown）
        作为图片报告的文字补充，方便快速阅读
        """
        direction_map = {
            "看涨": "📈 看涨",
            "看跌": "📉 看跌",
            "中性": "↔️ 中性",
        }
        direction_text = direction_map.get(result.final_direction, "❓ 未知")

        # 统计投票
        bull_count = sum(1 for r in result.agent_reports if r.direction == "看涨")
        bear_count = sum(1 for r in result.agent_reports if r.direction == "看跌")
        neutral_count = sum(1 for r in result.agent_reports if r.direction == "中性")

        lines = [
            f"⚖️ 【{result.stock_name}】多智能体博弈结论",
            "━━━━━━━━━━━━━━━━━",
            f"当前价格: {result.stock_price:.4f} ({result.stock_change_rate:+.2f}%)",
            f"裁定方向: {direction_text}",
            f"信心度: {result.confidence:.0f}/100",
            f"多方胜率: {result.bull_win_rate:.0f}% | 空方胜率: {result.bear_win_rate:.0f}%",
            "━━━━━━━━━━━━━━━━━",
            f"分析师投票: 看涨x{bull_count} 看跌x{bear_count} 中性x{neutral_count}",
        ]

        # 每个 Agent 一行
        for r in result.agent_reports:
            dir_emoji = {
                "看涨": "🟢",
                "看跌": "🔴",
                "中性": "🟡",
            }.get(r.direction, "⚪")
            lines.append(
                f"  {r.agent_emoji} {r.agent_name}: "
                f"{dir_emoji}{r.direction}({r.confidence:.0f})"
            )

        # 提取裁判简明结论
        conclusion = self._extract_plain_conclusion(result.judge_verdict)
        if conclusion:
            lines.append("━━━━━━━━━━━━━━━━━")
            lines.append(conclusion)

        lines.append("━━━━━━━━━━━━━━━━━")
        lines.append(
            f"共{result.total_llm_calls}次AI对话 | 耗时{result.total_time_seconds:.0f}s"
        )
        lines.append("⚠️ 仅供参考，不构成投资建议")

        return "\n".join(lines)
