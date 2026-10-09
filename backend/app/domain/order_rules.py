from __future__ import annotations

import hashlib
import io
import re
from datetime import date, datetime
from typing import Any

import pandas as pd


PLATFORM_NAMES = {0: "拼多多", 1: "淘宝", 2: "抖音"}
PLATFORM_COLUMNS = {
    1: {"订单编号": "订单号", "商品标题": "商品", "商品名称": "商品",
        "商品属性SKU": "商品规格", "总金额(旧版)": "商品总价(元)", "买家应付邮费": "邮费(元)",
        "买家实付金额": "用户实付金额(元)", "买家应付货款": "商家实收金额(元)",
        "宝贝总数量": "商品数量(件)", "订单创建时间": "订单成交时间", "发货时间": "发货时间",
        "确认收货时间": "确认收货时间", "订单状态": "订单状态", "商家备注": "商家备注",
        "物流单号": "快递单号", "物流公司": "快递公司", "退款金额": "_refund_amount",
        "订单关闭原因": "_close_reason", "商品ID": "商品id", "商品id": "商品id"},
    2: {"主订单编号": "parent_order_no", "子订单编号": "订单号", "选购商品": "商品",
        "商品数量": "商品数量(件)", "订单应付金额": "商家实收金额(元)", "运费": "邮费(元)",
        "订单状态": "订单状态", "售后状态": "售后状态", "发货时间": "发货时间",
        "订单完成时间": "确认收货时间", "订单提交时间": "订单成交时间", "支付完成时间": "订单付款时间",
        "物流SN码": "快递单号", "商家备注": "商家备注", "取消原因": "_close_reason",
        "商品编码": "商品id", "商品规格": "商品规格"},
}
STANDARD_COLUMNS = {
    "商品": "product", "订单号": "order_no", "订单状态": "order_status", "售后状态": "after_sale_status",
    "商品总价(元)": "product_total", "邮费(元)": "postage", "用户实付金额(元)": "user_payment",
    "商家实收金额(元)": "merchant_income", "商品数量(件)": "product_quantity", "发货时间": "delivery_time",
    "确认收货时间": "receive_time", "商品id": "product_id", "商品规格": "product_spec",
    "商家编码-规格维度": "merchant_code_spec", "商家编码-商品维度": "merchant_code_product",
    "商家备注": "merchant_remark", "快递单号": "express_no", "物流单号": "express_no",
    "物流公司": "express_company", "订单成交时间": "order_time", "订单付款时间": "payment_time",
    "parent_order_no": "parent_order_no", "订单号": "order_no",
}
ALIASES = {
    "白底黑色条纹": "白底乱纹", "几何乱纹": "白底乱纹", "蓝色唐人": "唐人蓝色",
    "紫色唐人": "唐人紫色", "皮粉唐人": "唐人粉色", "粉色唐人": "唐人粉色",
    "黄色唐人": "黄色小唐人", "水墨风蝴蝶": "水墨蝴蝶", "雅韵青花": "青花雅韵",
    "三色拼读": "三色拼写", "黑底条纹": "城市条纹", "黑白玄纹": "玄纹密码",
    "条纹哪吒": "黄底哪吒", "腰果花": "灰白底腰果花", "绿野浮蝶": "绿影浮蝶",
    "紫底小唐人": "唐人紫色", "白底条纹": "白底乱纹", "蓝底小唐人": "唐人蓝色",
    "粉底小唐人": "唐人粉色",
}
FULL_TO_HALF = str.maketrans({"，": ",", "；": ";", "．": ".", "（": "(", "）": ")",
                               **{chr(0xFF10 + i): str(i) for i in range(10)}})


def _text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _number(value: Any, default: float = 0.0) -> float:
    if value is None or pd.isna(value):
        return default
    cleaned = re.sub(r"[^0-9.\-]", "", str(value).replace(",", ""))
    try:
        return float(cleaned) if cleaned else default
    except ValueError:
        return default


