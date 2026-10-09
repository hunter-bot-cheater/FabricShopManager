from datetime import date, datetime
from io import BytesIO

import pandas as pd
import pytest

from app.domain.inventory_rules import order_meters, stock_changes
from app.domain.order_rules import (
    _date, extract_flower, extract_meter, is_cancelled, is_refunded, is_shipped,
    normalize_frame, order_dates, read_order_file,
)
from app.services.order_service import prepare_import


@pytest.mark.parametrize(("spec", "expected"), [
    ("花型,一米", 1.0), ("花型;半米", 0.5), ("花型,2.5米", 2.5),
    ("颜色分类:黑底条纹两米", 2.0), ("花型（门幅1.43米）", 0.0),
    ("花型,一米（门幅1.43米）", 1.0), ("花型,2m", 2.0),
    ("花型,２．５米", 2.5), ("花型,十一米", 11.0), ("花型,二十三米", 23.0),
    ("花型,半", 0.5), ("花型,宽度1.43米", 0.0), ("花型,45", 0.0),
    ("花型,1.43米幅宽", 0.0), ("花型,门幅一米", 0.0),
    ("花型,两米布宽", 0.0),
])
def test_extract_meter(spec, expected):
    assert extract_meter(spec) == expected


def test_extract_flower_normalizes_taobao_sku_alias():
    assert extract_flower("颜色分类:黑底条纹两米（长度自选）") == "城市条纹"


def test_platform_specific_business_dates():
    row = {"order_no": "260907123456", "payment_time": datetime(2026, 10, 1),
           "order_time": datetime(2026, 9, 7)}
    assert order_dates(row, 0)[0] == date(2026, 9, 7)
    row["order_no"] = "TB123"
    assert order_dates(row, 1)[0] == date(2026, 10, 1)


@pytest.mark.parametrize(("value", "expected"), [
    ("2026-10-09 10:04:07", datetime(2026, 10, 9, 10, 4, 7)),
    ("2026-10-09T10:04:07", datetime(2026, 10, 9, 10, 4, 7)),
    ("2026/10/09 10:04:07", datetime(2026, 10, 9, 10, 4, 7)),
    (date(2026, 10, 9), datetime(2026, 10, 9)),
    ("", None),
    (float("nan"), None),
])
def test_order_date_parser_fast_path_preserves_common_input_formats(value, expected):
    assert _date(value) == expected


def test_pdd_rows_normalize_and_keep_line_specific_identity():
    frame = pd.DataFrame([{
        "订单号": "260907-001", "商品": "纯棉布", "订单状态": "已发货",
        "商品规格": "城市条纹,一米", "商品数量(件)": 2,
        "商家实收金额(元)": 49.0,
    }])
    platform, rows = normalize_frame(frame)
    assert platform == 0
    assert rows[0]["order_no"] == "260907-001"
    assert rows[0]["product_quantity"] == 2
    assert rows[0]["product_spec"] == "城市条纹,一米"
    from app.services.order_service import _meters
    assert _meters(rows[0]) == 2


@pytest.mark.parametrize(("platform", "source", "expected_spec", "expected_unit", "expected_total"), [
    (0, {"订单号": "PDD-1", "商品": "布料", "商品规格": "城市条纹,2.5米（宽幅1.43米）", "商品数量(件)": 3},
     "城市条纹,2.5米（宽幅1.43米）", 2.5, 7.5),
    (1, {"订单编号": "TB-1", "商品标题": "布料", "宝贝种类": 0, "宝贝总数量": 3,
         "商品属性SKU": "颜色分类:腰果花两米（门幅1.43米）"},
     "颜色分类:腰果花两米（门幅1.43米）", 2.0, 6.0),
    (2, {"子订单编号": "DY-1", "主订单编号": "DY-PARENT", "选购商品": "布料", "商品数量": 3,
         "商品规格": "\t腰果花;二米（棉100%）"},
     "腰果花;二米（棉100%）", 2.0, 6.0),
])
def test_platform_sku_and_quantity_fields_produce_exact_order_meters(platform, source, expected_spec, expected_unit, expected_total):
    detected, rows = normalize_frame(pd.DataFrame([source]), platform=platform)
    assert detected == platform
    assert rows[0]["product_spec"] == expected_spec
    assert extract_meter(rows[0]["product_spec"]) == expected_unit
    from app.services.order_service import _meters
    assert _meters(rows[0]) == expected_total


