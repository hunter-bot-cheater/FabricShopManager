from __future__ import annotations

import keyring

from app.core.settings import APP_NAME, load_settings


def _account() -> str:
    return f"{load_settings()['mysql_user']}@{load_settings()['mysql_host']}"


def get_password() -> str:
    return keyring.get_password(APP_NAME, _account()) or ""


def save_password(password: str) -> None:
    if password:
        keyring.set_password(APP_NAME, _account(), password)
    else:
        keyring.delete_password(APP_NAME, _account())
