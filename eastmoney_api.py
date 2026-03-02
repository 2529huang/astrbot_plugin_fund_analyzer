"""
东方财富数据接口模块
直接使用 aiohttp 调用东方财富 API，绕过 akshare
解决 'Connection aborted' 和 'RemoteDisconnected' 错误
"""

import asyncio
import json
import re
from datetime import datetime, timedelta
from typing import Optional
import aiohttp
import random

from astrbot.api import logger

# 请求头，模拟浏览器访问
HEADERS_LIST = [
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Referer": "https://quote.eastmoney.com/",
    },
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,en-US;q=0.5,en;q=0.3",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Referer": "https://quote.eastmoney.com/",
    },
    {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh-Hans;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Referer": "https://quote.eastmoney.com/",
    },
]

# 超时设置
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30, connect=15, sock_read=20)


class EastMoneyAPI:
    """东方财富数据 API 封装"""

    # API 地址
    # 单只基金/股票实时行情 (场内)
    QUOTE_API = "http://push2.eastmoney.com/api/qt/stock/get"
    # LOF/ETF 基金列表 (备用，可能不稳定)
    LOF_LIST_API = "http://push2.eastmoney.com/api/qt/clist/get"
    # K线历史数据 (场内)
    KLINE_API = "http://push2his.eastmoney.com/api/qt/stock/kline/get"
    # 天天基金搜索 API (更稳定)
    FUND_SEARCH_API = "https://fundsuggest.eastmoney.com/FundSearch/api/FundSearchAPI.ashx"
    # 场外基金实时估值 API
    OTC_FUND_API = "https://fundgz.1234567.com.cn/js/{}.js"
    # 场外基金历史净值 API
    OTC_HISTORY_API = "https://api.fund.eastmoney.com/f10/lsjz"
    # 备用数据源 - 腾讯财经（当东方财富push2系列API被封锁时自动切换）
    TENCENT_QUOTE_API = "https://qt.gtimg.cn/q="
    TENCENT_KLINE_API = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    # 备用数据源 - 新浪财经
    SINA_QUOTE_API = "https://hq.sinajs.cn/list="
    # 资金流向 API (场内)
    FUND_FLOW_API = "http://push2.eastmoney.com/api/qt/stock/fflow/daykline/get"
    # 资金流向备用源 - 东方财富 datacenter
    FUND_FLOW_DETAIL_API = "https://datacenter-web.eastmoney.com/api/data/v1/get"

    def __init__(self):
        # 缓存
        self._lof_list_cache: Optional[list] = None
        self._lof_cache_time: Optional[datetime] = None
        self._cache_ttl = 1800  # 30分钟缓存
        # 持久化 session（复用连接，减少 Server disconnected）
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建持久化 HTTP session（复用TCP连接）"""
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                ssl=False,
                limit=10,  # 最大连接数
                limit_per_host=5,
                ttl_dns_cache=300,  # DNS缓存5分钟
                keepalive_timeout=30,  # keep-alive 30秒
                enable_cleanup_closed=True,
            )
            self._session = aiohttp.ClientSession(
                timeout=REQUEST_TIMEOUT,
                connector=connector,
                trust_env=False,  # 忽略系统代理
            )
        return self._session

    async def close(self):
        """关闭持久化 session"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _request(
        self,
        url: str,
        params: dict,
        max_retries: int = 3,
    ) -> Optional[dict]:
        """
        发送 HTTP 请求，带重试机制
        
        优化：使用持久化session复用TCP连接，避免频繁建立/断开导致Server disconnected
        
        Args:
            url: API 地址
            params: 请求参数
            max_retries: 最大重试次数
            
        Returns:
            JSON 响应或 None
        """
        for attempt in range(max_retries):
            try:
                # 随机选择请求头
                headers = random.choice(HEADERS_LIST)
                
                session = await self._get_session()
                
                async with session.get(url, params=params, headers=headers) as response:
                    if response.status == 200:
                        # 有些 API 返回 text/plain，需要手动解析 JSON
                        text = await response.text()
                        try:
                            return json.loads(text)
                        except json.JSONDecodeError as e:
                            logger.warning(f"JSON 解析失败: {e}")
                            return None
                    else:
                        logger.warning(f"HTTP {response.status}: {url}")
            except aiohttp.ServerDisconnectedError:
                # 服务器断开连接，关闭旧session重建
                logger.warning(f"服务器断开连接 (第{attempt + 1}次): {url}，正在重建连接...")
                await self.close()
            except asyncio.TimeoutError:
                logger.warning(f"请求超时 (第{attempt + 1}次): {url}")
            except aiohttp.ClientError as e:
                logger.warning(f"请求失败 (第{attempt + 1}次): {e}")
                # 连接相关错误，重建session
                if "disconnect" in str(e).lower() or "connection" in str(e).lower():
                    await self.close()
            except Exception as e:
                logger.error(f"请求异常: {e}")
            
            # 重试前短暂等待（首次快速重试，后续逐渐增加）
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 1.5 + random.uniform(0, 1)
                await asyncio.sleep(wait_time)
        
        return None

    def _get_market_code(self, fund_code: str) -> str:
        """
        根据基金代码判断市场代码
        
        Args:
            fund_code: 基金代码
            
        Returns:
            市场代码 (0=深交所, 1=上交所)
        """
        # 上交所: 5开头的ETF/LOF, 6开头的股票
        # 深交所: 1开头的LOF, 0/3开头的股票
        if fund_code.startswith(("5", "6")):
            return "1"
        return "0"

    def _is_otc_fund(self, fund_code: str) -> bool:
        """
        判断是否为场外基金
        
        场外基金代码通常是0开头的6位数字，但不包括以下场内基金:
        - 000xxx 部分是场内基金
        - 00xxxx 部分是场内基金
        
        场内基金代码特征:
        - 1xxxxx: 深交所LOF/ETF
        - 5xxxxx: 上交所ETF
        - 6xxxxx: 上交所股票
        
        场外基金代码特征:
        - 0xxxxx: 大部分场外基金
        - 2xxxxx: 部分场外基金
        - 3xxxxx: 创业板股票 (不处理)
        """
        if not fund_code or len(fund_code) != 6:
            return False
        
        # 1开头或5开头通常是场内ETF/LOF
        if fund_code.startswith(("1", "5")):
            return False
        
        # 0开头的大部分是场外基金
        if fund_code.startswith("0"):
            return True
        
        # 2开头的是场外基金
        if fund_code.startswith("2"):
            return True
        
        return False

    async def get_fund_realtime(self, fund_code: str) -> Optional[dict]:
        """
        获取单只基金实时行情（自动判断场内/场外）
        
        Args:
            fund_code: 基金代码
            
        Returns:
            行情数据字典或 None
        """
        fund_code = str(fund_code).strip()
        
        # 判断是场内还是场外基金
        if self._is_otc_fund(fund_code):
            return await self._get_otc_fund_realtime(fund_code)
        else:
            return await self._get_exchange_fund_realtime(fund_code)

    async def _get_otc_fund_realtime(self, fund_code: str) -> Optional[dict]:
        """
        获取场外基金实时估值
        
        Args:
            fund_code: 基金代码
            
        Returns:
            估值数据字典或 None
        """
        url = self.OTC_FUND_API.format(fund_code)
        
        for attempt in range(3):
            try:
                headers = random.choice(HEADERS_LIST)
                session = await self._get_session()
                
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        text = await response.text()
                        # 解析 JSONP: jsonpgz({...})
                        match = re.search(r'jsonpgz\((.*)\)', text)
                        if match:
                            data = json.loads(match.group(1))
                            
                            def safe_float(val):
                                if val is None or val == "":
                                    return 0.0
                                try:
                                    return float(val)
                                except (ValueError, TypeError):
                                    return 0.0
                            
                            return {
                                "code": data.get("fundcode", fund_code),
                                "name": data.get("name", ""),
                                "latest_price": safe_float(data.get("gsz")),  # 估算净值
                                "prev_close": safe_float(data.get("dwjz")),  # 昨日净值
                                "change_rate": safe_float(data.get("gszzl")),  # 估算涨跌幅
                                "change_amount": 0.0,
                                "update_time": data.get("gztime", ""),
                                "is_otc": True,  # 标记为场外基金
                            }
                    elif response.status == 404:
                        # 基金不存在
                        return None
            except aiohttp.ServerDisconnectedError:
                logger.warning(f"场外基金估值服务器断开 (第{attempt + 1}次): {fund_code}")
                await self.close()
            except Exception as e:
                logger.debug(f"获取场外基金估值失败 (第{attempt + 1}次): {e}")
            
            if attempt < 2:
                await asyncio.sleep((attempt + 1) * 1.5)
        
        return None

    async def _get_exchange_fund_realtime(self, fund_code: str) -> Optional[dict]:
        """
        获取场内基金（ETF/LOF）实时行情
        依次尝试：东方财富 → 腾讯财经 → 新浪财经 → 天天基金估值
        """
        market = self._get_market_code(fund_code)
        
        # === 1. 东方财富主源 ===
        params = {
            "secid": f"{market}.{fund_code}",
            "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f60,f152,f168,f169,f170",
        }
        
        data = await self._request(self.QUOTE_API, params)
        if data and data.get("rc") == 0:
            result = data.get("data", {})
            if result:
                # f152 表示价格的小数位数：股票=2, LOF/ETF基金=3
                # 用 10^f152 作为价格字段的除数，确保不同证券类型都正确
                decimal_places = result.get("f152", 2)
                try:
                    decimal_places = int(decimal_places)
                except (ValueError, TypeError):
                    decimal_places = 2
                price_divisor = 10 ** decimal_places
                
                def safe_float(val, divisor=1):
                    if val is None or val == "-":
                        return 0.0
                    try:
                        return float(val) / divisor
                    except (ValueError, TypeError):
                        return 0.0
                
                return {
                    "code": str(result.get("f57", fund_code)),
                    "name": str(result.get("f58", "")),
                    "latest_price": safe_float(result.get("f43"), price_divisor),
                    "change_amount": safe_float(result.get("f169"), price_divisor),
                    "change_rate": safe_float(result.get("f170"), 100),
                    "open_price": safe_float(result.get("f46"), price_divisor),
                    "high_price": safe_float(result.get("f44"), price_divisor),
                    "low_price": safe_float(result.get("f45"), price_divisor),
                    "prev_close": safe_float(result.get("f60"), price_divisor),
                    "volume": safe_float(result.get("f47")),
                    "amount": safe_float(result.get("f48")),
                    "turnover_rate": safe_float(result.get("f168"), 100),
                }
        
        # === 2. 腾讯财经备用源 ===
        logger.debug(f"东方财富获取失败，尝试腾讯财经: {fund_code}")
        result = await self._get_exchange_realtime_tencent(fund_code)
        if result:
            return result
        
        # === 3. 新浪财经备用源 ===
        logger.debug(f"腾讯财经获取失败，尝试新浪财经: {fund_code}")
        result = await self._get_exchange_realtime_sina(fund_code)
        if result:
            return result
        
        # === 4. 天天基金 API（部分ETF也有天天基金页面） ===
        logger.debug(f"所有场内数据源失败，尝试天天基金: {fund_code}")
        return await self._get_otc_fund_realtime(fund_code)

    async def _get_exchange_realtime_tencent(self, fund_code: str) -> Optional[dict]:
        """腾讯财经备用源 - 获取场内基金实时行情"""
        market_prefix = "sh" if fund_code.startswith(("5", "6")) else "sz"
        url = f"{self.TENCENT_QUOTE_API}{market_prefix}{fund_code}"
        
        try:
            session = await self._get_session()
            headers = {"User-Agent": random.choice(HEADERS_LIST)["User-Agent"]}
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    return None
                text = await response.text(encoding="gbk")
                match = re.search(r'"(.+)"', text)
                if not match:
                    return None
                parts = match.group(1).split("~")
                if len(parts) < 38:
                    return None
                
                def sf(val):
                    try:
                        return float(val) if val and val.strip() else 0.0
                    except (ValueError, TypeError):
                        return 0.0
                
                return {
                    "code": fund_code,
                    "name": parts[1],
                    "latest_price": sf(parts[3]),
                    "prev_close": sf(parts[4]),
                    "open_price": sf(parts[5]),
                    "volume": sf(parts[6]) * 100,  # 手→股
                    "change_amount": sf(parts[31]),
                    "change_rate": sf(parts[32]),
                    "high_price": sf(parts[33]),
                    "low_price": sf(parts[34]),
                    "amount": sf(parts[37]) * 10000,  # 万→元
                    "turnover_rate": sf(parts[38]) if len(parts) > 38 else 0.0,
                }
        except Exception as e:
            logger.debug(f"腾讯财经获取失败: {fund_code} - {e}")
        return None

    async def _get_exchange_realtime_sina(self, fund_code: str) -> Optional[dict]:
        """新浪财经备用源 - 获取场内基金实时行情"""
        market_prefix = "sh" if fund_code.startswith(("5", "6")) else "sz"
        url = f"{self.SINA_QUOTE_API}{market_prefix}{fund_code}"
        
        try:
            session = await self._get_session()
            headers = {
                "User-Agent": random.choice(HEADERS_LIST)["User-Agent"],
                "Referer": "https://finance.sina.com.cn/",
            }
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    return None
                text = await response.text(encoding="gbk")
                match = re.search(r'"(.+)"', text)
                if not match:
                    return None
                parts = match.group(1).split(",")
                if len(parts) < 10:
                    return None
                
                def sf(val):
                    try:
                        return float(val) if val and val.strip() else 0.0
                    except (ValueError, TypeError):
                        return 0.0
                
                current = sf(parts[3])
                prev_close = sf(parts[2])
                change_amount = round(current - prev_close, 4) if current and prev_close else 0.0
                change_rate = round(change_amount / prev_close * 100, 2) if prev_close else 0.0
                
                return {
                    "code": fund_code,
                    "name": parts[0],
                    "latest_price": current,
                    "prev_close": prev_close,
                    "open_price": sf(parts[1]),
                    "high_price": sf(parts[4]),
                    "low_price": sf(parts[5]),
                    "volume": sf(parts[8]),
                    "amount": sf(parts[9]),
                    "change_amount": change_amount,
                    "change_rate": change_rate,
                    "turnover_rate": 0.0,
                }
        except Exception as e:
            logger.debug(f"新浪财经获取失败: {fund_code} - {e}")
        return None

    async def get_fund_history(
        self,
        fund_code: str,
        days: int = 30,
        adjust: str = "qfq",
    ) -> Optional[list]:
        """
        获取基金历史数据（自动判断场内/场外）
        
        Args:
            fund_code: 基金代码
            days: 获取天数
            adjust: 复权类型 (qfq=前复权, hfq=后复权, 空=不复权)
            
        Returns:
            历史数据列表或 None
        """
        fund_code = str(fund_code).strip()
        
        # 判断是场内还是场外基金
        if self._is_otc_fund(fund_code):
            return await self._get_otc_fund_history(fund_code, days)
        else:
            return await self._get_exchange_fund_history(fund_code, days, adjust)

    async def _get_otc_fund_history(
        self,
        fund_code: str,
        days: int = 30,
    ) -> Optional[list]:
        """
        获取场外基金历史净值
        
        Args:
            fund_code: 基金代码
            days: 获取天数
            
        Returns:
            历史数据列表或 None
        """
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://fund.eastmoney.com/",
        }
        
        params = {
            "fundCode": fund_code,
            "pageIndex": "1",
            "pageSize": str(days),
        }
        
        for attempt in range(3):
            try:
                session = await self._get_session()
                
                async with session.get(
                    self.OTC_HISTORY_API, params=params, headers=headers
                ) as response:
                    if response.status == 200:
                        text = await response.text()
                        data = json.loads(text)
                        
                        if data.get("ErrCode") != 0:
                            logger.warning(f"获取场外基金历史失败: {data.get('ErrMsg')}")
                            return None
                        
                        lsjz_list = data.get("Data", {}).get("LSJZList", [])
                        if not lsjz_list:
                            return None
                        
                        history = []
                        prev_close = None
                        
                        # 倒序处理（API返回的是从新到旧）
                        for item in reversed(lsjz_list):
                            def safe_float(val):
                                if val is None or val == "" or val == "--":
                                    return 0.0
                                try:
                                    return float(val)
                                except (ValueError, TypeError):
                                    return 0.0
                            
                            close = safe_float(item.get("DWJZ"))
                            
                            # 计算涨跌幅
                            change_rate = 0.0
                            jzzzl = item.get("JZZZL")
                            if jzzzl and jzzzl != "--":
                                change_rate = safe_float(jzzzl)
                            elif prev_close and prev_close > 0:
                                change_rate = (close - prev_close) / prev_close * 100
                            
                            history.append({
                                "date": item.get("FSRQ", ""),
                                "open": close,  # 场外基金没有开盘价
                                "close": close,
                                "high": close,
                                "low": close,
                                "volume": 0.0,
                                "amount": 0.0,
                                "change_rate": change_rate,
                            })
                            
                            prev_close = close
                        
                        return history
            except aiohttp.ServerDisconnectedError:
                logger.warning(f"场外基金历史服务器断开 (第{attempt + 1}次): {fund_code}")
                await self.close()
            except Exception as e:
                logger.debug(f"获取场外基金历史失败 (第{attempt + 1}次): {e}")
            
            if attempt < 2:
                await asyncio.sleep((attempt + 1) * 2)
        
        return None

    async def _get_exchange_fund_history(
        self,
        fund_code: str,
        days: int = 30,
        adjust: str = "qfq",
    ) -> Optional[list]:
        """
        获取场内基金（ETF/LOF）历史K线数据
        
        Args:
            fund_code: 基金代码
            days: 获取天数
            adjust: 复权类型
            
        Returns:
            历史数据列表或 None
        """
        market = self._get_market_code(fund_code)
        
        # 复权类型转换
        fq_map = {"qfq": "1", "hfq": "2", "": "0"}
        fq = fq_map.get(adjust, "1")
        
        # 计算日期范围（多获取一些以覆盖节假日）
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days * 3 + 60)
        
        params = {
            "secid": f"{market}.{fund_code}",
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": "101",  # 日K线
            "fqt": fq,
            "beg": start_date.strftime("%Y%m%d"),
            "end": end_date.strftime("%Y%m%d"),
            "lmt": str(days * 3),  # 限制数量
        }
        
        data = await self._request(self.KLINE_API, params)
        if data and data.get("rc") == 0:
            result = data.get("data", {})
            klines = result.get("klines", [])
            
            if klines:
                history = []
                for line in klines:
                    # 格式: 日期,开盘,收盘,最高,最低,成交量,成交额,振幅,涨跌幅,涨跌额,换手率
                    parts = line.split(",")
                    if len(parts) >= 11:
                        try:
                            history.append({
                                "date": parts[0],
                                "open": float(parts[1]),
                                "close": float(parts[2]),
                                "high": float(parts[3]),
                                "low": float(parts[4]),
                                "volume": float(parts[5]),
                                "amount": float(parts[6]),
                                "change_rate": float(parts[8]) if parts[8] else 0.0,
                            })
                        except (ValueError, IndexError) as e:
                            logger.debug(f"解析K线数据失败: {line}, 错误: {e}")
                            continue
                
                if history:
                    return history[-days:] if len(history) > days else history
        
        # === 备用源: 腾讯财经K线 ===
        logger.debug(f"东方财富K线获取失败，尝试腾讯财经: {fund_code}")
        result = await self._get_exchange_history_tencent(fund_code, days)
        if result:
            return result
        
        # === 备用源: 场外基金历史净值 API ===
        logger.debug(f"腾讯K线获取失败，尝试场外基金历史API: {fund_code}")
        return await self._get_otc_fund_history(fund_code, days)

    async def _get_exchange_history_tencent(
        self,
        fund_code: str,
        days: int = 30,
    ) -> Optional[list]:
        """腾讯财经备用源 - 获取场内基金历史K线"""
        market_prefix = "sh" if fund_code.startswith(("5", "6")) else "sz"
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days * 2 + 30)
        
        params = {
            "param": f"{market_prefix}{fund_code},day,{start_date.strftime('%Y-%m-%d')},,{days * 2},qfq",
        }
        
        try:
            session = await self._get_session()
            headers = {"User-Agent": random.choice(HEADERS_LIST)["User-Agent"]}
            
            async with session.get(
                self.TENCENT_KLINE_API, params=params, headers=headers
            ) as response:
                if response.status != 200:
                    return None
                text = await response.text()
                data = json.loads(text)
                
                if data.get("code") != 0:
                    return None
                
                stock_data = data.get("data", {}).get(f"{market_prefix}{fund_code}", {})
                
                # 优先取前复权数据
                klines = stock_data.get("qfqday") or stock_data.get("day", [])
                if not klines:
                    return None
                
                history = []
                prev_close = None
                for line in klines:
                    if len(line) < 6:
                        continue
                    try:
                        close = float(line[2])
                        change_rate = 0.0
                        if prev_close and prev_close > 0:
                            change_rate = round(
                                (close - prev_close) / prev_close * 100, 2
                            )
                        
                        history.append({
                            "date": line[0],
                            "open": float(line[1]),
                            "close": close,
                            "high": float(line[3]),
                            "low": float(line[4]),
                            "volume": float(line[5]),
                            "amount": 0.0,
                            "change_rate": change_rate,
                        })
                        prev_close = close
                    except (ValueError, IndexError):
                        continue
                
                return history[-days:] if len(history) > days else history
        except Exception as e:
            logger.debug(f"腾讯K线获取失败: {fund_code} - {e}")
        return None

    async def get_lof_list(self, use_cache: bool = True) -> Optional[list]:
        """
        获取 LOF 基金列表
        
        Args:
            use_cache: 是否使用缓存
            
        Returns:
            基金列表或 None
        """
        now = datetime.now()
        
        # 检查缓存
        if use_cache and self._lof_list_cache is not None:
            if self._lof_cache_time and (now - self._lof_cache_time).total_seconds() < self._cache_ttl:
                logger.debug("使用缓存的LOF基金列表")
                return self._lof_list_cache
        
        # LOF 基金分类: MK0404(上交所LOF), MK0405(深交所LOF), MK0406, MK0407
        params = {
            "pn": "1",
            "pz": "500",  # 每页500条
            "po": "1",
            "np": "1",
            "fltt": "2",
            "invt": "2",
            "fid": "f3",
            "fs": "b:MK0404,b:MK0405,b:MK0406,b:MK0407",
            "fields": "f2,f3,f4,f5,f6,f7,f12,f14,f15,f16,f17,f18",
        }
        
        data = await self._request(self.LOF_LIST_API, params)
        if not data or data.get("rc") != 0:
            logger.error("获取LOF基金列表失败")
            # 如果有旧缓存，返回旧缓存
            if self._lof_list_cache:
                logger.warning("使用过期的缓存数据")
                return self._lof_list_cache
            return None
        
        result = data.get("data", {})
        diff = result.get("diff", [])
        
        if not diff:
            logger.warning("LOF基金列表为空")
            return None
        
        fund_list = []
        for item in diff:
            def safe_float(val, divisor=1):
                if val is None or val == "-":
                    return 0.0
                try:
                    return float(val) / divisor
                except (ValueError, TypeError):
                    return 0.0
            
            fund_list.append({
                "code": str(item.get("f12", "")),
                "name": str(item.get("f14", "")),
                "latest_price": safe_float(item.get("f2")),
                "change_rate": safe_float(item.get("f3")),
                "change_amount": safe_float(item.get("f4")),
                "volume": safe_float(item.get("f5")),
                "amount": safe_float(item.get("f6")),
                "open_price": safe_float(item.get("f17")),
                "high_price": safe_float(item.get("f15")),
                "low_price": safe_float(item.get("f16")),
                "prev_close": safe_float(item.get("f18")),
            })
        
        # 更新缓存
        self._lof_list_cache = fund_list
        self._lof_cache_time = now
        logger.info(f"LOF基金列表获取成功，共 {len(fund_list)} 只基金")
        
        return fund_list

    async def search_fund(self, keyword: str, fetch_realtime: bool = True) -> list:
        """
        搜索基金（使用天天基金搜索 API，更稳定）
        
        Args:
            keyword: 搜索关键词（代码或名称）
            fetch_realtime: 是否获取实时行情（涨跌幅等）
            
        Returns:
            匹配的基金列表
        """
        if not keyword or not keyword.strip():
            return []
        
        keyword = keyword.strip()
        
        params = {
            "m": "1",
            "key": keyword,
        }
        
        data = await self._request(self.FUND_SEARCH_API, params)
        if not data or data.get("ErrCode") != 0:
            logger.warning(f"搜索基金失败: {keyword}")
            return []
        
        datas = data.get("Datas", [])
        
        # 如果搜索API返回空结果（服务器IP可能被限制），尝试直接获取实时数据
        if not datas and keyword.isdigit() and len(keyword) == 6:
            logger.debug(f"搜索API返回空结果，尝试直接获取实时数据: {keyword}")
            realtime = await self.get_fund_realtime(keyword)
            if realtime and realtime.get("name"):
                return [{
                    "code": keyword,
                    "name": realtime.get("name", ""),
                    "fund_type": "",
                    "latest_price": realtime.get("latest_price", 0.0),
                    "change_rate": realtime.get("change_rate", 0.0),
                    "change_amount": realtime.get("change_amount", 0.0),
                }]
            return []
        
        if not datas:
            return []
        
        results = []
        for item in datas:
            # 只处理基金类型 (CATEGORY=700)
            category = item.get("CATEGORY")
            if category != 700:
                continue
            
            code = item.get("CODE", "")
            name = item.get("NAME", "")
            
            # 获取更详细的基金信息
            fund_info = item.get("FundBaseInfo", {})
            
            result = {
                "code": code,
                "name": name,
                "fund_type": fund_info.get("FTYPE", ""),
                "latest_price": 0.0,
                "change_rate": 0.0,
                "change_amount": 0.0,
            }
            
            # 如果有净值信息
            if fund_info:
                try:
                    dwjz = fund_info.get("DWJZ")
                    if dwjz is not None:
                        result["latest_price"] = float(dwjz)
                except (ValueError, TypeError):
                    pass
            
            results.append(result)
            
            if len(results) >= 10:  # 最多返回10条
                break
        
        # 获取实时行情数据（涨跌幅等）
        if fetch_realtime and results:
            await self._enrich_with_realtime(results)
        
        return results
    
    async def _enrich_with_realtime(self, fund_list: list) -> None:
        """
        为基金列表补充实时行情数据
        
        Args:
            fund_list: 基金列表（会被原地修改）
        """
        # 并发获取所有基金的实时行情
        tasks = []
        for fund in fund_list:
            code = fund.get("code", "")
            if code:
                tasks.append(self.get_fund_realtime(code))
        
        if not tasks:
            return
        
        realtime_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, realtime in enumerate(realtime_results):
            if isinstance(realtime, BaseException) or realtime is None:
                continue
            assert isinstance(realtime, dict)
            
            fund = fund_list[i]
            # 更新实时数据
            if realtime.get("latest_price"):
                fund["latest_price"] = realtime["latest_price"]
            if realtime.get("change_rate") is not None:
                fund["change_rate"] = realtime["change_rate"]
            if realtime.get("change_amount") is not None:
                fund["change_amount"] = realtime["change_amount"]
    
    async def get_fund_flow(
        self, fund_code: str, days: int = 10
    ) -> Optional[list[dict]]:
        """
        获取基金/股票资金流向数据（主力净流入等）
        
        依次尝试：东方财富push2 → 东方财富datacenter
        仅场内基金有资金流向数据，场外基金返回 None
        
        Args:
            fund_code: 基金代码（场内ETF/LOF/股票）
            days: 获取天数
            
        Returns:
            资金流向数据列表或 None，每条包含：
            date, main_net_inflow（主力净流入），
            super_large_inflow（超大单净流入），large_inflow（大单净流入），
            medium_inflow（中单净流入），small_inflow（小单净流入）
        """
        fund_code = str(fund_code).strip()
        
        # 场外基金无资金流向数据
        if self._is_otc_fund(fund_code):
            return None
        
        # === 1. 东方财富 push2 主源 ===
        result = await self._get_fund_flow_eastmoney(fund_code, days)
        if result:
            return result
        
        # === 2. 东方财富 datacenter 备用源 ===
        logger.debug(f"push2资金流向获取失败，尝试datacenter: {fund_code}")
        result = await self._get_fund_flow_datacenter(fund_code, days)
        if result:
            return result
        
        logger.warning(f"所有资金流向数据源均失败: {fund_code}")
        return None
    
    async def _get_fund_flow_eastmoney(
        self, fund_code: str, days: int = 10
    ) -> Optional[list[dict]]:
        """东方财富 push2 资金流向 API"""
        market = self._get_market_code(fund_code)
        
        params = {
            "lmt": str(days),
            "klt": "101",  # 日K
            "secid": f"{market}.{fund_code}",
            "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
            "ut": "b2884a393a59ad64002292a3e90d46a5",
        }
        
        data = await self._request(self.FUND_FLOW_API, params)
        if not data or data.get("rc") != 0:
            return None
        
        klines = data.get("data", {}).get("klines", [])
        if not klines:
            return None
        
        flow_list = []
        for line in klines:
            parts = line.split(",")
            if len(parts) < 7:
                continue
            try:
                flow_list.append({
                    "date": parts[0],
                    "main_net_inflow": float(parts[1]),      # 主力净流入
                    "small_inflow": float(parts[2]),          # 小单净流入
                    "medium_inflow": float(parts[3]),         # 中单净流入
                    "large_inflow": float(parts[4]),          # 大单净流入
                    "super_large_inflow": float(parts[5]),    # 超大单净流入
                })
            except (ValueError, IndexError):
                continue
        
        return flow_list if flow_list else None
    
    async def _get_fund_flow_datacenter(
        self, fund_code: str, days: int = 10
    ) -> Optional[list[dict]]:
        """东方财富 datacenter 资金流向备用 API"""
        market = self._get_market_code(fund_code)
        market_name = "上海" if market == "1" else "深圳"
        
        params = {
            "reportName": "RPT_STOCK_FFLOW_DAYKLINE",
            "columns": "ALL",
            "filter": f'(SECURITY_CODE="{fund_code}")(MARKET="{market_name}")',
            "pageNumber": "1",
            "pageSize": str(days),
            "sortTypes": "-1",
            "sortColumns": "TRADE_DATE",
            "source": "WEB",
            "client": "WEB",
        }
        
        try:
            session = await self._get_session()
            headers = {
                "User-Agent": random.choice(HEADERS_LIST)["User-Agent"],
                "Referer": "https://data.eastmoney.com/",
            }
            
            async with session.get(
                self.FUND_FLOW_DETAIL_API, params=params, headers=headers
            ) as response:
                if response.status != 200:
                    return None
                text = await response.text()
                data = json.loads(text)
                
                if not data.get("success"):
                    return None
                
                items = data.get("result", {}).get("data", [])
                if not items:
                    return None
                
                flow_list = []
                for item in reversed(items):  # 倒序，从旧到新
                    def sf(val):
                        if val is None:
                            return 0.0
                        try:
                            return float(val)
                        except (ValueError, TypeError):
                            return 0.0
                    
                    trade_date = item.get("TRADE_DATE", "")
                    if trade_date and len(trade_date) >= 10:
                        trade_date = trade_date[:10]  # "2025-01-02T00:00:00" → "2025-01-02"
                    
                    flow_list.append({
                        "date": trade_date,
                        "main_net_inflow": sf(item.get("MAIN_NET_INFLOW")),
                        "small_inflow": sf(item.get("SMALL_NET_INFLOW")),
                        "medium_inflow": sf(item.get("MIDDLE_NET_INFLOW")),
                        "large_inflow": sf(item.get("LARGE_NET_INFLOW")),
                        "super_large_inflow": sf(item.get("SUPER_LARGE_NET_INFLOW")),
                    })
                
                return flow_list if flow_list else None
        except Exception as e:
            logger.debug(f"datacenter资金流向获取失败: {fund_code} - {e}")
        return None
    
    def format_fund_flow_text(self, flow_data: Optional[list[dict]]) -> str:
        """
        格式化资金流向数据为文本
        
        Args:
            flow_data: get_fund_flow 返回的数据
            
        Returns:
            格式化文本
        """
        if not flow_data:
            return "暂无资金流向数据（场外基金或数据源不可用）"
        
        lines = []
        total_main = 0.0
        total_super = 0.0
        total_large = 0.0
        positive_days = 0
        
        lines.append("| 日期 | 主力净流入 | 超大单 | 大单 | 中单 | 小单 |")
        lines.append("|------|-----------|--------|------|------|------|")
        
        for item in flow_data[-10:]:  # 最多显示10天
            date = item["date"]
            main = item["main_net_inflow"]
            super_l = item["super_large_inflow"]
            large = item["large_inflow"]
            medium = item["medium_inflow"]
            small = item["small_inflow"]
            
            total_main += main
            total_super += super_l
            total_large += large
            if main > 0:
                positive_days += 1
            
            def fmt(val):
                if abs(val) >= 1e8:
                    return f"{val/1e8:+.2f}亿"
                elif abs(val) >= 1e4:
                    return f"{val/1e4:+.2f}万"
                else:
                    return f"{val:+.0f}"
            
            lines.append(
                f"| {date} | {fmt(main)} | {fmt(super_l)} | {fmt(large)} | {fmt(medium)} | {fmt(small)} |"
            )
        
        # 汇总统计
        n = len(flow_data[-10:])
        lines.append("")
        lines.append(f"**近{n}日汇总**：")
        
        def fmt_summary(val):
            if abs(val) >= 1e8:
                return f"{val/1e8:+.2f}亿"
            elif abs(val) >= 1e4:
                return f"{val/1e4:+.2f}万"
            else:
                return f"{val:+.0f}"
        
        lines.append(f"- 主力累计净流入: {fmt_summary(total_main)}")
        lines.append(f"- 超大单累计净流入: {fmt_summary(total_super)}")
        lines.append(f"- 大单累计净流入: {fmt_summary(total_large)}")
        lines.append(f"- 主力净流入天数: {positive_days}/{n}天")
        
        # 趋势判断
        if n >= 3:
            recent_3 = flow_data[-3:]
            recent_trend = sum(d["main_net_inflow"] for d in recent_3)
            if recent_trend > 0:
                lines.append(f"- 近3日趋势: 主力资金净流入 {fmt_summary(recent_trend)} 🔺")
            else:
                lines.append(f"- 近3日趋势: 主力资金净流出 {fmt_summary(recent_trend)} 🔻")
        
        return "\n".join(lines)

    async def validate_fund_code(self, fund_code: str) -> bool:
        """
        验证基金代码是否有效
        
        Args:
            fund_code: 基金代码
            
        Returns:
            是否有效
        """
        fund_code = str(fund_code).strip()
        
        # 使用搜索 API 验证
        results = await self.search_fund(fund_code)
        for r in results:
            if r.get("code") == fund_code:
                return True
        
        # 使用实时行情 API 验证
        realtime = await self.get_fund_realtime(fund_code)
        if realtime and realtime.get("name"):
            return True
        
        return False


# 全局实例
_api: Optional[EastMoneyAPI] = None


def get_api() -> EastMoneyAPI:
    """获取全局 API 实例"""
    global _api
    if _api is None:
        _api = EastMoneyAPI()
    return _api
