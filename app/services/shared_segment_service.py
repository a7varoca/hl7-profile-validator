"""
Shared segment library — save/load named segment definitions reusable across profiles.
"""
from __future__ import annotations
import copy
from datetime import date

from app.models.profile import SegmentDef, ValueSet
from app.services import db


def _today() -> str:
    return date.today().isoformat()


def list_shared() -> list[dict]:
    return db.shared_list()


def get_shared(shared_id: str) -> dict:
    entry = db.shared_get(shared_id)
    if entry is None:
        raise FileNotFoundError(f"Shared segment '{shared_id}' not found")
    return entry


def save_shared(shared_id: str, segment_def: SegmentDef,
                value_sets: dict, description: str | None = None) -> dict:
    """Save a SegmentDef (with its referenced value_sets) into the shared library."""
    if not shared_id or not shared_id.strip():
        raise ValueError("Shared segment ID is required")
    seg_data = segment_def.model_dump(mode="json")
    vs_data = {k: v.model_dump(mode="json") for k, v in value_sets.items()}
    db.shared_save(
        shared_id.strip(), segment_def.segment, description,
        _today(), seg_data, vs_data,
    )
    return db.shared_get(shared_id.strip())


def delete_shared(shared_id: str) -> None:
    db.shared_delete(shared_id)


def apply_shared_to_profile(profile_id: str, shared_id: str) -> "Profile":
    """
    Copy a shared segment (and its value_sets) into a profile.
    - Replaces the existing segment definition if one with the same name already exists.
    - Copies value_sets that don't already exist in the profile (no overwrite).
    Returns the updated Profile.
    """
    from app.services import profile_service

    entry = get_shared(shared_id)
    profile = profile_service._load(profile_id)

    # Build SegmentDef from stored data
    seg_def = SegmentDef.model_validate(entry["data"])

    # Remove existing segment with same name (will be replaced)
    from app.models.profile import GroupDef
    def _remove(nodes):
        return [n for n in nodes if not (isinstance(n, SegmentDef) and n.segment == seg_def.segment)]

    def _remove_recursive(nodes):
        result = []
        for n in nodes:
            if isinstance(n, SegmentDef) and n.segment == seg_def.segment:
                continue
            if isinstance(n, GroupDef):
                n = copy.copy(n)
                n.segments = _remove_recursive(n.segments)
            result.append(n)
        return result

    profile.structure = _remove_recursive(profile.structure)
    profile.structure.append(seg_def)

    # Copy value_sets that don't already exist
    for vs_name, vs_data in entry["value_sets"].items():
        if vs_name not in profile.value_sets:
            profile.value_sets[vs_name] = ValueSet.model_validate(vs_data)

    return profile_service._save(profile)
