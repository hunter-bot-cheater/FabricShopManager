from __future__ import annotations

import math
from datetime import date, timedelta


def rank_restock_dates(*, today: date, stock: float, daily_use: float, roll_length: float,
                       cost_per_meter: float, lead_days: int, target_days: int,
                       sales_window_days: int = 7, horizon_days: int = 14) -> dict:
    if roll_length <= 0:
        return {"status": "需要设置每卷米数", "options": []}
    if daily_use <= 0:
        return {"status": f"近 {sales_window_days} 天暂无有效销量", "options": []}
    lead_days = max(1, int(lead_days))
    reorder_level = daily_use * (lead_days + 1)
    wait_days = max(0, math.floor((stock - reorder_level) / daily_use))
    if wait_days > horizon_days:
        return {"status": "未来 14 天暂不需要补货", "days_until_order": wait_days, "options": []}

    options = []
    for rank, delay in enumerate((wait_days, wait_days + 1, wait_days + 2), start=1):
        arrival_day = delay + lead_days
        projected = round(stock - daily_use * arrival_day, 2)
        desired_stock = daily_use * (lead_days + max(1, target_days))
        needed = max(0.0, desired_stock - projected)
        rolls = max(1, math.ceil((needed - 1e-9) / roll_length))
        options.append({
            "rank": rank,
            "label": ("最优" if rank == 1 else "次优" if rank == 2 else "再次优"),
            "order_date": (today + timedelta(days=delay)).isoformat(),
            "arrival_date": (today + timedelta(days=arrival_day)).isoformat(),
            "days_until_order": delay,
            "roll_count": rolls,
            "meters": round(rolls * roll_length, 2),
            "estimated_cost": round(rolls * roll_length * max(0, cost_per_meter), 2),
            "projected_stock_on_arrival": projected,
            "risk": ("可能缺货" if projected < 0 else "低于预警线" if projected < reorder_level else "安全"),
        })
    priority = "立即关注" if wait_days == 0 else "近期安排" if wait_days <= 2 else "计划补货"
    return {"status": priority, "days_until_order": wait_days, "daily_use": round(daily_use, 2),
            "stock_cover_days": round(max(0, stock) / daily_use, 1), "options": options}
