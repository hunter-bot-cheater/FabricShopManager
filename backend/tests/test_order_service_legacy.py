from datetime import date

from sqlalchemy import create_engine, event, text

from app.domain.order_rules import line_key
from app.services import order_service
from app.services.order_service import commit_import, prepare_import


def _engine():
    engine = create_engine("sqlite://")
    event.listen(engine, "before_cursor_execute", lambda conn, cursor, statement, parameters, context, many:
                 (statement.replace(" FOR UPDATE", ""), parameters), retval=True)
    with engine.begin() as connection:
        connection.execute(text("""CREATE TABLE app_meta (meta_key TEXT PRIMARY KEY, meta_value TEXT)"""))
        connection.execute(text("INSERT INTO app_meta VALUES ('legacy_baseline_v1', '2026-10-08T20:10:06')"))
        connection.execute(text("""CREATE TABLE app_products (
            flower TEXT PRIMARY KEY, cost_per_meter REAL, current_stock REAL, active INTEGER)"""))
        connection.execute(text("INSERT INTO app_products VALUES ('城市条纹', 6, 100, 1)"))
        connection.execute(text("CREATE TABLE app_flower_aliases (alias_name TEXT, flower TEXT)"))
        connection.execute(text("""CREATE TABLE app_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, platform INTEGER, order_no TEXT, line_key TEXT,
            parent_order_no TEXT, product TEXT, product_spec TEXT, product_id TEXT,
            merchant_code_spec TEXT, merchant_code_product TEXT, merchant_remark TEXT,
            express_company TEXT, order_status TEXT, after_sale_status TEXT, product_quantity REAL,
            merchant_income REAL, postage REAL, product_total REAL, user_payment REAL,
            delivery_time TEXT, receive_time TEXT, payment_time TEXT, order_time TEXT,
            express_no TEXT, flower TEXT, meters REAL, stock_effect_meters REAL,
            baseline_stock_effect_meters REAL, order_date TEXT, inventory_date TEXT,
            refunded INTEGER, cancelled INTEGER, legacy INTEGER, version INTEGER)"""))
        connection.execute(text("""CREATE TABLE app_stock_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, movement_key TEXT UNIQUE, flower TEXT,
            effective_date DATE, event_type TEXT, change_qty REAL, before_stock REAL,
            after_stock REAL, reference TEXT)"""))
        connection.execute(text("CREATE TABLE app_ignored_unmatched (order_id INTEGER PRIMARY KEY)"))
        connection.execute(text("""CREATE TABLE app_imports (
            id INTEGER PRIMARY KEY AUTOINCREMENT, file_name TEXT, platform INTEGER,
            row_count INTEGER, unmatched_count INTEGER)"""))
    return engine


def _csv(status="已发货", after_sale="", code="NEW-CODE", order_time="2026-07-23 10:00:00",
         product_spec="城市条纹;一米"):
    return ("订单号,商品,商品规格,商品id,商家编码-规格维度,商品数量(件),订单状态,售后状态,订单成交时间\n"
            f"PDD-1,城市条纹,{product_spec},SKU-1,{code},2,{status},{after_sale},{order_time}\n"
            ).encode("utf-8-sig")


def _seed_legacy_order(connection, refunded=False):
    key = line_key({"product_id": "SKU-1", "product_spec": "城市条纹;一米"})
    connection.execute(text("""INSERT INTO app_orders (
        platform, order_no, line_key, product, product_spec, product_id,
        merchant_code_spec, order_status, after_sale_status, product_quantity,
        flower, meters, stock_effect_meters, baseline_stock_effect_meters,
        order_date, inventory_date, refunded, cancelled, legacy, version)
        VALUES (0, 'PDD-1', :key, '城市条纹', '城市条纹;一米', 'SKU-1', '',
        '已发货', '', 2, '城市条纹', 2, :effect, :baseline,
        '2026-07-23', '2026-07-23', :refunded, 0, 1, 1)"""),
        {"key": key, "effect": 0 if refunded else 2, "baseline": 0 if refunded else 2,
         "refunded": int(refunded)})


def test_import_preview_matches_existing_legacy_line_key_and_does_not_duplicate():
    engine = _engine()
    with engine.begin() as connection:
        _seed_legacy_order(connection)

    preview = prepare_import(engine, "pdd.csv", _csv(), platform=0)

    assert preview["counts"]["new"] == 0
    assert preview["counts"]["unchanged"] == 1
    assert preview["rows"][0]["original_line_key"] != preview["rows"][0]["row"]["line_key"]
    result = commit_import(engine, preview["token"])

    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM app_orders")).scalar_one() == 1
        assert connection.execute(text("SELECT current_stock FROM app_products WHERE flower='城市条纹'")).scalar_one() == 100
        assert connection.execute(text("SELECT COUNT(*) FROM app_stock_events")).scalar_one() == 0
        stored = connection.execute(text("SELECT line_key FROM app_orders")).scalar_one()
    assert stored == preview["rows"][0]["row"]["line_key"]
    assert result["stock_movements"] == 0


def test_first_import_of_prebaseline_order_seeds_baseline_without_replaying_sale():
    engine = _engine()

    preview = prepare_import(engine, "pdd.csv", _csv(), platform=0)
    result = commit_import(engine, preview["token"])

    with engine.connect() as connection:
        order = connection.execute(text("""SELECT legacy, baseline_stock_effect_meters,
            stock_effect_meters FROM app_orders""")).one()
        stock = connection.execute(text("SELECT current_stock FROM app_products WHERE flower='城市条纹'")).scalar_one()
        movement_count = connection.execute(text("SELECT COUNT(*) FROM app_stock_events")).scalar_one()
    assert result["stock_movements"] == 0
    assert order == (1, 2, 2)
    assert stock == 100
    assert movement_count == 0


