from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


APP_NAME = "FabricShopManager"


def app_data_dir() -> Path:
    root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    path = root / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_path() -> Path:
    return app_data_dir() / "settings.json"


def defaults() -> dict[str, Any]:
    output_root = Path.home() / "Documents" / "布料店报表"
    return {
        "mysql_host": "127.0.0.1",
        "mysql_port": 3306,
        "mysql_database": "shop_data",
        "mysql_user": "root",
        "output_daily": str(output_root / "日报"),
        "output_range": str(output_root / "区间报告"),
        "output_refund": str(output_root / "退款明细"),
        "output_inventory": str(output_root / "库存明细"),
        "output_inout": str(output_root / "出库入库明细报告"),
        "default_shipping_fee": 2.5,
        "inventory_sales_window_days": 7,
        "procurement_target_days": 14,
        "procurement_batch_capacity_meters": 1350,
        "baseline_imported": False,
    }


def load_settings() -> dict[str, Any]:
    path = settings_path()
    if not path.exists():
        return defaults()
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defaults()
    base = defaults()
    return {**base, **{key: value for key, value in saved.items() if key in base}}


def save_settings(values: dict[str, Any]) -> dict[str, Any]:
    current = load_settings()
    allowed = set(defaults())
    for key, value in values.items():
        if key in allowed:
            current[key] = value
    current["mysql_port"] = int(current["mysql_port"])
    current["default_shipping_fee"] = max(0.0, float(current["default_shipping_fee"]))
    current["procurement_target_days"] = min(max(1, int(current["procurement_target_days"])), 90)
    current["inventory_sales_window_days"] = min(max(1, int(current["inventory_sales_window_days"])), 90)
    current["procurement_batch_capacity_meters"] = min(
        max(1, int(current["procurement_batch_capacity_meters"])), 1_000_000
    )
    path = settings_path()
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)
    return current
