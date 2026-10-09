from sqlalchemy import create_engine, text

from app.api import orders


def test_unmatched_orders_can_be_paginated_ignored_and_restored(monkeypatch):
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("""CREATE TABLE app_orders (
            id INTEGER PRIMARY KEY, platform INTEGER, order_no TEXT, product TEXT, product_spec TEXT,
            product_quantity REAL, meters REAL, flower TEXT, refunded INTEGER, cancelled INTEGER, order_status TEXT,
            after_sale_status TEXT, order_date DATE, order_time DATE, merchant_income REAL, updated_at TEXT)"""))
        connection.execute(text("""CREATE TABLE app_ignored_unmatched (
            order_id INTEGER PRIMARY KEY, ignored_at TEXT DEFAULT CURRENT_TIMESTAMP)"""))
        connection.execute(text("""INSERT INTO app_orders VALUES
            (1, 0, 'A-1', '旧花型A', '1米', 1, 0, NULL, 0, 0, '已发货', '', '2026-10-01', '2026-10-01', 20, '2026-10-01'),
            (2, 1, 'B-1', '旧花型B', '2米', 1, 0, NULL, 0, 0, '已发货', '', '2026-10-02', '2026-10-02', 30, '2026-10-02'),
            (3, 2, 'C-1', '已退款旧花型', '', 1, 0, NULL, 1, 0, '交易关闭', '退款成功', '2026-10-03', '2026-10-03', 0, '2026-10-03')"""))
    monkeypatch.setattr(orders, "get_engine", lambda: engine)

    first_page = orders.unmatched_orders(limit=1, offset=0)
    assert first_page["total"] == 3
    assert len(first_page["items"]) == 1

    sorted_first = orders._unmatched_page(False, limit=2, offset=0, sort_by="order_no", sort_order="asc")
    sorted_second = orders._unmatched_page(False, limit=2, offset=2, sort_by="order_no", sort_order="asc")
    assert [item["order_no"] for item in sorted_first["items"] + sorted_second["items"]] == ["A-1", "B-1", "C-1"]

    assert orders.ignore_unmatched(orders.UnmatchedIds(all=True, exclude_order_ids=[2])) == {"ignored": 2}
    assert orders.unmatched_orders()["total"] == 1
    assert {item["id"] for item in orders.ignored_unmatched_orders()["items"]} == {1, 3}

    assert orders.restore_unmatched(orders.UnmatchedIds(order_ids=[1])) == {"restored": 1}
    assert orders.ignore_unmatched(orders.UnmatchedIds(all=True)) == {"ignored": 2}
    assert orders.unmatched_orders()["total"] == 0

    assert orders.restore_unmatched(orders.UnmatchedIds(order_ids=[1, 2, 3])) == {"restored": 3}
    assert orders.unmatched_orders()["total"] == 3
