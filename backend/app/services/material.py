"""养护材料业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "material"
REQUIRED_FIELDS = ["材料编号", "材料名称", "规格型号"]
EXTRA_FIELDS = ["计量单位", "存放场地", "保管人员"]
STOCK_FIELD = "结存数量"
RESERVE_FIELD = "储备下限"
STATUS_FIELD = "材料状态"
STATUS_ORDER = ["正常可用", "临近不足", "已冻结", "已耗尽"]
ACTION_RULES = {"冻结材料": "已冻结", "解冻材料": "正常可用", "登记耗尽": "已耗尽"}


def _to_number(value: Any) -> float | None:
    """把录入的数量转成数字；空值、非数字一律按 None 处理。"""
    if value is None:
        return None
    if isinstance(value, bool):
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


def _fmt_number(value: float) -> int | float:
    """整数数量按整数落库，避免列表与明细里出现 10.0 这类显示。"""
    return int(value) if float(value).is_integer() else value


def _usable_status(stock: float, reserve: float) -> str:
    """结存低于储备下限即视为储备不足，否则正常可用。"""
    return "临近不足" if stock < reserve else "正常可用"


class MaterialService:
    def _deduped_rows(self) -> list[dict[str, Any]]:
        """材料编号重复时只保留一条（以最新登记为准），列表、明细与统计共用同一口径。"""
        rows = store.rows(MODULE)
        deduped: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for row in rows:
            code = str(row.get("材料编号") or "").strip() or f"#{row.get('id', '')}"
            if code not in deduped:
                order.append(code)
            deduped[code] = row
        return [deduped[code] for code in order]

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._deduped_rows()
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("材料编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def summary(self) -> dict[str, int]:
        """看板统计：可用、储备不足、已冻结与总数，和列表去重口径保持一致。"""
        rows = self._deduped_rows()
        return {
            "可用材料": sum(1 for row in rows if row.get("status") == "正常可用"),
            "储备不足材料": sum(1 for row in rows if row.get("status") == "临近不足"),
            "已冻结材料": sum(1 for row in rows if row.get("status") == "已冻结"),
            "材料总数": len(rows),
        }

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        problems: list[str] = []
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            problems.append(f"缺少必填字段：{'、'.join(missing)}")

        raw_stock = values.get(STOCK_FIELD)
        stock_text = "" if raw_stock is None else str(raw_stock).strip()
        stock = _to_number(raw_stock)
        if not stock_text:
            problems.append("结存数量为空，不能按正常可用入库")
        elif stock is None:
            problems.append(f"结存数量「{stock_text}」不是有效数字，不能按正常可用入库")
        elif stock <= 0:
            label = "零" if stock == 0 else f"负数（{_fmt_number(stock)}）"
            problems.append(f"结存数量为{label}，不能按正常可用入库")

        raw_reserve = values.get(RESERVE_FIELD)
        reserve_text = "" if raw_reserve is None else str(raw_reserve).strip()
        reserve = _to_number(raw_reserve)
        if reserve_text and reserve is None:
            problems.append(f"储备下限「{reserve_text}」不是有效数字")
        elif reserve is not None and reserve < 0:
            problems.append(f"储备下限不能为负数（{_fmt_number(reserve)}）")
        if reserve is None:
            reserve = 0.0

        if problems:
            return None, problems

        assert stock is not None  # 通过校验后结存数量必为有效数字
        rows = store.rows(MODULE)
        code = str(values.get("材料编号") or "").strip()
        status = _usable_status(stock, reserve)
        fields = {field: values.get(field) for field in REQUIRED_FIELDS + EXTRA_FIELDS}
        fields[STOCK_FIELD] = _fmt_number(stock)
        fields[RESERVE_FIELD] = _fmt_number(reserve)

        existing = next(
            (row for row in rows if str(row.get("材料编号") or "").strip() == code),
            None,
        )
        if existing is not None:
            # 材料编号重复：合并回原有记录，库里始终只保留一条。
            existing.update(fields)
            if existing.get("status") != "已冻结":
                existing["status"] = status
            self._sync_flags(existing)
            return existing, []

        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update(fields)
        entry["status"] = status
        self._sync_flags(entry)
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"养护材料 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于养护材料可执行范围"
        current = str(entry.get("status") or "")
        if action == "冻结材料":
            if current == "已冻结":
                return None, "该材料已处于冻结状态，无需重复冻结"
            if current == "已耗尽":
                return None, "该材料已耗尽，不能再执行冻结"
            entry["status"] = "已冻结"
        elif action == "解冻材料":
            if current != "已冻结":
                return None, f"仅已冻结的材料可以解冻，当前状态为「{current or '未知'}」"
            # 解冻后按结存与储备下限重新判定，保证能回到正常可用。
            entry["status"] = self._status_from_stock(entry)
        elif action == "登记耗尽":
            if current == "已耗尽":
                return None, "该材料已登记耗尽，请勿重复操作"
            entry["status"] = "已耗尽"
            entry[STOCK_FIELD] = 0
        self._sync_flags(entry)
        if action == "解冻材料":
            return entry, f"养护材料已解冻，当前状态：{entry['status']}"
        return entry, f"养护材料已{action.replace('材料', '')}"

    def _status_from_stock(self, entry: dict[str, Any]) -> str:
        stock = _to_number(entry.get(STOCK_FIELD)) or 0.0
        reserve = _to_number(entry.get(RESERVE_FIELD)) or 0.0
        return _usable_status(stock, reserve)

    @staticmethod
    def _sync_flags(entry: dict[str, Any]) -> None:
        status = str(entry.get("status") or "")
        entry[STATUS_FIELD] = status or entry.get(STATUS_FIELD)
        entry["pending"] = status != "已耗尽"
        entry["abnormal"] = status == "临近不足"
