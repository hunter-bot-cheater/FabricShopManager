from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import bindparam, text

from app.core.database import get_engine
from app.services.order_service import commit_import, prepare_import, recalculate_preview, rematch_unmatched


router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.post("/preview")
async def import_preview(file: UploadFile = File(...), platform: int | None = Form(default=None)) -> dict:
    try:
        content = await file.read()
        return prepare_import(get_engine(), file.filename or "订单表.xlsx", content, platform)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class CommitInput(BaseModel):
    token: str
    edits: list[dict] = Field(default_factory=list)


@router.post("/preview/recalculate")
def preview_recalculate(payload: CommitInput) -> dict:
    try:
        return recalculate_preview(get_engine(), payload.token, payload.edits)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/commit")
def import_commit(payload: CommitInput) -> dict:
    try:
        return commit_import(get_engine(), payload.token, payload.edits)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/unmatched")
def unmatched_orders(limit: int = 20, offset: int = 0) -> dict:
    return _unmatched_page(ignored=False, limit=limit, offset=offset)


@router.get("/unmatched/ignored")
def ignored_unmatched_orders(limit: int = 20, offset: int = 0) -> dict:
    return _unmatched_page(ignored=True, limit=limit, offset=offset)


def _unmatched_page(ignored: bool, limit: int, offset: int) -> dict:
    limit = min(max(limit, 1), 100)
    offset = max(offset, 0)
    match_clause = "EXISTS" if ignored else "NOT EXISTS"
    where = f"""(o.flower IS NULL OR o.meters<=0)
        AND {match_clause} (SELECT 1 FROM app_ignored_unmatched i WHERE i.order_id=o.id)"""
    with get_engine().connect() as connection:
        total = connection.execute(text(f"SELECT COUNT(*) FROM app_orders o WHERE {where}")).scalar_one()
        rows = connection.execute(text(f"""SELECT o.id, o.platform, o.order_no, o.product, o.product_spec,
            o.product_quantity, o.meters, o.flower, o.order_status, o.after_sale_status,
            o.order_date, o.order_time, o.merchant_income
            FROM app_orders o WHERE {where}
            ORDER BY o.updated_at DESC, o.id DESC LIMIT :limit OFFSET :offset"""),
            {"limit": limit, "offset": offset}).mappings().all()
    return {"items": [dict(row) for row in rows], "total": int(total), "limit": limit, "offset": offset}


class UnmatchedIds(BaseModel):
    order_ids: list[int] = Field(default_factory=list)
    exclude_order_ids: list[int] = Field(default_factory=list)
    all: bool = False


@router.post("/unmatched/ignore")
def ignore_unmatched(payload: UnmatchedIds) -> dict:
    if payload.all:
        with get_engine().connect() as connection:
            where = """(o.flower IS NULL OR o.meters<=0)
                AND NOT EXISTS (SELECT 1 FROM app_ignored_unmatched i WHERE i.order_id=o.id)"""
            if payload.exclude_order_ids:
                where += " AND o.id NOT IN :excluded"
                query = text(f"SELECT o.id FROM app_orders o WHERE {where}").bindparams(
                    bindparam("excluded", expanding=True))
                ids = connection.execute(query, {"excluded": payload.exclude_order_ids}).scalars().all()
            else:
                ids = connection.execute(text(f"SELECT o.id FROM app_orders o WHERE {where}")).scalars().all()
    else:
        ids = sorted(set(payload.order_ids))
    ids = sorted(set(ids))
    ignored = 0
    with get_engine().begin() as connection:
        for order_id in ids:
            unresolved = connection.execute(text("""SELECT id FROM app_orders
                WHERE id=:id AND (flower IS NULL OR meters<=0)"""),
                {"id": order_id}).scalar_one_or_none()
            if unresolved is None:
                continue
            exists = connection.execute(text(
                "SELECT order_id FROM app_ignored_unmatched WHERE order_id=:id"),
                {"id": order_id}).scalar_one_or_none()
            if exists is None:
                connection.execute(text("INSERT INTO app_ignored_unmatched (order_id) VALUES (:id)"),
                                   {"id": order_id})
                ignored += 1
    return {"ignored": ignored}


@router.post("/unmatched/rematch")
def rematch_orders() -> dict:
    return rematch_unmatched(get_engine())


@router.post("/unmatched/restore")
def restore_unmatched(payload: UnmatchedIds) -> dict:
    ids = sorted(set(payload.order_ids))
    with get_engine().begin() as connection:
        restored = 0
        for order_id in ids:
            result = connection.execute(text("DELETE FROM app_ignored_unmatched WHERE order_id=:id"),
                                        {"id": order_id})
            restored += result.rowcount
    return {"restored": restored}

