"""
量化分析模块
提供策略回测、绩效分析、技术指标计算等专业量化功能
"""

import math
from dataclasses import dataclass, field


@dataclass
class BacktestResult:
    """回测结果"""

    strategy_name: str  # 策略名称
    total_return: float  # 总收益率 (%)
    annual_return: float  # 年化收益率 (%)
    max_drawdown: float  # 最大回撤 (%)
    sharpe_ratio: float  # 夏普比率
    win_rate: float  # 胜率 (%)
    profit_loss_ratio: float  # 盈亏比
    trade_count: int  # 交易次数
    signals: list[dict] = field(default_factory=list)  # 交易信号


@dataclass
class PerformanceMetrics:
    """绩效指标"""

    # 收益指标
    total_return: float  # 累计收益率 (%)
    annual_return: float  # 年化收益率 (%)
    daily_return_mean: float  # 日均收益率 (%)
    daily_return_std: float  # 日收益率标准差 (%)

    # 风险指标
    volatility: float  # 年化波动率 (%)
    max_drawdown: float  # 最大回撤 (%)
    max_drawdown_duration: int  # 最大回撤持续天数
    var_95: float  # 95% VaR
    var_99: float  # 99% VaR

    # 风险调整收益
    sharpe_ratio: float  # 夏普比率
    sortino_ratio: float  # 索提诺比率
    calmar_ratio: float  # 卡玛比率

    # 其他统计
    positive_days: int  # 上涨天数
    negative_days: int  # 下跌天数
    best_day: float  # 最佳单日收益 (%)
    worst_day: float  # 最差单日收益 (%)


@dataclass
class TechnicalIndicators:
    """技术指标"""

    # 趋势指标
    ma5: float | None = None
    ma10: float | None = None
    ma20: float | None = None
    ma60: float | None = None
    ema12: float | None = None
    ema26: float | None = None

    # MACD
    macd: float | None = None
    macd_signal: float | None = None
    macd_hist: float | None = None

    # RSI
    rsi_6: float | None = None
    rsi_14: float | None = None

    # 布林带
    boll_upper: float | None = None
    boll_middle: float | None = None
    boll_lower: float | None = None
    boll_width: float | None = None

    # KDJ
    kdj_k: float | None = None
    kdj_d: float | None = None
    kdj_j: float | None = None

    # 其他
    atr: float | None = None  # 平均真实波幅
    obv_trend: str | None = None  # OBV趋势

    # 综合判断
    trend_score: int = 0  # 趋势评分 (-100 到 100)
    signal: str = "观望"  # 信号: 强买/买入/观望/卖出/强卖


