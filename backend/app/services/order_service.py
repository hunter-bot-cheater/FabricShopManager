from __future__ import annotations

import uuid
from collections import Counter
from datetime import date, datetime
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Engine

from app.domain.order_rules import (
    PLATFORM_NAMES, extract_meter, is_cancelled, is_refunded, is_shipped, line_key,
    match_flower, order_dates, read_order_file,
)
from app.domain.inventory_rules import order_meters, stock_changes
from app.services.inventory_service import rebuild_product_stock


_previews: dict[str, dict[str, Any]] = {}


def _meters(row: dict) -> float:
    unit = extract_meter(row.get("product_spec"))
    if unit <= 0:
        return 0.0
    quantity = row.get("product_quantity")
    return order_meters(unit, 1.0 if quantity is None else float(quantity))


def _date_for_json(value):
    return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat() if value else None


def prepare_import(engine: Engine, filename: str, content: bytes, platform: int | None = None) -> dict:
    platform, rows = read_order_file(filename, content, platform)
    with engine.connect() as connection:
        products = connection.execute(text(
            "SELECT flower, cost_per_meter FROM app_products WHERE active=1 ORDER BY flower"
        )).mappings().all()
        names = {row["flower"] for row in products}
        aliases = {row["alias_name"]: row["flower"] for row in connection.execute(
            text("SELECT alias_name, flower FROM app_flower_aliases")).mappings()}
        order_numbers = list({row["order_no"] for row in rows})
        existing_by_key = {}
        existing_by_order = {}
        if order_numbers:
            query = text("""SELECT id, order_no, line_key, flower, stock_effect_meters,
                baseline_stock_effect_meters, refunded, cancelled, legacy, order_status, after_sale_status FROM app_orders
                WHERE platform=:platform AND order_no IN :order_numbers""").bindparams(
                bindparam("order_numbers", expanding=True)
            )
            for source in connection.execute(query, {"platform": platform, "order_numbers": order_numbers}).mappings():
                record = dict(source)
                key = (record["order_no"], record["line_key"])
                existing_by_key[key] = record
                existing_by_order.setdefault(record["order_no"], []).append(record)

    source_counts = Counter(row["order_no"] for row in rows)
    used_existing = set()

    token = uuid.uuid4().hex
    today = date.today()
    preview_rows = []
    counts = {"new": 0, "changed": 0, "unchanged": 0, "unmatched": 0, "refund": 0,
              "invalid_meters": 0, "excluded": 0}
    for row_index, row in enumerate(rows):
        suggested_flower = match_flower(row.get("product"), row.get("product_spec"), names, aliases)
        refunded, cancelled = is_refunded(row), is_cancelled(row)
        shipped = is_shipped(row) and not refunded and not cancelled
        meters = _meters(row)
        unit_meters = extract_meter(row.get("product_spec"))
        flower = suggested_flower if unit_meters > 0 else None
        effect = meters if flower and shipped else 0.0
        business_date, inventory_date = order_dates(row, platform)
        identity = (row["order_no"], row["line_key"])
        previous = existing_by_key.get(identity)
        if previous and identity in used_existing:
            previous = None
        matched_identity = identity
        if previous is None:
            legacy_identity = (row["order_no"], line_key({**row, "merchant_code_spec": None}))
            candidate = existing_by_key.get(legacy_identity)
            if candidate and legacy_identity not in used_existing:
                previous, matched_identity = candidate, legacy_identity
            else:
                candidates = [record for record in existing_by_order.get(row["order_no"], [])
                              if (record["order_no"], record["line_key"]) not in used_existing]
                if source_counts[row["order_no"]] == 1 and len(candidates) == 1:
                    previous = candidates[0]
                    matched_identity = (previous["order_no"], previous["line_key"])
        if previous:
            used_existing.add(matched_identity)
        state = ("退款成功" if refunded else "已取消" if cancelled else
                 "未匹配" if shipped and not flower else
                 "已发货" if shipped else "待发货/未成交")
        reasons = []
        if unit_meters <= 0:
            reasons.append("规格未识别出米数")
            counts["invalid_meters"] += 1
        if not suggested_flower:
            reasons.append("花型未匹配")
        if not shipped and not refunded and not cancelled:
            counts["excluded"] += 1
        if not suggested_flower or unit_meters <= 0:
            counts["unmatched"] += 1
        if refunded:
            counts["refund"] += 1
        if previous is None:
            counts["new"] += 1
            change = "新增"
        elif (float(previous["stock_effect_meters"] or 0) == effect
              and bool(previous["refunded"]) == refunded and bool(previous["cancelled"]) == cancelled
              and previous["flower"] == flower):
            counts["unchanged"] += 1
            change = "无变化"
        else:
            counts["changed"] += 1
            change = "状态/商品变化"
        normalized = dict(row)
        for key in ("delivery_time", "receive_time", "payment_time", "order_time"):
            normalized[key] = _date_for_json(row.get(key))
        record = {
            "row_index": row_index, "original_order_no": previous["order_no"] if previous else row["order_no"],
            "original_line_key": previous["line_key"] if previous else row["line_key"],
            "row": normalized, "flower": flower,
            "suggested_flower": suggested_flower, "state": state, "meters": meters,
            "unit_meters": unit_meters,
            "needs_attention": bool(reasons), "attention_reason": "、".join(reasons),
            "edited_fields": {},
            "stock_effect_meters": effect, "order_date": business_date.isoformat() if business_date else None,
            "inventory_date": inventory_date.isoformat() if inventory_date else None,
            "change": change, "previous_stock_effect_meters": float(previous["stock_effect_meters"] or 0) if previous else 0,
            "previous": ({"stock_effect_meters": float(previous["stock_effect_meters"] or 0),
                          "refunded": bool(previous["refunded"]), "cancelled": bool(previous["cancelled"]),
                          "flower": previous["flower"], "legacy": bool(previous["legacy"]),
                          "baseline_stock_effect_meters": float(previous["baseline_stock_effect_meters"] or 0)}
                         if previous else None),
        }
        preview_rows.append(record)
    _previews[token] = {"filename": filename, "platform": platform, "rows": preview_rows,
                        "counts": counts, "created": datetime.now()}
    if len(_previews) > 20:
        oldest = sorted(_previews, key=lambda key: _previews[key]["created"])[0]
        del _previews[oldest]
    return {"token": token, "platform": platform, "platform_name": PLATFORM_NAMES[platform],
            "total": len(preview_rows), "counts": counts, "rows": preview_rows}


