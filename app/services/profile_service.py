from __future__ import annotations

import yaml
from datetime import date
from typing import Union

from app.models.profile import (
    Profile,
    ProfileMetadata,
    ProfileSummary,
    ProfileCreateRequest,
    SegmentDef,
    GroupDef,
    FieldDef,
    FieldUpsertRequest,
    SegmentAddRequest,
    SegmentUpdateRequest,
    ValueSet,
    ValueSetUpsertRequest,
    UsageCode,
)
from app.services import db


# ---------------------------------------------------------------------------
# In-memory cache (warm copy of deserialized Profile objects)
# ---------------------------------------------------------------------------

_profile_cache: dict[str, Profile] = {}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _today() -> str:
    return str(date.today())


def _serialize(profile: Profile) -> dict:
    return profile.model_dump(mode="json", exclude_none=False)


def _deserialize(data: dict) -> Profile:
    return Profile.model_validate(data)


def _save(profile: Profile) -> Profile:
    profile.profile.updated_at = _today()
    data = _serialize(profile)
    db.save(profile.profile.id, data)
    _profile_cache[profile.profile.id] = profile
    return profile


def _load(profile_id: str) -> Profile:
    if profile_id in _profile_cache:
        return _profile_cache[profile_id]
    data = db.load(profile_id)  # raises FileNotFoundError if missing
    profile = _deserialize(data)
    _profile_cache[profile_id] = profile
    return profile


# ---------------------------------------------------------------------------
# Segment tree navigation helpers
# ---------------------------------------------------------------------------

def _find_segment(
    nodes: list[Union[SegmentDef, GroupDef]],
    segment_name: str,
) -> SegmentDef | None:
    for node in nodes:
        if isinstance(node, SegmentDef) and node.segment == segment_name:
            return node
        if isinstance(node, GroupDef):
            found = _find_segment(node.segments, segment_name)
            if found:
                return found
    return None


def _remove_segment(
    nodes: list[Union[SegmentDef, GroupDef]],
    segment_name: str,
) -> bool:
    for i, node in enumerate(nodes):
        if isinstance(node, SegmentDef) and node.segment == segment_name:
            nodes.pop(i)
            return True
        if isinstance(node, GroupDef):
            if _remove_segment(node.segments, segment_name):
                return True
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_profiles() -> list[ProfileSummary]:
    rows = db.list_summaries()
    return [
        ProfileSummary(
            id=r["id"],
            message_type=r["message_type"],
            trigger_event=r["trigger_event"],
            hl7_version=r["hl7_version"],
            description=r.get("description"),
            updated_at=r.get("updated_at"),
        )
        for r in rows
    ]


def get_profile(profile_id: str) -> Profile:
    return _load(profile_id)


def get_profile_yaml(profile_id: str) -> str:
    return db.load_yaml(profile_id)


def create_profile(req: ProfileCreateRequest) -> Profile:
    base = f"{req.message_type}_{req.trigger_event}"
    suffix = f"_{req.name.strip().replace(' ', '_')}" if req.name and req.name.strip() else ""
    profile_id = f"{base}{suffix}"
    if db.exists(profile_id):
        raise ValueError(f"Profile '{profile_id}' already exists")
    today = _today()
    profile = Profile(
        profile=ProfileMetadata(
            id=profile_id,
            message_type=req.message_type,
            trigger_event=req.trigger_event,
            hl7_version=req.hl7_version,
            description=req.description,
            author=req.author,
            created_at=today,
            updated_at=today,
        )
    )
    return _save(profile)


def duplicate_profile(source_id: str, new_name: str, message_type: str = None, trigger_event: str = None) -> Profile:
    source = _load(source_id)
    msg_type = (message_type or source.profile.message_type).strip().upper()
    trig = (trigger_event or source.profile.trigger_event).strip().upper()
    suffix = f"_{new_name.strip().replace(' ', '_')}" if new_name and new_name.strip() else "_copy"
    new_id = f"{msg_type}_{trig}{suffix}"
    if db.exists(new_id):
        raise ValueError(f"Profile '{new_id}' already exists")
    import copy
    dup = copy.deepcopy(source)
    today = _today()
    dup.profile.id = new_id
    dup.profile.message_type = msg_type
    dup.profile.trigger_event = trig
    dup.profile.created_at = today
    dup.profile.updated_at = today
    return _save(dup)


def rename_profile(profile_id: str, new_name: str, message_type: str = None, trigger_event: str = None) -> Profile:
    profile = _load(profile_id)
    msg_type = (message_type or profile.profile.message_type).strip().upper()
    trig = (trigger_event or profile.profile.trigger_event).strip().upper()
    suffix = f"_{new_name.strip().replace(' ', '_')}" if new_name and new_name.strip() else ""
    new_id = f"{msg_type}_{trig}{suffix}"
    if new_id != profile_id and db.exists(new_id):
        raise ValueError(f"Profile '{new_id}' already exists")
    db.delete(profile_id)
    _profile_cache.pop(profile_id, None)
    profile.profile.id = new_id
    profile.profile.message_type = msg_type
    profile.profile.trigger_event = trig
    return _save(profile)


def update_profile(profile_id: str, profile: Profile) -> Profile:
    if not db.exists(profile_id):
        raise FileNotFoundError(f"Profile '{profile_id}' not found")
    profile.profile.id = profile_id
    return _save(profile)


