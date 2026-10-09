from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.database import get_engine
from app.services.inventory_service import (
    export_inventory, get_recommendations, list_events, list_inventory, list_purchases,
    receive_rolls, record_movement,
)


router = APIRouter(prefix="/api/inventory", tags=["inventory"])


class MovementInput(BaseModel):
    flower: str
    operation: str
    quantity: float = Field(ge=0)
    effective_date: date
    reference: str = ""


class ReceiptInput(BaseModel):
    flower: str
    roll_count: int = Field(ge=1, le=10000)
    received_date: date
    reference: str = ""


@router.get("")
def inventory(as_of: date | None = None) -> list[dict]:
    return list_inventory(get_engine(), as_of)


@router.get("/events")
def events(limit: int = 20, offset: int = 0, sort_by: str = "created_at",
           sort_order: str = "desc", search: str = "") -> dict:
    return list_events(get_engine(), limit, offset, sort_by, sort_order, search)


@router.get("/purchases")
def purchases(limit: int = 20, offset: int = 0, sort_by: str = "received_date",
              sort_order: str = "desc", search: str = "") -> dict:
    return list_purchases(get_engine(), limit, offset, sort_by, sort_order, search)


@router.get("/recommendations")
def recommendations() -> dict:
    return get_recommendations(get_engine())


@router.get("/export")
def export():
    target = export_inventory(get_engine())
    return {"ok": True, "filename": target.name, "path": str(target)}


@router.post("/movements")
def movement(payload: MovementInput) -> dict:
    try:
        return record_movement(get_engine(), payload.flower, payload.operation,
                               payload.quantity, payload.effective_date, payload.reference)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/receipts")
def receipt(payload: ReceiptInput) -> dict:
    try:
        return receive_rolls(get_engine(), payload.flower, payload.roll_count,
                             payload.received_date, payload.reference)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