def test_taobao_uses_product_attribute_sku_not_baby_kind():
    _, rows = normalize_frame(pd.DataFrame([{
        "订单编号": "TB-2", "商品标题": "印花布", "宝贝种类": 0,
        "商品属性SKU": "颜色分类:腰果花两米（门幅1.43米）",
    }]))
    assert rows[0]["product_spec"] == "颜色分类:腰果花两米（门幅1.43米）"
    assert extract_meter(rows[0]["product_spec"]) == 2


def test_taobao_xlsx_reader_uses_sku_column_and_reads_length():
    frame = pd.DataFrame([{
        "订单编号": "TB-XLSX", "商品标题": "印花布", "宝贝种类": 0,
        "商品属性SKU": "颜色分类:腰果花两米（门幅1.43米）",
    }])
    content = BytesIO()
    frame.to_excel(content, index=False)
    platform, rows = read_order_file("taobao.xlsx", content.getvalue())
    assert platform == 1
    assert rows[0]["product_spec"] == "颜色分类:腰果花两米（门幅1.43米）"
    assert extract_meter(rows[0]["product_spec"]) == 2


def test_rows_without_order_number_are_skipped_even_when_excel_value_is_nan():
    frame = pd.DataFrame([
        {"订单号": None, "商品": "无订单号", "商品规格": "无花型,一米"},
        {"订单号": "PDD-1", "商品": "有效订单", "商品规格": "城市条纹,一米"},
    ])
    _, rows = normalize_frame(frame, platform=0)
    assert [row["order_no"] for row in rows] == ["PDD-1"]


def test_import_preview_keeps_unknown_length_as_editable_attention_row():
    from sqlalchemy import create_engine, text

    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE app_products (flower TEXT, cost_per_meter REAL, active INTEGER)"))
        connection.execute(text("CREATE TABLE app_flower_aliases (alias_name TEXT, flower TEXT)"))
        connection.execute(text("""CREATE TABLE app_orders (
            id INTEGER, platform INTEGER, order_no TEXT, line_key TEXT, flower TEXT, stock_effect_meters REAL,
            baseline_stock_effect_meters REAL, legacy INTEGER, refunded INTEGER, cancelled INTEGER,
            order_status TEXT, after_sale_status TEXT)"""))
        connection.execute(text("INSERT INTO app_products VALUES ('城市条纹', 6, 1)"))
    csv = ("订单号,商品,商品规格,订单状态\n"
           "PDD-UNKNOWN,布料,城市条纹,已发货\n"
           "PDD-CANCELLED,旧布料,城市条纹,交易关闭\n"
           "PDD-COMPLETED,布料,城市条纹;半米,已完成\n").encode("utf-8-sig")
    preview = prepare_import(engine, "orders.csv", csv, platform=0)
    assert preview["counts"]["invalid_meters"] == 2
    assert preview["counts"]["unmatched"] == 2
    assert preview["rows"][0]["needs_attention"] is True
    assert preview["rows"][0]["flower"] is None
    assert preview["rows"][0]["stock_effect_meters"] == 0
    assert preview["rows"][1]["state"] == "已取消"
    assert preview["rows"][1]["needs_attention"] is True
    assert preview["rows"][2]["state"] == "已发货"
    assert preview["rows"][2]["stock_effect_meters"] == 0.5
    assert preview["counts"]["excluded"] == 0

    from app.services.order_service import recalculate_preview
    result = recalculate_preview(engine, preview["token"], [{"row_index": 0, "fields": {
        "product_spec": "城市条纹,半米", "product_quantity": "2", "flower": "城市条纹",
    }}])
    assert result["counts"]["unmatched"] == 1
    assert result["rows"][0]["meters"] == 1.0
    assert result["rows"][0]["stock_effect_meters"] == 1.0
    assert result["rows"][0]["state"] == "已发货"


