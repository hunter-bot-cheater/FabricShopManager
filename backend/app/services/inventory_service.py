from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.settings import load_settings
from app.domain.procurement_rules import rank_restock_dates


def _as_date(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def _event_order(event: dict) -> tuple:
    # A count is the end-of-day anchor. Later-entered same-day movements must
    # not silently change the physical count for that date.
    return (_as_date(event["effective_date"]), event["event_type"] == "盘点", int(event["id"]))


def _stock_baseline(current_stock: float, events: list[dict]) -> float:
    return round(current_stock - sum(float(event["change_qty"] or 0) for event in events), 2)


def _stock_at_date(baseline: float, events: list[dict], as_of: date) -> dict:
    stock = baseline
    theoretical = None
    counted = None
    for event in sorted(events, key=_event_order):
        event_date = _as_date(event["effective_date"])
        if event_date > as_of:
            break
        if event_date == as_of and event["event_type"] == "盘点":
            theoretical = stock if theoretical is None else theoretical
            counted = float(event["after_stock"] or 0)
            stock = counted
        else:
            stock = round(stock + float(event["change_qty"] or 0), 2)
    return {"stock": stock, "theoretical": theoretical if counted is not None else stock,
            "counted": counted}


def rebuild_product_stock(connection, flower: str) -> float:
    product = connection.execute(text(
        "SELECT current_stock FROM app_products WHERE flower=:flower FOR UPDATE"
    ), {"flower": flower}).mappings().first()
    if not product:
        return 0.0
    events = [dict(row) for row in connection.execute(text("""SELECT id, effective_date, event_type,
        change_qty, before_stock, after_stock FROM app_stock_events WHERE flower=:flower"""),
        {"flower": flower}).mappings().all()]
    stock = _stock_baseline(float(product["current_stock"] or 0), events)
    anchor_updates = []
    movement_updates = []

    def changed(old, new):
        return old is None or round(float(old), 2) != round(float(new), 2)

    for event in sorted(events, key=_event_order):
        before = stock
        if event["event_type"] == "盘点":
            after = round(float(event["after_stock"] or 0), 2)
            change = round(after - before, 2)
            if changed(event["before_stock"], before) or changed(event["change_qty"], change):
                anchor_updates.append({"before": before, "change": change, "id": event["id"]})
        else:
            change = float(event["change_qty"] or 0)
            after = round(before + change, 2)
            if changed(event["before_stock"], before) or changed(event["after_stock"], after):
                movement_updates.append({"before": before, "after": after, "id": event["id"]})
        stock = after
    if anchor_updates:
        connection.execute(text("""UPDATE app_stock_events SET before_stock=:before,
            change_qty=:change WHERE id=:id"""), anchor_updates)
    if movement_updates:
        connection.execute(text("""UPDATE app_stock_events SET before_stock=:before,
            after_stock=:after WHERE id=:id"""), movement_updates)
    connection.execute(text("UPDATE app_products SET current_stock=:stock WHERE flower=:flower"),
                       {"stock": stock, "flower": flower})
    return stock


def list_inventory(engine: Engine, as_of: date | None = None) -> list[dict]:
    as_of = as_of or date.today()
    settings = load_settings()
    days = int(settings["inventory_sales_window_days"])
    start = as_of - timedelta(days=days - 1)
    with engine.connect() as connection:
        rows = connection.execute(text("""SELECT p.flower, p.cost_per_meter, p.current_stock, p.active,
            p.roll_length_meters, p.replenishment_days,
            COALESCE(SUM(CASE WHEN e.effective_date BETWEEN :start AND :as_of
                AND e.event_type IN ('订单出库','退款回补') THEN -e.change_qty ELSE 0 END), 0) AS recent_sales
            FROM app_products p LEFT JOIN app_stock_events e ON e.flower=p.flower
            WHERE p.active=1 GROUP BY p.flower, p.cost_per_meter, p.current_stock, p.active,
            p.roll_length_meters, p.replenishment_days ORDER BY p.flower"""),
            {"start": start, "as_of": as_of}).mappings().all()
        legacy_sales = connection.execute(text("""SELECT flower,
            SUM(baseline_stock_effect_meters) AS recent_sales FROM app_orders
            WHERE legacy=1 AND inventory_date BETWEEN :start AND :as_of GROUP BY flower"""),
            {"start": start, "as_of": as_of}).mappings().all()
        all_events = connection.execute(text("""SELECT id, flower, effective_date, event_type,
            change_qty, after_stock FROM app_stock_events ORDER BY effective_date, id""")).mappings().all()
    recent_sales_by_flower = {row["flower"]: float(row["recent_sales"] or 0) for row in rows}
    for source in legacy_sales:
        recent_sales_by_flower[source["flower"]] = (
            recent_sales_by_flower.get(source["flower"], 0) + float(source["recent_sales"] or 0)
        )
    events_by_flower: dict[str, list[dict]] = {}
    for event in all_events:
        events_by_flower.setdefault(event["flower"], []).append(dict(event))
    result = []
    for source in rows:
        row = dict(source)
        flower_events = events_by_flower.get(row["flower"], [])
        state = _stock_at_date(_stock_baseline(float(row["current_stock"] or 0), flower_events),
                               flower_events, as_of)
        row["current_stock"] = state["stock"]
        row["counted_stock"] = state["counted"]
        row["theoretical_stock"] = state["theoretical"]
        row["inventory_difference"] = (round(state["theoretical"] - state["counted"], 2)
                                       if state["counted"] is not None else None)
        row["as_of_date"] = as_of.isoformat()
        row["recent_sales"] = round(max(0.0, recent_sales_by_flower.get(row["flower"], 0.0)), 2)
        row["reorder_level"] = round(float(row["recent_sales"] or 0) / days * (int(row["replenishment_days"] or 1) + 1), 2)
        row["low_stock"] = float(row["current_stock"] or 0) < row["reorder_level"]
        result.append(row)
    return result


def list_events(engine: Engine, limit: int = 20, offset: int = 0,
                sort_by: str = "created_at", sort_order: str = "desc", search: str = "") -> dict:
    columns = {"effective_date": "effective_date", "flower": "flower", "event_type": "event_type",
               "change_qty": "change_qty", "before_stock": "before_stock", "after_stock": "after_stock",
               "reference": "reference", "created_at": "created_at"}
    sort_column = columns.get(sort_by, "created_at")
    direction = "ASC" if sort_order.lower() == "asc" else "DESC"
    limit, offset = min(max(limit, 1), 100), max(offset, 0)
    query = search.strip()
    with engine.connect() as connection:
        total = connection.execute(text("""SELECT COUNT(*) FROM app_stock_events
            WHERE :search='' OR flower LIKE :pattern OR reference LIKE :pattern OR event_type LIKE :pattern"""),
            {"search": query, "pattern": f"%{query}%"}).scalar_one()
        rows = connection.execute(text(f"""SELECT id, flower, effective_date, event_type, change_qty,
            before_stock, after_stock, reference, created_at FROM app_stock_events
            WHERE :search='' OR flower LIKE :pattern OR reference LIKE :pattern OR event_type LIKE :pattern
            ORDER BY {sort_column} {direction}, id DESC LIMIT :limit OFFSET :offset"""),
            {"search": query, "pattern": f"%{query}%", "limit": limit, "offset": offset}).mappings().all()
    return {"items": [dict(row) for row in rows], "total": int(total), "limit": limit, "offset": offset}


def record_movement(engine: Engine, flower: str, operation: str, quantity: float,
                    effective_date: date, reference: str = "") -> dict:
    if quantity < 0:
        raise ValueError("数量应填写正数")
    if operation not in {"主动出库", "盘点"}:
        raise ValueError("不支持的库存操作")
    with engine.begin() as connection:
        product = connection.execute(text(
            "SELECT current_stock FROM app_products WHERE flower=:flower AND active=1 FOR UPDATE"
        ), {"flower": flower}).mappings().first()
        if not product:
            raise ValueError("找不到该花型，请先在商品成本中添加")
        current = float(product["current_stock"] or 0)
        events = [dict(row) for row in connection.execute(text("""SELECT id, effective_date,
            event_type, change_qty, after_stock FROM app_stock_events WHERE flower=:flower"""),
            {"flower": flower}).mappings().all()]
        baseline = _stock_baseline(current, events)
        before = float(_stock_at_date(baseline, events, effective_date)["theoretical"])
        change = round(quantity - before, 2) if operation == "盘点" else -quantity
        after = round(before + change, 2)
        connection.execute(text("UPDATE app_products SET current_stock=:stock WHERE flower=:flower"),
                           {"stock": round(current + change, 2), "flower": flower})
        connection.execute(text("""INSERT INTO app_stock_events
            (movement_key, flower, effective_date, event_type, change_qty, before_stock, after_stock, reference)
            VALUES (:key, :flower, :effective_date, :kind, :change, :before, :after, :reference)"""),
            {"key": f"manual:{uuid.uuid4().hex}", "flower": flower, "effective_date": effective_date,
             "kind": operation, "change": change, "before": before, "after": after,
             "reference": reference[:255]})
        current_after = rebuild_product_stock(connection, flower)
    return {"flower": flower, "operation": operation, "change": round(change, 2),
            "before_stock": before, "after_stock": after, "current_stock": current_after,
            "warning": "操作后库存为负数，请核对" if current_after < 0 else None}


def receive_rolls(engine: Engine, flower: str, roll_count: int, received_date: date,
                  reference: str = "") -> dict:
    if roll_count < 1:
        raise ValueError("入库卷数至少为 1")
    with engine.begin() as connection:
        product = connection.execute(text("""SELECT current_stock, roll_length_meters
            FROM app_products WHERE flower=:flower AND active=1 FOR UPDATE"""),
            {"flower": flower}).mappings().first()
        if not product:
            raise ValueError("找不到该花型，请先在商品成本中添加")
        roll_length = float(product["roll_length_meters"] or 0)
        if roll_length <= 0:
            raise ValueError("请先在商品成本中设置该花型每卷米数")
        meters = round(roll_count * roll_length, 2)
        before = float(product["current_stock"] or 0)
        after = round(before + meters, 2)
        existing_events = [dict(row) for row in connection.execute(text("""SELECT id,
            effective_date, event_type, change_qty, after_stock FROM app_stock_events WHERE flower=:flower"""),
            {"flower": flower}).mappings().all()]
        baseline = _stock_baseline(before, existing_events)
        day_before = float(_stock_at_date(baseline, existing_events, received_date)["theoretical"])
        key = f"purchase:{uuid.uuid4().hex}"
        receipt_note = f"{roll_count} 卷 × {roll_length:g} 米"
        connection.execute(text("UPDATE app_products SET current_stock=:stock WHERE flower=:flower"),
                           {"stock": after, "flower": flower})
        connection.execute(text("""INSERT INTO app_stock_events
            (movement_key, flower, effective_date, event_type, change_qty, before_stock, after_stock, reference)
            VALUES (:key, :flower, :received_date, '采购入库', :meters, :before, :after, :reference)"""),
            {"key": key, "flower": flower, "received_date": received_date, "meters": meters,
             "before": day_before, "after": round(day_before + meters, 2),
             "reference": (receipt_note + (f" · {reference}" if reference else ""))[:255]})
        connection.execute(text("""INSERT INTO app_purchase_receipts
            (flower, received_date, roll_count, roll_length_meters, total_meters,
             cost_per_meter, total_cost, reference)
            VALUES (:flower, :received_date, :roll_count, :roll_length, :meters,
                    0, 0, :reference)"""),
            {"flower": flower, "received_date": received_date, "roll_count": roll_count,
             "roll_length": roll_length, "meters": meters, "reference": reference[:255]})
        after = rebuild_product_stock(connection, flower)
    return {"flower": flower, "roll_count": roll_count, "meters": meters,
            "before_stock": before, "after_stock": after}


def list_purchases(engine: Engine, limit: int = 20, offset: int = 0,
                   sort_by: str = "received_date", sort_order: str = "desc", search: str = "") -> dict:
    columns = {"received_date": "received_date", "flower": "flower", "roll_count": "roll_count",
               "roll_length_meters": "roll_length_meters", "total_meters": "total_meters",
               "cost_per_meter": "cost_per_meter", "total_cost": "total_cost",
               "reference": "reference", "created_at": "created_at"}
    sort_column = columns.get(sort_by, "received_date")
    direction = "ASC" if sort_order.lower() == "asc" else "DESC"
    limit, offset = min(max(limit, 1), 100), max(offset, 0)
    query = search.strip()
    with engine.connect() as connection:
        total = connection.execute(text("""SELECT COUNT(*) FROM app_purchase_receipts
            WHERE :search='' OR flower LIKE :pattern OR reference LIKE :pattern"""),
            {"search": query, "pattern": f"%{query}%"}).scalar_one()
        rows = connection.execute(text(f"""SELECT id, flower, received_date, roll_count,
            roll_length_meters, total_meters, cost_per_meter, total_cost, reference, created_at
            FROM app_purchase_receipts WHERE :search='' OR flower LIKE :pattern OR reference LIKE :pattern
            ORDER BY {sort_column} {direction}, id DESC LIMIT :limit OFFSET :offset"""),
            {"search": query, "pattern": f"%{query}%", "limit": limit, "offset": offset}).mappings().all()
    return {"items": [dict(row) for row in rows], "total": int(total), "limit": limit, "offset": offset}


def export_inventory(engine: Engine) -> Path:
    settings = load_settings()
    folder = Path(settings["output_inventory"])
    folder.mkdir(parents=True, exist_ok=True)
    with engine.connect() as connection:
        stock = connection.execute(text("""SELECT flower AS '花型', cost_per_meter AS '每米成本(元)',
            roll_length_meters AS '每卷米数', replenishment_days AS '预计到店天数',
            current_stock AS '当前库存(米)' FROM app_products WHERE active=1 ORDER BY flower""")).mappings().all()
        events = connection.execute(text("""SELECT effective_date AS '生效日期', flower AS '花型',
            event_type AS '操作类型', change_qty AS '变动米数', before_stock AS '变动前库存',
            after_stock AS '变动后库存', reference AS '备注', created_at AS '登记时间'
            FROM app_stock_events ORDER BY effective_date DESC, id DESC""")).mappings().all()
        purchases = connection.execute(text("""SELECT received_date AS '到店日期', flower AS '花型',
            roll_count AS '卷数', roll_length_meters AS '每卷米数', total_meters AS '入库米数',
            reference AS '备注'
            FROM app_purchase_receipts ORDER BY received_date DESC, id DESC""")).mappings().all()
    target = folder / f"库存明细_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    with pd.ExcelWriter(target, engine="openpyxl") as writer:
        for name, rows in (("当前库存", stock), ("库存流水", events), ("采购到货", purchases)):
            frame = pd.DataFrame([dict(row) for row in rows])
            frame.to_excel(writer, sheet_name=name, index=False)
            sheet = writer.book[name]
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
            for column in sheet.columns:
                width = min(max(max(len(str(cell.value or "")) for cell in column) + 2, 10), 36)
                sheet.column_dimensions[column[0].column_letter].width = width
    return target


def get_recommendations(engine: Engine, today: date | None = None) -> dict:
    today = today or date.today()
    settings = load_settings()
    sales_window_days = int(settings["inventory_sales_window_days"])
    start = today - timedelta(days=sales_window_days - 1)
    with engine.connect() as connection:
        products = connection.execute(text("""SELECT flower, cost_per_meter, current_stock,
            roll_length_meters, replenishment_days FROM app_products WHERE active=1""")).mappings().all()
        baseline = connection.execute(text("""SELECT flower, SUM(baseline_stock_effect_meters) AS meters
            FROM app_orders WHERE legacy=1 AND inventory_date BETWEEN :start AND :end
            GROUP BY flower"""), {"start": start, "end": today}).mappings().all()
        events = connection.execute(text("""SELECT flower, SUM(change_qty) AS change_qty
            FROM app_stock_events WHERE effective_date BETWEEN :start AND :end
            AND event_type IN ('订单出库','退款回补') GROUP BY flower"""),
            {"start": start, "end": today}).mappings().all()
    recent_meters = {row["flower"]: float(row["meters"] or 0) for row in baseline}
    for row in events:
        recent_meters[row["flower"]] = recent_meters.get(row["flower"], 0) - float(row["change_qty"] or 0)

    items = []
    for product in products:
        recent = max(0.0, recent_meters.get(product["flower"], 0))
        daily_use = recent / sales_window_days
        suggestion = rank_restock_dates(
            today=today, stock=float(product["current_stock"] or 0), daily_use=daily_use,
            roll_length=float(product["roll_length_meters"] or 0),
            cost_per_meter=float(product["cost_per_meter"] or 0),
            lead_days=int(product["replenishment_days"] or 1),
            target_days=int(settings["procurement_target_days"]),
            sales_window_days=sales_window_days,
        )
        items.append({"flower": product["flower"], "current_stock": float(product["current_stock"] or 0),
                      "cost_per_meter": float(product["cost_per_meter"] or 0),
                      "roll_length_meters": float(product["roll_length_meters"] or 0),
                      "replenishment_days": int(product["replenishment_days"] or 0),
                      "recent_sales": round(recent, 2), "sales_window_days": sales_window_days, **suggestion})
    items.sort(key=lambda item: (item.get("days_until_order", 9999), item["flower"]))
    return {"generated_on": today.isoformat(), "sales_window_days": sales_window_days,
            "target_coverage_days": int(settings["procurement_target_days"]), "items": items}