class QuantAnalyzer:
    """量化分析器"""

    # 无风险利率（年化），用于计算夏普比率
    RISK_FREE_RATE = 0.02  # 2%

    def __init__(self):
        pass

    # ============================================================
    # 技术指标计算
    # ============================================================

    @staticmethod
    def _sma(data: list[float], period: int) -> float | None:
        """简单移动平均"""
        if len(data) < period:
            return None
        return sum(data[-period:]) / period

    @staticmethod
    def _ema(data: list[float], period: int) -> float | None:
        """指数移动平均"""
        if len(data) < period:
            return None
        multiplier = 2 / (period + 1)
        ema = sum(data[:period]) / period  # 初始EMA用SMA
        for price in data[period:]:
            ema = (price - ema) * multiplier + ema
        return ema

    @staticmethod
    def _std(data: list[float]) -> float:
        """计算标准差"""
        if len(data) < 2:
            return 0
        mean = sum(data) / len(data)
        variance = sum((x - mean) ** 2 for x in data) / (len(data) - 1)
        return math.sqrt(variance)

    def calculate_rsi(self, prices: list[float], period: int = 14) -> float | None:
        """计算RSI指标"""
        if len(prices) < period + 1:
            return None

        changes = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
        gains = [max(0, c) for c in changes[-period:]]
        losses = [abs(min(0, c)) for c in changes[-period:]]

        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period

        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def calculate_macd(
        self, prices: list[float], fast: int = 12, slow: int = 26, signal: int = 9
    ) -> tuple[float | None, float | None, float | None]:
        """计算MACD指标"""
        if len(prices) < slow + signal:
            return None, None, None

        ema_fast = self._ema(prices, fast)
        ema_slow = self._ema(prices, slow)

        if ema_fast is None or ema_slow is None:
            return None, None, None

        macd_line = ema_fast - ema_slow

        # 计算MACD历史值用于信号线
        macd_history = []
        for i in range(slow, len(prices) + 1):
            ef = self._ema(prices[:i], fast)
            es = self._ema(prices[:i], slow)
            if ef and es:
                macd_history.append(ef - es)

        if len(macd_history) < signal:
            return macd_line, None, None

        signal_line = self._sma(macd_history, signal)
        histogram = macd_line - signal_line if signal_line else None

        return macd_line, signal_line, histogram

    def calculate_bollinger(
        self, prices: list[float], period: int = 20, std_dev: float = 2
    ) -> tuple[float | None, float | None, float | None]:
        """计算布林带"""
        if len(prices) < period:
            return None, None, None

        middle = self._sma(prices, period)
        std = self._std(prices[-period:])

        upper = middle + std_dev * std
        lower = middle - std_dev * std

        return upper, middle, lower

    def calculate_kdj(
        self,
        highs: list[float],
        lows: list[float],
        closes: list[float],
        period: int = 9,
    ) -> tuple[float | None, float | None, float | None]:
        """计算KDJ指标"""
        if len(closes) < period:
            return None, None, None

        # 计算RSV
        highest = max(highs[-period:])
        lowest = min(lows[-period:])

        if highest == lowest:
            rsv = 50
        else:
            rsv = (closes[-1] - lowest) / (highest - lowest) * 100

        # 简化计算K、D、J（使用当前RSV）
        k = rsv  # 实际应该是平滑后的值
        d = k  # 实际应该是K的平滑
        j = 3 * k - 2 * d

        return k, d, j

    def calculate_atr(
        self,
        highs: list[float],
        lows: list[float],
        closes: list[float],
        period: int = 14,
    ) -> float | None:
        """计算ATR（平均真实波幅）"""
        if len(closes) < period + 1:
            return None

        trs = []
        for i in range(1, len(closes)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            trs.append(tr)

        return sum(trs[-period:]) / period

    def calculate_all_indicators(self, history_data: list[dict]) -> TechnicalIndicators:
        """计算所有技术指标"""
        indicators = TechnicalIndicators()

        if not history_data or len(history_data) < 5:
            return indicators

        closes = [d["close"] for d in history_data]
        highs = [d.get("high", d["close"]) for d in history_data]
        lows = [d.get("low", d["close"]) for d in history_data]

        # 均线
        indicators.ma5 = self._sma(closes, 5)
        indicators.ma10 = self._sma(closes, 10)
        indicators.ma20 = self._sma(closes, 20)
        indicators.ma60 = self._sma(closes, 60)
        indicators.ema12 = self._ema(closes, 12)
        indicators.ema26 = self._ema(closes, 26)

        # MACD
        macd, signal, hist = self.calculate_macd(closes)
        indicators.macd = macd
        indicators.macd_signal = signal
        indicators.macd_hist = hist

        # RSI
        indicators.rsi_6 = self.calculate_rsi(closes, 6)
        indicators.rsi_14 = self.calculate_rsi(closes, 14)

        # 布林带
        upper, middle, lower = self.calculate_bollinger(closes)
        indicators.boll_upper = upper
        indicators.boll_middle = middle
        indicators.boll_lower = lower
        if upper and lower:
            indicators.boll_width = (upper - lower) / middle * 100 if middle else None

        # KDJ
        k, d, j = self.calculate_kdj(highs, lows, closes)
        indicators.kdj_k = k
        indicators.kdj_d = d
        indicators.kdj_j = j

        # ATR
        indicators.atr = self.calculate_atr(highs, lows, closes)

        # 综合评分和信号
        indicators.trend_score, indicators.signal = self._calculate_signal(
            closes[-1], indicators
        )

        return indicators

    def _calculate_signal(
        self, current_price: float, indicators: TechnicalIndicators
    ) -> tuple[int, str]:
        """计算综合信号评分"""
        score = 0

        # 均线评分 (-30 到 30)
        if indicators.ma5 and indicators.ma10 and indicators.ma20:
            if current_price > indicators.ma5 > indicators.ma10 > indicators.ma20:
                score += 30  # 多头排列
            elif current_price > indicators.ma5 > indicators.ma10:
                score += 20
            elif current_price > indicators.ma5:
                score += 10
            elif current_price < indicators.ma5 < indicators.ma10 < indicators.ma20:
                score -= 30  # 空头排列
            elif current_price < indicators.ma5 < indicators.ma10:
                score -= 20
            elif current_price < indicators.ma5:
                score -= 10

        # MACD评分 (-25 到 25)
        if indicators.macd_hist is not None:
            if indicators.macd_hist > 0:
                score += 15 if indicators.macd_hist > 0.01 else 10
            else:
                score -= 15 if indicators.macd_hist < -0.01 else 10

            if indicators.macd and indicators.macd_signal:
                if indicators.macd > indicators.macd_signal:
                    score += 10
                else:
                    score -= 10

        # RSI评分 (-25 到 25)
        if indicators.rsi_14:
            if indicators.rsi_14 > 70:
                score -= 25  # 超买
            elif indicators.rsi_14 > 60:
                score -= 10
            elif indicators.rsi_14 < 30:
                score += 25  # 超卖反弹机会
            elif indicators.rsi_14 < 40:
                score += 10

        # KDJ评分 (-20 到 20)
        if indicators.kdj_j is not None:
            if indicators.kdj_j > 100:
                score -= 20  # 超买
            elif indicators.kdj_j > 80:
                score -= 10
            elif indicators.kdj_j < 0:
                score += 20  # 超卖
            elif indicators.kdj_j < 20:
                score += 10

        # 限制评分范围
        score = max(-100, min(100, score))

        # 生成信号
        if score >= 60:
            signal = "强烈买入"
        elif score >= 30:
            signal = "买入"
        elif score >= -30:
            signal = "观望"
        elif score >= -60:
            signal = "卖出"
        else:
            signal = "强烈卖出"

        return score, signal

    # ============================================================
    # 绩效分析
    # ============================================================

    def calculate_performance(
        self, history_data: list[dict]
    ) -> PerformanceMetrics | None:
        """计算绩效指标"""
        if not history_data or len(history_data) < 5:
            return None

        closes = [d["close"] for d in history_data]
        daily_returns = []

        for i in range(1, len(closes)):
            if closes[i - 1] != 0:
                ret = (closes[i] - closes[i - 1]) / closes[i - 1] * 100
                daily_returns.append(ret)

        if not daily_returns:
            return None

        # 基础收益指标
        total_return = (closes[-1] - closes[0]) / closes[0] * 100 if closes[0] else 0
        days = len(history_data)
        annual_return = total_return * (252 / days) if days > 0 else 0
        daily_mean = sum(daily_returns) / len(daily_returns)
        daily_std = self._std(daily_returns)

        # 年化波动率
        volatility = daily_std * math.sqrt(252)

        # 最大回撤
        max_dd, max_dd_duration = self._calculate_max_drawdown(closes)

        # VaR
        sorted_returns = sorted(daily_returns)
        var_95_idx = int(len(sorted_returns) * 0.05)
        var_99_idx = int(len(sorted_returns) * 0.01)
        var_95 = sorted_returns[var_95_idx] if var_95_idx < len(sorted_returns) else 0
        var_99 = sorted_returns[var_99_idx] if var_99_idx < len(sorted_returns) else 0

        # 风险调整收益
        risk_free_daily = self.RISK_FREE_RATE / 252

        # 夏普比率
        if daily_std > 0:
            sharpe = (daily_mean - risk_free_daily * 100) / daily_std * math.sqrt(252)
        else:
            sharpe = 0

        # 索提诺比率（只考虑下行风险）
        downside_returns = [r for r in daily_returns if r < 0]
        if downside_returns:
            downside_std = self._std(downside_returns)
            sortino = (
                (daily_mean - risk_free_daily * 100) / downside_std * math.sqrt(252)
                if downside_std > 0
                else 0
            )
        else:
            sortino = 0

        # 卡玛比率
        calmar = annual_return / abs(max_dd) if max_dd != 0 else 0

        # 统计
        positive_days = sum(1 for r in daily_returns if r > 0)
        negative_days = sum(1 for r in daily_returns if r < 0)
        best_day = max(daily_returns)
        worst_day = min(daily_returns)

        return PerformanceMetrics(
            total_return=round(total_return, 2),
            annual_return=round(annual_return, 2),
            daily_return_mean=round(daily_mean, 4),
            daily_return_std=round(daily_std, 4),
            volatility=round(volatility, 2),
            max_drawdown=round(max_dd, 2),
            max_drawdown_duration=max_dd_duration,
            var_95=round(var_95, 2),
            var_99=round(var_99, 2),
            sharpe_ratio=round(sharpe, 2),
            sortino_ratio=round(sortino, 2),
            calmar_ratio=round(calmar, 2),
            positive_days=positive_days,
            negative_days=negative_days,
            best_day=round(best_day, 2),
            worst_day=round(worst_day, 2),
        )

    def _calculate_max_drawdown(self, prices: list[float]) -> tuple[float, int]:
        """计算最大回撤和持续天数"""
        if not prices:
            return 0, 0

        max_dd = 0
        max_dd_duration = 0
        peak = prices[0]
        peak_idx = 0
        current_duration = 0

        for i, price in enumerate(prices):
            if price > peak:
                peak = price
                peak_idx = i
                current_duration = 0
            else:
                dd = (peak - price) / peak * 100 if peak > 0 else 0
                current_duration = i - peak_idx
                if dd > max_dd:
                    max_dd = dd
                    max_dd_duration = current_duration

        return max_dd, max_dd_duration

    # ============================================================
    # 策略回测
    # ============================================================

    def backtest_ma_cross(
        self, history_data: list[dict], fast_period: int = 5, slow_period: int = 20
    ) -> BacktestResult | None:
        """
        均线交叉策略回测

        当快线上穿慢线时买入，下穿时卖出
        """
        if not history_data or len(history_data) < slow_period + 10:
            return None

        closes = [d["close"] for d in history_data]
        dates = [d.get("date", "") for d in history_data]

        signals = []
        position = 0  # 0: 空仓, 1: 持仓
        entry_price = 0
        trades = []

        for i in range(slow_period, len(closes)):
            fast_ma = sum(closes[i - fast_period + 1 : i + 1]) / fast_period
            slow_ma = sum(closes[i - slow_period + 1 : i + 1]) / slow_period
            prev_fast = sum(closes[i - fast_period : i]) / fast_period
            prev_slow = sum(closes[i - slow_period : i]) / slow_period

            # 金叉买入
            if prev_fast <= prev_slow and fast_ma > slow_ma and position == 0:
                position = 1
                entry_price = closes[i]
                signals.append(
                    {
                        "date": dates[i],
                        "type": "买入",
                        "price": closes[i],
                        "reason": f"MA{fast_period}上穿MA{slow_period}",
                    }
                )

            # 死叉卖出
            elif prev_fast >= prev_slow and fast_ma < slow_ma and position == 1:
                position = 0
                profit = (closes[i] - entry_price) / entry_price * 100
                trades.append(profit)
                signals.append(
                    {
                        "date": dates[i],
                        "type": "卖出",
                        "price": closes[i],
                        "profit": round(profit, 2),
                        "reason": f"MA{fast_period}下穿MA{slow_period}",
                    }
                )

        # 计算回测指标
        if not trades:
            return BacktestResult(
                strategy_name=f"MA{fast_period}/{slow_period}交叉",
                total_return=0,
                annual_return=0,
                max_drawdown=0,
                sharpe_ratio=0,
                win_rate=0,
                profit_loss_ratio=0,
                trade_count=0,
                signals=signals,
            )

        total_return = sum(trades)
        wins = [t for t in trades if t > 0]
        losses = [t for t in trades if t < 0]
        win_rate = len(wins) / len(trades) * 100 if trades else 0

        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = abs(sum(losses) / len(losses)) if losses else 1
        profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0

        days = len(history_data)
        annual_return = total_return * (252 / days) if days > 0 else 0

        # 简化的最大回撤和夏普
        max_dd = abs(min(trades)) if trades else 0
        sharpe = (
            (sum(trades) / len(trades)) / self._std(trades) * math.sqrt(len(trades))
            if trades and self._std(trades) > 0
            else 0
        )

        return BacktestResult(
            strategy_name=f"MA{fast_period}/{slow_period}交叉",
            total_return=round(total_return, 2),
            annual_return=round(annual_return, 2),
            max_drawdown=round(max_dd, 2),
            sharpe_ratio=round(sharpe, 2),
            win_rate=round(win_rate, 2),
            profit_loss_ratio=round(profit_loss_ratio, 2),
            trade_count=len(trades),
            signals=signals[-5:],  # 只保留最近5个信号
        )

    def backtest_rsi(
        self,
        history_data: list[dict],
        period: int = 14,
        oversold: float = 30,
        overbought: float = 70,
    ) -> BacktestResult | None:
        """
        RSI策略回测

        RSI低于超卖线买入，高于超买线卖出
        """
        if not history_data or len(history_data) < period + 10:
            return None

        closes = [d["close"] for d in history_data]
        dates = [d.get("date", "") for d in history_data]

        signals = []
        position = 0
        entry_price = 0
        trades = []

        for i in range(period + 1, len(closes)):
            rsi = self.calculate_rsi(closes[: i + 1], period)
            prev_rsi = self.calculate_rsi(closes[:i], period)

            if rsi is None or prev_rsi is None:
                continue

            # 超卖买入
            if prev_rsi <= oversold and rsi > oversold and position == 0:
                position = 1
                entry_price = closes[i]
                signals.append(
                    {
                        "date": dates[i],
                        "type": "买入",
                        "price": closes[i],
                        "rsi": round(rsi, 2),
                        "reason": "RSI从超卖区反弹",
                    }
                )

            # 超买卖出
            elif prev_rsi >= overbought and rsi < overbought and position == 1:
                position = 0
                profit = (closes[i] - entry_price) / entry_price * 100
                trades.append(profit)
                signals.append(
                    {
                        "date": dates[i],
                        "type": "卖出",
                        "price": closes[i],
                        "rsi": round(rsi, 2),
                        "profit": round(profit, 2),
                        "reason": "RSI进入超买区",
                    }
                )

        if not trades:
            return BacktestResult(
                strategy_name=f"RSI({period})",
                total_return=0,
                annual_return=0,
                max_drawdown=0,
                sharpe_ratio=0,
                win_rate=0,
                profit_loss_ratio=0,
                trade_count=0,
                signals=signals,
            )

        total_return = sum(trades)
        wins = [t for t in trades if t > 0]
        losses = [t for t in trades if t < 0]
        win_rate = len(wins) / len(trades) * 100 if trades else 0

        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = abs(sum(losses) / len(losses)) if losses else 1
        profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0

        days = len(history_data)
        annual_return = total_return * (252 / days) if days > 0 else 0
        max_dd = abs(min(trades)) if trades else 0
        sharpe = (
            (sum(trades) / len(trades)) / self._std(trades) * math.sqrt(len(trades))
            if trades and self._std(trades) > 0
            else 0
        )

        return BacktestResult(
            strategy_name=f"RSI({period})",
            total_return=round(total_return, 2),
            annual_return=round(annual_return, 2),
            max_drawdown=round(max_dd, 2),
            sharpe_ratio=round(sharpe, 2),
            win_rate=round(win_rate, 2),
            profit_loss_ratio=round(profit_loss_ratio, 2),
            trade_count=len(trades),
            signals=signals[-5:],
        )

    def run_all_backtests(self, history_data: list[dict]) -> list[BacktestResult]:
        """运行所有策略回测"""
        results = []

        # MA交叉策略
        ma_result = self.backtest_ma_cross(history_data, 5, 20)
        if ma_result:
            results.append(ma_result)

        ma_result2 = self.backtest_ma_cross(history_data, 10, 30)
        if ma_result2:
            results.append(ma_result2)

        # RSI策略
        rsi_result = self.backtest_rsi(history_data)
        if rsi_result:
            results.append(rsi_result)

        return results

    # ============================================================
    # 格式化输出
    # ============================================================

    def format_indicators_text(self, indicators: TechnicalIndicators) -> str:
        """格式化技术指标为文本"""
        lines = []

        lines.append("【趋势指标】")
        if indicators.ma5:
            lines.append(f"  MA5: {indicators.ma5:.4f}")
        if indicators.ma10:
            lines.append(f"  MA10: {indicators.ma10:.4f}")
        if indicators.ma20:
            lines.append(f"  MA20: {indicators.ma20:.4f}")

        lines.append("【MACD】")
        if indicators.macd is not None:
            lines.append(f"  DIF: {indicators.macd:.4f}")
        if indicators.macd_signal is not None:
            lines.append(f"  DEA: {indicators.macd_signal:.4f}")
        if indicators.macd_hist is not None:
            hist_status = "红柱" if indicators.macd_hist > 0 else "绿柱"
            lines.append(f"  MACD柱: {indicators.macd_hist:.4f} ({hist_status})")

        lines.append("【RSI】")
        if indicators.rsi_6:
            rsi6_status = (
                "超买"
                if indicators.rsi_6 > 70
                else "超卖"
                if indicators.rsi_6 < 30
                else "中性"
            )
            lines.append(f"  RSI(6): {indicators.rsi_6:.2f} ({rsi6_status})")
        if indicators.rsi_14:
            rsi14_status = (
                "超买"
                if indicators.rsi_14 > 70
                else "超卖"
                if indicators.rsi_14 < 30
                else "中性"
            )
            lines.append(f"  RSI(14): {indicators.rsi_14:.2f} ({rsi14_status})")

        lines.append("【布林带】")
        if indicators.boll_upper:
            lines.append(f"  上轨: {indicators.boll_upper:.4f}")
        if indicators.boll_middle:
            lines.append(f"  中轨: {indicators.boll_middle:.4f}")
        if indicators.boll_lower:
            lines.append(f"  下轨: {indicators.boll_lower:.4f}")

        lines.append("【KDJ】")
        if indicators.kdj_k is not None:
            lines.append(
                f"  K: {indicators.kdj_k:.2f}, D: {indicators.kdj_d:.2f}, J: {indicators.kdj_j:.2f}"
            )

        lines.append(f"【综合评分】{indicators.trend_score} 分")
        lines.append(f"【技术信号】{indicators.signal}")

        return "\n".join(lines)

    def format_performance_text(self, perf: PerformanceMetrics) -> str:
        """格式化绩效指标为文本"""
        lines = [
            "【收益指标】",
            f"  累计收益: {perf.total_return:+.2f}%",
            f"  年化收益: {perf.annual_return:+.2f}%",
            f"  日均收益: {perf.daily_return_mean:+.4f}%",
            "",
            "【风险指标】",
            f"  年化波动率: {perf.volatility:.2f}%",
            f"  最大回撤: {perf.max_drawdown:.2f}%",
            f"  回撤持续: {perf.max_drawdown_duration} 天",
            f"  95% VaR: {perf.var_95:.2f}%",
            "",
            "【风险调整收益】",
            f"  夏普比率: {perf.sharpe_ratio:.2f}",
            f"  索提诺比率: {perf.sortino_ratio:.2f}",
            f"  卡玛比率: {perf.calmar_ratio:.2f}",
            "",
            "【统计数据】",
            f"  上涨天数: {perf.positive_days} 天",
            f"  下跌天数: {perf.negative_days} 天",
            f"  最佳单日: {perf.best_day:+.2f}%",
            f"  最差单日: {perf.worst_day:+.2f}%",
        ]
        return "\n".join(lines)

    def format_backtest_text(self, results: list[BacktestResult]) -> str:
        """格式化回测结果为文本"""
        if not results:
            return "暂无回测数据"

        lines = []
        for result in results:
            lines.append(f"【{result.strategy_name}策略】")
            lines.append(f"  总收益: {result.total_return:+.2f}%")
            lines.append(f"  年化收益: {result.annual_return:+.2f}%")
            lines.append(f"  最大回撤: {result.max_drawdown:.2f}%")
            lines.append(f"  夏普比率: {result.sharpe_ratio:.2f}")
            lines.append(f"  胜率: {result.win_rate:.1f}%")
            lines.append(f"  盈亏比: {result.profit_loss_ratio:.2f}")
            lines.append(f"  交易次数: {result.trade_count}")

            if result.signals:
                lines.append("  最近信号:")
                for sig in result.signals[-3:]:
                    sig_type = sig.get("type", "")
                    sig_date = sig.get("date", "")
                    sig_price = sig.get("price", 0)
                    lines.append(f"    {sig_date} {sig_type} @ {sig_price:.4f}")

            lines.append("")

        return "\n".join(lines)
