"""
六位基金/证券代码与用户意图解析（场内行情 vs 场外净值）。

无显式标记时 prefer_otc 为 False，走交易所行情接口。
场外基金请在代码后加 ``.OF`` / ``.otc``，或前缀 ``场外``。
"""

from __future__ import annotations

import re
from typing import Optional


def parse_fund_code_hint(raw: str | int | None) -> tuple[Optional[str], bool]:
    """
    从用户输入解析标准六位代码，以及场外/场内偏好。

    Returns:
        (code, prefer_otc) — ``prefer_otc`` 为 True 时使用场外净值接口；
        为 False（默认）时使用交易所行情接口。
    """
    if raw is None:
        return None, False
    s = str(raw).strip()
    if not s:
        return None, False

    prefer_otc = False

    if s.startswith("场外"):
        prefer_otc = True
        s = s[2:].strip()
    elif s.startswith("场内"):
        prefer_otc = False
        s = s[2:].strip()

    sl = s.lower()
    dot = s.rfind(".")
    if dot >= 0 and dot < len(s) - 1:
        ext = sl[dot + 1 :]
        if ext in ("of", "otc"):
            prefer_otc = True
            s = s[:dot].strip()
        elif ext in ("sz", "sh", "exchange"):
            prefer_otc = False
            s = s[:dot].strip()

    digits = re.sub(r"\D", "", s)
    if not digits:
        return None, prefer_otc
    if len(digits) > 6:
        digits = digits[-6:]
    code = digits.zfill(6)
    return code, prefer_otc
