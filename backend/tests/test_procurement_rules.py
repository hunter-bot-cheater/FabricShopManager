from datetime import date

from app.domain.procurement_rules import rank_restock_dates


def test_restock_options_rank_dates_whole_rolls_and_costs():
    result = rank_restock_dates(
        today=date(2026, 10, 8), stock=12, daily_use=2, roll_length=45,
        cost_per_meter=18.5, lead_days=2, target_days=14,
    )

    assert result["status"] == "计划补货"
    assert [option["label"] for option in result["options"]] == ["最优", "次优", "再次优"]
    assert result["days_until_order"] == 3
    assert result["options"][0]["order_date"] == "2026-10-11"
    assert result["options"][0]["arrival_date"] == "2026-10-13"
    assert all(option["roll_count"] == 1 and option["meters"] == 45 for option in result["options"])
    assert all(option["estimated_cost"] == 832.5 for option in result["options"])
    assert [option["risk"] for option in result["options"]] == ["低于预警线", "低于预警线", "可能缺货"]


def test_restock_without_recent_sales_does_not_invent_a_purchase():
    result = rank_restock_dates(
        today=date(2026, 10, 8), stock=0, daily_use=0, roll_length=45,
        cost_per_meter=18.5, lead_days=1, target_days=14,
    )
    assert result["status"] == "近 7 天暂无有效销量"
    assert result["options"] == []


def test_restock_waits_until_stock_approaches_threshold():
    result = rank_restock_dates(
        today=date(2026, 10, 8), stock=100, daily_use=2, roll_length=45,
        cost_per_meter=18.5, lead_days=2, target_days=14,
    )
    assert result["days_until_order"] == 47
    assert result["options"] == []


def test_restock_threshold_is_daily_sales_times_arrival_days_plus_one():
    result = rank_restock_dates(
        today=date(2026, 10, 8), stock=6, daily_use=2, roll_length=45,
        cost_per_meter=18.5, lead_days=2, target_days=14,
    )
    assert result["days_until_order"] == 0
    assert result["options"][0]["order_date"] == "2026-10-08"
