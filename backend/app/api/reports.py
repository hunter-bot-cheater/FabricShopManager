from datetime import date

from fastapi import APIRouter
from app.core.database import get_engine
from app.services.report_service import (
    build_inout_report, build_refund_report, build_report, export_inout_report, export_refund_report,
    export_report,
)


router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("")
def report(start_date: date, end_date: date, group_by: str = "day") -> dict:
    if group_by not in {"day", "month"}:
        return {"rows": [], "details": [], "totals": {}, "error": "group_by 仅支持 day/month"}
    return build_report(get_engine(), start_date, end_date, group_by)


@router.get("/export")
def report_export(start_date: date, end_date: date, kind: str = "daily"):
    try:
        target = export_report(get_engine(), start_date, end_date, kind)
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "filename": target.name, "path": str(target)}


@router.get("/inout-export")
def inout_report_export(start_date: date, end_date: date):
    try:
        target = export_inout_report(get_engine(), start_date, end_date)
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "filename": target.name, "path": str(target)}


@router.get("/refunds")
def refund_report(start_date: date, end_date: date) -> dict:
    try:
        return build_refund_report(get_engine(), start_date, end_date)
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/inout")
def inout_report(start_date: date, end_date: date) -> dict:
    try:
        return build_inout_report(get_engine(), start_date, end_date)
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/refunds/export")
def refund_report_export(start_date: date, end_date: date) -> dict:
    try:
        target = export_refund_report(get_engine(), start_date, end_date)
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "filename": target.name, "path": str(target)}

