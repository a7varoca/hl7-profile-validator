from pydantic import BaseModel
from typing import Optional


class ValidationError(BaseModel):
    severity: str           # ERROR | WARNING
    segment: str            # e.g. "PID"
    field: str              # e.g. "PID.5"
    seq: int                # field sequence number (0 = segment-level)
    value: str              # actual value found in the message
    rule: str               # rule code: FIELD_REQUIRED, INVALID_CODE, etc.
    message: str            # human-readable description


class ValidationResult(BaseModel):
    profile_id: str
    hl7_version: str
    message_type: str       # extracted from MSH.9
    is_valid: bool
    error_count: int
    warning_count: int
    errors: list[ValidationError]
    warnings: list[ValidationError]
    segments_found: list[str]
    segments_not_in_profile: list[str]


class ValidateRequest(BaseModel):
    profile_id: str
    message: str            # raw HL7 v2.x pipe-delimited message


class BatchMessageResult(BaseModel):
    index: int
    raw_preview: str        # first ~80 chars of the message for identification
    valid_format: bool      # False if block doesn't start with MSH|
    result: Optional[ValidationResult] = None
    error: Optional[str] = None  # format error description


class BatchValidateRequest(BaseModel):
    profile_id: str
    messages: list[str]     # list of raw HL7 messages


class BatchValidationSummary(BaseModel):
    profile_id: str
    total: int
    valid: int
    invalid: int
    format_errors: int
    results: list[BatchMessageResult]
