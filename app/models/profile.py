from __future__ import annotations
from typing import Optional, List, Union, Dict
from pydantic import BaseModel, Field
from enum import Enum


class UsageCode(str, Enum):
    R  = "R"    # Required
    RE = "RE"   # Required but may be Empty
    O  = "O"    # Optional
    C  = "C"    # Conditional
    X  = "X"    # Not Supported


class ValueCode(BaseModel):
    code: str
    display: str
    description: Optional[str] = None


class ValueSet(BaseModel):
    description: Optional[str] = None
    codes: List[ValueCode] = Field(default_factory=list)


class ComponentDef(BaseModel):
    seq: int           # component position (1-based)
    name: str
    datatype: str
    usage: UsageCode = UsageCode.O
    repeatable: bool = False
    value_set: Optional[str] = None  # references a key in profile.value_sets
    components: List["ComponentDef"] = Field(default_factory=list)  # subcomponents


ComponentDef.model_rebuild()


class FieldDef(BaseModel):
    seq: int
    name: str
    datatype: str
    usage: UsageCode = UsageCode.O
    repeatable: bool = False
    min_length: int = 0
    max_length: int = 999
    description: Optional[str] = None
    notes: Optional[str] = None
    value_set: Optional[str] = None  # references a key in profile.value_sets
    components: List["ComponentDef"] = Field(default_factory=list)


class SegmentDef(BaseModel):
    segment: str
    usage: UsageCode = UsageCode.O
    min: int = 0
    max: Union[int, str] = 1
    description: Optional[str] = None
    fields: List[FieldDef] = Field(default_factory=list)


class GroupDef(BaseModel):
    group: str
    usage: UsageCode = UsageCode.O
    min: int = 0
    max: Union[int, str] = 1
    description: Optional[str] = None
    segments: List[Union[SegmentDef, "GroupDef"]] = Field(default_factory=list)


GroupDef.model_rebuild()


class ProfileMetadata(BaseModel):
    id: str
    message_type: str
    trigger_event: str
    hl7_version: str = "2.5.1"
    description: Optional[str] = None
    author: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class Profile(BaseModel):
    profile: ProfileMetadata
    value_sets: Dict[str, ValueSet] = Field(default_factory=dict)
    structure: List[Union[SegmentDef, GroupDef]] = Field(default_factory=list)


class ProfileSlim(BaseModel):
    """Profile without value_sets — for fast initial load."""
    profile: ProfileMetadata
    structure: List[Union[SegmentDef, GroupDef]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Request / Response shapes for the API
# ---------------------------------------------------------------------------

class ProfileSummary(BaseModel):
    id: str
    message_type: str
    trigger_event: str
    hl7_version: str
    description: Optional[str] = None
    updated_at: Optional[str] = None


class ProfileCreateRequest(BaseModel):
    message_type: str
    trigger_event: str
    hl7_version: str = "2.7"
    description: Optional[str] = None
    author: Optional[str] = None
    name: Optional[str] = None  # custom suffix to allow multiple profiles per message type


class SegmentAddRequest(BaseModel):
    segment: str
    usage: UsageCode = UsageCode.O
    min: int = 0
    max: Union[int, str] = 1
    description: Optional[str] = None


class SegmentUpdateRequest(BaseModel):
    usage: Optional[UsageCode] = None
    min: Optional[int] = None
    max: Optional[Union[int, str]] = None
    description: Optional[str] = None


class FieldUpsertRequest(BaseModel):
    seq: int
    name: str
    datatype: str
    usage: UsageCode = UsageCode.O
    repeatable: bool = False
    min_length: int = 0
    max_length: int = 999
    description: Optional[str] = None
    notes: Optional[str] = None
    value_set: Optional[str] = None
    components: List[ComponentDef] = Field(default_factory=list)


class ValueSetUpsertRequest(BaseModel):
    description: Optional[str] = None
    codes: List[ValueCode] = Field(default_factory=list)
