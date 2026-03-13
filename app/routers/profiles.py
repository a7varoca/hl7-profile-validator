from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import Response
from functools import wraps
from inspect import iscoroutinefunction
from typing import Optional
from pydantic import BaseModel
from app.models.profile import (
    Profile,
    ProfileSlim,
    ProfileSummary,
    ProfileCreateRequest,
    SegmentAddRequest,
    SegmentUpdateRequest,
    FieldUpsertRequest,
    ValueSet,
    ValueSetUpsertRequest,
)
from app.services import profile_service

router = APIRouter()


def _handle_errors(fn):
    if iscoroutinefunction(fn):
        @wraps(fn)
        async def async_wrapper(*args, **kwargs):
            try:
                return await fn(*args, **kwargs)
            except FileNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))
            except ValueError as e:
                raise HTTPException(status_code=409, detail=str(e))
        return async_wrapper

    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
    return wrapper


# ---------------------------------------------------------------------------
# Profile CRUD
# ---------------------------------------------------------------------------

@router.get("/", response_model=list[ProfileSummary])
def list_profiles():
    return profile_service.list_profiles()


@router.post("/", response_model=Profile, status_code=201)
@_handle_errors
def create_profile(req: ProfileCreateRequest):
    return profile_service.create_profile(req)


@router.get("/import", include_in_schema=False)
def import_placeholder():
    raise HTTPException(status_code=405, detail="Use POST /import")


@router.post("/import", response_model=Profile, status_code=201)
async def import_profile(file: UploadFile = File(...)):
    content = (await file.read()).decode("utf-8")
    try:
        return profile_service.import_profile_yaml(content)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid YAML: {e}")


@router.get("/{profile_id}/slim", response_model=ProfileSlim)
@_handle_errors
def get_profile_slim(profile_id: str):
    """Profile without value_sets — fast initial load."""
    p = profile_service.get_profile(profile_id)
    return ProfileSlim(profile=p.profile, structure=p.structure)


@router.get("/{profile_id}", response_model=Profile)
@_handle_errors
def get_profile(profile_id: str):
    return profile_service.get_profile(profile_id)


@router.put("/{profile_id}", response_model=Profile)
@_handle_errors
def update_profile(profile_id: str, profile: Profile):
    return profile_service.update_profile(profile_id, profile)


@router.delete("/{profile_id}", status_code=204)
@_handle_errors
def delete_profile(profile_id: str):
    profile_service.delete_profile(profile_id)


class DuplicateRequest(BaseModel):
    name: str
    message_type: Optional[str] = None
    trigger_event: Optional[str] = None


class RenameRequest(BaseModel):
    name: str
    message_type: Optional[str] = None
    trigger_event: Optional[str] = None


@router.post("/{profile_id}/duplicate", response_model=Profile, status_code=201)
@_handle_errors
def duplicate_profile(profile_id: str, req: DuplicateRequest):
    return profile_service.duplicate_profile(profile_id, req.name, req.message_type, req.trigger_event)


@router.post("/{profile_id}/rename", response_model=Profile)
@_handle_errors
def rename_profile(profile_id: str, req: RenameRequest):
    return profile_service.rename_profile(profile_id, req.name, req.message_type, req.trigger_event)


@router.get("/{profile_id}/export")
@_handle_errors
def export_profile(profile_id: str):
    yaml_content = profile_service.get_profile_yaml(profile_id)
    return Response(
        content=yaml_content,
        media_type="application/x-yaml",
        headers={"Content-Disposition": f'attachment; filename="{profile_id}.yaml"'},
    )


# ---------------------------------------------------------------------------
# Segment operations
# ---------------------------------------------------------------------------

@router.post("/{profile_id}/segments", response_model=Profile)
@_handle_errors
def add_segment(profile_id: str, req: SegmentAddRequest):
    return profile_service.add_segment(profile_id, req)


@router.put("/{profile_id}/segments/{segment_name}", response_model=Profile)
@_handle_errors
def update_segment(profile_id: str, segment_name: str, req: SegmentUpdateRequest):
    return profile_service.update_segment(profile_id, segment_name, req)


@router.delete("/{profile_id}/segments/{segment_name}", response_model=Profile)
@_handle_errors
def delete_segment(profile_id: str, segment_name: str):
    return profile_service.delete_segment(profile_id, segment_name)


class MoveSegmentRequest(BaseModel):
    direction: str  # first | up | down | last


@router.post("/{profile_id}/segments/{segment_name}/move", response_model=Profile)
@_handle_errors
def move_segment(profile_id: str, segment_name: str, req: MoveSegmentRequest):
    return profile_service.move_segment(profile_id, segment_name, req.direction)


# ---------------------------------------------------------------------------
# Field operations
# ---------------------------------------------------------------------------

@router.post("/{profile_id}/segments/{segment_name}/fields", response_model=Profile)
@_handle_errors
def upsert_field(profile_id: str, segment_name: str, req: FieldUpsertRequest):
    return profile_service.upsert_field(profile_id, segment_name, req)


@router.put("/{profile_id}/segments/{segment_name}/fields/{seq}", response_model=Profile)
@_handle_errors
def update_field(profile_id: str, segment_name: str, seq: int, req: FieldUpsertRequest):
    req.seq = seq
    return profile_service.upsert_field(profile_id, segment_name, req)


@router.delete("/{profile_id}/segments/{segment_name}/fields/{seq}", response_model=Profile)
@_handle_errors
def delete_field(profile_id: str, segment_name: str, seq: int):
    return profile_service.delete_field(profile_id, segment_name, seq)


# ---------------------------------------------------------------------------
# Value set operations
# ---------------------------------------------------------------------------

@router.get("/{profile_id}/value-sets", response_model=dict[str, ValueSet])
@_handle_errors
def list_value_sets(profile_id: str):
    return profile_service.list_value_sets(profile_id)


@router.post("/{profile_id}/value-sets/{vs_name}", response_model=Profile)
@_handle_errors
def upsert_value_set(profile_id: str, vs_name: str, req: ValueSetUpsertRequest):
    return profile_service.upsert_value_set(profile_id, vs_name, req)


@router.delete("/{profile_id}/value-sets/{vs_name}", response_model=Profile)
@_handle_errors
def delete_value_set(profile_id: str, vs_name: str):
    return profile_service.delete_value_set(profile_id, vs_name)
