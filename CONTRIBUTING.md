# Contributing

## Development Setup

```bash
git clone <repo-url>
cd command-validator
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./run.sh
```

The server starts on `http://localhost:8000` with hot-reload enabled.

## Project Structure

- **`app/`** — FastAPI backend
  - `models/` — Pydantic models
  - `routers/` — API endpoints
  - `services/` — Business logic
  - `reference_data/` — Static HL7 reference data
- **`static/`** — Frontend (Alpine.js, no build step)
- **`profiles/`** — YAML profile files (gitignored by default)

## Adding Reference Data

### New HL7 segment

Edit [`app/reference_data/segments.py`](app/reference_data/segments.py):

```python
SEGMENTS = {
    ...
    "ZXX": {"name": "Custom Segment", "description": "Company-specific segment"},
}
```

### New datatype

Edit [`app/reference_data/datatypes.py`](app/reference_data/datatypes.py).

### New HL7 version

Edit [`app/reference_data/versions.py`](app/reference_data/versions.py).

## Adding Validation Rules

Validation logic lives in [`app/services/validator_service.py`](app/services/validator_service.py).

The main entry points:
- `validate()` — orchestrates parsing and validation
- `_validate_nodes()` — recursive tree traversal
- `_validate_segment()` — per-segment checks

Current checks: `SEGMENT_REQUIRED`, `SEGMENT_NOT_SUPPORTED`, `SEGMENT_CARDINALITY`, `FIELD_REQUIRED`, `FIELD_MAX_LENGTH`, `INVALID_CODE`.

## Profile YAML Format

See [README.md](README.md#profile-format) for the full schema.

## Docker Build

```bash
# Standard
docker compose up -d --build
```
