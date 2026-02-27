VERSIONS: list[str] = [
    "2.3",
    "2.3.1",
    "2.4",
    "2.5",
    "2.5.1",
    "2.6",
    "2.7",
    "2.7.1",
    "2.8",
    "2.8.1",
    "2.8.2",
]

USAGE_CODES: list[dict] = [
    {
        "code": "R",
        "name": "Required",
        "description": "Must be present and non-empty. Absence is an error.",
    },
    {
        "code": "RE",
        "name": "Required but may be Empty",
        "description": "Must be present in the message, but value may be empty.",
    },
    {
        "code": "O",
        "name": "Optional",
        "description": "May or may not be present. No constraint on value.",
    },
    {
        "code": "C",
        "name": "Conditional",
        "description": "Required or not allowed depending on another field's value.",
    },
    {
        "code": "X",
        "name": "Not Supported",
        "description": "Must NOT be present. If received, it should be rejected or ignored.",
    },
]
