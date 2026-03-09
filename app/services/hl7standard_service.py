from __future__ import annotations

import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Any

from app.models.profile import (
    ComponentDef,
    FieldDef,
    GroupDef,
    Profile,
    ProfileMetadata,
    SegmentDef,
    UsageCode,
    ValueCode,
    ValueSet,
)
from app.services import db
from app.services.profile_service import _save

_HL7_API_BASE = "https://hl7-definition.caristix.com/v2-api/1"

HL7_VERSIONS = ["2.8", "2.7", "2.6", "2.5.1", "2.5", "2.4", "2.3.1", "2.3", "2.2", "2.1"]


# ---------------------------------------------------------------------------
# HTTP fetch
# ---------------------------------------------------------------------------

def _fetch(url: str) -> Any:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Raw API cache (SQLite-backed, replaces file-based hl7standard_cache/)
# ---------------------------------------------------------------------------

def _raw_get(version: str, resource_type: str, resource_id: str) -> Any | None:
    return db.hl7_raw_get(f"HL7v{version}", resource_type, resource_id)


def _raw_set(version: str, resource_type: str, resource_id: str, data: Any) -> None:
    db.hl7_raw_set(f"HL7v{version}", resource_type, resource_id, data)


# ---------------------------------------------------------------------------
# Public API (cached)
# ---------------------------------------------------------------------------

def get_trigger_events(version: str) -> list[dict]:
    cached = _raw_get(version, "root", "TriggerEvents")
    if cached is not None:
        return cached
    data = _fetch(f"{_HL7_API_BASE}/HL7v{version}/TriggerEvents")
    _raw_set(version, "root", "TriggerEvents", data)
    return data


def get_trigger_event(version: str, event_id: str) -> dict:
    cached = _raw_get(version, "trigger_events", event_id)
    if cached is not None:
        return cached
    data = _fetch(f"{_HL7_API_BASE}/HL7v{version}/TriggerEvents/{event_id}")
    _raw_set(version, "trigger_events", event_id, data)
    return data


def get_segment(version: str, segment_name: str) -> dict:
    cached = _raw_get(version, "segments", segment_name)
    if cached is not None:
        return cached
    data = _fetch(f"{_HL7_API_BASE}/HL7v{version}/Segments/{segment_name}")
    _raw_set(version, "segments", segment_name, data)
    return data


def get_field(version: str, field_id: str) -> dict:
    cached = _raw_get(version, "fields", field_id)
    if cached is not None:
        return cached
    data = _fetch(f"{_HL7_API_BASE}/HL7v{version}/Fields/{field_id}")
    _raw_set(version, "fields", field_id, data)
    return data


def get_table(version: str, table_id: str) -> dict:
    cached = _raw_get(version, "tables", table_id)
    if cached is not None:
        return cached
    data = _fetch(f"{_HL7_API_BASE}/HL7v{version}/Tables/{table_id}")
    _raw_set(version, "tables", table_id, data)
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
    name_slug = (table_name or "").strip().replace(" ", "_")
    return f"HL7T{table_id}_{name_slug}" if name_slug else f"HL7T{table_id}"


def _fetch_table_vs_key(version: str, table_id: str | None) -> str | None:
    if not table_id:
        return None
    try:
        tbl = get_table(version, table_id)
        if tbl.get("entries"):
            return _vs_key(table_id, tbl.get("name", ""))
    except Exception:
        pass
    return None


def _fetch_field_data(version: str, f: dict) -> tuple:
    position = f.get("position", "")
    description: str | None = None
    vs_key: str | None = None
    table_id = f.get("tableId")
    components_raw: list[dict] = []

    try:
        field_detail = get_field(version, position)
        description = field_detail.get("description") or None
        table_id = field_detail.get("tableId") or table_id
        components_raw = field_detail.get("fields") or []
    except Exception:
        pass

    if table_id:
        vs_key = _fetch_table_vs_key(version, table_id)

    return f, description, vs_key, table_id, components_raw


def _register_vs(
    version: str,
    table_id: str | None,
    vs_key: str | None,
    value_sets: dict[str, ValueSet],
) -> str | None:
    if not vs_key or not table_id or vs_key in value_sets:
        return vs_key
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
            return None
    except Exception:
        return None
    return vs_key


