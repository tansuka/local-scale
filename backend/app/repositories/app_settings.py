from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AppSettings


def get_app_settings(db: Session) -> AppSettings:
    settings = db.scalar(select(AppSettings).limit(1))
    if settings is None:
        settings = AppSettings(id=1)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def update_app_settings(
    db: Session,
    *,
    llm_base_url: str,
    llm_model: str,
    api_key: str | None,
    clear_api_key: bool = False,
) -> AppSettings:
    settings = get_app_settings(db)
    settings.llm_base_url = llm_base_url
    settings.llm_model = llm_model
    if clear_api_key:
        settings.llm_api_key = None
    elif api_key is not None:
        settings.llm_api_key = api_key
    db.commit()
    db.refresh(settings)
    return settings
