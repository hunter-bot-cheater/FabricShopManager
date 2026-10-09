from datetime import date

from app.domain.procurement_rules import build_purchase_strategy


def _product(flower, *, stock=0, sales=14, roll=45, lead=1, cost=6):
    return {"flower": flower, "current_stock": stock, "recent_sales": sales,
            "roll_length_meters": roll, "replenishment_days": lead, "cost_per_meter": cost}


def test_sellout_date_and_replenishment_day_use_sales_window_and_lead_time():
    result = build_purchase_strategy(
        today=date(2026, 10, 8), products=[_product("花型A", stock=6)],
        batch_capacity_meters=1350, target_coverage_days=14, sales_window_days=7,
    )
    item = result["items"][0]
    assert item["daily_use"] == 2
    assert item["sellout_date"] == "2026-10-11"
    assert item["order_date"] == "2026-10-09"
    assert item["arrival_date"] == "2026-10-10"
    assert item["roll_count"] == 1 and item["meters"] == 45
    assert result["strategy"][0]["order_date"] == "2026-10-09"


def test_zero_stock_is_flagged_but_no_sales_does_not_invent_purchase():
    result = build_purchase_strategy(
        today=date(2026, 10, 8), products=[_product("无销量", sales=0)],
        batch_capacity_meters=1350, target_coverage_days=14, sales_window_days=7,
    )
    item = result["items"][0]
    assert item["sellout_label"] == "已无库存"
    assert item["plan_issue"] == "无有效销量，无法推算补货量"
    assert result["strategy"] == []


def test_whole_rolls_pack_by_meter_capacity_and_extra_trip_is_same_day():
    result = build_purchase_strategy(
        today=date(2026, 10, 8), products=[
            _product("45米花型", sales=315, roll=45),
            _product("90米花型", sales=21, roll=90),
        ], batch_capacity_meters=1350, target_coverage_days=30, sales_window_days=7,
    )
    day = result["strategy"][0]
    assert day["order_date"] == "2026-10-08"
    assert day["trip_count"] == 2
    assert day["batches"][0]["total_meters"] == 1350
    assert day["batches"][1]["items"][0]["flower"] == "90米花型"
    assert day["batches"][1]["total_meters"] == 90
    assert all(batch["total_meters"] <= 1350 for batch in day["batches"])


def test_a_roll_larger_than_trip_capacity_is_not_split_or_silently_dropped():
    result = build_purchase_strategy(
        today=date(2026, 10, 8), products=[_product("超长卷", roll=1400)],
        batch_capacity_meters=1350, target_coverage_days=14, sales_window_days=7,
    )
    assert result["strategy"] == []
    assert result["unplannable"][0]["plan_issue"] == "单卷长度超过单次进货上限"
