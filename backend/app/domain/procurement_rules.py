from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from math import ceil, floor


def _whole_rolls(meters: float, roll_length: float) -> int:
    return max(0, ceil(meters / roll_length - 1e-9)) if roll_length > 0 else 0


def build_purchase_strategy(
    *, today: date, products: list[dict], batch_capacity_meters: float,
    target_coverage_days: int, sales_window_days: int,
) -> dict:
    """Forecast sell-out and pack whole-roll purchases into meter-limited trips."""
    capacity = max(1.0, float(batch_capacity_meters))
    coverage_days = max(1, int(target_coverage_days))
    window_days = max(1, int(sales_window_days))
    items = []

    for product in products:
        flower = str(product["flower"])
        stock = max(0.0, float(product.get("current_stock") or 0))
        recent_sales = max(0.0, float(product.get("recent_sales") or 0))
        daily_use = recent_sales / window_days
        lead_days = max(1, int(product.get("replenishment_days") or 1))
        roll_length = max(0.0, float(product.get("roll_length_meters") or 0))
        cost_per_meter = max(0.0, float(product.get("cost_per_meter") or 0))

        if stock <= 0:
            sellout_date, days_until_sellout, sellout_label = today, 0, "已无库存"
        elif daily_use <= 0:
            sellout_date, days_until_sellout = None, None
            sellout_label = f"近 {window_days} 天无销量"
        else:
            days_until_sellout = max(0, ceil(stock / daily_use - 1e-9))
            sellout_date = today + timedelta(days=days_until_sellout)
            sellout_label = sellout_date.isoformat()

        if daily_use > 0 and roll_length > 0:
            # Preserve the configured safety threshold: average daily sales × (lead time + 1).
            order_offset = max(0, floor(stock / daily_use - (lead_days + 1) + 1e-9))
            order_date = today + timedelta(days=order_offset)
            arrival_date = order_date + timedelta(days=lead_days)
            projected_stock = max(0.0, stock - daily_use * (order_offset + lead_days))
            needed_meters = max(0.0, daily_use * coverage_days - projected_stock)
            roll_count = _whole_rolls(needed_meters, roll_length)
            planned_meters = round(roll_count * roll_length, 2)
            plan_issue = "单卷长度超过单次进货上限" if roll_length > capacity else ""
        else:
            order_offset = None
            order_date = arrival_date = None
            projected_stock = stock
            needed_meters = roll_count = planned_meters = 0
            plan_issue = "无有效销量，无法推算补货量" if daily_use <= 0 else "每卷米数无效"

        items.append({
            "flower": flower,
            "current_stock": round(stock, 2),
            "recent_sales": round(recent_sales, 2),
            "daily_use": round(daily_use, 2),
            "replenishment_days": lead_days,
            "roll_length_meters": round(roll_length, 2),
            "cost_per_meter": round(cost_per_meter, 4),
            "sellout_date": sellout_date.isoformat() if sellout_date else None,
            "days_until_sellout": days_until_sellout,
            "sellout_label": sellout_label,
            "status": "立即关注" if stock <= daily_use * (lead_days + 1) else "正常",
            "order_date": order_date.isoformat() if order_date else None,
            "arrival_date": arrival_date.isoformat() if arrival_date else None,
            "days_until_order": order_offset,
            "projected_stock_on_arrival": round(projected_stock, 2),
            "needed_meters": round(needed_meters, 2),
            "roll_count": roll_count,
            "meters": planned_meters,
            "estimated_cost": round(planned_meters * cost_per_meter, 2),
            "plan_issue": plan_issue,
        })

    items.sort(key=lambda item: (
        item["days_until_sellout"] if item["days_until_sellout"] is not None else float("inf"),
        item["days_until_order"] if item["days_until_order"] is not None else float("inf"),
        item["flower"],
    ))
    for priority, item in enumerate((row for row in items if row["roll_count"]), start=1):
        item["priority"] = priority

    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        if item["roll_count"] and not item["plan_issue"]:
            grouped[item["order_date"]].append(item)

    strategy = []
    unplannable = []
    for item in items:
        if item["roll_count"] and item["plan_issue"]:
            unplannable.append(item)

    for order_date in sorted(grouped):
        batches: list[dict] = []
        for item in grouped[order_date]:
            roll_length = item["roll_length_meters"]
            for _ in range(item["roll_count"]):
                candidates = [batch for batch in batches
                              if batch["total_meters"] + roll_length <= capacity + 1e-9]
                batch = min(candidates, key=lambda row: capacity - row["total_meters"] - roll_length) if candidates else None
                if batch is None:
                    batch = {"trip": len(batches) + 1, "total_meters": 0.0,
                             "estimated_cost": 0.0, "items": []}
                    batches.append(batch)
                packed_item = next((row for row in batch["items"] if row["flower"] == item["flower"]), None)
                if packed_item is None:
                    packed_item = {"flower": item["flower"], "roll_count": 0, "roll_length_meters": roll_length,
                                   "meters": 0.0, "estimated_cost": 0.0, "priority": item["priority"],
                                   "sellout_date": item["sellout_date"], "arrival_date": item["arrival_date"]}
                    batch["items"].append(packed_item)
                packed_item["roll_count"] += 1
                packed_item["meters"] = round(packed_item["meters"] + roll_length, 2)
                packed_item["estimated_cost"] = round(packed_item["estimated_cost"] + roll_length * item["cost_per_meter"], 2)
                batch["total_meters"] = round(batch["total_meters"] + roll_length, 2)
                batch["estimated_cost"] = round(batch["estimated_cost"] + roll_length * item["cost_per_meter"], 2)
        strategy.append({"order_date": order_date, "trip_count": len(batches), "batches": batches})

    return {"items": items, "strategy": strategy, "unplannable": unplannable,
            "batch_capacity_meters": capacity, "sales_window_days": window_days,
            "target_coverage_days": coverage_days}
