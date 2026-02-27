from app.models.reference import DatatypeInfo, SegmentInfo, UsageCodeInfo
from app.reference_data.datatypes import DATATYPES
from app.reference_data.segments import SEGMENTS
from app.reference_data.versions import VERSIONS, USAGE_CODES


def get_datatypes() -> list[DatatypeInfo]:
    return [
        DatatypeInfo(code=code, name=v["name"], description=v.get("description"))
        for code, v in sorted(DATATYPES.items())
    ]


def get_segments() -> list[SegmentInfo]:
    seen = set()
    result = []
    for code, name in sorted(SEGMENTS.items()):
        if code not in seen:
            seen.add(code)
            result.append(SegmentInfo(code=code, name=name))
    return result


def get_versions() -> list[str]:
    return VERSIONS


def get_usage_codes() -> list[UsageCodeInfo]:
    return [UsageCodeInfo(**u) for u in USAGE_CODES]
