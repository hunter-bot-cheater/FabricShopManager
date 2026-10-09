from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


def list_products(engine: Engine) -> list[dict]:
    with engine.connect() as connection:
        rows = connection.execute(text("""SELECT flower, cost_per_meter, current_stock, active,
            roll_length_meters, replenishment_days, updated_at
            FROM app_products ORDER BY active DESC, flower""")).mappings().all()
        aliases = connection.execute(text("SELECT alias_name, flower FROM app_flower_aliases ORDER BY alias_name")).mappings().all()
    by_flower: dict[str, list[str]] = {}
    for row in aliases:
        by_flower.setdefault(row["flower"], []).append(row["alias_name"])
    return [{**dict(row), "aliases": by_flower.get(row["flower"], [])} for row in rows]


def save_product(engine: Engine, flower: str, cost_per_meter: float,
                 roll_length_meters: float = 45, replenishment_days: int = 1,
                 aliases: list[str] | None = None) -> dict:
    flower = flower.strip()
    if not flower or len(flower) > 100:
        raise ValueError("花型名称不能为空且最多 100 个字符")
    cost_per_meter = float(cost_per_meter)
    if cost_per_meter < 0 or round(cost_per_meter, 2) != cost_per_meter:
        raise ValueError("成本必须是非负数且最多保留两位小数")
    if int(roll_length_meters) != roll_length_meters or roll_length_meters <= 0:
        raise ValueError("每卷米数必须是正整数")
    if int(replenishment_days) != replenishment_days or replenishment_days < 1:
        raise ValueError("预计到店天数必须是正整数")
    normalized_aliases = sorted({alias.strip() for alias in (aliases or []) if alias.strip() and alias.strip() != flower})
    with engine.begin() as connection:
        connection.execute(text("""INSERT INTO app_products
            (flower, cost_per_meter, roll_length_meters, replenishment_days, active)
            VALUES (:flower, :cost, :roll_length, :lead_days, 1) ON DUPLICATE KEY UPDATE
            cost_per_meter=VALUES(cost_per_meter), roll_length_meters=VALUES(roll_length_meters),
            replenishment_days=VALUES(replenishment_days), active=1"""),
            {"flower": flower, "cost": cost_per_meter, "roll_length": roll_length_meters,
             "lead_days": replenishment_days})
        connection.execute(text("DELETE FROM app_flower_aliases WHERE flower=:flower"), {"flower": flower})
        for alias in normalized_aliases:
            connection.execute(text("""INSERT INTO app_flower_aliases (alias_name, flower)
                VALUES (:alias, :flower) ON DUPLICATE KEY UPDATE flower=VALUES(flower)"""),
                {"alias": alias[:100], "flower": flower})
    return {"flower": flower, "cost_per_meter": cost_per_meter,
            "roll_length_meters": roll_length_meters, "replenishment_days": replenishment_days,
            "aliases": normalized_aliases}


def update_product(engine: Engine, original_flower: str, flower: str | None = None,
                   cost_per_meter: float | None = None, roll_length_meters: int | None = None,
                   replenishment_days: int | None = None, aliases: list[str] | None = None) -> dict:
    with engine.begin() as connection:
        existing = connection.execute(text("""SELECT flower, cost_per_meter, roll_length_meters,
            replenishment_days FROM app_products WHERE flower=:flower FOR UPDATE"""),
            {"flower": original_flower}).mappings().first()
        if not existing:
            raise ValueError("该花型已不存在，请刷新后重试")
        flower = str(flower).strip() if flower is not None and str(flower).strip() else original_flower
        cost_per_meter = float(existing["cost_per_meter"] if cost_per_meter is None else cost_per_meter)
        roll_length_meters = int(existing["roll_length_meters"] if roll_length_meters is None else roll_length_meters)
        replenishment_days = int(existing["replenishment_days"] if replenishment_days is None else replenishment_days)
        if not flower or len(flower) > 100:
            raise ValueError("花型名称不能为空且最多 100 个字符")
        if cost_per_meter < 0 or round(cost_per_meter, 2) != cost_per_meter:
            raise ValueError("成本必须是非负数且最多保留两位小数")
        if roll_length_meters <= 0:
            raise ValueError("每卷米数必须是正整数")
        if replenishment_days < 1:
            raise ValueError("预计到店天数必须是正整数")
        normalized_aliases = (None if aliases is None else sorted({
            alias.strip() for alias in aliases if alias.strip() and alias.strip() != flower
        }))
        if flower != original_flower and connection.execute(
            text("SELECT 1 FROM app_products WHERE flower=:flower"), {"flower": flower}
        ).scalar():
            raise ValueError("新花型名称已存在")
        if flower != original_flower:
            connection.execute(text("UPDATE app_flower_aliases SET flower=:new WHERE flower=:old"),
                               {"new": flower, "old": original_flower})
            connection.execute(text("UPDATE app_products SET flower=:new WHERE flower=:old"),
                               {"new": flower, "old": original_flower})
            connection.execute(text("UPDATE app_orders SET flower=:new WHERE flower=:old"),
                               {"new": flower, "old": original_flower})
            connection.execute(text("UPDATE app_stock_events SET flower=:new WHERE flower=:old"),
                               {"new": flower, "old": original_flower})
            connection.execute(text("UPDATE app_purchase_receipts SET flower=:new WHERE flower=:old"),
                               {"new": flower, "old": original_flower})
        connection.execute(text("""UPDATE app_products SET cost_per_meter=:cost,
            roll_length_meters=:roll_length, replenishment_days=:lead_days, active=1 WHERE flower=:flower"""),
            {"cost": cost_per_meter, "roll_length": roll_length_meters,
             "lead_days": replenishment_days, "flower": flower})
        if normalized_aliases is not None:
            connection.execute(text("DELETE FROM app_flower_aliases WHERE flower=:flower"), {"flower": flower})
            for alias in normalized_aliases:
                connection.execute(text("""INSERT INTO app_flower_aliases (alias_name, flower)
                    VALUES (:alias, :flower) ON DUPLICATE KEY UPDATE flower=VALUES(flower)"""),
                    {"alias": alias[:100], "flower": flower})
    return {"flower": flower, "cost_per_meter": cost_per_meter,
            "roll_length_meters": roll_length_meters, "replenishment_days": replenishment_days,
            "aliases": normalized_aliases}


def archive_product(engine: Engine, flower: str) -> dict:
    with engine.begin() as connection:
        result = connection.execute(text("UPDATE app_products SET active=0 WHERE flower=:flower AND active=1"),
                                    {"flower": flower})
        if not result.rowcount:
            raise ValueError("该花型已停用或不存在")
    return {"flower": flower, "archived": True}