def _parse_datetime(value):
    if not value:
        return None
    return datetime.fromisoformat(value) if isinstance(value, str) else value


_EDITABLE_FIELDS = {
    "order_no", "parent_order_no", "product", "product_spec", "product_id",
    "merchant_code_spec", "merchant_code_product", "order_status", "after_sale_status",
    "product_quantity", "merchant_income", "postage", "product_total", "user_payment",
    "delivery_time", "receive_time", "payment_time", "order_time", "express_no",
    "express_company", "merchant_remark", "flower",
}
_TEXT_FIELDS = _EDITABLE_FIELDS - {
    "product_quantity", "merchant_income", "postage", "product_total", "user_payment",
    "delivery_time", "receive_time", "payment_time", "order_time", "flower",
}
_AMOUNT_FIELDS = {"product_quantity", "merchant_income", "postage", "product_total", "user_payment"}
_DATE_FIELDS = {"delivery_time", "receive_time", "payment_time", "order_time"}


def _apply_preview_edits(engine: Engine, preview: dict, edits: list[dict]) -> None:
    if not edits:
        return
    with engine.connect() as connection:
        names = set(connection.execute(text(
            "SELECT flower FROM app_products WHERE active=1"
        )).scalars())
        aliases = {row["alias_name"]: row["flower"] for row in connection.execute(
            text("SELECT alias_name, flower FROM app_flower_aliases")
        ).mappings()}

    rows = preview["rows"]
    for edit in edits:
        index = int(edit.get("row_index", -1))
        if index < 0 or index >= len(rows):
            raise ValueError("导入预览中的订单行已失效，请重新解析文件")
        fields = edit.get("fields") or {}
        unknown = set(fields) - _EDITABLE_FIELDS
        if unknown:
            raise ValueError("订单预览包含不支持修改的字段")
        item = rows[index]
        row = item["row"]
        selected_flower = fields.get("flower") if "flower" in fields else None
        for field, value in fields.items():
            if field == "flower":
                continue
            if field in _TEXT_FIELDS:
                row[field] = str(value or "").strip()
            elif field in _AMOUNT_FIELDS:
                try:
                    row[field] = float(value) if value not in (None, "") else 0.0
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"订单 {row.get('order_no')} 的数量/金额不是有效数字") from exc
            elif field in _DATE_FIELDS:
                try:
                    row[field] = _parse_datetime(value)
                except ValueError as exc:
                    raise ValueError(f"订单 {row.get('order_no')} 的日期格式无效") from exc
        row["order_no"] = str(row.get("order_no") or "").strip()
        if not row["order_no"]:
            raise ValueError("订单号不能为空")
        row["line_key"] = line_key(row)
        unit = extract_meter(row.get("product_spec"))
        item["unit_meters"] = unit
        item["meters"] = _meters(row)
        if selected_flower is not None:
            selected_flower = str(selected_flower).strip()
            if selected_flower and selected_flower not in names:
                selected_flower = aliases.get(selected_flower)
                if selected_flower not in names:
                    selected_flower = None
            suggested = selected_flower or None
        else:
            suggested = match_flower(row.get("product"), row.get("product_spec"), names, aliases)
        item["suggested_flower"] = suggested
        item["flower"] = suggested if unit > 0 else None
        refunded, cancelled = is_refunded(row), is_cancelled(row)
        shipped = is_shipped(row) and not refunded and not cancelled
        item["state"] = ("退款成功" if refunded else "已取消" if cancelled else
                         "未匹配" if shipped and not item["flower"] else
                         "已发货" if shipped else "待发货/未成交")
        reasons = []
        if unit <= 0:
            reasons.append("规格未识别出米数")
        if not suggested:
            reasons.append("花型未匹配")
        item["needs_attention"] = bool(reasons)
        item["attention_reason"] = "、".join(reasons)
        item["stock_effect_meters"] = item["meters"] if item["flower"] and shipped else 0.0
        previous = item.get("previous")
        item["change"] = ("新增" if previous is None else "无变化" if
            float(previous["stock_effect_meters"]) == item["stock_effect_meters"] and
            bool(previous["refunded"]) == refunded and bool(previous["cancelled"]) == cancelled and
            previous["flower"] == item["flower"] else "状态/商品变化")
        business_date, inventory_date = order_dates(row, preview["platform"])
        item["order_date"] = business_date.isoformat() if business_date else None
        item["inventory_date"] = inventory_date.isoformat() if inventory_date else None
        item["edited_fields"] = fields


