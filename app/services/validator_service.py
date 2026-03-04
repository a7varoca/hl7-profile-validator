"""
HL7 v2.x message validator.

Parses a raw pipe-delimited HL7 message and validates it against a Profile,
checking:
  - Segment presence and cardinality (R / RE / O / C / X usage codes)
  - Field presence      (R fields must be non-empty, X fields must be absent)
  - Field max length
  - Value set membership (first component of CWE/IS/ID fields)
"""
from __future__ import annotations
from dataclasses import dataclass, field

from app.models.profile import Profile, SegmentDef, GroupDef, UsageCode
from app.models.validation import ValidationError, ValidationResult


# ---------------------------------------------------------------------------
# HL7 parser — no external dependencies
# ---------------------------------------------------------------------------

@dataclass
class ParsedSegment:
    name: str
    fields: list[str]   # index 0 = segment name, index N = field at position N


def parse_message(raw: str) -> tuple[list[ParsedSegment], str]:
    """
    Parse raw HL7 v2.x message.
    Returns (segments, encoding_chars).
    """
    # Normalize line endings: HL7 uses CR, many senders use LF or CRLF
    normalized = raw.strip().replace('\r\n', '\r').replace('\n', '\r')
    lines = [l for l in normalized.split('\r') if l.strip()]

    segments: list[ParsedSegment] = []
    encoding_chars = '^~\\&'

    for line in lines:
        parts = line.split('|')
        seg_name = parts[0].strip().upper()
        if seg_name == 'MSH' and len(parts) > 1:
            # parts[1] is MSH.2 (encoding chars): '^~\&'
            encoding_chars = parts[1] if parts[1] else encoding_chars
        segments.append(ParsedSegment(name=seg_name, fields=parts))

    return segments, encoding_chars


def _get_field_raw(seg: ParsedSegment, seq: int) -> str:
    """
    Return the raw field value for position `seq` in a parsed segment.

    HL7 field numbering:
      MSH.1 = '|'  (field separator, implicit — not stored in the array)
      MSH.2 = fields[1]  (encoding chars)
      MSH.3 = fields[2]  → seq=3 → idx = seq-1
      MSH.N → idx = seq-1

      PID.1 = fields[1]  → seq=1 → idx = seq
      PID.N → idx = seq
    """
    if seg.name == 'MSH':
        # MSH.1 = field separator '|' — implicit, never in the split array
        # MSH.2 = encoding chars — lives at fields[1]
        if seq == 1:
            return '|'
        idx = seq - 1
    else:
        idx = seq

    if idx < 1 or idx >= len(seg.fields):
        return ''
    return seg.fields[idx].strip()


def _first_component(value: str, component_sep: str = '^') -> str:
    """Return the first component of a composite field (e.g. 'CODE^Display^System' → 'CODE')."""
    return value.split(component_sep)[0].strip()


# ---------------------------------------------------------------------------
# Validation engine
# ---------------------------------------------------------------------------

def validate(raw_message: str, profile: Profile) -> ValidationResult:
    errors: list[ValidationError] = []
    warnings: list[ValidationError] = []

    segments, encoding_chars = parse_message(raw_message)
    component_sep = encoding_chars[0] if encoding_chars else '^'

    # Build index: {SEG_NAME: [ParsedSegment, ...]}
    seg_index: dict[str, list[ParsedSegment]] = {}
    for seg in segments:
        seg_index.setdefault(seg.name, []).append(seg)

    segments_found = list(seg_index.keys())

    # Extract MSH.9 message type
    message_type = ''
    if 'MSH' in seg_index:
        raw_mt = _get_field_raw(seg_index['MSH'][0], 9)
        message_type = raw_mt.split(component_sep)[0] + ('^' + raw_mt.split(component_sep)[1] if len(raw_mt.split(component_sep)) > 1 else '')

    # Collect all segment names defined in profile
    profile_segments: set[str] = set()
    _collect_segment_names(profile.structure, profile_segments)

    segments_not_in_profile = [s for s in segments_found if s not in profile_segments]

    # Walk profile structure and validate
    _validate_nodes(
        profile.structure, seg_index, profile, component_sep, errors, warnings
    )

    return ValidationResult(
        profile_id=profile.profile.id,
        hl7_version=profile.profile.hl7_version,
        message_type=message_type,
        is_valid=len(errors) == 0,
        error_count=len(errors),
        warning_count=len(warnings),
        errors=errors,
        warnings=warnings,
        segments_found=segments_found,
        segments_not_in_profile=segments_not_in_profile,
    )


def _collect_segment_names(nodes, result: set[str]):
    for node in nodes:
        if isinstance(node, SegmentDef):
            result.add(node.segment)
        elif isinstance(node, GroupDef):
            _collect_segment_names(node.segments, result)


def _validate_nodes(nodes, seg_index, profile, component_sep, errors, warnings):
    for node in nodes:
        if isinstance(node, SegmentDef):
            _validate_segment(node, seg_index, profile, component_sep, errors, warnings)
        elif isinstance(node, GroupDef):
            # For optional/conditional groups: only validate children if at least
            # one segment from the group is actually present in the message.
            if node.usage in (UsageCode.O, UsageCode.RE, UsageCode.C):
                group_segs: set[str] = set()
                _collect_segment_names(node.segments, group_segs)
                if not any(s in seg_index for s in group_segs):
                    continue  # group absent and not required — skip
            _validate_nodes(node.segments, seg_index, profile, component_sep, errors, warnings)


