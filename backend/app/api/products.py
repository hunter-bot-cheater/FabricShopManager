from fastapi import APIRouter, HTTPException
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator

from app.core.database import get_engine
from app.services.product_service import archive_product, list_products, save_product, update_product


router = APIRouter(prefix="/api/products", tags=["products"])


class ProductInput(BaseModel):
    flower: str = Field(min_length=1, max_length=100)
    cost_per_meter: Decimal = Field(ge=0)
    roll_length_meters: int = Field(default=45, gt=0, le=9999)
    replenishment_days: int = Field(default=1, ge=1, le=365)
    aliases: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("cost_per_meter")
    @classmethod
    def validate_cost_scale(cls, value: Decimal) -> Decimal:
        if value.quantize(Decimal("0.01")) != value:
            raise ValueError("成本最多保留两位小数")
        return value


class ProductUpdateInput(BaseModel):
    flower: str | None = Field(default=None, min_length=1, max_length=100)
    cost_per_meter: Decimal | None = Field(default=None, ge=0)
    roll_length_meters: int | None = Field(default=None, gt=0, le=9999)
    replenishment_days: int | None = Field(default=None, ge=1, le=365)
    aliases: list[str] | None = Field(default=None, max_length=30)

    @field_validator("cost_per_meter")
    @classmethod
    def validate_cost_scale(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and value.quantize(Decimal("0.01")) != value:
            raise ValueError("成本最多保留两位小数")
        return value


@router.get("")
def get_products() -> list[dict]:
    return list_products(get_engine())


@router.post("")
def put_product(payload: ProductInput) -> dict:
    try:
        return save_product(get_engine(), payload.flower, payload.cost_per_meter,
                            payload.roll_length_meters, payload.replenishment_days, payload.aliases)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/{original_flower}")
def edit_product(original_flower: str, payload: ProductUpdateInput) -> dict:
    try:
        return update_product(get_engine(), original_flower, payload.flower, payload.cost_per_meter,
                              payload.roll_length_meters, payload.replenishment_days, payload.aliases)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{flower}")
def delete_product(flower: str) -> dict:
    try:
        return archive_product(get_engine(), flower)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

