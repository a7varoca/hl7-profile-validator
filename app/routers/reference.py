from fastapi import APIRouter
from app.models.reference import DatatypeInfo, SegmentInfo, UsageCodeInfo
from app.services import reference_service

router = APIRouter()


@router.get("/datatypes", response_model=list[DatatypeInfo])
def list_datatypes():
    return reference_service.get_datatypes()


@router.get("/segments", response_model=list[SegmentInfo])
def list_segments():
    return reference_service.get_segments()


@router.get("/versions", response_model=list[str])
def list_versions():
    return reference_service.get_versions()


@router.get("/usage-codes", response_model=list[UsageCodeInfo])
def list_usage_codes():
    return reference_service.get_usage_codes()
