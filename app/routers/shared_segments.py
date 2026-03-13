from fastapi import APIRouter, HTTPException
from typing import Optional
from pydantic import BaseModel
from app.services import shared_segment_service, profile_service
from app.models.profile import Profile

router = APIRouter()


class SaveSharedRequest(BaseModel):
    shared_id: str
    description: Optional[str] = None


class ApplySharedRequest(BaseModel):
    shared_id: str


@router.get("/", response_model=list[dict])
def list_shared():
    return shared_segment_service.list_shared()


@router.get("/{shared_id}")
def get_shared(shared_id: str):
    try:
        return shared_segment_service.get_shared(shared_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/from-profile/{profile_id}/segments/{segment_name}", response_model=dict)
def save_from_profile(profile_id: str, segment_name: str, req: SaveSharedRequest):
    """Save a segment from an existing profile into the shared library."""
    try:
        profile = profile_service.get_profile(profile_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    from app.services.profile_service import _find_segment
    seg_def = _find_segment(profile.structure, segment_name)
    if seg_def is None:
        raise HTTPException(status_code=404, detail=f"Segment '{segment_name}' not found in profile")

    referenced_vs = shared_segment_service.collect_referenced_value_sets(seg_def)
    vs_to_save = {k: v for k, v in profile.value_sets.items() if k in referenced_vs}

    try:
        return shared_segment_service.save_shared(req.shared_id, seg_def, vs_to_save, req.description)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.delete("/{shared_id}", status_code=204)
def delete_shared(shared_id: str):
    try:
        shared_segment_service.delete_shared(shared_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/apply-to-profile/{profile_id}", response_model=Profile)
def apply_to_profile(profile_id: str, req: ApplySharedRequest):
    """Copy a shared segment into a profile (snapshot)."""
    try:
        return shared_segment_service.apply_shared_to_profile(profile_id, req.shared_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