def recalculate_preview(engine: Engine, token: str, edits: list[dict]) -> dict:
    preview = _previews.get(token)
    if not preview:
        raise ValueError("导入预览已失效，请重新选择文件")
    _apply_preview_edits(engine, preview, edits)
    rows = preview["rows"]
    preview["counts"].update({
        "new": sum(1 for item in rows if item["change"] == "新增"),
        "changed": sum(1 for item in rows if item["change"] == "状态/商品变化"),
        "unchanged": sum(1 for item in rows if item["change"] == "无变化"),
        "unmatched": sum(1 for item in rows if item["needs_attention"]),
        "invalid_meters": sum(1 for item in rows if item["unit_meters"] <= 0),
        "refund": sum(1 for item in rows if is_refunded(item["row"])),
        "excluded": sum(1 for item in rows if not is_shipped(item["row"]) and
                        not is_refunded(item["row"]) and not is_cancelled(item["row"])),
    })
    return {"rows": rows, "counts": preview["counts"]}


def _apply_stock_change(connection, flower: str, change: float, effective_date: date,
                        event_type: str, movement_key: str, reference: str,
                        rebuild: bool = True, stock_cache: dict[str, float] | None = None,
                        event_batch: list[dict] | None = None) -> None:
    if abs(change) < 0.00001:
        return
    if stock_cache is not None and flower in stock_cache:
        before = stock_cache[flower]
    else:
        product = connection.execute(text(
            "SELECT current_stock FROM app_products WHERE flower=:flower AND active=1 FOR UPDATE"
        ), {"flower": flower}).mappings().first()
        if not product:
            return
        before = float(product["current_stock"] or 0)
    after = round(before + change, 2)
    if rebuild or stock_cache is None:
        connection.execute(text(
            "UPDATE app_products SET current_stock=:stock WHERE flower=:flower"
        ), {"stock": after, "flower": flower})
    if stock_cache is not None:
        stock_cache[flower] = after
    event = {"key": movement_key, "flower": flower, "date": effective_date, "kind": event_type,
             "qty": change, "before": before, "after": after, "reference": reference[:255]}
    if event_batch is not None:
        event_batch.append(event)
    else:
        connection.execute(text("""INSERT INTO app_stock_events
            (movement_key, flower, effective_date, event_type, change_qty, before_stock, after_stock, reference)
            VALUES (:key, :flower, :date, :kind, :qty, :before, :after, :reference)"""), event)
    if rebuild:
        rebuild_product_stock(connection, flower)


