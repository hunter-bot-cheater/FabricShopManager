from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.credentials import get_password, save_password
from app.core.database import test_connection
from app.core.settings import defaults, load_settings, save_settings


router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsInput(BaseModel):
    mysql_host: str | None = None
    mysql_port: int | None = Field(default=None, ge=1, le=65535)
    mysql_database: str | None = None
    mysql_user: str | None = None
    mysql_password: str | None = None
    output_daily: str | None = None
    output_range: str | None = None
    output_refund: str | None = None
    output_inventory: str | None = None
    output_inout: str | None = None
    default_shipping_fee: float | None = Field(default=None, ge=0)
    inventory_sales_window_days: int | None = Field(default=None, ge=1, le=90)
    procurement_target_days: int | None = Field(default=None, ge=1, le=90)


@router.get("")
def get_settings() -> dict[str, Any]:
    values = load_settings()
    return {**values, "mysql_password": "", "has_password": bool(get_password()),
            "defaults": defaults()}


@router.put("")
def put_settings(payload: SettingsInput) -> dict[str, Any]:
    values = payload.model_dump(exclude_unset=True)
    password = values.pop("mysql_password", None)
    result = save_settings(values)
    if password is not None:
        save_password(password)
    return {**result, "mysql_password": "", "has_password": bool(get_password())}


@router.post("/test-connection")
def connection_test() -> dict[str, str]:
    try:
        return test_connection()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"MySQL 连接失败：{exc}") from exc