def test_postbaseline_shipment_still_deducts_inventory():
    engine = _engine()

    preview = prepare_import(engine, "pdd.csv", _csv(order_time="2026-10-09 10:00:00"), platform=0)
    result = commit_import(engine, preview["token"])

    with engine.connect() as connection:
        stock = connection.execute(text("SELECT current_stock FROM app_products WHERE flower='城市条纹'")).scalar_one()
        movement = connection.execute(text("SELECT event_type, change_qty FROM app_stock_events")).one()
    assert result["stock_movements"] == 1
    assert stock == 98
    assert movement == ("订单出库", -2)


def test_batch_import_locks_existing_orders_once_and_rebuilds_stock_once_per_flower(monkeypatch):
    engine = _engine()
    header = _csv(order_time="2026-10-09 10:00:00").decode("utf-8-sig").splitlines()[0]
    rows = [header] + [
        f"PDD-{index},城市条纹,城市条纹;一米,SKU-{index},NEW-{index},2,已发货,,2026-10-09 10:00:00"
        for index in range(1, 4)
    ]
    preview = prepare_import(engine, "pdd.csv", ("\n".join(rows) + "\n").encode("utf-8-sig"), platform=0)
    rebuild_calls = []
    original_rebuild = order_service.rebuild_product_stock

    def count_rebuild(connection, flower):
        rebuild_calls.append(flower)
        return original_rebuild(connection, flower)

    monkeypatch.setattr(order_service, "rebuild_product_stock", count_rebuild)
    locked_order_queries = []

    def count_order_query(connection, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith("SELECT * FROM APP_ORDERS"):
            locked_order_queries.append(statement)

    from sqlalchemy import event
    event.listen(engine, "before_cursor_execute", count_order_query)
    result = commit_import(engine, preview["token"])
    event.remove(engine, "before_cursor_execute", count_order_query)
    repeated = prepare_import(engine, "pdd.csv", ("\n".join(rows) + "\n").encode("utf-8-sig"), platform=0)
    repeated_result = commit_import(engine, repeated["token"])

    with engine.connect() as connection:
        stock = connection.execute(text("SELECT current_stock FROM app_products WHERE flower='城市条纹'")).scalar_one()
        event_count = connection.execute(text("SELECT COUNT(*) FROM app_stock_events")).scalar_one()
        order_count = connection.execute(text("SELECT COUNT(*) FROM app_orders")).scalar_one()
    assert result["stock_movements"] == 3
    assert stock == 94
    assert event_count == 3
    assert order_count == 3
    assert len(locked_order_queries) == 1
    assert rebuild_calls == ["城市条纹"]
    assert repeated["counts"]["unchanged"] == 3
    assert repeated_result["stock_movements"] == 0


def test_legacy_shipped_to_refunded_transition_restocks_once_at_observation_date():
    engine = _engine()
    with engine.begin() as connection:
        _seed_legacy_order(connection)

    preview = prepare_import(engine, "pdd.csv", _csv(after_sale="退款成功"), platform=0)
    result = commit_import(engine, preview["token"])
    repeated = prepare_import(engine, "pdd.csv", _csv(after_sale="退款成功"), platform=0)
    second = commit_import(engine, repeated["token"])

    with engine.connect() as connection:
        stock = connection.execute(text("SELECT current_stock FROM app_products WHERE flower='城市条纹'")).scalar_one()
        events = connection.execute(text("SELECT effective_date, event_type, change_qty FROM app_stock_events")).all()
    assert result["stock_movements"] == 1
    assert second["stock_movements"] == 0
    assert stock == 102
    assert len(events) == 1
    assert str(events[0][0]) == date.today().isoformat()
    assert events[0][1:] == ("退款回补", 2)


def test_unknown_source_spec_clears_stale_legacy_meters_without_changing_baseline_stock():
    engine = _engine()
    with engine.begin() as connection:
        key = line_key({"product_id": "SKU-1", "product_spec": "城市条纹"})
        connection.execute(text("""INSERT INTO app_orders (
            platform, order_no, line_key, product, product_spec, product_id,
            order_status, product_quantity, flower, meters, stock_effect_meters,
            baseline_stock_effect_meters, order_date, inventory_date, refunded, cancelled, legacy, version)
            VALUES (0, 'PDD-1', :key, '城市条纹', '城市条纹', 'SKU-1', '已发货', 2,
            '城市条纹', 2, 2, 2, '2026-07-23', '2026-07-23', 0, 0, 1, 1)"""), {"key": key})

    preview = prepare_import(engine, "pdd.csv", _csv(product_spec="城市条纹"), platform=0)
    assert preview["counts"]["unmatched"] == 1
    assert preview["rows"][0]["unit_meters"] == 0
    assert preview["rows"][0]["flower"] is None
    result = commit_import(engine, preview["token"])

    with engine.connect() as connection:
        order = connection.execute(text("SELECT flower, meters, stock_effect_meters FROM app_orders")).one()
        stock = connection.execute(text("SELECT current_stock FROM app_products WHERE flower='城市条纹'")).scalar_one()
        movement_count = connection.execute(text("SELECT COUNT(*) FROM app_stock_events")).scalar_one()
    assert result["stock_movements"] == 0
    assert order == (None, 0, 0)
    assert stock == 100
    assert movement_count == 0
