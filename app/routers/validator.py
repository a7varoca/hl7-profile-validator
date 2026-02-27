from fastapi import APIRouter, HTTPException
from app.models.validation import ValidateRequest, ValidationResult
from app.services import profile_service, validator_service

router = APIRouter()


@router.post("/", response_model=ValidationResult)
def validate_message(req: ValidateRequest):
    if not req.message.strip():
        raise HTTPException(status_code=422, detail="Message body is empty")
    try:
        profile = profile_service.get_profile(req.profile_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Profile '{req.profile_id}' not found")
    return validator_service.validate(req.message, profile)
