import pytest
from sqlalchemy import create_engine, inspect, text

from app.core.schema import (INDEX_MIGRATIONS, _backfill_legacy_keys, _ensure_table_indexes,
                             _set_default_replenishment_days_once)


def test_missing_indexes_are_created_and_migration_is_idempotent():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("""CREATE TABLE app_orders (
            id INTEGER PRIMARY KEY, platform INTEGER, order_no TEXT, line_key TEXT,
            order_date TEXT, flower TEXT)"""))
        connection.execute(text("INSERT INTO app_orders VALUES (1, 0, 'A', 'line-a', '2026-10-01', '花型A')"))
        definitions = INDEX_MIGRATIONS["app_orders"]
        _ensure_table_indexes(connection, "app_orders", definitions)
        _ensure_table_indexes(connection, "app_orders", definitions)

    indexes = {index["name"] for index in inspect(engine).get_indexes("app_orders")}
    assert {"uq_app_order_line", "idx_app_order_date", "idx_app_order_flower"}.issubset(indexes)


def test_unique_index_migration_refuses_to_hide_duplicate_order_lines():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("""CREATE TABLE app_orders (
            id INTEGER PRIMARY KEY, platform INTEGER, order_no TEXT, line_key TEXT,
            order_date TEXT, flower TEXT)"""))
        connection.execute(text("""INSERT INTO app_orders VALUES
            (1, 0, 'A', 'same-line', '2026-10-01', '花型A'),
            (2, 0, 'A', 'same-line', '2026-10-01', '花型A')"""))

        with pytest.raises(RuntimeError, match="存在重复键"):
            _ensure_table_indexes(connection, "app_orders", INDEX_MIGRATIONS["app_orders"])


def test_old_empty_idempotency_keys_receive_stable_values():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("""CREATE TABLE app_orders (
            id INTEGER PRIMARY KEY, line_key TEXT, merchant_code_spec TEXT, product_id TEXT,
            product_spec TEXT, product TEXT)"""))
        connection.execute(text("INSERT INTO app_orders VALUES (7, '', NULL, 'sku-1', '1米', '花型A')"))
        connection.execute(text("""CREATE TABLE app_stock_events (
            id INTEGER PRIMARY KEY, movement_key TEXT)"""))
        connection.execute(text("INSERT INTO app_stock_events VALUES (9, '')"))

        _backfill_legacy_keys(connection)
        first_order_key = connection.execute(text("SELECT line_key FROM app_orders WHERE id=7")).scalar_one()
        first_event_key = connection.execute(text("SELECT movement_key FROM app_stock_events WHERE id=9")).scalar_one()
        _backfill_legacy_keys(connection)
        assert connection.execute(text("SELECT line_key FROM app_orders WHERE id=7")).scalar_one() == first_order_key
        assert connection.execute(text("SELECT movement_key FROM app_stock_events WHERE id=9")).scalar_one() == first_event_key
        assert first_order_key
        assert first_event_key == "legacy:stock-event:9"


def test_existing_replenishment_days_are_reset_to_one_only_once():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE app_meta (meta_key TEXT PRIMARY KEY, meta_value TEXT NOT NULL)"))
        connection.execute(text("CREATE TABLE app_products (flower TEXT PRIMARY KEY, replenishment_days INTEGER)"))
        connection.execute(text("INSERT INTO app_products VALUES ('花型A', 4), ('花型B', 2)"))

        _set_default_replenishment_days_once(connection)
        connection.execute(text("UPDATE app_products SET replenishment_days=3 WHERE flower='花型A'"))
        _set_default_replenishment_days_once(connection)

        values = dict(connection.execute(text(
            "SELECT flower, replenishment_days FROM app_products"
        )).all())

    assert values == {"花型A": 3, "花型B": 1}
