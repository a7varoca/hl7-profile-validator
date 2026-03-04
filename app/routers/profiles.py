from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import Response
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


def _not_found(e: Exception):
    raise HTTPException(status_code=404, detail=str(e))


def _conflict(e: Exception):
    raise HTTPException(status_code=409, detail=str(e))


# ---------------------------------------------------------------------------
# Profile CRUD
# ---------------------------------------------------------------------------

@router.get("/", response_model=list[ProfileSummary])
def list_profiles():
    return profile_service.list_profiles()


@router.post("/", response_model=Profile, status_code=201)
def create_profile(req: ProfileCreateRequest):
    try:
        return profile_service.create_profile(req)
    except ValueError as e:
        _conflict(e)


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
def get_profile_slim(profile_id: str):
    """Profile without value_sets — fast initial load."""
    try:
        p = profile_service.get_profile(profile_id)
        return ProfileSlim(profile=p.profile, structure=p.structure)
    except FileNotFoundError as e:
        _not_found(e)


@router.get("/{profile_id}", response_model=Profile)
def get_profile(profile_id: str):
    try:
        return profile_service.get_profile(profile_id)
    except FileNotFoundError as e:
        _not_found(e)


@router.put("/{profile_id}", response_model=Profile)
def update_profile(profile_id: str, profile: Profile):
    try:
        return profile_service.update_profile(profile_id, profile)
    except FileNotFoundError as e:
        _not_found(e)


@router.delete("/{profile_id}", status_code=204)
def delete_profile(profile_id: str):
    try:
        profile_service.delete_profile(profile_id)
    except FileNotFoundError as e:
        _not_found(e)


class DuplicateRequest(BaseModel):
    name: str


@router.post("/{profile_id}/duplicate", response_model=Profile, status_code=201)
def duplicate_profile(profile_id: str, req: DuplicateRequest):
    try:
        return profile_service.duplicate_profile(profile_id, req.name)
    except FileNotFoundError as e:
        _not_found(e)
    except ValueError as e:
        _conflict(e)


@router.get("/{profile_id}/export")
def export_profile(profile_id: str):
    try:
        yaml_content = profile_service.get_profile_yaml(profile_id)
    except FileNotFoundError as e:
        _not_found(e)
    return Response(
        content=yaml_content,
        media_type="application/x-yaml",
        headers={"Content-Disposition": f'attachment; filename="{profile_id}.yaml"'},
    )


# ---------------------------------------------------------------------------
# Segment operations
# ---------------------------------------------------------------------------

@router.post("/{profile_id}/segments", response_model=Profile)
def add_segment(profile_id: str, req: SegmentAddRequest):
    try:
        return profile_service.add_segment(profile_id, req)
    except FileNotFoundError as e:
        _not_found(e)
    except ValueError as e:
        _conflict(e)


@router.put("/{profile_id}/segments/{segment_name}", response_model=Profile)
def update_segment(profile_id: str, segment_name: str, req: SegmentUpdateRequest):
    try:
        return profile_service.update_segment(profile_id, segment_name, req)
    except FileNotFoundError as e:
        _not_found(e)


@router.delete("/{profile_id}/segments/{segment_name}", response_model=Profile)
def delete_segment(profile_id: str, segment_name: str):
    try:
        return profile_service.delete_segment(profile_id, segment_name)
    except FileNotFoundError as e:
        _not_found(e)


# ---------------------------------------------------------------------------
# Field operations
# ---------------------------------------------------------------------------

@router.post("/{profile_id}/segments/{segment_name}/fields", response_model=Profile)
def upsert_field(profile_id: str, segment_name: str, req: FieldUpsertRequest):
    try:
        return profile_service.upsert_field(profile_id, segment_name, req)
    except FileNotFoundError as e:
        _not_found(e)


@router.put("/{profile_id}/segments/{segment_name}/fields/{seq}", response_model=Profile)
def update_field(profile_id: str, segment_name: str, seq: int, req: FieldUpsertRequest):
    req.seq = seq
    try:
        return profile_service.upsert_field(profile_id, segment_name, req)
    except FileNotFoundError as e:
        _not_found(e)


@router.delete("/{profile_id}/segments/{segment_name}/fields/{seq}", response_model=Profile)
def delete_field(profile_id: str, segment_name: str, seq: int):
    try:
        return profile_service.delete_field(profile_id, segment_name, seq)
    except FileNotFoundError as e:
        _not_found(e)


# ---------------------------------------------------------------------------
# Value set operations
# ---------------------------------------------------------------------------

@router.get("/{profile_id}/value-sets", response_model=dict[str, ValueSet])
def list_value_sets(profile_id: str):
    try:
        return profile_service.list_value_sets(profile_id)
    except FileNotFoundError as e:
        _not_found(e)


@router.post("/{profile_id}/value-sets/{vs_name}", response_model=Profile)
def upsert_value_set(profile_id: str, vs_name: str, req: ValueSetUpsertRequest):
    try:
        return profile_service.upsert_value_set(profile_id, vs_name, req)
    except FileNotFoundError as e:
        _not_found(e)


@router.put("/{profile_id}/value-sets/{vs_name}", response_model=Profile)
def update_value_set(profile_id: str, vs_name: str, req: ValueSetUpsertRequest):
    try:
        return profile_service.upsert_value_set(profile_id, vs_name, req)
    except FileNotFoundError as e:
        _not_found(e)


@router.delete("/{profile_id}/value-sets/{vs_name}", response_model=Profile)
def delete_value_set(profile_id: str, vs_name: str):
    try:
        return profile_service.delete_value_set(profile_id, vs_name)
    except FileNotFoundError as e:
        _not_found(e)