def _date(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    elif pd.isna(value):
        return None
    if isinstance(value, datetime):
        return value.to_pydatetime() if hasattr(value, "to_pydatetime") else value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed.to_pydatetime()


def detect_platform(columns: list[str]) -> int:
    names = set(columns)
    if names.intersection({"主订单编号", "子订单编号", "选购商品"}):
        return 2
    if names.intersection({"订单编号", "商品标题", "宝贝种类", "商品名称"}):
        return 1
    if "订单号" in names and ("商品" in names or "商家实收金额(元)" in names):
        return 0
    raise ValueError("无法识别平台，请上传拼多多、淘宝或抖音导出的订单表")


def extract_meter(spec: Any) -> float:
    value = _text(spec).translate(FULL_TO_HALF)
    if not value:
        return 0.0

    # Platform exports place the selected length on different sides of their
    # comma/semicolon. Search the SKU text, excluding parenthetical notes.
    selection = re.sub(r"[（(][^）)]*[）)]", "", value).strip()
    width_value = r"(?:\d+(?:\.\d+)?|[一二两三四五六七八九]?十[一二两三四五六七八九]?|[一二两三四五六七八九]|半)"
    selection = re.sub(
        rf"(?:门幅|幅宽|宽幅|布宽|宽度)\s*{width_value}\s*(?:米|m)(?![a-z])|"
        rf"{width_value}\s*(?:米|m)(?![a-z])\s*(?:门幅|幅宽|宽幅|布宽|宽度)",
        "", selection, flags=re.I,
    )

    if "半米" in selection or re.search(r"(?:^|[,;:：\s])半(?:$|\s|[,;])", selection):
        return 0.5

    digit_values = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
                    "六": 6, "七": 7, "八": 8, "九": 9}
    chinese_match = re.search(r"([一二两三四五六七八九]?十[一二两三四五六七八九]?|[一二两三四五六七八九])\s*米", selection)
    if chinese_match:
        token = chinese_match.group(1)
        if "十" in token:
            tens, _, ones = token.partition("十")
            return float((digit_values.get(tens, 1) * 10) + digit_values.get(ones, 0))
        return float(digit_values[token])

    match = re.search(r"(?<![\d.])(\d+(?:\.\d+)?)\s*(?:米|m)(?![a-z])", selection, re.I)
    if match:
        return float(match.group(1))
    return 0.0


def extract_flower(spec: Any, aliases: dict[str, str] | None = None) -> str:
    value = _text(spec).translate(FULL_TO_HALF)
    if not value:
        return ""
    if "颜色分类" in value:
        value = re.sub(r"^.*?颜色分类[:：]?", "", value).strip()
    # 淘宝常将长度放在逗号后，抖音常以分号分隔花型与长度。
    value = re.split(r"[,;]", value, maxsplit=1)[0].strip()
    value = re.sub(r"[（(].*?[)）]", "", value).strip()
    value = re.sub(r"(?:半米|一米|两米|二米|三米|四米|五米|六米|\d+(?:\.\d+)?\s*(?:米|m)).*$", "", value, flags=re.I).strip()
    return {**ALIASES, **(aliases or {})}.get(value, value)


def match_flower(product: Any, spec: Any, known: set[str], aliases: dict[str, str] | None = None) -> str | None:
    alias_map = {**ALIASES, **(aliases or {})}
    spec_name = extract_flower(spec, alias_map)
    if spec_name in known:
        return spec_name
    haystack = f"{_text(product)} {_text(spec)}".casefold()
    # Prefer the longest match to avoid a short flower name swallowing another.
    for flower in sorted(known, key=len, reverse=True):
        if flower.casefold() in haystack:
            return flower
    for alias in sorted(alias_map, key=len, reverse=True):
        target = alias_map[alias]
        if alias.casefold() in haystack and target in known:
            return target
    product_text = _text(product)
    rules = [("唐人", "紫色", "唐人紫色"), ("唐人", "蓝色", "唐人蓝色"),
             ("唐人", "粉色", "唐人粉色"), ("唐人", "皮粉", "唐人粉色"),
             ("唐人", "黄色", "黄色小唐人"), ("东北大花", "红底红花", "东北红底红花"),
             ("东北大花", "绿底红花", "东北绿底红花")]
    for product_key, spec_key, target in rules:
        if product_key in product_text and spec_key in _text(spec) and target in known:
            return target
    product_rules = [
        ("黄底哪吒", "黄底哪吒"), ("条纹哪吒", "条纹哪吒"), ("哪吒", "Q版哪吒"),
        ("黑白城市条纹", "城市条纹"), ("城市条纹", "城市条纹"),
        ("油墨风银杏", "油墨风银杏"), ("银杏叶", "油墨风银杏"),
        ("雕印", "雕印绿色海浪纹"), ("3D太阳花", "3D立体太阳花"),
    ]
    for keyword, target in product_rules:
        if keyword in product_text and target in known:
            return target
    if "七彩数码印花" in product_text:
        target = "雕印绿色海浪纹" if any(key in haystack for key in ("雕印", "绿色海浪")) else "3D数码印花"
        if target in known:
            return target
    return None


def order_dates(row: dict[str, Any], platform: int) -> tuple[date | None, date | None]:
    payment = row.get("payment_time")
    created = row.get("order_time")
    if platform == 0:
        number = str(row.get("order_no") or "").strip()
        try:
            business = datetime.strptime(number[:6], "%y%m%d").date()
        except (ValueError, TypeError):
            business = (payment or created).date() if payment or created else None
    else:
        business = (payment or created).date() if payment or created else None
    delivery = row.get("delivery_time")
    received = row.get("receive_time")
    # Sales stock effects follow the order's placed date, not the import time.
    # Use the payment date only when the platform export has no creation time.
    inventory_basis = created or payment
    inventory = inventory_basis.date() if inventory_basis else business
    return business, inventory


