# HL7 Profile Editor & Validator

A local web tool for defining and validating HL7 v2.x message profiles.

> All data stays local — no cloud services. Designed for sensitive healthcare environments.

---

## Features

- **Profile Editor** — Define HL7 v2.x validation profiles: segments, fields, cardinality, usage codes and value sets
- **HL7 Standard Import** — Import profiles directly from the HL7 standard for any version (2.1–2.8) and trigger event
- **Message Validator** — Paste any HL7 v2.x pipe-delimited message and validate it against a profile
- **Backup & Restore** — Export/import all profiles as a ZIP of YAML files

---

## Quick Start

### Docker (recommended)

```bash
docker compose up -d --build
```

Access at **http://localhost:8000**

### Local (Linux / macOS)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Local (Windows)

```bat
setup.bat   # first time only
start.bat   # every time
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12 + FastAPI |
| Frontend | Alpine.js + Tailwind CSS (CDN, no build step) |
| Storage | SQLite (`profiles.db`) |
| Container | Docker + Docker Compose |

---

## Data Persistence

Everything lives in a single SQLite file — `profiles.db`:

| Table | Contents |
|-------|----------|
| `profiles` | All user-defined profiles (JSON) |
| `hl7_raw` | HL7 Standard API response cache |
| `hl7_segments` | Pre-built segment definitions cache |

The file is mounted as a Docker volume so it survives container rebuilds:

```yaml
# docker-compose.yml
volumes:
  - ./profiles.db:/app/profiles.db
```

---

## Migrating to a New Server

All data is in `profiles.db`. To move the tool to another machine:

1. **Copy `profiles.db`** to the new server alongside the project files
2. Run as usual — profiles and HL7 cache are immediately available

If you only want to move the profiles (without the HL7 cache):

1. In the current instance, open the **⋮ menu → Download backup** — downloads a `.zip` with all profiles as YAML files
2. Deploy the tool on the new server (fresh `profiles.db` will be created on first start)
3. Open the **⋮ menu → Restore backup** and upload the `.zip`

> The HL7 standard cache will be rebuilt automatically on demand (one-time per message type, results cached in the DB).

---

## Profile Format

Profiles can be exported/imported as YAML. Minimal example:

```yaml
profile:
  id: ADT_A04_Urgencias
  message_type: ADT
  trigger_event: A04
  hl7_version: "2.7"

value_sets:
  VS_PATIENT_CLASS:
    description: Patient class codes
    codes:
      - { code: E, display: Emergency }
      - { code: I, display: Inpatient }

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
```

### Usage Codes

| Code | Meaning |
|------|---------|
| R  | Required — must be present and non-empty |
| RE | Required but may be empty |
| O  | Optional |
| C  | Conditional |
| X  | Not supported — must not be present |

---

## Validation Rules

| Rule | Description |
|------|-------------|
| `SEGMENT_REQUIRED` | Required segment missing |
| `SEGMENT_NOT_SUPPORTED` | Segment marked `X` is present |
| `SEGMENT_CARDINALITY` | Segment exceeds max occurrences |
| `FIELD_REQUIRED` | Required field empty or missing |
| `FIELD_MAX_LENGTH` | Field value exceeds max length |
| `INVALID_CODE` | Value not in the associated value set |

---

## API

Interactive docs at **http://localhost:8000/docs**

Key endpoints:

```
POST /api/validate/                      Validate an HL7 message
GET  /api/profiles/                      List profiles
POST /api/profiles/import                Import YAML
GET  /api/profiles/{id}/export           Export YAML
GET  /api/backup/                        Download all profiles (ZIP)
POST /api/backup/restore                 Restore from ZIP
POST /api/hl7standard/import             Import from HL7 standard
```