def _build_components(
    version: str,
    components_raw: list[dict],
    value_sets: dict[str, ValueSet],
) -> list[ComponentDef]:
    if not components_raw:
        return []

    def _fetch_component(c: dict) -> tuple[dict, str | None, str | None, list]:
        position = c.get("position", "")
        table_id = c.get("tableId")
        sub_raw: list[dict] = []
        try:
            detail = get_field(version, position)
            table_id = detail.get("tableId") or table_id
            sub_raw = detail.get("fields") or []
        except Exception:
            pass
        vs_key = _fetch_table_vs_key(version, table_id)
        return c, vs_key, table_id, sub_raw

    comp_results = []
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(_fetch_component, c): c for c in components_raw}
        for fut in as_completed(futures):
            try:
                comp_results.append(fut.result())
            except Exception:
                pass

    components = []
    for c, vs_key, table_id, sub_raw in comp_results:
        position = c.get("position", "")
        try:
            seq = int(position.split(".")[-1])
        except (ValueError, IndexError):
            continue

        vs_key = _register_vs(version, table_id, vs_key, value_sets)
        subcomponents = _build_components(version, sub_raw, value_sets) if sub_raw else []

        rpt = c.get("rpt") or "1"
        components.append(ComponentDef(
            seq=seq,
            name=c.get("name", ""),
            datatype=c.get("dataType") or "ST",
            usage=_map_usage(c.get("usage")),
            repeatable=rpt not in ("1", "0", None),
            value_set=vs_key,
            components=subcomponents,
        ))

    components.sort(key=lambda cd: cd.seq)
    return components


def _build_fields(
    version: str,
    segment_name: str,
    value_sets: dict[str, ValueSet],
) -> list[FieldDef]:
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
    for f, description, vs_key, table_id, components_raw in results:
        position = f.get("position", "")
        try:
            seq = int(position.split(".")[-1])
        except (ValueError, IndexError):
            continue

        vs_key = _register_vs(version, table_id, vs_key, value_sets)
        components = _build_components(version, components_raw, value_sets)

        rpt = f.get("rpt") or "1"
        fields.append(FieldDef(
            seq=seq,
            name=f.get("name", ""),
            datatype=f.get("dataType") or "ST",
            usage=_map_usage(f.get("usage")),
            repeatable=rpt not in ("1", "0", None),
            min_length=f.get("length") or 0,
            max_length=f.get("length") or 999,
            value_set=vs_key,
            components=components,
            description=description,
        ))

    fields.sort(key=lambda fd: fd.seq)
    return fields


# ---------------------------------------------------------------------------
# Segment builder with SQLite cache
# ---------------------------------------------------------------------------

def _build_segment_node(version: str, item: dict, value_sets: dict[str, ValueSet]):
    """Build a SegmentDef, using the segment cache if available."""
    seg_name = item.get("name") or item.get("id", "")
    if not seg_name:
        return None

    usage = _map_usage(item.get("usage"))

    # Check segment cache — avoids rebuilding shared segments (PID, MSH, etc.)
    cached = db.segment_cache_get(version, seg_name)
    if cached is not None:
        seg_data, cached_vs = cached
        value_sets.update({
            k: ValueSet(**v) if isinstance(v, dict) else v
            for k, v in cached_vs.items()
        })
        seg_def = SegmentDef.model_validate(seg_data)
        # Override usage/min/max from the trigger event (may differ per message)
        seg_def.usage = usage
        seg_def.min = 1 if usage == UsageCode.R else 0
        seg_def.max = _map_max(item.get("rpt"))
        return item, seg_def, {}

    # Build from scratch
    local_vs: dict[str, ValueSet] = {}
    fields = _build_fields(version, seg_name, local_vs)

    seg_def = SegmentDef(
        segment=seg_name,
        usage=usage,
        min=1 if usage == UsageCode.R else 0,
        max=_map_max(item.get("rpt")),
        description=item.get("longName") or None,
        fields=fields,
    )

    # Store in segment cache (serialise to plain dict for JSON storage)
    db.segment_cache_set(
        version,
        seg_name,
        seg_def.model_dump(mode="json"),
        {k: v.model_dump(mode="json") for k, v in local_vs.items()},
    )

    return item, seg_def, local_vs


def _build_structure(
    version: str,
    segments: list[dict],
    value_sets: dict[str, ValueSet],
) -> list:
    plain_items = [(i, item) for i, item in enumerate(segments) if not item.get("isGroup")]
    group_items = [(i, item) for i, item in enumerate(segments) if item.get("isGroup")]

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