def test_zero_quantity_is_not_reported_as_unrecognized_specification():
    from sqlalchemy import create_engine, text

    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE app_products (flower TEXT, cost_per_meter REAL, active INTEGER)"))
        connection.execute(text("CREATE TABLE app_flower_aliases (alias_name TEXT, flower TEXT)"))
        connection.execute(text("""CREATE TABLE app_orders (
            id INTEGER, platform INTEGER, order_no TEXT, line_key TEXT, flower TEXT, stock_effect_meters REAL,
            baseline_stock_effect_meters REAL, legacy INTEGER, refunded INTEGER, cancelled INTEGER,
            order_status TEXT, after_sale_status TEXT)"""))
        connection.execute(text("INSERT INTO app_products VALUES ('城市条纹', 6, 1)"))
    csv = ("订单号,商品,商品规格,商品数量(件),订单状态\n"
           "PDD-ZERO,布料,城市条纹;一米,0,交易关闭\n").encode("utf-8-sig")

    preview = prepare_import(engine, "orders.csv", csv, platform=0)

    assert preview["counts"]["invalid_meters"] == 0
    assert preview["counts"]["unmatched"] == 0
    assert preview["rows"][0]["unit_meters"] == 1
    assert preview["rows"][0]["meters"] == 0
    assert preview["rows"][0]["flower"] == "城市条纹"
    assert preview["rows"][0]["needs_attention"] is False

def test_status_classification_excludes_refund_and_cancel():
    assert is_shipped({"order_status": "已发货"})
    assert is_shipped({"order_status": "已完成"})
    assert is_refunded({"after_sale_status": "已发货，退款成功"})
    assert not is_cancelled({"order_status": "已发货，退款成功"})
    assert is_cancelled({"order_status": "交易关闭"})


@pytest.mark.parametrize("status", ["未付款", "待付款", "未支付", "待支付"])
def test_unpaid_orders_are_not_statistically_shipped(status):
    assert not is_shipped({"order_status": status})
    assert not is_shipped({"order_status": "已发货", "after_sale_status": status})


def test_order_meters_is_exact_unit_length_times_quantity():
    assert order_meters(1.5, 3) == 4.5
    assert order_meters(0.5, 3) == 1.5
    assert order_meters(1.5, 0) == 0
    with pytest.raises(ValueError):
        order_meters(0, 1)
    with pytest.raises(ValueError):
        order_meters(1, -1)


def test_import_meters_are_unit_length_times_quantity_without_step_rounding():
    from app.services.order_service import _meters

    assert _meters({"product_spec": "花型,1.5米", "product_quantity": 3}) == 4.5


def test_order_state_inventory_deltas_cover_shipment_refund_and_reimport():
    # New shipped order deducts. A first import already refunded has zero effect.
    assert stock_changes(None, 0, "城市条纹", 2.5) == {"城市条纹": -2.5}
    assert stock_changes(None, 0, "城市条纹", 0) == {}
    # The next import changes shipped -> refunded and restores once.
    assert stock_changes("城市条纹", 2.5, "城市条纹", 0) == {"城市条纹": 2.5}
    # Reimporting the unchanged refunded state creates no movement.
    assert stock_changes("城市条纹", 0, "城市条纹", 0) == {}
    # A flower remap restores the old style and deducts the new one atomically.
    assert stock_changes("旧花型", 1.5, "新花型", 2.0) == {"旧花型": 1.5, "新花型": -2.0}
