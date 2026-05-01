# pyright: reportImplicitRelativeImport=false, reportUnusedParameter=false
from __future__ import annotations

import json
from typing import Annotated
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.engine import CursorResult
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models import ProfileEvent, UserProfile
from schemas import ProfileCreate, ProfileEventResponse, ProfileResponse, ProfileUpdate

router = APIRouter()


@router.post("", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
def create_profile(
    payload: ProfileCreate,
    db: Annotated[Session, Depends(get_db)],
) -> ProfileResponse:
    profile = UserProfile(
        email=str(payload.email),
        display_name=payload.display_name,
        bio=payload.bio,
        version=1,
    )
    db.add(profile)
    try:
        db.flush()
        event = ProfileEvent(
            profile_id=profile.id,
            event_type="created",
            payload=json.dumps(
                {
                    "email": profile.email,
                    "display_name": profile.display_name,
                    "bio": profile.bio,
                },
                sort_keys=True,
            ),
            version=profile.version,
        )
        db.add(event)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")
    db.refresh(profile)
    return ProfileResponse.model_validate(profile)


@router.patch("/{profile_id}", response_model=ProfileResponse)
def update_profile(
    profile_id: int,
    payload: ProfileUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> ProfileResponse:
    profile = db.get(UserProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    if payload.expected_version != profile.version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Stale version")

    changed_fields: dict[str, str | None] = {}
    if "email" in payload.model_fields_set and payload.email is not None:
        email = str(payload.email)
        if email != profile.email:
            changed_fields["email"] = email

    if "display_name" in payload.model_fields_set and payload.display_name is not None:
        if payload.display_name != profile.display_name:
            changed_fields["display_name"] = payload.display_name

    if "bio" in payload.model_fields_set and payload.bio != profile.bio:
        changed_fields["bio"] = payload.bio

    if not changed_fields:
        return ProfileResponse.model_validate(profile)

    new_version = payload.expected_version + 1
    try:
        result = db.execute(
            update(UserProfile)
            .where(UserProfile.id == profile_id, UserProfile.version == payload.expected_version)
            .values(version=new_version, **changed_fields)
        )
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")
    if cast(CursorResult[object], result).rowcount == 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Stale version")

    event = ProfileEvent(
        profile_id=profile.id,
        event_type="updated",
        payload=json.dumps(changed_fields, sort_keys=True),
        version=new_version,
    )
    db.add(event)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Concurrent event conflict",
        )
    db.refresh(profile)
    return ProfileResponse.model_validate(profile)


@router.get("/{profile_id}", response_model=ProfileResponse)
def get_profile(profile_id: int, db: Annotated[Session, Depends(get_db)]) -> ProfileResponse:
    profile = db.get(UserProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return ProfileResponse.model_validate(profile)


@router.get("/{profile_id}/events", response_model=list[ProfileEventResponse])
def list_profile_events(
    profile_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> list[ProfileEventResponse]:
    profile = db.get(UserProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    stmt = (
        select(ProfileEvent)
        .where(ProfileEvent.profile_id == profile_id)
        .order_by(ProfileEvent.version.asc())
    )
    events = db.scalars(stmt).all()
    return [ProfileEventResponse.model_validate(event) for event in events]


@router.get("/{profile_id}/events/{version}", response_model=ProfileEventResponse)
def get_profile_event(
    profile_id: int,
    version: int,
    db: Annotated[Session, Depends(get_db)],
) -> ProfileEventResponse:
    stmt = select(ProfileEvent).where(
        ProfileEvent.profile_id == profile_id, ProfileEvent.version == version
    )
    event = db.scalar(stmt)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return ProfileEventResponse.model_validate(event)
