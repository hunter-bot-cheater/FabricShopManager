from datetime import date

from sqlalchemy import create_engine, text

from app.services.inventory_service import _stock_at_date, rebuild_product_stock


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
