from typing import Any


def _array_schema(description: str) -> dict[str, Any]:
    return {
        "type": "array",
        "description": description,
        "items": {"type": "string"},
    }


ORCHESTRATOR_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_physician_data",
            "description": "Retrieve filtered mock physician records. Extract specialty, geography, ICD-10 codes, and volume tier from the user's natural-language query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "specialty": _array_schema("Specialty terms such as Medical Oncology, Pulmonology, or Thoracic Surgery."),
                    "state": _array_schema("Two-letter US state codes such as CA or NY."),
                    "region": _array_schema("Named US regions such as northeast, west, south, or midwest."),
                    "icd10_codes": _array_schema("ICD-10 codes such as C341 or C342."),
                    "volume_threshold": {
                        "type": "string",
                        "enum": ["low", "high", "very_high"],
                        "description": "Minimum volume tier. high includes high and very_high physicians.",
                    },
                    "board_certified": {
                        "type": "boolean",
                        "description": "Optional board certification filter.",
                    },
                },
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "call_ppt_agent",
            "description": "Generate a downloadable PowerPoint deck grounded in the filtered physician list.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "physician_list": {
                        "type": "array",
                        "description": "Filtered physician records returned by get_physician_data.",
                        "items": {"type": "object"},
                    },
                    "icd10_codes": _array_schema("ICD-10 codes in scope for the deck."),
                    "slide_count": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 12,
                        "default": 4,
                    },
                    "style_notes": {"type": "string"},
                },
                "required": ["topic", "physician_list"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "call_excel_agent",
            "description": "Generate a downloadable Excel workbook with raw data and summary sheets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "analysis_type": {"type": "string"},
                    "physician_list": {
                        "type": "array",
                        "description": "Filtered physician records returned by get_physician_data.",
                        "items": {"type": "object"},
                    },
                    "dimensions": _array_schema("Breakdown dimensions such as state, specialty, or ICD-10 code."),
                    "icd10_codes": _array_schema("ICD-10 codes in scope for the workbook."),
                },
                "required": ["analysis_type", "physician_list", "dimensions"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "call_report_agent",
            "description": "Generate a structured markdown report grounded in physician data and user preferences.",
            "parameters": {
                "type": "object",
                "properties": {
                    "report_type": {"type": "string"},
                    "sections": _array_schema("Report sections to generate."),
                    "physician_list": {
                        "type": "array",
                        "description": "Filtered physician records returned by get_physician_data.",
                        "items": {"type": "object"},
                    },
                    "icd10_context": _array_schema("ICD-10 codes and disease context to reference explicitly."),
                    "geographic_scope": _array_schema("States or regions in scope."),
                },
                "required": ["report_type", "sections", "physician_list"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "call_sandbox_agent",
            "description": "Generate and execute Python analysis code over the filtered physician dataset.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code_goal": {"type": "string"},
                    "dataset": {
                        "type": "array",
                        "description": "Physician records or derived summary rows for code execution.",
                        "items": {"type": "object"},
                    },
                    "chart_type": {
                        "type": "string",
                        "description": "Optional chart type such as bar, line, scatter, or histogram.",
                    },
                },
                "required": ["code_goal", "dataset"],
                "additionalProperties": False,
            },
        },
    },
]


def get_orchestrator_tools() -> list[dict[str, Any]]:
    return ORCHESTRATOR_TOOLS