def is_refunded(row: dict[str, Any]) -> bool:
    return "退款成功" in f"{row.get('order_status') or ''} {row.get('after_sale_status') or ''}"


def is_cancelled(row: dict[str, Any]) -> bool:
    if is_refunded(row):
        return False
    order_status = str(row.get("order_status") or "")
    after_sale_status = str(row.get("after_sale_status") or "")
    # 售后“关闭”不代表交易取消；平台订单状态才是交易是否关闭的依据。
    return (any(term in order_status for term in ("已取消", "已关闭", "交易关闭"))
            or any(term in after_sale_status for term in ("已取消", "交易关闭")))


def is_shipped(row: dict[str, Any]) -> bool:
    status = f"{row.get('order_status') or ''} {row.get('after_sale_status') or ''}"
    if any(term in status for term in ("未付款", "待付款", "未支付", "待支付")):
        return False
    return any(term in status for term in ("已发货", "已收货", "交易成功", "已完成"))


def line_key(row: dict[str, Any]) -> str:
    stable = row.get("merchant_code_spec") or "|".join((
        str(row.get("product_id") or ""), str(row.get("product_spec") or "")
    ))
    if not stable:
        stable = "|".join((str(row.get("product") or ""), str(row.get("product_spec") or "")))
    return hashlib.sha256(str(stable).encode("utf-8")).hexdigest()[:32]


def normalize_frame(frame: pd.DataFrame, platform: int | None = None) -> tuple[int, list[dict[str, Any]]]:
    if frame.empty:
        raise ValueError("订单文件没有数据行")
    platform = detect_platform([str(c) for c in frame.columns]) if platform is None else platform
    mapping = PLATFORM_COLUMNS.get(platform, {})
    normalized = frame.rename(columns={key: value for key, value in mapping.items() if key in frame.columns})
    normalized = normalized.loc[:, ~normalized.columns.duplicated()]
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for source in normalized.to_dict(orient="records"):
        row = {db: source.get(column) for column, db in STANDARD_COLUMNS.items() if column in source}
        row["order_no"] = _text(row.get("order_no"))
        if not row["order_no"]:
            continue
        row["product"] = _text(row.get("product"))
        row["product_spec"] = _text(row.get("product_spec"))
        row["order_status"] = _text(row.get("order_status"))
        row["after_sale_status"] = _text(row.get("after_sale_status"))
        row["product_quantity"] = _number(row.get("product_quantity"), 1.0)
        for key in ("merchant_income", "postage", "product_total", "user_payment"):
            row[key] = _number(row.get(key))
        for key in ("delivery_time", "receive_time", "order_time", "payment_time"):
            row[key] = _date(row.get(key))
        if platform == 1:
            refund_amount = _number(source.get("_refund_amount"))
            close_reason = _text(source.get("_close_reason"))
            if "退款成功" not in row["after_sale_status"] and refund_amount > 0 and (
                row["order_status"] == "交易关闭" or "退款" in close_reason
            ):
                shipped = bool(row.get("delivery_time") or row.get("receive_time"))
                row["after_sale_status"] = "已发货，退款成功" if shipped else "未发货，退款成功"
        if platform == 2:
            reason = _text(source.get("_close_reason"))
            if "退款" in reason and "退款成功" not in row["after_sale_status"]:
                row["after_sale_status"] = "已发货，退款成功" if row.get("delivery_time") else "未发货，退款成功"
        row["platform"] = platform
        row["line_key"] = line_key(row)
        rows[(row["order_no"], row["line_key"])] = row
    result = list(rows.values())
    if not result:
        raise ValueError("没有找到有效订单号，请确认上传的是平台订单明细")
    return platform, result


def read_order_file(filename: str, content: bytes, platform: int | None = None) -> tuple[int, list[dict[str, Any]]]:
    name = filename.lower()
    if name.endswith(".csv"):
        error = None
        for encoding in ("utf-8-sig", "gb18030"):
            try:
                frame = pd.read_csv(io.BytesIO(content), encoding=encoding)
                break
            except UnicodeDecodeError as exc:
                error = exc
        else:
            raise ValueError(f"CSV 编码无法识别：{error}")
    elif name.endswith((".xlsx", ".xlsm")):
        frame = pd.read_excel(io.BytesIO(content), sheet_name=0, engine="openpyxl")
    elif name.endswith(".xls"):
        frame = pd.read_excel(io.BytesIO(content), sheet_name=0)
    else:
        raise ValueError("仅支持 .xlsx、.xlsm、.xls 或 .csv 文件")
    return normalize_frame(frame, platform)
