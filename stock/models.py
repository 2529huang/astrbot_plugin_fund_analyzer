"""
A股股票数据模型
"""

from dataclasses import dataclass


@dataclass
class StockInfo:
    """A股股票基本信息"""

    code: str  # 股票代码
    name: str  # 股票名称
    latest_price: float  # 最新价
    change_amount: float  # 涨跌额
    change_rate: float  # 涨跌幅
    open_price: float  # 开盘价
    high_price: float  # 最高价
    low_price: float  # 最低价
    prev_close: float  # 昨收
    volume: float  # 成交量（手）
    amount: float  # 成交额
    amplitude: float  # 振幅
    turnover_rate: float  # 换手率
    pe_ratio: float  # 市盈率
    pb_ratio: float  # 市净率
    total_market_cap: float  # 总市值
    circulating_market_cap: float  # 流通市值

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
        if self.change_rate >= 9.9:
            return "🔥涨停"
        elif self.change_rate >= 5:
            return "🚀"
        elif self.change_rate >= 2:
            return "↗️"
        elif self.change_rate > 0:
            return "↑"
        elif self.change_rate <= -9.9:
            return "💀跌停"
        elif self.change_rate <= -5:
            return "💥"
        elif self.change_rate <= -2:
            return "↘️"
        elif self.change_rate < 0:
            return "↓"
        return "➡️"

    @staticmethod
    def format_market_cap(value: float) -> str:
        """格式化市值（转换为亿元或万元）"""
        if value >= 100000000:  # 亿元
            return f"{value / 100000000:.2f}亿"
        elif value >= 10000:  # 万元
            return f"{value / 10000:.2f}万"
        return f"{value:.2f}"
