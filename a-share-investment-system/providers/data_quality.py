"""数据完整性契约 — 定义选股必需的字段标准 & 验证函数"""

from collections.abc import Callable
from typing import Any

Validator = Callable[[Any], bool]

# Required fields for screening
# {field_name: validation_function(value) -> bool}
STOCK_REQUIRED_FIELDS: dict[str, Validator] = {
    "stock_name": lambda v: bool(v and len(str(v)) > 1 and str(v)[0].isalnum()),
    "latest_price": lambda v: v is not None and float(v) > 0,
    "pe_ratio": lambda v: v is not None and float(v) > 0,
    "turnover_rate": lambda v: v is not None,
    "total_market_cap": lambda v: v is not None and float(v) > 0,
    "change_pct": lambda v: v is not None,
    "amount": lambda v: v is not None,
    "industry": bool,
    "volume": lambda v: v is not None,
}

# 非必需但有更好
STOCK_OPTIONAL_FIELDS = {
    "pb_ratio",
    "float_market_cap",
    "gross_margin",
    "roe",
    "eps",
    "bvps",
    "debt_to_equity",
    "current_assets",
    "total_liabilities",
    "free_cash_flow",
    "revenue_growth_3y",
    "earnings_growth_3y",
}

# All known fields (for merge decision)
ALL_STOCK_FIELDS = set(STOCK_REQUIRED_FIELDS.keys()) | STOCK_OPTIONAL_FIELDS


def verify_stock_info(info_dict: dict) -> dict[str, bool]:
    """返回全部 21 个字段的状态: True=有效, False=缺失/无效"""
    result: dict[str, bool] = {}
    for field, validator in STOCK_REQUIRED_FIELDS.items():
        val = info_dict.get(field)
        try:
            result[field] = bool(validator(val))
        except (ValueError, TypeError):
            result[field] = False
    for field in STOCK_OPTIONAL_FIELDS:
        val = info_dict.get(field)
        if val is not None and val not in {0, "", "未知"}:
            try:
                result[field] = float(val) != 0
            except (ValueError, TypeError):
                result[field] = bool(val)
        else:
            result[field] = False
    return result


def is_stock_complete(info_dict: dict) -> bool:
    """检查所有必需字段是否已有效填充"""
    return all(verify_stock_info(info_dict).values())


def missing_required_fields(info_dict: dict) -> list:
    """返回缺失的必需字段列表"""
    return [f for f, ok in verify_stock_info(info_dict).items() if not ok]


def completeness_score(info_dict: dict) -> tuple[float, int]:
    """返回完整度评分 (0-1) 和缺失字段数"""
    verify = verify_stock_info(info_dict)
    filled = sum(1 for ok in verify.values() if ok)
    total = len(verify)
    return (filled / total, total - filled)


def should_overwrite(current_val, new_val) -> bool:
    """判断是否应用新值: 当前值为空/0/None 且 新值有效"""
    if new_val is None:
        return False
    try:
        f_new = float(new_val)
    except (ValueError, TypeError):
        f_new = 0
    try:
        f_cur = float(current_val) if current_val else 0
    except (ValueError, TypeError):
        f_cur = 0
    # 当前为空/0/None 且 新值有效(>0)
    return (f_cur == 0) and (f_new != 0)


def is_field_computed(field_name: str) -> bool:
    """判断某字段是否允许计算填充"""
    return field_name in {"eps", "bvps", "debt_to_equity", "roe", "gross_margin"}


def can_compute_field(field_name: str, info_dict: dict) -> bool:
    """判断某字段是否具备计算条件"""
    if field_name == "eps":
        return float(info_dict.get("latest_price", 0) or 0) > 0 and float(
            info_dict.get("pe_ratio", 0) or 0
        ) > 0
    if field_name == "bvps":
        return float(info_dict.get("latest_price", 0) or 0) > 0 and float(
            info_dict.get("pb_ratio", 0) or 0
        ) > 0
    if field_name == "debt_to_equity":
        return float(info_dict.get("total_liabilities", 0) or 0) > 0 and float(
            info_dict.get("shareholders_equity", 0) or 0
        ) > 0
    if field_name == "roe":
        return float(info_dict.get("net_income", 0) or 0) > 0 and float(
            info_dict.get("shareholders_equity", 0) or 0
        ) > 0
    if field_name == "gross_margin":
        return float(info_dict.get("revenue", 0) or 0) > 0 and float(
            info_dict.get("cost_of_goods_sold", 0) or 0
        ) > 0
    return False


def compute_missing_fields(info_dict: dict) -> dict:
    """对可计算字段进行填充,返回更新后的 dict。不覆盖已有有效值。"""
    result = dict(info_dict)
    if not result.get("eps") and can_compute_field("eps", result):
        result["eps"] = result["latest_price"] / result["pe_ratio"]
    if not result.get("bvps") and can_compute_field("bvps", result):
        result["bvps"] = result["latest_price"] / result["pb_ratio"]
    if not result.get("debt_to_equity") and can_compute_field("debt_to_equity", result):
        result["debt_to_equity"] = result["total_liabilities"] / result["shareholders_equity"]
    if not result.get("roe") and can_compute_field("roe", result):
        result["roe"] = result["net_income"] / result["shareholders_equity"]
    return result
