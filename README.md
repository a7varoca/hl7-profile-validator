# HL7 Profile Editor & Validator

A local web tool for defining and validating HL7 v2.x message profiles against company-specific implementation specifications.

> All data stays local — no external APIs, no cloud services. Designed for sensitive healthcare environments.

---

## Features

- **Profile Editor** — Define HL7 v2.x validation profiles: segments, fields, cardinality, usage codes and value sets
- **Message Validator** — Paste any HL7 v2.x pipe-delimited message and validate it against a profile
- **PDF Report** — Export validation results as a formatted PDF report with highlighted fields
- **Profile Management** — Create, duplicate, import/export profiles as YAML files
- **Responsive UI** — Resizable panels, works on tablet and desktop
- **No build step** — Pure Alpine.js + Tailwind CSS CDN frontend

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12 + FastAPI + PyYAML |
| Frontend | Alpine.js 3.x + Tailwind CSS (CDN) |
| Storage | YAML files in `profiles/` |
| Container | Docker + Docker Compose |

---

## Quick Start

### Option A — Docker (recommended)

```bash
docker compose up -d --build
```

Access at: **http://localhost:8000**

### Option B — Local (development)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./run.sh
```

Access at: **http://localhost:8000**

---

## Project Structure

```
command-validator/
├── app/
│   ├── main.py                  # FastAPI app, routes, static files
│   ├── config.py                # Settings (profiles dir)
│   ├── models/
│   │   ├── profile.py           # Profile, SegmentDef, GroupDef, FieldDef, ValueSet
│   │   ├── reference.py         # Datatype/Segment reference models
│   │   └── validation.py        # ValidationResult, ValidationError
│   ├── routers/
│   │   ├── profiles.py          # CRUD + segments/fields/value sets
│   │   ├── reference.py         # HL7 reference data endpoints
│   │   └── validator.py         # POST /api/validate/
│   ├── services/
│   │   ├── profile_service.py   # YAML persistence, profile operations
│   │   ├── reference_service.py # Reference data access
│   │   └── validator_service.py # HL7 parser + validation engine
│   └── reference_data/
│       ├── datatypes.py         # 55+ HL7 datatypes
│       ├── segments.py          # 80+ HL7 segments
│       └── versions.py          # HL7 versions + usage code definitions
├── static/
│   ├── index.html               # SPA layout + modals
│   ├── app.js                   # Alpine.js component
│   ├── style.css                # Custom styles
│   └── logo.png                 # Application logo
├── profiles/                    # YAML profile files (mounted as Docker volume)
│   └── ADT_A04_Example.yaml
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── run.sh
```

---

## Profile Format

Profiles are plain YAML files stored in the `profiles/` directory. Example structure:

```yaml
profile:
  id: ADT_A04_Urgencias
  message_type: ADT
  trigger_event: A04
  hl7_version: "2.7"
  description: ADT Register Patient — Urgencias
  author: Integration Team
  created_at: "2026-01-01"
  updated_at: "2026-01-15"

value_sets:
  VS_PATIENT_CLASS:
    description: Patient class codes
    codes:
      - code: E
        display: Emergency
      - code: I
        display: Inpatient
      - code: O
        display: Outpatient

structure:
  - segment: MSH
    usage: R
    min: 1
    max: 1
    fields:
      - seq: 9
        name: Message Type
        datatype: MSG
        usage: R
        max_length: 15

  - group: PATIENT
    usage: R
    min: 1
    max: 1
    segments:
      - segment: PID
        usage: R
        min: 1
        max: 1
        fields:
          - seq: 3
            name: Patient Identifier List
            datatype: CX
            usage: R
            max_length: 250
            value_set: VS_IDENTIFIER_TYPE
```

### Usage Codes

| Code | Meaning |
|------|---------|
| R | Required — must be present and non-empty |
| RE | Required but may be Empty |
| O | Optional — no constraint |
| C | Conditional — depends on another field |
| X | Not Supported — must not be present |

---

## API Reference

Base URL: `http://localhost:8000/api`

### Profiles

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/profiles/` | List all profiles |
| `POST` | `/profiles/` | Create new profile |
| `GET` | `/profiles/{id}` | Get profile |
| `PUT` | `/profiles/{id}` | Update profile |
| `DELETE` | `/profiles/{id}` | Delete profile |
| `POST` | `/profiles/{id}/duplicate` | Duplicate profile |
| `GET` | `/profiles/{id}/export` | Download YAML |
| `POST` | `/profiles/import` | Upload YAML file |
| `POST` | `/profiles/{id}/segments` | Add segment |
| `PUT` | `/profiles/{id}/segments/{seg}` | Update segment |
| `DELETE` | `/profiles/{id}/segments/{seg}` | Delete segment |
| `POST` | `/profiles/{id}/segments/{seg}/fields` | Add/update field |
| `DELETE` | `/profiles/{id}/segments/{seg}/fields/{seq}` | Delete field |
| `POST` | `/profiles/{id}/value-sets/{name}` | Add/update value set |
| `DELETE` | `/profiles/{id}/value-sets/{name}` | Delete value set |

### Validator

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/validate/` | Validate HL7 message |

**Request body:**
```json
{
  "profile_id": "ADT_A04_Urgencias",
  "message": "MSH|^~\\&|APP|FAC|APP2|FAC2|20260101||ADT^A04^ADT_A01|MSG001|P|2.7\rPID|1||MRN123^^^HOSP^MR||DOE^JANE||19850315|F"
}
```

### Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/reference/datatypes` | HL7 datatypes (55+) |
| `GET` | `/reference/segments` | HL7 segments (80+) |
| `GET` | `/reference/versions` | Supported versions |
| `GET` | `/reference/usage-codes` | Usage code definitions |

Interactive API docs available at: `http://localhost:8000/docs`

---

## Validation Rules

The validator checks:

- **SEGMENT_REQUIRED** — Required segment (`R`) missing from message
- **SEGMENT_NOT_SUPPORTED** — Segment marked `X` present in message
- **SEGMENT_CARDINALITY** — Segment appears more times than `max` allows
- **FIELD_REQUIRED** — Required field (`R`) empty or missing
- **FIELD_MAX_LENGTH** — Field value exceeds defined maximum length
- **INVALID_CODE** — Field value not found in the associated value set

> Group validation is conditional: optional groups (`O`, `RE`, `C`) are only validated if at least one of their child segments is present in the message.

---

## Profile Naming

Profile IDs are generated as:

```
{MESSAGE_TYPE}_{TRIGGER_EVENT}[_{VARIANT}]
```

Examples:
- `ADT_A04` — base profile
- `ADT_A04_Urgencias` — variant for the Emergency department
- `ADT_A04_HIS_central` — variant for a specific HIS system

This allows multiple profiles for the same message type without conflicts.

---

## Data Persistence

The `profiles/` directory is mounted as a Docker volume — profiles survive container restarts and rebuilds:

```yaml
volumes:
  - ./profiles:/app/profiles
```

Profiles can be version-controlled in Git alongside the application code.

---

## Requirements

- Docker + Docker Compose v2, **or**
- Python 3.12+

No other dependencies. The frontend loads Alpine.js and Tailwind CSS from CDN.