def _validate_segment(
    seg_def: SegmentDef,
    seg_index: dict,
    profile: Profile,
    component_sep: str,
    errors: list,
    warnings: list,
):
    instances = seg_index.get(seg_def.segment, [])
    count = len(instances)
    max_val = None if seg_def.max == '*' else int(seg_def.max)

    # --- Cardinality / presence ---
    if seg_def.usage == UsageCode.R:
        if count < seg_def.min:
            errors.append(ValidationError(
                severity='ERROR',
                segment=seg_def.segment,
                field=seg_def.segment,
                seq=0,
                value='',
                rule='SEGMENT_REQUIRED',
                message=(
                    f"Segment {seg_def.segment} is required "
                    f"(min={seg_def.min}) but found {count} occurrence(s)"
                ),
            ))

    elif seg_def.usage == UsageCode.RE:
        # Presence optional — no error if absent, just a note
        pass

    elif seg_def.usage == UsageCode.X:
        if count > 0:
            errors.append(ValidationError(
                severity='ERROR',
                segment=seg_def.segment,
                field=seg_def.segment,
                seq=0,
                value='',
                rule='SEGMENT_NOT_SUPPORTED',
                message=(
                    f"Segment {seg_def.segment} must NOT be present (usage=X) "
                    f"but found {count} occurrence(s)"
                ),
            ))
        return  # nothing else to check

    if max_val is not None and count > max_val:
        errors.append(ValidationError(
            severity='ERROR',
            segment=seg_def.segment,
            field=seg_def.segment,
            seq=0,
            value='',
            rule='SEGMENT_CARDINALITY',
            message=(
                f"Segment {seg_def.segment} max occurrences={max_val} "
                f"but found {count}"
            ),
        ))

    # --- Field-level validation for each occurrence ---
    for instance in instances:
        for field_def in seg_def.fields:
            raw_val = _get_field_raw(instance, field_def.seq)
            field_ref = f"{seg_def.segment}.{field_def.seq}"

            # R: must be present and non-empty
            if field_def.usage == UsageCode.R:
                if not raw_val:
                    errors.append(ValidationError(
                        severity='ERROR',
                        segment=seg_def.segment,
                        field=field_ref,
                        seq=field_def.seq,
                        value='',
                        rule='FIELD_REQUIRED',
                        message=f"{field_ref} ({field_def.name}) is required but missing or empty",
                    ))
                    continue

            # X: must NOT be populated
            elif field_def.usage == UsageCode.X:
                if raw_val:
                    errors.append(ValidationError(
                        severity='ERROR',
                        segment=seg_def.segment,
                        field=field_ref,
                        seq=field_def.seq,
                        value=raw_val,
                        rule='FIELD_NOT_SUPPORTED',
                        message=(
                            f"{field_ref} ({field_def.name}) must not be populated "
                            f"(usage=X) but has value '{raw_val}'"
                        ),
                    ))
                continue

            # RE: if present, may be empty — nothing to check if empty

            if not raw_val:
                continue  # empty optional field — no further checks

            # Max length check
            if len(raw_val) > field_def.max_length:
                errors.append(ValidationError(
                    severity='ERROR',
                    segment=seg_def.segment,
                    field=field_ref,
                    seq=field_def.seq,
                    value=raw_val,
                    rule='FIELD_MAX_LENGTH',
                    message=(
                        f"{field_ref} ({field_def.name}) length {len(raw_val)} "
                        f"exceeds maximum {field_def.max_length}"
                    ),
                ))

            # Value set check
            # Component selection depends on the field's datatype:
            #   CX  → component 5 is the identifier type code (0-based index 4)
            #   CWE, CNE, CE → component 1 is the code (0-based index 0)
            #   IS, ID, ST and other simple types → the whole value (no ^ splitting)
            #   XPN, XAD, HD, XCN, XON, XTN, PL → skip (ambiguous composite)
            _SKIP_VS_TYPES = {'XPN', 'XAD', 'HD', 'XCN', 'XON', 'XTN', 'PL', 'PT', 'MSG', 'VID', 'ED', 'RP'}
            _CX_VS_COMPONENT = 4   # 0-based: CX.5 = index 4

            if field_def.value_set and field_def.value_set in profile.value_sets:
                dt = field_def.datatype.upper()
                if dt not in _SKIP_VS_TYPES:
                    vs = profile.value_sets[field_def.value_set]
                    allowed = {c.code for c in vs.codes}
                    components = raw_val.split(component_sep)

                    if dt == 'CX':
                        # Validate identifier type code (CX.5 = index 4)
                        check_val = components[_CX_VS_COMPONENT] if len(components) > _CX_VS_COMPONENT else ''
                    elif dt in ('CWE', 'CNE', 'CE', 'CF'):
                        check_val = components[0]  # code is the first component
                    else:
                        check_val = components[0]  # IS, ID, ST, NM…

                    if check_val and check_val not in allowed:
                        errors.append(ValidationError(
                            severity='ERROR',
                            segment=seg_def.segment,
                            field=field_ref,
                            seq=field_def.seq,
                            value=raw_val,
                            rule='INVALID_CODE',
                            message=(
                                f"{field_ref} ({field_def.name}): "
                                f"value '{check_val}' not in value set "
                                f"{field_def.value_set} "
                                f"(allowed: {', '.join(sorted(allowed))})"
                            ),
                        ))
