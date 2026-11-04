"""The structured answer Claude must return, as a Pydantic model and a JSON schema.

Fields the server can establish for itself (weather context, data sources) are deliberately absent:
they are filled in from the record of tool executions after the model has answered.
"""

import re

from pydantic import BaseModel, Field

from app.intelligence.types import Confidence, Intent, RiskLevel


class AgentFinalOutput(BaseModel):
    intent: Intent
    recommendation: str | None = None
    summary: str = Field(min_length=1)
    reasoning: list[str] = []
    risk_level: RiskLevel
    confidence: Confidence
    missing_information: list[str] = []
    next_steps: list[str] = []
    requires_expert_verification: bool = False


_STRING_LIST = {"type": "array", "items": {"type": "string"}}

FINAL_OUTPUT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": [i.value for i in Intent]},
        "recommendation": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "description": "One actionable sentence, or null when this is not advice.",
        },
        "summary": {
            "type": "string",
            "description": "The direct answer to the farmer, in one to four sentences.",
        },
        "reasoning": _STRING_LIST,
        "risk_level": {"type": "string", "enum": [r.value for r in RiskLevel]},
        "confidence": {"type": "string", "enum": [c.value for c in Confidence]},
        "missing_information": _STRING_LIST,
        "next_steps": _STRING_LIST,
        "requires_expert_verification": {"type": "boolean"},
    },
    "required": [
        "intent",
        "recommendation",
        "summary",
        "reasoning",
        "risk_level",
        "confidence",
        "missing_information",
        "next_steps",
        "requires_expert_verification",
    ],
    "additionalProperties": False,
}

# "200 ml/acre", "1.5 kg per hectare": the shape of a chemical dose instruction.
_DOSAGE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:ml|l|litres?|liters?|g|gm|grams?|kg)\s*(?:/|per)\s*"
    r"(?:acre|ha|hectare|litre|liter|l)\b",
    re.IGNORECASE,
)


def contains_dosage(output: AgentFinalOutput) -> bool:
    text = " ".join(
        [output.recommendation or "", output.summary, *output.next_steps, *output.reasoning]
    )
    return _DOSAGE.search(text) is not None