def commit_import(engine: Engine, token: str, edits: list[dict] | None = None) -> dict:
    preview = _previews.get(token)
    if not preview:
        raise ValueError("导入预览已失效，请重新选择文件")
    _apply_preview_edits(engine, preview, edits or [])
    imported_at = datetime.now()
    today = imported_at.date()
    changed_orders = 0
    movements = 0
    with engine.begin() as connection:
        marker = connection.execute(text(
            "SELECT meta_value FROM app_meta WHERE meta_key='legacy_baseline_v1'"
        )).scalar()
        baseline_date = date.fromisoformat(str(marker)[:10]) if marker else None
        order_numbers = list({
            order_no
            for item in preview["rows"]
            for order_no in (item.get("original_order_no"), item["row"].get("order_no"))
            if order_no
        })
        existing_by_key = {}
        if order_numbers:
            query = text("""SELECT * FROM app_orders
                WHERE platform=:platform AND order_no IN :order_numbers FOR UPDATE""").bindparams(
                bindparam("order_numbers", expanding=True)
            )
            for source in connection.execute(query, {
                "platform": preview["platform"], "order_numbers": order_numbers
            }).mappings():
                existing_by_key[(source["order_no"], source["line_key"])] = dict(source)
        update_rows = []
        insert_rows = []
        movement_rows = []
        ignored_ids = []
        stock_cache: dict[str, float] = {}
        stock_events = []
        changed_stock_flowers: set[str] = set()
        for item in preview["rows"]:
            row = item["row"]
            key = {"platform": preview["platform"], "order_no": row["order_no"], "line_key": row["line_key"]}
            lookup_key = {"platform": preview["platform"],
                          "order_no": item.get("original_order_no", row["order_no"]),
                          "line_key": item.get("original_line_key", row["line_key"])}
            old = existing_by_key.get((lookup_key["order_no"], lookup_key["line_key"]))
            if not old and lookup_key != key:
                old = existing_by_key.get((key["order_no"], key["line_key"]))
            values = {
                **key, "parent_order_no": row.get("parent_order_no"), "product": row.get("product"),
                "product_spec": row.get("product_spec"), "product_id": row.get("product_id"),
                "merchant_code_spec": row.get("merchant_code_spec"),
                "merchant_code_product": row.get("merchant_code_product"),
                "merchant_remark": row.get("merchant_remark"), "express_company": row.get("express_company"),
                "order_status": row.get("order_status"),
                "after_sale_status": row.get("after_sale_status"), "product_quantity": row.get("product_quantity") if row.get("product_quantity") is not None else 1,
                "merchant_income": row.get("merchant_income") or 0, "postage": row.get("postage") or 0,
                "product_total": row.get("product_total") or 0, "user_payment": row.get("user_payment") or 0,
                "delivery_time": _parse_datetime(row.get("delivery_time")),
                "receive_time": _parse_datetime(row.get("receive_time")),
                "payment_time": _parse_datetime(row.get("payment_time")), "order_time": _parse_datetime(row.get("order_time")),
                "express_no": row.get("express_no"), "flower": item["flower"], "meters": item["meters"],
                "effect": item["stock_effect_meters"], "order_date": item["order_date"],
                "inventory_date": item["inventory_date"], "refunded": int(item["state"] == "退款成功"),
                "cancelled": int(item["state"] == "已取消"),
            }
            if old:
                old_flower = old["flower"]
                old_effect = float(old["stock_effect_meters"] or 0)
                old_version = int(old["version"] or 1)
                historical = bool(old["legacy"])
                values["legacy"] = int(historical)
                values["baseline_effect"] = float(old["baseline_stock_effect_meters"] or
                                                   (old_effect if historical else 0))
                unchanged = (old_flower == values["flower"] and old_effect == float(values["effect"])
                             and bool(old["refunded"]) == bool(values["refunded"])
                             and bool(old["cancelled"]) == bool(values["cancelled"]))
                new_version = old_version if unchanged else old_version + 1
                values.update({"id": old["id"], "version": new_version})
                update_rows.append(values)
                if values["flower"]:
                    ignored_ids.append({"id": old["id"]})
                if unchanged:
                    continue
                old_flower, old_effect = old["flower"], float(old["stock_effect_meters"] or 0)
                order_id = old["id"]
                new_identity = None
            else:
                inventory_day = (date.fromisoformat(str(values["inventory_date"])[:10])
                                 if values["inventory_date"] else None)
                historical = baseline_date is not None and inventory_day is not None and inventory_day <= baseline_date
                values["legacy"] = int(historical)
                values["baseline_effect"] = float(values["effect"] or 0) if historical else 0.0
                values["version"] = 1
                insert_rows.append(values)
                order_id, new_version = None, 1
                new_identity = (row["order_no"], row["line_key"])
                old_flower, old_effect = None, 0.0

            movement_rows.append({"order_id": order_id, "new_identity": new_identity,
                                  "new_version": new_version, "old": old, "old_flower": old_flower,
                                  "old_effect": old_effect, "values": values, "row": row})
            changed_orders += 1

        update_sql = text("""UPDATE app_orders SET order_no=:order_no, line_key=:line_key,
            parent_order_no=:parent_order_no, product=:product, product_spec=:product_spec,
            product_id=:product_id, merchant_code_spec=:merchant_code_spec,
            merchant_code_product=:merchant_code_product, merchant_remark=:merchant_remark,
            express_company=:express_company, order_status=:order_status,
            after_sale_status=:after_sale_status, product_quantity=:product_quantity,
            merchant_income=:merchant_income, postage=:postage, product_total=:product_total,
            user_payment=:user_payment, delivery_time=:delivery_time, receive_time=:receive_time,
            payment_time=:payment_time, order_time=:order_time, express_no=:express_no,
            flower=:flower, meters=:meters, stock_effect_meters=:effect, order_date=:order_date,
            inventory_date=:inventory_date, refunded=:refunded, cancelled=:cancelled, version=:version,
            legacy=:legacy, baseline_stock_effect_meters=:baseline_effect WHERE id=:id""")
        if update_rows:
            connection.execute(update_sql, update_rows)
        if insert_rows:
            connection.execute(text("""INSERT INTO app_orders
                (platform, order_no, line_key, parent_order_no, product, product_spec, product_id,
                 merchant_code_spec, merchant_code_product, merchant_remark, express_company,
                 order_status, after_sale_status, product_quantity, merchant_income,
                 postage, product_total, user_payment, delivery_time, receive_time, payment_time, order_time,
                 express_no, flower, meters, stock_effect_meters, order_date, inventory_date, refunded,
                 cancelled, legacy, baseline_stock_effect_meters, version)
                VALUES (:platform, :order_no, :line_key, :parent_order_no, :product, :product_spec, :product_id,
                 :merchant_code_spec, :merchant_code_product, :merchant_remark, :express_company,
                 :order_status, :after_sale_status, :product_quantity, :merchant_income,
                 :postage, :product_total, :user_payment, :delivery_time, :receive_time, :payment_time,
                 :order_time, :express_no, :flower, :meters, :effect, :order_date, :inventory_date,
                 :refunded, :cancelled, :legacy, :baseline_effect, :version)"""), insert_rows)
            new_order_numbers = list({row["order_no"] for row in insert_rows})
            new_id_query = text("""SELECT id, order_no, line_key FROM app_orders
                WHERE platform=:platform AND order_no IN :order_numbers""").bindparams(
                bindparam("order_numbers", expanding=True)
            )
            new_ids = {(row["order_no"], row["line_key"]): row["id"]
                       for row in connection.execute(new_id_query, {
                           "platform": preview["platform"], "order_numbers": new_order_numbers
                       }).mappings()}
            for entry in movement_rows:
                if entry["new_identity"]:
                    entry["order_id"] = new_ids[entry["new_identity"]]
            ignored_ids.extend({"id": new_ids[(row["order_no"], row["line_key"])]}
                               for row in insert_rows if row["flower"])

        if ignored_ids:
            connection.execute(text("DELETE FROM app_ignored_unmatched WHERE order_id=:id"), ignored_ids)

        for entry in movement_rows:
            values, old = entry["values"], entry["old"]
            if old and bool(old["legacy"]):
                deltas = ({entry["old_flower"]: entry["old_effect"]} if values["refunded"] and
                          not bool(old["refunded"]) and entry["old_flower"] and entry["old_effect"] > 0 else {})
            elif not old and values["legacy"]:
                deltas = {}
            else:
                deltas = stock_changes(entry["old_flower"], entry["old_effect"],
                                       values["flower"], float(values["effect"]))
            for flower, stock_delta in deltas.items():
                is_return = stock_delta > 0
                movement_date = today if is_return else (values["inventory_date"] or today)
                kind = "退款回补" if is_return else "订单出库"
                movement_key = f"order:{entry['order_id']}:v{entry['new_version']}:{flower}"
                _apply_stock_change(connection, flower, stock_delta, movement_date, kind, movement_key,
                                    f"{PLATFORM_NAMES[preview['platform']]}订单 {entry['row']['order_no']}",
                                    rebuild=False, stock_cache=stock_cache, event_batch=stock_events)
                if abs(stock_delta) > 0.00001:
                    movements += 1
                    changed_stock_flowers.add(flower)

        if stock_events:
            connection.execute(text("""INSERT INTO app_stock_events
                (movement_key, flower, effective_date, event_type, change_qty,
                 before_stock, after_stock, reference)
                VALUES (:key, :flower, :date, :kind, :qty, :before, :after, :reference)"""), stock_events)

        for flower in sorted(changed_stock_flowers):
            if flower in stock_cache:
                connection.execute(text(
                    "UPDATE app_products SET current_stock=:stock WHERE flower=:flower"
                ), {"stock": stock_cache[flower], "flower": flower})
            rebuild_product_stock(connection, flower)

        connection.execute(text("""INSERT INTO app_imports
            (file_name, platform, row_count, unmatched_count) VALUES (:name, :platform, :rows, :unmatched)"""),
            {"name": preview["filename"][:255], "platform": preview["platform"],
             "rows": len(preview["rows"]),
             "unmatched": sum(1 for row in preview["rows"] if row["needs_attention"])})
    del _previews[token]
    return {"imported": len(preview["rows"]), "changed_orders": changed_orders,
            "stock_movements": movements,
            "unmatched": sum(1 for row in preview["rows"] if row["needs_attention"])}


