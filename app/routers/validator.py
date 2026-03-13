from fastapi import APIRouter, HTTPException
from app.models.validation import (
    ValidateRequest, ValidationResult,
    BatchValidateRequest, BatchValidationSummary, BatchMessageResult,
)
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


@router.post("/batch", response_model=BatchValidationSummary)
def validate_batch(req: BatchValidateRequest):
    if not req.messages:
        raise HTTPException(status_code=422, detail="No messages provided")
    try:
        profile = profile_service.get_profile(req.profile_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Profile '{req.profile_id}' not found")

    results: list[BatchMessageResult] = []
    for i, raw in enumerate(req.messages):
        preview = raw.strip()[:80]
        if not raw.strip().startswith("MSH|"):
            results.append(BatchMessageResult(
                index=i,
                raw_preview=preview,
                valid_format=False,
                error="Block does not start with MSH|",
            ))
            continue
        try:
            result = validator_service.validate(raw, profile)
            results.append(BatchMessageResult(
                index=i,
                raw_preview=preview,
                valid_format=True,
                result=result,
            ))
        except Exception as e:
            results.append(BatchMessageResult(
                index=i,
                raw_preview=preview,
                valid_format=True,
                error=str(e),
            ))

    valid_count   = sum(1 for r in results if r.valid_format and r.result and r.result.is_valid)
    invalid_count = sum(1 for r in results if r.valid_format and r.result and not r.result.is_valid)
    fmt_errors    = sum(1 for r in results if not r.valid_format or (r.valid_format and r.error))

    return BatchValidationSummary(
        profile_id=req.profile_id,
        total=len(results),
        valid=valid_count,
        invalid=invalid_count,
        format_errors=fmt_errors,
        results=results,
    )
