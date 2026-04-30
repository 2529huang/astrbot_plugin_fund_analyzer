"""
从 AstrMessageEvent 取纯文本及「板块/搜索」类指令的尾部解析。
"""

from __future__ import annotations

import re
from typing import Any

DEFAULT_BOARD_DISPLAY_LIMIT = 40
MIN_BOARD_DISPLAY_LIMIT = 1
MAX_BOARD_DISPLAY_LIMIT = 200

# 板块内量化排序：分析上限与 TOP 输出（与「量化精选股票」语义类似，双数字在尾部）
DEFAULT_BOARD_QUANT_MAX_SCAN = 80
DEFAULT_BOARD_QUANT_TOP = 10
MIN_BOARD_QUANT_MAX_SCAN = 1
MAX_BOARD_QUANT_MAX_SCAN = 200
MIN_BOARD_QUANT_TOP = 1
MAX_BOARD_QUANT_TOP = 50


def get_event_plain_text(event: Any) -> str:
    """尽量兼容不同 AstrBot 版本的事件 API。"""
    gt = getattr(event, "get_plain_text", None)
    if callable(gt):
        try:
            t = gt()
            if t is not None:
                return str(t).strip()
        except TypeError:
            try:
                t = gt(False)
                if t is not None:
                    return str(t).strip()
            except Exception:
                pass
        except Exception:
            pass
    for attr in ("message_str", "plain_text", "text"):
        v = getattr(event, attr, None)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def strip_command_prefix(text: str, command: str) -> str:
    """去掉可选 /、! 前缀及命令名，返回剩余参数段。"""
    s = (text or "").strip()
    for p in ("/", "！", "!"):
        if s.startswith(p):
            s = s[len(p) :].strip()
    if s.startswith(command):
        return s[len(command) :].strip()
    return s


def parse_keyword_and_limit(
    tail: str,
    *,
    default_limit: int = DEFAULT_BOARD_DISPLAY_LIMIT,
) -> tuple[str, int]:
    """
    解析「关键词/名称 … [条数]」：若尾部为纯数字且前面非空，则该数字为 limit；
    若整段为纯数字且无名称语义，返回 ("", limit) 由调用方判无效。
    """
    tail = (tail or "").strip()
    if not tail:
        return "", default_limit
    m = re.match(r"^(.+?)\s+(\d+)\s*$", tail)
    if m:
        name = m.group(1).strip()
        try:
            limit = int(m.group(2))
        except ValueError:
            limit = default_limit
        limit = max(MIN_BOARD_DISPLAY_LIMIT, min(MAX_BOARD_DISPLAY_LIMIT, limit))
        return name, limit
    if tail.isdigit():
        try:
            lim = int(tail)
        except ValueError:
            lim = default_limit
        lim = max(MIN_BOARD_DISPLAY_LIMIT, min(MAX_BOARD_DISPLAY_LIMIT, lim))
        return "", lim
    return tail, max(
        MIN_BOARD_DISPLAY_LIMIT, min(MAX_BOARD_DISPLAY_LIMIT, default_limit)
    )


def parse_name_maxscan_top(
    tail: str,
    *,
    default_max_scan: int = DEFAULT_BOARD_QUANT_MAX_SCAN,
    default_top: int = DEFAULT_BOARD_QUANT_TOP,
) -> tuple[str, int, int]:
    """
    解析「名称 … [分析上限] [输出条数]」：末尾可有 1 或 2 个纯数字 token；
    两个数字时依次为 max_scan、top_n；一个数字时为 max_scan，top_n 用 default_top。
    """
    tail = (tail or "").strip()
    if not tail:
        return "", default_max_scan, default_top
    parts = tail.split()
    if len(parts) >= 2 and parts[-1].isdigit() and parts[-2].isdigit():
        try:
            max_scan = int(parts[-2])
            top_n = int(parts[-1])
        except ValueError:
            max_scan, top_n = default_max_scan, default_top
        name = " ".join(parts[:-2]).strip()
    elif len(parts) >= 1 and parts[-1].isdigit():
        try:
            max_scan = int(parts[-1])
        except ValueError:
            max_scan = default_max_scan
        name = " ".join(parts[:-1]).strip()
        top_n = default_top
    else:
        name = tail
        max_scan = default_max_scan
        top_n = default_top
    max_scan = max(
        MIN_BOARD_QUANT_MAX_SCAN, min(MAX_BOARD_QUANT_MAX_SCAN, max_scan)
    )
    top_n = max(MIN_BOARD_QUANT_TOP, min(MAX_BOARD_QUANT_TOP, top_n))
    return name, max_scan, top_n
