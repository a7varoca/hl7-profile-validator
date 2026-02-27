from pydantic import BaseModel
from typing import Optional


class DatatypeInfo(BaseModel):
    code: str
    name: str
    description: Optional[str] = None


class SegmentInfo(BaseModel):
    code: str
    name: str
    description: Optional[str] = None


class UsageCodeInfo(BaseModel):
    code: str
    name: str
    description: str
