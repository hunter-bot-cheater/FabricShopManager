from datetime import date

from sqlalchemy import create_engine, text

from app.services.inventory_service import (
    _stock_at_date, get_recommendations, list_inventory, rebuild_product_stock,
)


class SQLiteCompatConnection:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, statement, params=None):
        sql = str(statement).replace(" FOR UPDATE", "")
        return self.connection.execute(text(sql), params or {})


def test_later_backdated_movement_does_not_change_counted_stock_anchor():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE app_products (flower TEXT PRIMARY KEY, current_stock REAL)"))
        connection.execute(text("""CREATE TABLE app_stock_events (
            id INTEGER PRIMARY KEY, flower TEXT, effective_date TEXT, event_type TEXT, change_qty REAL,
            before_stock REAL, after_stock REAL)"""))
        connection.execute(text("INSERT INTO app_products VALUES ('花型A', 90)"))
        connection.execute(text("""INSERT INTO app_stock_events VALUES
            (1, '花型A', '2026-10-06', '采购入库', 45, 80, 125),
            (2, '花型A', '2026-10-08', '盘点', -25, 125, 100),
            (3, '花型A', '2026-10-06', '主动出库', -10, 125, 115)"""))

        current = rebuild_product_stock(SQLiteCompatConnection(connection), "花型A")
        events = [dict(row) for row in connection.execute(text("""SELECT id, effective_date,
            event_type, change_qty, after_stock FROM app_stock_events WHERE id<>3""")).mappings()]

    assert current == 100
    state = _stock_at_date(80, events + [{
        "id": 3, "effective_date": date(2026, 10, 6), "event_type": "主动出库",
        "change_qty": -10, "after_stock": 115,
    }], date(2026, 10, 8))
    assert state["counted"] == 100
    assert state["theoretical"] == 115


def _inventory_listing_engine(current_stock=17):
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("""CREATE TABLE app_products (
            flower TEXT PRIMARY KEY, cost_per_meter REAL, current_stock REAL, active INTEGER,
            roll_length_meters REAL, replenishment_days INTEGER)"""))
        connection.execute(text("""CREATE TABLE app_stock_events (
            id INTEGER PRIMARY KEY, flower TEXT, effective_date TEXT, event_type TEXT,
            change_qty REAL, before_stock REAL, after_stock REAL)"""))
        connection.execute(text("""CREATE TABLE app_orders (
            flower TEXT, legacy INTEGER, inventory_date TEXT,
            baseline_stock_effect_meters REAL)"""))
        connection.execute(text("INSERT INTO app_products VALUES ('花型A', 6, :stock, 1, 45, 1)"),
                           {"stock": current_stock})
    return engine


def test_historical_inventory_uses_matching_sales_window_and_legacy_baseline_sales(monkeypatch):
    engine = _inventory_listing_engine()
    monkeypatch.setattr("app.services.inventory_service.load_settings", lambda: {
        "inventory_sales_window_days": 7, "procurement_target_days": 14,
        "procurement_batch_capacity_meters": 1350,
    })
    with engine.begin() as connection:
        connection.execute(text("""INSERT INTO app_stock_events VALUES
            (1, '花型A', '2026-10-02', '订单出库', -2, 20, 18),
            (2, '花型A', '2026-10-03', '退款回补', 0.5, 18, 18.5)"""))
        connection.execute(text("""INSERT INTO app_orders VALUES
            ('花型A', 1, '2026-10-08', 1)"""))

    inventory = list_inventory(engine, date(2026, 10, 8))[0]
    recommendation = get_recommendations(engine, date(2026, 10, 8))["items"][0]

    assert inventory["recent_sales"] == 2.5
    assert inventory["recent_sales"] == recommendation["recent_sales"]


def test_inventory_current_stock_on_count_day_is_the_counted_anchor(monkeypatch):
    engine = _inventory_listing_engine(current_stock=85)
    monkeypatch.setattr("app.services.inventory_service.load_settings", lambda: {
        "inventory_sales_window_days": 7,
    })
    with engine.begin() as connection:
        connection.execute(text("""INSERT INTO app_stock_events VALUES
            (1, '花型A', '2026-10-01', '期初库存', 100, 0, 100),
            (2, '花型A', '2026-10-08', '订单出库', -20, 100, 80),
            (3, '花型A', '2026-10-08', '盘点', 5, 80, 85)"""))

    inventory = list_inventory(engine, date(2026, 10, 8))[0]

    assert inventory["current_stock"] == 85
    assert inventory["theoretical_stock"] == 80
    assert inventory["counted_stock"] == 85
    assert inventory["inventory_difference"] == -5
