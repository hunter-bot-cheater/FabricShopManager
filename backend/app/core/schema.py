from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pandas as pd
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Engine

from app.domain.order_rules import is_cancelled, is_refunded, is_shipped, line_key, match_flower, order_dates
from app.domain.inventory_rules import order_meters


DDL = (
    """CREATE TABLE IF NOT EXISTS app_meta (
        meta_key VARCHAR(80) PRIMARY KEY, meta_value TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS app_products (
        flower VARCHAR(100) PRIMARY KEY, cost_per_meter DECIMAL(12,4) NOT NULL DEFAULT 0,
        current_stock DECIMAL(12,2) NOT NULL DEFAULT 0, active TINYINT(1) NOT NULL DEFAULT 1,
        roll_length_meters DECIMAL(12,2) NOT NULL DEFAULT 45, replenishment_days INT NOT NULL DEFAULT 1,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS app_orders (
        id BIGINT AUTO_INCREMENT PRIMARY KEY, platform TINYINT NOT NULL,
        order_no VARCHAR(100) NOT NULL, line_key VARCHAR(64) NOT NULL,
        parent_order_no VARCHAR(100), product VARCHAR(255), product_spec TEXT,
        product_id VARCHAR(100), merchant_code_spec VARCHAR(100), merchant_code_product VARCHAR(100),
        merchant_remark VARCHAR(255), express_company VARCHAR(100), order_status VARCHAR(100),
        after_sale_status VARCHAR(150), product_quantity DECIMAL(12,2) NOT NULL DEFAULT 1,
        merchant_income DECIMAL(12,2) NOT NULL DEFAULT 0, postage DECIMAL(12,2) NOT NULL DEFAULT 0,
        product_total DECIMAL(12,2) NOT NULL DEFAULT 0, user_payment DECIMAL(12,2) NOT NULL DEFAULT 0,
        delivery_time DATETIME NULL, receive_time DATETIME NULL, payment_time DATETIME NULL,
        order_time DATETIME NULL, express_no VARCHAR(100), flower VARCHAR(100),
        meters DECIMAL(12,2) NOT NULL DEFAULT 0, stock_effect_meters DECIMAL(12,2) NOT NULL DEFAULT 0,
        baseline_stock_effect_meters DECIMAL(12,2) NOT NULL DEFAULT 0,
        order_date DATE NULL, inventory_date DATE NULL, refunded TINYINT(1) NOT NULL DEFAULT 0,
        cancelled TINYINT(1) NOT NULL DEFAULT 0, legacy TINYINT(1) NOT NULL DEFAULT 0,
        version INT NOT NULL DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_app_order_line (platform, order_no, line_key),
        KEY idx_app_order_date (order_date), KEY idx_app_order_flower (flower)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS app_stock_events (
        id BIGINT AUTO_INCREMENT PRIMARY KEY, movement_key VARCHAR(220) NOT NULL UNIQUE,
        flower VARCHAR(100) NOT NULL, effective_date DATE NOT NULL, event_type VARCHAR(30) NOT NULL,
        change_qty DECIMAL(12,2) NOT NULL, before_stock DECIMAL(12,2) NOT NULL,
        after_stock DECIMAL(12,2) NOT NULL, reference VARCHAR(255),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, KEY idx_app_stock_date (effective_date),
        KEY idx_app_stock_flower (flower, effective_date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS app_imports (
        id BIGINT AUTO_INCREMENT PRIMARY KEY, file_name VARCHAR(255) NOT NULL,
        platform TINYINT NOT NULL, row_count INT NOT NULL, unmatched_count INT NOT NULL DEFAULT 0,
        imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS app_purchase_receipts (
        id BIGINT AUTO_INCREMENT PRIMARY KEY, flower VARCHAR(100) NOT NULL,
        received_date DATE NOT NULL, roll_count INT NOT NULL, roll_length_meters DECIMAL(12,2) NOT NULL,
        total_meters DECIMAL(12,2) NOT NULL, cost_per_meter DECIMAL(12,4) NOT NULL,
        total_cost DECIMAL(14,2) NOT NULL, reference VARCHAR(255), created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        KEY idx_app_purchase_date (received_date), KEY idx_app_purchase_flower (flower, received_date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS app_ignored_unmatched (
        order_id BIGINT PRIMARY KEY, ignored_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        KEY idx_app_ignored_at (ignored_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS app_flower_aliases (
        alias_name VARCHAR(100) PRIMARY KEY, flower VARCHAR(100) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, KEY idx_app_alias_flower (flower)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
)

MIGRATIONS = {
    "app_meta": {"meta_value": "TEXT NOT NULL DEFAULT ''", "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"},
    "app_products": {
        "cost_per_meter": "DECIMAL(12,4) NOT NULL DEFAULT 0", "current_stock": "DECIMAL(12,2) NOT NULL DEFAULT 0",
        "active": "TINYINT(1) NOT NULL DEFAULT 1", "roll_length_meters": "DECIMAL(12,2) NOT NULL DEFAULT 45",
        "replenishment_days": "INT NOT NULL DEFAULT 1", "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
    },
    "app_orders": {
        "platform": "TINYINT NOT NULL DEFAULT 0", "order_no": "VARCHAR(100) NOT NULL DEFAULT ''",
        "line_key": "VARCHAR(64) NOT NULL DEFAULT ''", "parent_order_no": "VARCHAR(100) NULL",
        "product": "VARCHAR(255) NULL", "product_spec": "TEXT NULL", "product_id": "VARCHAR(100) NULL",
        "merchant_code_spec": "VARCHAR(100) NULL", "merchant_code_product": "VARCHAR(100) NULL",
        "merchant_remark": "VARCHAR(255) NULL", "express_company": "VARCHAR(100) NULL",
        "order_status": "VARCHAR(100) NOT NULL DEFAULT ''",
        "after_sale_status": "VARCHAR(150) NOT NULL DEFAULT ''", "product_quantity": "DECIMAL(12,2) NOT NULL DEFAULT 1",
        "merchant_income": "DECIMAL(12,2) NOT NULL DEFAULT 0", "postage": "DECIMAL(12,2) NOT NULL DEFAULT 0",
        "product_total": "DECIMAL(12,2) NOT NULL DEFAULT 0", "user_payment": "DECIMAL(12,2) NOT NULL DEFAULT 0",
        "delivery_time": "DATETIME NULL", "receive_time": "DATETIME NULL", "payment_time": "DATETIME NULL",
        "order_time": "DATETIME NULL", "express_no": "VARCHAR(100) NULL", "flower": "VARCHAR(100) NULL",
        "meters": "DECIMAL(12,2) NOT NULL DEFAULT 0", "stock_effect_meters": "DECIMAL(12,2) NOT NULL DEFAULT 0",
        "baseline_stock_effect_meters": "DECIMAL(12,2) NOT NULL DEFAULT 0", "order_date": "DATE NULL",
        "inventory_date": "DATE NULL", "refunded": "TINYINT(1) NOT NULL DEFAULT 0",
        "cancelled": "TINYINT(1) NOT NULL DEFAULT 0", "legacy": "TINYINT(1) NOT NULL DEFAULT 0",
        "version": "INT NOT NULL DEFAULT 1", "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
    },
    "app_stock_events": {
        "movement_key": "VARCHAR(220) NOT NULL DEFAULT ''", "flower": "VARCHAR(100) NOT NULL DEFAULT ''",
        "effective_date": "DATE NULL", "event_type": "VARCHAR(30) NOT NULL DEFAULT ''",
        "change_qty": "DECIMAL(12,2) NOT NULL DEFAULT 0", "before_stock": "DECIMAL(12,2) NOT NULL DEFAULT 0",
        "after_stock": "DECIMAL(12,2) NOT NULL DEFAULT 0", "reference": "VARCHAR(255) NULL",
        "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    },
    "app_imports": {
        "file_name": "VARCHAR(255) NOT NULL DEFAULT ''", "platform": "TINYINT NOT NULL DEFAULT 0",
        "row_count": "INT NOT NULL DEFAULT 0", "unmatched_count": "INT NOT NULL DEFAULT 0",
        "imported_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    },
    "app_purchase_receipts": {
        "flower": "VARCHAR(100) NOT NULL DEFAULT ''", "received_date": "DATE NULL",
        "roll_count": "INT NOT NULL DEFAULT 1", "roll_length_meters": "DECIMAL(12,2) NOT NULL DEFAULT 45",
        "total_meters": "DECIMAL(12,2) NOT NULL DEFAULT 0", "cost_per_meter": "DECIMAL(12,4) NOT NULL DEFAULT 0",
        "total_cost": "DECIMAL(14,2) NOT NULL DEFAULT 0", "reference": "VARCHAR(255) NULL",
        "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    },
    "app_ignored_unmatched": {"order_id": "BIGINT NOT NULL DEFAULT 0", "ignored_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"},
    "app_flower_aliases": {"alias_name": "VARCHAR(100) NOT NULL DEFAULT ''", "flower": "VARCHAR(100) NOT NULL DEFAULT ''",
                           "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"},
}


def ensure_schema(engine: Engine) -> None:
    with engine.begin() as connection:
        for statement in DDL:
            connection.execute(text(statement))
        inspector = inspect(connection)
        for table, columns in MIGRATIONS.items():
            present = {column["name"] for column in inspector.get_columns(table)}
            for name, definition in columns.items():
                if name not in present:
                    connection.execute(text(f"ALTER TABLE `{table}` ADD COLUMN `{name}` {definition}"))
        connection.execute(text("UPDATE app_products SET replenishment_days=1 WHERE replenishment_days<1"))


def _value(row: dict, name: str, default=None):
    value = row.get(name, default)
    if value is None or pd.isna(value):
        return default
    return value


def _legacy_products(connection: Connection, tables: set[str]) -> dict[str, dict]:
    products: dict[str, dict] = {}
    if "product_cost" not in tables:
        return products
    columns = {column["name"] for column in inspect(connection).get_columns("product_cost")}
    if not {"flower", "cost_per_meter"}.issubset(columns):
        return products
    active_clause = " WHERE is_deleted = 0" if "is_deleted" in columns else ""
    for row in connection.execute(text(
        f"SELECT flower, cost_per_meter FROM product_cost{active_clause}"
    )).mappings():
        flower = str(row["flower"] or "").strip()
        if flower:
            products[flower] = {"cost": float(row["cost_per_meter"] or 0), "stock": 0.0}
    if "inventory" in tables:
        inventory_columns = {column["name"] for column in inspect(connection).get_columns("inventory")}
        fields = ["flower", "current_stock"]
        if "supplier_lead_time" in inventory_columns:
            fields.append("supplier_lead_time")
        sql = "SELECT " + ", ".join(f"`{field}`" for field in fields) + " FROM inventory"
        for row in connection.execute(text(sql)).mappings():
            flower = str(row["flower"] or "").strip()
            if flower:
                product = products.setdefault(flower, {"cost": 0.0, "stock": 0.0, "lead_days": 1})
                product["stock"] = float(row["current_stock"] or 0)
                if row.get("supplier_lead_time") is not None:
                    product["lead_days"] = max(1, int(row["supplier_lead_time"]))
    return products


def initialize_legacy_baseline(engine: Engine) -> dict:
    """Copy current inventory and order state into app_* tables without changing legacy tables."""
    ensure_schema(engine)
    with engine.begin() as connection:
        marker = connection.execute(text(
            "SELECT meta_value FROM app_meta WHERE meta_key='legacy_baseline_v1'"
        )).scalar()
        if marker:
            return {"already_initialized": True, "products": 0, "orders": 0}

        tables = set(inspect(connection).get_table_names())
        products = _legacy_products(connection, tables)
        for flower, product in products.items():
            connection.execute(text("""INSERT IGNORE INTO app_products
                (flower, cost_per_meter, current_stock, active, replenishment_days)
                VALUES (:flower, :cost, :stock, 1, :lead_days)"""),
                {"flower": flower, **product, "lead_days": product.get("lead_days", 1)})
            if product["stock"]:
                connection.execute(text("""INSERT IGNORE INTO app_stock_events
                    (movement_key, flower, effective_date, event_type, change_qty,
                     before_stock, after_stock, reference)
                    VALUES (:key, :flower, :today, '期初库存', :stock, 0, :stock, '旧系统当前库存基线')"""),
                    {"key": f"baseline:{flower}", "flower": flower, "today": date.today(), "stock": product["stock"]})

        order_count = 0
        if "data2026" in tables:
            columns = {column["name"] for column in inspect(connection).get_columns("data2026")}
            fields = ["platform", "parent_order_no", "product", "order_no", "order_status",
                      "product_total", "postage", "user_payment", "merchant_income", "product_quantity",
                      "delivery_time", "receive_time", "product_id", "product_spec", "merchant_code_spec",
                      "merchant_remark", "after_sale_status", "express_no", "order_time", "payment_time"]
            selected = [field for field in fields if field in columns]
            if "order_no" in selected:
                source_rows = connection.execute(text(
                    "SELECT " + ", ".join(f"`{field}`" for field in selected) + " FROM data2026"
                )).mappings().all()
                known = set(products)
                for source in source_rows:
                    row = dict(source)
                    row.setdefault("platform", 0)
                    row["order_no"] = str(row.get("order_no") or "").strip()
                    if not row["order_no"]:
                        continue
                    row["line_key"] = line_key(row)
                    row["product"] = str(_value(row, "product", "") or "")
                    row["product_spec"] = str(_value(row, "product_spec", "") or "")
                    quantity = float(_value(row, "product_quantity", 1) or 1)
                    unit = 0.0
                    from app.domain.order_rules import extract_meter
                    unit = extract_meter(row["product_spec"])
                    meters = order_meters(unit, quantity) if unit > 0 else 0.0
                    flower = match_flower(row["product"], row["product_spec"], known)
                    refunded, cancelled = is_refunded(row), is_cancelled(row)
                    shipped = is_shipped(row) and not refunded and not cancelled
                    business_date, inventory_date = order_dates(row, int(row.get("platform") or 0))
                    values = {
                        "platform": int(row.get("platform") or 0), "order_no": row["order_no"],
                        "line_key": row["line_key"], "parent_order_no": _value(row, "parent_order_no"),
                        "product": row["product"], "product_spec": row["product_spec"],
                        "product_id": _value(row, "product_id"), "merchant_code_spec": _value(row, "merchant_code_spec"),
                        "order_status": _value(row, "order_status", ""), "after_sale_status": _value(row, "after_sale_status", ""),
                        "product_quantity": quantity, "merchant_income": float(_value(row, "merchant_income", 0) or 0),
                        "postage": float(_value(row, "postage", 0) or 0), "product_total": float(_value(row, "product_total", 0) or 0),
                        "user_payment": float(_value(row, "user_payment", 0) or 0), "delivery_time": _value(row, "delivery_time"),
                        "receive_time": _value(row, "receive_time"), "payment_time": _value(row, "payment_time"),
                        "order_time": _value(row, "order_time"), "express_no": _value(row, "express_no"),
                        "flower": flower, "meters": meters if flower else 0,
                        "effect": meters if flower and shipped else 0, "order_date": business_date,
                        "inventory_date": inventory_date, "refunded": int(refunded), "cancelled": int(cancelled),
                    }
                    connection.execute(text("""INSERT IGNORE INTO app_orders
                        (platform, order_no, line_key, parent_order_no, product, product_spec, product_id,
                         merchant_code_spec, order_status, after_sale_status, product_quantity, merchant_income,
                         postage, product_total, user_payment, delivery_time, receive_time, payment_time, order_time,
                         express_no, flower, meters, stock_effect_meters, baseline_stock_effect_meters, order_date, inventory_date, refunded,
                         cancelled, legacy)
                        VALUES (:platform, :order_no, :line_key, :parent_order_no, :product, :product_spec,
                         :product_id, :merchant_code_spec, :order_status, :after_sale_status, :product_quantity,
                         :merchant_income, :postage, :product_total, :user_payment, :delivery_time, :receive_time,
                         :payment_time, :order_time, :express_no, :flower, :meters, :effect, :effect, :order_date,
                         :inventory_date, :refunded, :cancelled, 1)"""), values)
                    order_count += 1

        connection.execute(text("""INSERT INTO app_meta (meta_key, meta_value)
            VALUES ('legacy_baseline_v1', :value) ON DUPLICATE KEY UPDATE meta_value=VALUES(meta_value)"""),
            {"value": datetime.now().isoformat(timespec="seconds")})
        return {"already_initialized": False, "products": len(products), "orders": order_count}
