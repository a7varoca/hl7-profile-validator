from __future__ import annotations
import yaml
from pathlib import Path
from datetime import date
from typing import Union

from app.config import settings
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


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_profile_cache: dict[str, Profile] = {}


def _profile_path(profile_id: str) -> Path:
    return settings.profiles_dir / f"{profile_id}.yaml"


def _today() -> str:
    return str(date.today())


def _serialize(profile: Profile) -> dict:
    """Convert Profile to a plain dict suitable for YAML serialization."""
    return profile.model_dump(mode="json", exclude_none=False)


def _deserialize(data: dict) -> Profile:
    return Profile.model_validate(data)


def _save(profile: Profile) -> Profile:
    profile.profile.updated_at = _today()
    path = _profile_path(profile.profile.id)
    path.write_text(
        yaml.dump(
            _serialize(profile),
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    _profile_cache[profile.profile.id] = profile
    return profile


def _load(profile_id: str) -> Profile:
    if profile_id in _profile_cache:
        return _profile_cache[profile_id]
    path = _profile_path(profile_id)
    if not path.exists():
        raise FileNotFoundError(f"Profile '{profile_id}' not found")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
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
    """Depth-first search through structure for a SegmentDef by name."""
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
    summaries = []
    for f in sorted(settings.profiles_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
            meta = data.get("profile", {})
            summaries.append(
                ProfileSummary(
                    id=meta.get("id", f.stem),
                    message_type=meta.get("message_type", ""),
                    trigger_event=meta.get("trigger_event", ""),
                    hl7_version=meta.get("hl7_version", ""),
                    description=meta.get("description"),
                    updated_at=meta.get("updated_at"),
                )
            )
        except Exception:
            continue
    return summaries


def get_profile(profile_id: str) -> Profile:
    return _load(profile_id)


def get_profile_yaml(profile_id: str) -> str:
    path = _profile_path(profile_id)
    if not path.exists():
        raise FileNotFoundError(f"Profile '{profile_id}' not found")
    return path.read_text(encoding="utf-8")


def create_profile(req: ProfileCreateRequest) -> Profile:
    base = f"{req.message_type}_{req.trigger_event}"
    suffix = f"_{req.name.strip().replace(' ', '_')}" if req.name and req.name.strip() else ""
    profile_id = f"{base}{suffix}"
    if _profile_path(profile_id).exists():
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


def duplicate_profile(source_id: str, new_name: str) -> Profile:
    source = _load(source_id)
    suffix = f"_{new_name.strip().replace(' ', '_')}" if new_name and new_name.strip() else "_copy"
    base = f"{source.profile.message_type}_{source.profile.trigger_event}"
    new_id = f"{base}{suffix}"
    if _profile_path(new_id).exists():
        raise ValueError(f"Profile '{new_id}' already exists")
    today = _today()
    source.profile.id = new_id
    source.profile.created_at = today
    source.profile.updated_at = today
    return _save(source)


def update_profile(profile_id: str, profile: Profile) -> Profile:
    if not _profile_path(profile_id).exists():
        raise FileNotFoundError(f"Profile '{profile_id}' not found")
    profile.profile.id = profile_id
    return _save(profile)


def delete_profile(profile_id: str) -> None:
    path = _profile_path(profile_id)
    if not path.exists():
        raise FileNotFoundError(f"Profile '{profile_id}' not found")
    path.unlink()
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
    # Check not already in structure at top level
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


# ---------------------------------------------------------------------------
# Field operations
# ---------------------------------------------------------------------------

def upsert_field(profile_id: str, segment_name: str, req: FieldUpsertRequest) -> Profile:
    profile = _load(profile_id)
    seg = _find_segment(profile.structure, segment_name)
    if not seg:
        raise FileNotFoundError(f"Segment '{segment_name}' not found in profile '{profile_id}'")
    # Remove existing field with same seq (upsert)
    seg.fields = [f for f in seg.fields if f.seq != req.seq]
    new_field = FieldDef(
        seq=req.seq,
        name=req.name,
        datatype=req.datatype,
        usage=req.usage,
        min_length=req.min_length,
        max_length=req.max_length,
        description=req.description,
        notes=req.notes,
        value_set=req.value_set,
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
