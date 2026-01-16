"""
基金影响因素配置模块
定义不同类型基金的影响因素和搜索关键词
"""

import re
from typing import TypedDict


class FactorInfo(TypedDict):
    """影响因素信息类型"""

    type: str  # 基金类型
    underlying: str  # 追踪标的
    factors: dict[str, list[str]]  # 因素分类及关键词


# 基金类型关键词映射配置
FUND_TYPE_FACTORS: dict[str, FactorInfo] = {
    "白银": {
        "type": "贵金属",
        "underlying": "白银期货",
        "factors": {
            "商品价格": ["白银价格走势", "COMEX白银", "上海白银期货"],
            "宏观经济": ["美联储利率决议", "美元指数走势", "通胀数据"],
            "地缘政治": ["地缘政治风险", "避险情绪"],
            "供需关系": ["白银工业需求", "光伏白银需求", "白银产量"],
            "市场情绪": ["贵金属ETF持仓", "白银投资需求"],
        },
    },
    "黄金": {
        "type": "贵金属",
        "underlying": "黄金期货",
        "factors": {
            "商品价格": ["黄金价格走势", "COMEX黄金", "上海金"],
            "宏观经济": ["美联储利率", "美元走势", "实际利率"],
            "地缘政治": ["地缘风险", "避险需求"],
            "央行政策": ["央行购金", "黄金储备"],
            "市场情绪": ["黄金ETF持仓", "投资需求"],
        },
    },
    "原油|石油": {
        "type": "能源",
        "underlying": "原油期货",
        "factors": {
            "商品价格": ["原油价格", "WTI原油", "布伦特原油"],
            "供需关系": ["OPEC减产", "原油库存", "美国页岩油"],
            "宏观经济": ["全球经济增长", "制造业PMI"],
            "地缘政治": ["中东局势", "俄乌冲突"],
        },
    },
    "医药|医疗|生物": {
        "type": "医药行业",
        "underlying": "医药股票",
        "factors": {
            "政策因素": ["医药集采", "医保谈判", "药品审批"],
            "行业动态": ["创新药研发", "医药企业业绩"],
            "市场情绪": ["医药板块资金流向"],
        },
    },
    "科技|芯片|半导体": {
        "type": "科技行业",
        "underlying": "科技股票",
        "factors": {
            "产业政策": ["芯片政策", "科技自主"],
            "行业周期": ["半导体周期", "消费电子需求"],
            "国际贸易": ["芯片出口管制", "科技摩擦"],
        },
    },
    "消费|食品|白酒": {
        "type": "消费行业",
        "underlying": "消费股票",
        "factors": {
            "宏观数据": ["社会消费品零售", "CPI数据"],
            "政策因素": ["促消费政策", "消费补贴"],
            "企业业绩": ["消费龙头业绩", "白酒销售"],
        },
    },
    "新能源|光伏|锂电": {
        "type": "新能源行业",
        "underlying": "新能源股票",
        "factors": {
            "产业政策": ["新能源补贴", "碳中和政策"],
            "供需关系": ["锂价走势", "硅料价格", "装机量"],
            "技术进步": ["电池技术", "光伏效率"],
        },
    },
    "银行|金融": {
        "type": "金融行业",
        "underlying": "银行股票",
        "factors": {
            "货币政策": ["LPR利率", "存款准备金率"],
            "宏观经济": ["GDP增速", "信贷数据"],
            "监管政策": ["金融监管", "资本充足率"],
        },
    },
    "房地产|地产": {
        "type": "房地产行业",
        "underlying": "地产股票",
        "factors": {
            "政策因素": ["房地产政策", "限购限贷"],
            "市场数据": ["房价走势", "销售数据"],
            "资金链": ["房企融资", "债务风险"],
        },
    },
    "军工|国防": {
        "type": "军工行业",
        "underlying": "军工股票",
        "factors": {
            "国防预算": ["军费开支", "国防预算"],
            "地缘局势": ["周边安全形势", "国际关系"],
            "订单交付": ["军工订单", "装备交付"],
        },
    },
}

# 默认因素（通用）
DEFAULT_FACTORS: FactorInfo = {
    "type": "综合",
    "underlying": "多元资产",
    "factors": {
        "宏观经济": ["宏观经济数据", "GDP增速", "PMI数据"],
        "政策因素": ["货币政策", "财政政策"],
        "市场情绪": ["A股市场走势", "资金流向"],
    },
}


class FundInfluenceFactors:
    """基金影响因素分析器"""

    @staticmethod
    def get_factors(fund_name: str) -> FactorInfo:
        """
        根据基金名称获取可能的影响因素

        Args:
            fund_name: 基金名称

        Returns:
            影响因素信息
        """
        # 根据基金名称匹配类型
        for keyword_pattern, info in FUND_TYPE_FACTORS.items():
            if re.search(keyword_pattern, fund_name):
                return info

        return DEFAULT_FACTORS

    @staticmethod
    def get_search_keywords(fund_name: str) -> list[str]:
        """
        获取用于搜索新闻的关键词列表

        Args:
            fund_name: 基金名称

        Returns:
            搜索关键词列表
        """
        factors = FundInfluenceFactors.get_factors(fund_name)
        keywords = []

        # 添加追踪标的
        if factors["underlying"]:
            keywords.append(factors["underlying"])

        # 从各因素中提取关键词
        for category, kw_list in factors["factors"].items():
            keywords.extend(kw_list[:2])  # 每个类别取前2个

        return keywords[:10]  # 最多返回10个

    @staticmethod
    def format_factors_text(fund_name: str) -> str:
        """
        格式化影响因素为文本

        Args:
            fund_name: 基金名称

        Returns:
            格式化的文本
        """
        factors = FundInfluenceFactors.get_factors(fund_name)

        text = f"基金类型: {factors['type']}\n"
        text += f"追踪标的: {factors['underlying']}\n"
        text += "主要影响因素:\n"

        for category, keywords in factors["factors"].items():
            text += f"  【{category}】{', '.join(keywords)}\n"

        return text