def delete_profile(profile_id: str) -> None:
    db.delete(profile_id)  # raises FileNotFoundError if missing
    _profile_cache.pop(profile_id, None)


def import_profile_yaml(yaml_content: str) -> Profile:
    data = yaml.safe_load(yaml_content)
    profile = _deserialize(data)
    return _save(profile)


# ---------------------------------------------------------------------------
# Segment operations
# ---------------------------------------------------------------------------

def add_segment(profile_id: str, req: SegmentAddRequest) -> Profile:
    profile = _load(profile_id)
    existing = _find_segment(profile.structure, req.segment)
    if existing:
        raise ValueError(f"Segment '{req.segment}' already exists in profile")
    seg = SegmentDef(
        segment=req.segment,
        usage=req.usage,
        min=req.min,
        max=req.max,
        description=req.description,
    )
    profile.structure.append(seg)
    return _save(profile)


def update_segment(profile_id: str, segment_name: str, req: SegmentUpdateRequest) -> Profile:
    profile = _load(profile_id)
    seg = _find_segment(profile.structure, segment_name)
    if not seg:
        raise FileNotFoundError(f"Segment '{segment_name}' not found in profile '{profile_id}'")
    if req.usage is not None:
        seg.usage = req.usage
    if req.min is not None:
        seg.min = req.min
    if req.max is not None:
        seg.max = req.max
    if req.description is not None:
        seg.description = req.description
    return _save(profile)


def delete_segment(profile_id: str, segment_name: str) -> Profile:
    profile = _load(profile_id)
    removed = _remove_segment(profile.structure, segment_name)
    if not removed:
        raise FileNotFoundError(f"Segment '{segment_name}' not found in profile '{profile_id}'")
    return _save(profile)


def _find_segment_index(
    nodes: list[Union[SegmentDef, GroupDef]],
    segment_name: str,
) -> tuple[list, int] | None:
    """Return (parent_list, index) for the first matching SegmentDef, searching recursively."""
    for i, node in enumerate(nodes):
        if isinstance(node, SegmentDef) and node.segment == segment_name:
            return nodes, i
        if isinstance(node, GroupDef):
            result = _find_segment_index(node.segments, segment_name)
            if result is not None:
                return result
    return None


def move_segment(profile_id: str, segment_name: str, direction: str) -> Profile:
    """Move a segment within its sibling list. direction: first|up|down|last."""
    profile = _load(profile_id)
    result = _find_segment_index(profile.structure, segment_name)
    if result is None:
        raise FileNotFoundError(f"Segment '{segment_name}' not found in profile '{profile_id}'")
    siblings, idx = result
    n = len(siblings)
    if direction == "first":
        new_idx = 0
    elif direction == "up":
        new_idx = max(0, idx - 1)
    elif direction == "down":
        new_idx = min(n - 1, idx + 1)
    elif direction == "last":
        new_idx = n - 1
    else:
        raise ValueError(f"Invalid direction '{direction}'")
    if new_idx == idx:
        return profile  # already at limit, nothing to save
    item = siblings.pop(idx)
    siblings.insert(new_idx, item)
    return _save(profile)


# ---------------------------------------------------------------------------
# Field operations
# ---------------------------------------------------------------------------

def upsert_field(profile_id: str, segment_name: str, req: FieldUpsertRequest) -> Profile:
    profile = _load(profile_id)
    seg = _find_segment(profile.structure, segment_name)
    if not seg:
        raise FileNotFoundError(f"Segment '{segment_name}' not found in profile '{profile_id}'")
    seg.fields = [f for f in seg.fields if f.seq != req.seq]
    new_field = FieldDef(
        seq=req.seq,
        name=req.name,
        datatype=req.datatype,
        usage=req.usage,
        repeatable=req.repeatable,
        min_length=req.min_length,
        max_length=req.max_length,
        description=req.description,
        notes=req.notes,
        value_set=req.value_set,
        format_pattern=req.format_pattern,
        components=req.components,
    )
    seg.fields.append(new_field)
    seg.fields.sort(key=lambda f: f.seq)
    return _save(profile)


def delete_field(profile_id: str, segment_name: str, seq: int) -> Profile:
    profile = _load(profile_id)
    seg = _find_segment(profile.structure, segment_name)
    if not seg:
        raise FileNotFoundError(f"Segment '{segment_name}' not found in profile '{profile_id}'")
    original_len = len(seg.fields)
    seg.fields = [f for f in seg.fields if f.seq != seq]
    if len(seg.fields) == original_len:
        raise FileNotFoundError(f"Field seq={seq} not found in segment '{segment_name}'")
    return _save(profile)


# ---------------------------------------------------------------------------
# Value set operations
# ---------------------------------------------------------------------------

def list_value_sets(profile_id: str) -> dict:
    profile = _load(profile_id)
    return profile.value_sets


def upsert_value_set(profile_id: str, vs_name: str, req: ValueSetUpsertRequest) -> Profile:
    profile = _load(profile_id)
    profile.value_sets[vs_name] = ValueSet(
        description=req.description,
        codes=req.codes,
    )
    return _save(profile)


def delete_value_set(profile_id: str, vs_name: str) -> Profile:
    profile = _load(profile_id)
    if vs_name not in profile.value_sets:
        raise FileNotFoundError(f"Value set '{vs_name}' not found in profile '{profile_id}'")
    del profile.value_sets[vs_name]
    return _save(profile)
