from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Profile
from app.schemas import ProfileCreate


def list_profiles(db: Session) -> list[Profile]:
    return list(db.scalars(select(Profile).order_by(Profile.name)).all())


def get_profile(db: Session, profile_id: int) -> Profile | None:
    return db.get(Profile, profile_id)


def get_profile_by_name(db: Session, name: str) -> Profile | None:
    return db.scalar(select(Profile).where(Profile.name == name))


def create_profile(db: Session, payload: ProfileCreate) -> Profile:
    profile = Profile(**payload.model_dump())
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def update_profile(db: Session, profile: Profile, payload: ProfileCreate) -> Profile:
    for key, value in payload.model_dump().items():
        setattr(profile, key, value)
    db.commit()
    db.refresh(profile)
    return profile
