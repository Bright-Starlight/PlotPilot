"""Chapter state lock APIs."""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from application.core.services.state_lock_service import StateLockService
from interfaces.api.dependencies import get_state_lock_service

router = APIRouter(tags=["state-locks"])


class StateLockEntryModel(BaseModel):
    key: str
    label: str
    value: Any
    source: str = "manual"
    kind: str = "constraint"
    status: str = "normal"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class StateLockGroupModel(BaseModel):
    entries: List[StateLockEntryModel] = Field(default_factory=list)


class GenerateStateLocksRequest(BaseModel):
    plan_version: int | None = Field(default=None, gt=0)


class UpdateStateLocksRequest(BaseModel):
    change_reason: str = Field(..., min_length=1)
    time_lock: StateLockGroupModel = Field(default_factory=StateLockGroupModel)
    location_lock: StateLockGroupModel = Field(default_factory=StateLockGroupModel)
    character_lock: StateLockGroupModel = Field(default_factory=StateLockGroupModel)
    item_lock: StateLockGroupModel = Field(default_factory=StateLockGroupModel)
    numeric_lock: StateLockGroupModel = Field(default_factory=StateLockGroupModel)
    event_lock: StateLockGroupModel = Field(default_factory=StateLockGroupModel)
    ending_lock: StateLockGroupModel = Field(default_factory=StateLockGroupModel)


class StateLockSnapshotResponse(BaseModel):
    state_lock_id: str
    chapter_id: str
    version: int
    plan_version: int
    source: str
    change_reason: str = ""
    changed_fields: List[str] = Field(default_factory=list)
    inference_notes: List[str] = Field(default_factory=list)
    critical_change: Dict[str, Any] = Field(default_factory=dict)
    time_lock: StateLockGroupModel = Field(default_factory=StateLockGroupModel)
    location_lock: StateLockGroupModel = Field(default_factory=StateLockGroupModel)
    character_lock: StateLockGroupModel = Field(default_factory=StateLockGroupModel)
    item_lock: StateLockGroupModel = Field(default_factory=StateLockGroupModel)
    numeric_lock: StateLockGroupModel = Field(default_factory=StateLockGroupModel)
    event_lock: StateLockGroupModel = Field(default_factory=StateLockGroupModel)
    ending_lock: StateLockGroupModel = Field(default_factory=StateLockGroupModel)


def _to_response(snapshot) -> StateLockSnapshotResponse:
    return StateLockSnapshotResponse(
        state_lock_id=snapshot.state_lock_id,
        chapter_id=snapshot.chapter_id,
        version=snapshot.version,
        plan_version=snapshot.plan_version,
        source=snapshot.source,
        change_reason=snapshot.change_reason,
        changed_fields=list(snapshot.changed_fields or []),
        inference_notes=list(snapshot.inference_notes or []),
        critical_change=dict(snapshot.critical_change or {}),
        **{key: snapshot.locks.get(key, {"entries": []}) for key in (
            "time_lock",
            "location_lock",
            "character_lock",
            "item_lock",
            "numeric_lock",
            "event_lock",
            "ending_lock",
        )},
    )


@router.post("/chapters/{chapter_id}/state-locks", response_model=StateLockSnapshotResponse, status_code=201)
async def generate_state_locks(
    chapter_id: str,
    request: GenerateStateLocksRequest,
    service: StateLockService = Depends(get_state_lock_service),
):
    try:
        snapshot = await service.generate_state_locks(chapter_id, plan_version=request.plan_version)
        return _to_response(snapshot)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/chapters/{chapter_id}/state-locks/current", response_model=StateLockSnapshotResponse)
async def get_current_state_locks(
    chapter_id: str,
    service: StateLockService = Depends(get_state_lock_service),
):
    try:
        snapshot = service.get_current_state_locks(chapter_id)
        return _to_response(snapshot)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.patch("/state-locks/{state_lock_id}", response_model=StateLockSnapshotResponse)
async def update_state_locks(
    state_lock_id: str,
    request: UpdateStateLocksRequest,
    service: StateLockService = Depends(get_state_lock_service),
):
    try:
        snapshot = service.update_state_locks(
            state_lock_id,
            locks=request.model_dump(exclude={"change_reason"}),
            change_reason=request.change_reason,
        )
        return _to_response(snapshot)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
