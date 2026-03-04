from __future__ import annotations

import json
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import Any

_cache_lock = threading.Lock()

from app.config import settings
from app.models.profile import (
    FieldDef,
    GroupDef,
    Profile,
    ProfileMetadata,
    SegmentDef,
    UsageCode,
    ValueCode,
    ValueSet,
)
from app.services.profile_service import _save

_HL7_API_BASE = "https://hl7-definition.caristix.com/v2-api/1"

HL7_VERSIONS = ["2.8", "2.7", "2.6", "2.5.1", "2.5", "2.4", "2.3.1", "2.3", "2.2", "2.1"]


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_path(version: str, *parts: str) -> Path:
    return settings.hl7standard_cache_dir / f"HL7v{version}" / Path(*parts)


def _load_cache(path: Path) -> Any | None:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def _save_cache(path: Path, data: Any) -> None:
    with _cache_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# HTTP fetch
# ---------------------------------------------------------------------------

def _fetch(url: str) -> Any:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_trigger_events(version: str) -> list[dict]:
    cache = _cache_path(version, "TriggerEvents.json")
    data = _load_cache(cache)
    if data is None:
        data = _fetch(f"{_HL7_API_BASE}/HL7v{version}/TriggerEvents")
        _save_cache(cache, data)
    return data


def get_trigger_event(version: str, event_id: str) -> dict:
    cache = _cache_path(version, "trigger_events", f"{event_id}.json")
    data = _load_cache(cache)
    if data is None:
        data = _fetch(f"{_HL7_API_BASE}/HL7v{version}/TriggerEvents/{event_id}")
        _save_cache(cache, data)
    return data


def get_segment(version: str, segment_name: str) -> dict:
    cache = _cache_path(version, "segments", f"{segment_name}.json")
    data = _load_cache(cache)
    if data is None:
        data = _fetch(f"{_HL7_API_BASE}/HL7v{version}/Segments/{segment_name}")
        _save_cache(cache, data)
    return data


def get_field(version: str, field_id: str) -> dict:
    """Fetch full field detail (includes description and tableId) for a single field."""
    cache = _cache_path(version, "fields", f"{field_id}.json")
    data = _load_cache(cache)
    if data is None:
        data = _fetch(f"{_HL7_API_BASE}/HL7v{version}/Fields/{field_id}")
        _save_cache(cache, data)
    return data


def get_table(version: str, table_id: str) -> dict:
    """Fetch HL7 table (value set) by table ID."""
    cache = _cache_path(version, "tables", f"{table_id}.json")
    data = _load_cache(cache)
    if data is None:
        data = _fetch(f"{_HL7_API_BASE}/HL7v{version}/Tables/{table_id}")
        _save_cache(cache, data)
    return data


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------

def _map_usage(raw: str | None) -> UsageCode:
    mapping = {"R": UsageCode.R, "RE": UsageCode.RE, "O": UsageCode.O,
               "C": UsageCode.C, "X": UsageCode.X}
    return mapping.get((raw or "").upper(), UsageCode.O)


def _map_max(rpt: str | None) -> int | str:
    if rpt in (None, "*", "∞"):
        return "*"
    try:
        return int(rpt)
    except (ValueError, TypeError):
        return "*"


def _vs_key(table_id: str, table_name: str) -> str:
    """Derive a clean value set key from table ID and name."""
    name_slug = (table_name or "").strip().replace(" ", "_")
    return f"HL7T{table_id}_{name_slug}" if name_slug else f"HL7T{table_id}"


def _fetch_field_data(version: str, f: dict) -> tuple[dict, str | None, str | None]:
    """Fetch field detail + table for a single field entry. Returns (f, description, vs_key)."""
    position = f.get("position", "")
    description: str | None = None
    vs_key: str | None = None
    table_id = f.get("tableId")

    try:
        field_detail = get_field(version, position)
        description = field_detail.get("description") or None
        table_id = field_detail.get("tableId") or table_id
    except Exception:
        pass

    if table_id:
        try:
            tbl = get_table(version, table_id)
            entries = tbl.get("entries") or []
            if entries:
                vs_key = _vs_key(table_id, tbl.get("name", ""))
        except Exception:
            pass

    return f, description, vs_key, table_id


