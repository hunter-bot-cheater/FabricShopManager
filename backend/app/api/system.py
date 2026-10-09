from fastapi import APIRouter
from sqlalchemy import inspect, text

from app.core.database import get_engine, test_connection
from app.core.schema import ensure_schema, initialize_legacy_baseline


router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/status")
def status() -> dict:
    try:
        test_connection()
        engine = get_engine()
        # Every existing installation receives idempotent schema migrations at connect time.
        ensure_schema(engine)
        tables = set(inspect(engine).get_table_names())
        initialized = False
        if "app_meta" in tables:
            with engine.connect() as connection:
                initialized = bool(connection.execute(text(
                    "SELECT 1 FROM app_meta WHERE meta_key='legacy_baseline_v1'"
                )).scalar())
        return {"connected": True, "initialized": initialized}
    except Exception as exc:
        return {"connected": False, "initialized": False, "message": str(exc)}


@router.post("/initialize")
def initialize() -> dict:
    result = initialize_legacy_baseline(get_engine())
    return {"ok": True, **result}

