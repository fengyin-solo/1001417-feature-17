"""养护材料业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "material"
REQUIRED_FIELDS = ["材料编号", "材料名称", "规格型号"]
OPTIONAL_FIELDS = ["计量单位", "存放场地", "保管人员"]
STATUS_ORDER = ["正常可用", "临近不足", "已冻结", "已耗尽"]
ACTION_RULES = {"冻结材料": "已冻结", "解冻材料": "正常可用", "登记耗尽": "已耗尽"}
ACTION_MESSAGES = {
    "冻结材料": "养护材料已冻结",
    "解冻材料": "养护材料已解冻，恢复为正常可用",
    "登记耗尽": "养护材料已登记耗尽",
}
ACTION_SOURCES = {
    "冻结材料": {"正常可用", "临近不足"},
    "解冻材料": {"已冻结"},
    "登记耗尽": {"正常可用", "临近不足", "已冻结"},
}
NEGATIVE_ACTIONS: list[str] = []


def _to_number(value: Any) -> float | None:
    """把录入的数量转成浮点数；空串、非数字一律按 None 处理，不让脏数据蒙混过关。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _normalize_number(value: float) -> int | float:
    """整数数量按整数存，避免列表里出现 10.0 这样的显示。"""
    return int(value) if value == int(value) else value


def _is_low_stock(row: dict[str, Any]) -> bool:
    """结存数量低于储备下限即视为储备不足；任一数值缺失时不误判。"""
    quantity = _to_number(row.get("结存数量"))
    lower_limit = _to_number(row.get("储备下限"))
    if quantity is None or lower_limit is None:
        return False
    return quantity < lower_limit


def _decorate(row: dict[str, Any]) -> dict[str, Any]:
    """列表与明细统一带上储备不足标记，前端按它把材料单独标出来。"""
    decorated = dict(row)
    decorated["low_stock"] = _is_low_stock(row)
    return decorated


class MaterialService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        low_only: bool = False,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int, dict[str, int]]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("材料编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if low_only:
            rows = [row for row in rows if _is_low_stock(row)]
        total = len(rows)
        summary = {
            "可用材料": sum(1 for row in rows if row.get("status") == STATUS_ORDER[0]),
            "储备不足材料": sum(1 for row in rows if _is_low_stock(row)),
            "已冻结材料": sum(1 for row in rows if row.get("status") == "已冻结"),
        }
        start = max(page - 1, 0) * size
        return [_decorate(row) for row in rows[start:start + size]], total, summary

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        return _decorate(row) if row is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        code = str(values.get("材料编号")).strip()
        duplicated = any(
            str(row.get("材料编号", "")).strip() == code for row in store.rows(MODULE)
        )
        if duplicated:
            return None, f"材料编号 {code} 已存在，相同编号只保留一条，未重复登记"
        raw_quantity = values.get("结存数量")
        if raw_quantity is None or str(raw_quantity).strip() == "":
            return None, "结存数量不合规：不能为空，不能按正常可用入库"
        quantity = _to_number(raw_quantity)
        if quantity is None:
            return None, f"结存数量不合规：「{raw_quantity}」不是有效数字"
        if quantity <= 0:
            return None, f"结存数量不合规：{_normalize_number(quantity)} 不大于 0，不能按正常可用入库"
        raw_limit = values.get("储备下限")
        if raw_limit is None or str(raw_limit).strip() == "":
            lower_limit = 0.0
        else:
            parsed_limit = _to_number(raw_limit)
            if parsed_limit is None:
                return None, f"储备下限不合规：「{raw_limit}」不是有效数字"
            if parsed_limit < 0:
                return None, f"储备下限不合规：{_normalize_number(parsed_limit)} 不能小于 0"
            lower_limit = parsed_limit
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: str(values.get(field)).strip() for field in REQUIRED_FIELDS})
        entry["结存数量"] = _normalize_number(quantity)
        entry["储备下限"] = _normalize_number(lower_limit)
        for field in OPTIONAL_FIELDS:
            text = str(values.get(field) or "").strip()
            if text:
                entry[field] = text
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return _decorate(entry), None

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"养护材料 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于养护材料可执行范围"
        current = str(entry.get("status") or "")
        if current not in ACTION_SOURCES[action]:
            return None, f"当前状态「{current}」不允许{action}"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return _decorate(entry), ACTION_MESSAGES[action]