def _build_fields(
    version: str,
    segment_name: str,
    value_sets: dict[str, ValueSet],
) -> list[FieldDef]:
    """Build fields for a segment, fetching field details in parallel."""
    try:
        seg_data = get_segment(version, segment_name)
    except Exception:
        return []

    raw_fields = seg_data.get("fields", [])
    if not raw_fields:
        return []

    results: list[tuple] = []
    with ThreadPoolExecutor(max_workers=20) as ex:
        futures = {ex.submit(_fetch_field_data, version, f): f for f in raw_fields}
        for fut in as_completed(futures):
            try:
                results.append(fut.result())
            except Exception:
                pass

    fields = []
    for f, description, vs_key, table_id in results:
        position = f.get("position", "")
        try:
            seq = int(position.split(".")[-1])
        except (ValueError, IndexError):
            continue

        if vs_key and vs_key not in value_sets and table_id:
            try:
                tbl = get_table(version, table_id)
                entries = tbl.get("entries") or []
                if entries:
                    value_sets[vs_key] = ValueSet(
                        description=tbl.get("name"),
                        codes=[
                            ValueCode(
                                code=e["value"],
                                display=e.get("description") or e["value"],
                                description=e.get("comment") or None,
                            )
                            for e in entries
                            if e.get("value")
                        ],
                    )
                else:
                    vs_key = None
            except Exception:
                vs_key = None

        fields.append(FieldDef(
            seq=seq,
            name=f.get("name", ""),
            datatype=f.get("dataType") or "ST",
            usage=_map_usage(f.get("usage")),
            min_length=f.get("length") or 0,
            max_length=f.get("length") or 999,
            value_set=vs_key,
        ))

    fields.sort(key=lambda fd: fd.seq)
    return fields


def _build_segment_node(version: str, item: dict, value_sets: dict[str, ValueSet]):
    """Build a single SegmentDef (called in thread pool)."""
    seg_name = item.get("name") or item.get("id", "")
    if not seg_name:
        return None
    usage = _map_usage(item.get("usage"))
    local_vs: dict[str, ValueSet] = {}
    fields = _build_fields(version, seg_name, local_vs)
    return item, SegmentDef(
        segment=seg_name,
        usage=usage,
        min=1 if usage == UsageCode.R else 0,
        max=_map_max(item.get("rpt")),
        description=item.get("longName") or None,
        fields=fields,
    ), local_vs


def _build_structure(
    version: str,
    segments: list[dict],
    value_sets: dict[str, ValueSet],
) -> list:
    # Separate groups from plain segments so we can parallelize plain segments
    plain_items = [(i, item) for i, item in enumerate(segments) if not item.get("isGroup")]
    group_items = [(i, item) for i, item in enumerate(segments) if item.get("isGroup")]

    # Process plain segments in parallel
    seg_results: dict[int, SegmentDef] = {}
    if plain_items:
        with ThreadPoolExecutor(max_workers=10) as ex:
            futures = {ex.submit(_build_segment_node, version, item, value_sets): idx
                       for idx, item in plain_items}
            for fut in as_completed(futures):
                idx = futures[fut]
                try:
                    result = fut.result()
                    if result:
                        _, seg_def, local_vs = result
                        seg_results[idx] = seg_def
                        value_sets.update(local_vs)
                except Exception:
                    pass

    # Process groups recursively (order preserved)
    group_results: dict[int, GroupDef] = {}
    for idx, item in group_items:
        children = _build_structure(version, item.get("segments") or [], value_sets)
        group_results[idx] = GroupDef(
            group=item.get("name", "GROUP"),
            usage=_map_usage(item.get("usage")),
            min=1 if _map_usage(item.get("usage")) == UsageCode.R else 0,
            max=_map_max(item.get("rpt")),
            segments=children,
        )

    # Reconstruct in original order
    nodes = []
    for i, item in enumerate(segments):
        if i in seg_results:
            nodes.append(seg_results[i])
        elif i in group_results:
            nodes.append(group_results[i])
    return nodes


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_profile_from_standard(
    version: str,
    event_id: str,
    name: str = "",
    description: str = "",
    author: str = "",
) -> Profile:
    event = get_trigger_event(version, event_id)

    parts = event_id.split("_", 1)
    message_type = parts[0]
    trigger_event = parts[1] if len(parts) > 1 else event_id

    base_id = f"{message_type}_{trigger_event}"
    suffix = f"_{name.strip().replace(' ', '_')}" if name and name.strip() else ""
    profile_id = f"{base_id}{suffix}"

    value_sets: dict[str, ValueSet] = {}
    structure = _build_structure(version, event.get("segments") or [], value_sets)

    today = str(date.today())
    profile = Profile(
        profile=ProfileMetadata(
            id=profile_id,
            message_type=message_type,
            trigger_event=trigger_event,
            hl7_version=version,
            description=description or event.get("eventDesc") or None,
            author=author or None,
            created_at=today,
            updated_at=today,
        ),
        structure=structure,
        value_sets=value_sets,
    )
    return _save(profile)
