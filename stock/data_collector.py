"""
数据采集器模块
为六大 Agent 统一采集和整理所需的市场数据
"""

from datetime import datetime
from typing import Any


class DataCollector:
    """多 Agent 数据采集器，统一收集各维度原始数据"""

    def __init__(self, eastmoney_api, quant_analyzer):
        """
        Args:
            eastmoney_api: EastMoneyAPI 实例
            quant_analyzer: QuantAnalyzer 实例
        """
        self._api = eastmoney_api
        self._quant = quant_analyzer

    async def collect_all(
        self,
        fund_code: str,
        fund_info: Any,
        history_data: list[dict],
        fund_flow_data: list[dict] | None = None,
        news_summary: str = "",
        factors_text: str = "",
        global_situation_text: str = "",
    ) -> dict[str, str]:
        """
        采集所有 Agent 所需数据，返回各 Agent 的数据文本

        Returns:
            dict: key 为 agent id，value 为该 agent 的数据文本
        """
        # 计算量化指标
        tech_indicators = self._quant.calculate_all_indicators(history_data)
        performance = self._quant.calculate_performance(history_data)
        backtest_results = self._quant.run_all_backtests(history_data)

        # 格式化基础信息（所有 Agent 共享）
        base_info = self._format_base_info(fund_info, history_data)

        # 格式化资金流向
        flow_text = self._format_fund_flow(fund_flow_data)

        # 格式化技术指标
        tech_text = self._quant.format_indicators_text(tech_indicators)

        # 格式化绩效指标
        perf_text = (
            self._quant.format_performance_text(performance)
            if performance
            else "历史数据不足"
        )

        # 格式化回测结果
        bt_text = self._quant.format_backtest_text(backtest_results)

        # 格式化近期行情（最近 15 天）
        recent_history = self._format_recent_history(history_data, days=15)

        # 格式化量价关系
        volume_price_text = self._format_volume_price(history_data)

        # 构建各 Agent 的专属数据包
        agent_data = {}

        # 1. 舆情 Agent：新闻 + 国际形势 + 季节性 + 基础信息
        agent_data["sentiment"] = (
            f"{base_info}\n\n"
            f"## 相关新闻与舆情\n{news_summary or '暂无新闻数据'}\n\n"
            f"## 影响因素与季节性\n{factors_text or '暂无'}\n\n"
            f"## 国际形势\n{global_situation_text or '暂无'}\n\n"
            f"## 近期行情\n{recent_history}"
        )

        # 2. 游资 Agent：资金流向 + 换手率 + 成交量 + 基础信息
        agent_data["hot_money"] = (
            f"{base_info}\n\n"
            f"## 资金流向数据（主力/超大单/大单/中单/小单）\n{flow_text}\n\n"
            f"## 量价关系\n{volume_price_text}\n\n"
            f"## 近期行情\n{recent_history}"
        )

        # 3. 风控 Agent：绩效指标 + 国际形势 + 季节性 + 技术指标
        agent_data["risk_control"] = (
            f"{base_info}\n\n"
            f"## 绩效与风险指标\n{perf_text}\n\n"
            f"## 技术指标\n{tech_text}\n\n"
            f"## 策略回测\n{bt_text}\n\n"
            f"## 国际形势\n{global_situation_text or '暂无'}\n\n"
            f"## 影响因素与季节性\n{factors_text or '暂无'}\n\n"
            f"## 近期行情\n{recent_history}"
        )

        # 4. 技术 Agent：技术指标 + 绩效指标 + K线数据
        agent_data["technical"] = (
            f"{base_info}\n\n"
            f"## 技术指标详情\n{tech_text}\n\n"
            f"## 绩效指标\n{perf_text}\n\n"
            f"## 策略回测结果\n{bt_text}\n\n"
            f"## 近期行情（含量价）\n{recent_history}\n\n"
            f"## 量价关系分析\n{volume_price_text}"
        )

        # 5. 筹码 Agent：资金流向 + 量价关系 + 技术指标
        agent_data["chip"] = (
            f"{base_info}\n\n"
            f"## 资金流向数据\n{flow_text}\n\n"
            f"## 量价关系\n{volume_price_text}\n\n"
            f"## 技术指标（辅助）\n{tech_text}\n\n"
            f"## 近期行情\n{recent_history}"
        )

        # 6. 大单异动 Agent：资金流向 + 成交量异动 + 量价关系
        agent_data["big_order"] = (
            f"{base_info}\n\n"
            f"## 资金流向数据（重点关注超大单和大单）\n{flow_text}\n\n"
            f"## 量价关系与异动检测\n{volume_price_text}\n\n"
            f"## 近期行情（含成交量）\n{recent_history}"
        )

        return agent_data

    def _format_base_info(self, fund_info: Any, history_data: list[dict]) -> str:
        """格式化基础信息（所有 Agent 共享）"""
        lines = [
            f"# 分析标的：{fund_info.name} ({fund_info.code})",
            f"- 当前价格：{fund_info.latest_price:.4f}",
            f"- 今日涨跌：{fund_info.change_rate:+.2f}%",
            f"- 涨跌额：{fund_info.change_amount:+.4f}",
        ]

        if hasattr(fund_info, "open_price") and fund_info.open_price:
            lines.append(f"- 今开：{fund_info.open_price:.4f}")
        if hasattr(fund_info, "high_price") and fund_info.high_price:
            lines.append(f"- 最高：{fund_info.high_price:.4f}")
        if hasattr(fund_info, "low_price") and fund_info.low_price:
            lines.append(f"- 最低：{fund_info.low_price:.4f}")
        if hasattr(fund_info, "prev_close") and fund_info.prev_close:
            lines.append(f"- 昨收：{fund_info.prev_close:.4f}")
        if hasattr(fund_info, "volume") and fund_info.volume:
            lines.append(f"- 成交量：{fund_info.volume:,.0f}")
        if hasattr(fund_info, "amount") and fund_info.amount:
            lines.append(f"- 成交额：{fund_info.amount:,.0f}")
        if hasattr(fund_info, "turnover_rate") and fund_info.turnover_rate:
            lines.append(f"- 换手率：{fund_info.turnover_rate:.2f}%")

        lines.append(f"- 分析时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")

        return "\n".join(lines)

    def _format_fund_flow(self, flow_data: list[dict] | None) -> str:
        """格式化资金流向数据"""
        if not flow_data:
            return "暂无资金流向数据（场外基金或数据源不可用）"

        lines = []
        lines.append("| 日期 | 主力净流入 | 超大单 | 大单 | 中单 | 小单 |")
        lines.append("|------|-----------|--------|------|------|------|")

        total_main = 0.0
        total_super = 0.0
        total_large = 0.0
        total_small = 0.0
        positive_days = 0

        for item in flow_data[-10:]:
            date = item["date"]
            main = item["main_net_inflow"]
            super_l = item["super_large_inflow"]
            large = item["large_inflow"]
            medium = item["medium_inflow"]
            small = item["small_inflow"]

            total_main += main
            total_super += super_l
            total_large += large
            total_small += small
            if main > 0:
                positive_days += 1

            def fmt(val):
                if abs(val) >= 1e8:
                    return f"{val / 1e8:+.2f}亿"
                elif abs(val) >= 1e4:
                    return f"{val / 1e4:+.2f}万"
                else:
                    return f"{val:+.0f}"

            lines.append(
                f"| {date} | {fmt(main)} | {fmt(super_l)} "
                f"| {fmt(large)} | {fmt(medium)} | {fmt(small)} |"
            )

        n = len(flow_data[-10:])
        lines.append("")
        lines.append(f"**近{n}日汇总**：")

        def fmt_s(val):
            if abs(val) >= 1e8:
                return f"{val / 1e8:+.2f}亿"
            elif abs(val) >= 1e4:
                return f"{val / 1e4:+.2f}万"
            else:
                return f"{val:+.0f}"

        lines.append(f"- 主力累计净流入: {fmt_s(total_main)}")
        lines.append(f"- 超大单累计净流入: {fmt_s(total_super)}")
        lines.append(f"- 大单累计净流入: {fmt_s(total_large)}")
        lines.append(f"- 小单累计净流入: {fmt_s(total_small)}")
        lines.append(f"- 主力净流入天数: {positive_days}/{n}天")

        # 主力 vs 散户对比
        if total_main > 0 and total_small < 0:
            lines.append("- ⚠️ 主力买入+散户卖出 → 可能吸筹")
        elif total_main < 0 and total_small > 0:
            lines.append("- ⚠️ 主力卖出+散户买入 → 可能出货")

        # 近3日趋势
        if n >= 3:
            recent_3 = flow_data[-3:]
            recent_trend = sum(d["main_net_inflow"] for d in recent_3)
            if recent_trend > 0:
                lines.append(
                    f"- 近3日趋势: 主力资金净流入 {fmt_s(recent_trend)} 🔺"
                )
            else:
                lines.append(
                    f"- 近3日趋势: 主力资金净流出 {fmt_s(recent_trend)} 🔻"
                )

        return "\n".join(lines)

    def _format_recent_history(
        self, history_data: list[dict], days: int = 15
    ) -> str:
        """格式化近期行情"""
        if not history_data:
            return "暂无历史行情数据"

        recent = history_data[-days:]
        lines = ["| 日期 | 收盘 | 涨跌% | 成交量 | 成交额 |"]
        lines.append("|------|------|-------|--------|--------|")

        for d in recent:
            change = d.get("change_rate", 0)
            emoji = "📈" if change > 0 else "📉" if change < 0 else "➡️"
            vol = d.get("volume", 0)
            amt = d.get("amount", 0)

            vol_str = f"{vol:,.0f}" if vol else "-"
            if amt >= 1e8:
                amt_str = f"{amt / 1e8:.2f}亿"
            elif amt >= 1e4:
                amt_str = f"{amt / 1e4:.0f}万"
            else:
                amt_str = f"{amt:.0f}" if amt else "-"

            lines.append(
                f"| {d['date']} | {d['close']:.4f} "
                f"| {emoji}{change:+.2f}% | {vol_str} | {amt_str} |"
            )

        return "\n".join(lines)

    def _format_volume_price(self, history_data: list[dict]) -> str:
        """分析量价关系"""
        if not history_data or len(history_data) < 5:
            return "历史数据不足，无法分析量价关系"

        recent = history_data[-10:]
        lines = []

        # 计算平均成交量
        volumes = [
            d.get("volume", 0) for d in recent if d.get("volume", 0) > 0
        ]
        if not volumes:
            return "无成交量数据"

        avg_vol = sum(volumes) / len(volumes)
        latest = recent[-1]
        latest_vol = latest.get("volume", 0)
        latest_change = latest.get("change_rate", 0)

        # 量比
        vol_ratio = latest_vol / avg_vol if avg_vol > 0 else 0

        lines.append(f"- 最新成交量: {latest_vol:,.0f}")
        lines.append(f"- 近10日均量: {avg_vol:,.0f}")
        lines.append(f"- 量比: {vol_ratio:.2f}")

        # 量价关系判断
        if vol_ratio > 1.5 and latest_change > 0:
            lines.append("- 📊 量价关系: **放量上涨** — 多头强势")
        elif vol_ratio < 0.7 and latest_change > 0:
            lines.append("- 📊 量价关系: **缩量上涨** — 上涨乏力，警惕回调")
        elif vol_ratio > 1.5 and latest_change < 0:
            lines.append("- 📊 量价关系: **放量下跌** — 恐慌抛售或主力出货")
        elif vol_ratio < 0.7 and latest_change < 0:
            lines.append("- 📊 量价关系: **缩量下跌** — 下跌动能减弱")
        elif vol_ratio < 0.5:
            lines.append(
                "- 📊 量价关系: **地量** — 极度低迷，可能接近变盘点"
            )
        else:
            lines.append("- 📊 量价关系: **量价正常** — 无明显异动")

        # 连续放量/缩量检测
        if len(recent) >= 3:
            last3_vols = [d.get("volume", 0) for d in recent[-3:]]
            if all(last3_vols[i] > last3_vols[i - 1] for i in range(1, 3)):
                lines.append("- ⚡ 异动: 连续3日成交量递增（量能放大）")
            elif all(
                last3_vols[i] < last3_vols[i - 1] for i in range(1, 3)
            ):
                lines.append("- ⚡ 异动: 连续3日成交量递减（量能萎缩）")

        # 最近单日成交量异常检测（超过均值2倍）
        for d in recent[-5:]:
            v = d.get("volume", 0)
            if avg_vol > 0 and v > avg_vol * 2:
                ratio = v / avg_vol
                lines.append(
                    f"- ⚡ 异动: {d['date']} 成交量 {v:,.0f} "
                    f"为均值 {avg_vol:,.0f} 的 {ratio:.1f} 倍"
                )

        return "\n".join(lines)