def rematch_unmatched(engine: Engine) -> dict:
    with engine.connect() as connection:
        names = set(connection.execute(text(
            "SELECT flower FROM app_products WHERE active=1"
        )).scalars())
        aliases = {row["alias_name"]: row["flower"] for row in connection.execute(
            text("SELECT alias_name, flower FROM app_flower_aliases")
        ).mappings()}
    matched = movements = 0
    with engine.begin() as connection:
        candidates = connection.execute(text("""SELECT * FROM app_orders
            WHERE (flower IS NULL OR meters<=0)
            AND NOT EXISTS (SELECT 1 FROM app_ignored_unmatched i WHERE i.order_id=app_orders.id)
            ORDER BY id FOR UPDATE""")).mappings().all()
        for source in candidates:
            row = dict(source)
            unit = extract_meter(row.get("product_spec"))
            if unit <= 0:
                continue
            meters = order_meters(unit, float(row.get("product_quantity") or 0))
            flower = match_flower(row.get("product"), row.get("product_spec"), names, aliases)
            if not flower:
                continue
            effect = meters if (is_shipped(row) and not is_refunded(row) and not is_cancelled(row)) else 0.0
            _, inventory_date = order_dates(row, int(row.get("platform") or 0))
            connection.execute(text("""UPDATE app_orders SET flower=:flower, meters=:meters,
                stock_effect_meters=:effect, inventory_date=:inventory_date, version=version+1
                WHERE id=:id"""), {"flower": flower, "meters": meters, "effect": effect,
                "inventory_date": inventory_date, "id": row["id"]})
            connection.execute(text("DELETE FROM app_ignored_unmatched WHERE order_id=:id"),
                               {"id": row["id"]})
            for changed_flower, delta in stock_changes(
                row.get("flower"), float(row.get("stock_effect_meters") or 0), flower, effect
            ).items():
                _apply_stock_change(connection, changed_flower, delta,
                                    inventory_date or date.today(), "订单出库",
                                    f"order:{row['id']}:v{int(row.get('version') or 1) + 1}:{changed_flower}",
                                    f"{PLATFORM_NAMES.get(int(row.get('platform') or 0), '拼多多')}订单 {row['order_no']}")
                movements += 1
            matched += 1
        remaining = connection.execute(text("""SELECT COUNT(*) FROM app_orders o
            WHERE (o.flower IS NULL OR o.meters<=0)
            AND NOT EXISTS (SELECT 1 FROM app_ignored_unmatched i WHERE i.order_id=o.id)""")).scalar_one()
    return {"matched": matched, "stock_movements": movements, "unmatched": int(remaining)}

