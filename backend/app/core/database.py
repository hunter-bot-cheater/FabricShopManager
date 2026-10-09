from __future__ import annotations

from sqlalchemy import URL, create_engine, text
from sqlalchemy.engine import Engine

from app.core.credentials import get_password
from app.core.settings import load_settings


_engine: Engine | None = None
_engine_key: tuple | None = None


def get_engine() -> Engine:
    global _engine, _engine_key
    settings = load_settings()
    password = get_password()
    key = (
        settings["mysql_host"], int(settings["mysql_port"]),
        settings["mysql_database"], settings["mysql_user"], password,
    )
    if _engine is None or key != _engine_key:
        if _engine is not None:
            _engine.dispose()
        url = URL.create(
            "mysql+pymysql", username=key[3], password=password,
            host=key[0], port=key[1], database=key[2], query={"charset": "utf8mb4"},
        )
        _engine = create_engine(url, pool_pre_ping=True, pool_recycle=1800)
        _engine_key = key
    return _engine


def test_connection() -> dict[str, str]:
    with get_engine().connect() as connection:
        version = connection.execute(text("SELECT VERSION()")).scalar_one()
    return {"status": "connected", "version": str(version)}
