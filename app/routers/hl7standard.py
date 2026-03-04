from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.models.profile import Profile
from app.services import hl7standard_service

router = APIRouter()


class ImportRequest(BaseModel):
    version: str
    event_id: str
    name: Optional[str] = ""
    description: Optional[str] = ""
    author: Optional[str] = ""


@router.get("/versions")
def list_versions():
    return hl7standard_service.HL7_VERSIONS


@router.get("/trigger-events")
def list_trigger_events(version: str = Query(...)):
    try:
        return hl7standard_service.get_trigger_events(version)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"HL7 standard API error: {e}")


@router.post("/import", response_model=Profile, status_code=201)
def import_from_standard(req: ImportRequest):
    try:
        return hl7standard_service.build_profile_from_standard(
            version=req.version,
            event_id=req.event_id,
            name=req.name or "",
            description=req.description or "",
            author=req.author or "",
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"HL7 standard API error: {e}")
